from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import oss2
from oss2.exceptions import NoSuchBucket, NoSuchCors, OssError
from oss2.models import BucketCors, CorsRule

OSS_REGION_ID = "cn-beijing"
OSS_ENDPOINT_TEMPLATE = "https://oss-{region_id}.aliyuncs.com"
OSS_REQUIRED_ENV_VARS = [
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
]
OSS_BUCKET_PREFIX = "stock-daily-analysis"
OSS_SIGNED_URL_EXPIRES = 7 * 24 * 60 * 60
OSS_MULTIPART_THRESHOLD = 8 * 1024 * 1024
OSS_PART_SIZE = 8 * 1024 * 1024
OSS_UPLOAD_RETRIES = 3
OSS_DOWNLOAD_RETRIES = 3
OSS_BROWSER_UPLOAD_URL_EXPIRES = 30 * 60
OSS_CHECKPOINT_DIR = Path(__file__).resolve().parent / "data" / ".oss-checkpoints"
OSS_STATUS_CACHE_TTL_SECONDS = 300
OSS_BRIDGE_CACHE_LOCK = threading.RLock()
OSS_CORS_CACHE_LOCK = threading.RLock()
OSS_CORS_READY_ORIGINS: set[tuple[str, str]] = set()
OSS_BRIDGE_CACHE: dict[str, Any] = {
    "key": None,
    "expires_at": 0.0,
    "status": None,
}


@dataclass(slots=True)
class OssConfig:
    access_key_id: str
    access_key_secret: str
    region_id: str = OSS_REGION_ID
    endpoint: str = ""
    bucket_name: str = ""
    bucket_prefix: str = OSS_BUCKET_PREFIX
    signed_url_expires: int = OSS_SIGNED_URL_EXPIRES
    app_key: str = ""

    @property
    def is_ready(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret)

    @property
    def resolved_bucket_name(self) -> str:
        if self.bucket_name:
            return self.bucket_name

        seed = self.app_key or self.access_key_id or self.region_id
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:14]
        prefix = sanitize_bucket_prefix(self.bucket_prefix)
        return f"{prefix}-{digest}"


def sanitize_bucket_prefix(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned[:48].rstrip("-")
    return cleaned or OSS_BUCKET_PREFIX


def load_oss_config() -> OssConfig:
    region_id = os.getenv("ALIYUN_OSS_REGION_ID", "").strip() or os.getenv(
        "ALIYUN_TINGWU_REGION_ID",
        OSS_REGION_ID,
    ).strip() or OSS_REGION_ID
    endpoint = os.getenv("ALIYUN_OSS_ENDPOINT", "").strip() or OSS_ENDPOINT_TEMPLATE.format(region_id=region_id)

    try:
        signed_url_expires = int(os.getenv("ALIYUN_OSS_SIGNED_URL_EXPIRES", str(OSS_SIGNED_URL_EXPIRES)).strip())
    except ValueError:
        signed_url_expires = OSS_SIGNED_URL_EXPIRES
    signed_url_expires = min(max(signed_url_expires, 900), 7 * 24 * 60 * 60)

    return OssConfig(
        access_key_id=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "").strip(),
        access_key_secret=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "").strip(),
        region_id=region_id,
        endpoint=endpoint,
        bucket_name=os.getenv("ALIYUN_OSS_BUCKET", "").strip().lower(),
        bucket_prefix=os.getenv("ALIYUN_OSS_BUCKET_PREFIX", OSS_BUCKET_PREFIX).strip() or OSS_BUCKET_PREFIX,
        signed_url_expires=signed_url_expires,
        app_key=os.getenv("ALIYUN_TINGWU_APP_KEY", "").strip(),
    )


def create_oss_auth(config: OssConfig | None = None) -> oss2.AuthV4:
    active_config = config or load_oss_config()
    return oss2.AuthV4(active_config.access_key_id, active_config.access_key_secret)


def create_bucket_client(config: OssConfig | None = None, *, bucket_name: str | None = None) -> oss2.Bucket:
    active_config = config or load_oss_config()
    name = bucket_name or active_config.resolved_bucket_name
    return oss2.Bucket(
        create_oss_auth(active_config),
        active_config.endpoint,
        name,
        region=active_config.region_id,
    )


def create_service_client(config: OssConfig | None = None) -> oss2.Service:
    active_config = config or load_oss_config()
    return oss2.Service(
        create_oss_auth(active_config),
        active_config.endpoint,
        region=active_config.region_id,
    )


def build_oss_status() -> dict[str, Any]:
    config = load_oss_config()
    missing = [
        variable
        for variable in OSS_REQUIRED_ENV_VARS
        if not getattr(
            config,
            {
                "ALIBABA_CLOUD_ACCESS_KEY_ID": "access_key_id",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "access_key_secret",
            }[variable],
        )
    ]

    return {
        "is_ready": config.is_ready,
        "bridge_ready": config.is_ready,
        "missing_variables": missing,
        "required_variables": OSS_REQUIRED_ENV_VARS,
        "region_id": config.region_id,
        "endpoint": config.endpoint,
        "bucket_name": config.resolved_bucket_name,
        "bucket_source": "env" if config.bucket_name else "auto",
        "signed_url_expires": config.signed_url_expires,
        "bucket_created": False,
        "error_message": "",
    }


def clone_oss_status(status: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(status)
    cloned["missing_variables"] = list(status.get("missing_variables", []))
    cloned["required_variables"] = list(status.get("required_variables", []))
    return cloned


def build_oss_status_cache_key(status: dict[str, Any]) -> tuple[Any, ...]:
    return (
        bool(status.get("is_ready")),
        str(status.get("region_id") or ""),
        str(status.get("endpoint") or ""),
        str(status.get("bucket_name") or ""),
        tuple(status.get("missing_variables", [])),
    )


def humanize_oss_exception(exc: BaseException) -> str:
    raw_text = str(exc).strip()
    details = getattr(exc, "details", None)
    code = ""
    if isinstance(details, dict):
        code = str(details.get("Code") or details.get("code") or "").strip()
    if not code and "UserDisable" in raw_text:
        code = "UserDisable"
    if not code and "AccessDenied" in raw_text:
        code = "AccessDenied"

    if code == "UserDisable":
        return "阿里云当前拒绝创建或使用 OSS Bucket。请先在控制台开通或启用 OSS 服务，或者在 `.env.local` 里填写现成可用的 `ALIYUN_OSS_BUCKET`。"
    if code in {"AccessDenied", "Forbidden"}:
        return "当前阿里云凭证没有可用的 OSS 权限，请检查 RAM 策略或改填一个已有 Bucket。"
    if "Connection aborted" in raw_text or "10053" in raw_text:
        return "上传到 OSS 时连接被本机网络或安全软件中断了。系统稍后会自动重试；如果仍反复出现，建议暂时关闭代理、杀软扫描或更换网络后再试。"

    return raw_text or "OSS 操作失败，请稍后重试。"


def probe_oss_bridge() -> dict[str, Any]:
    status = build_oss_status()
    if not status["is_ready"]:
        status["bridge_ready"] = False
        return status

    cache_key = build_oss_status_cache_key(status)
    now = time.time()
    with OSS_BRIDGE_CACHE_LOCK:
        if (
            OSS_BRIDGE_CACHE["key"] == cache_key
            and OSS_BRIDGE_CACHE["status"] is not None
            and float(OSS_BRIDGE_CACHE["expires_at"] or 0.0) > now
        ):
            return clone_oss_status(OSS_BRIDGE_CACHE["status"])

    try:
        bucket_info = ensure_bucket()
        status["bridge_ready"] = True
        status["bucket_name"] = bucket_info["bucket_name"]
        status["bucket_created"] = bool(bucket_info["created"])
    except Exception as exc:
        status["bridge_ready"] = False
        status["error_message"] = humanize_oss_exception(exc)

    with OSS_BRIDGE_CACHE_LOCK:
        OSS_BRIDGE_CACHE["key"] = cache_key
        OSS_BRIDGE_CACHE["status"] = clone_oss_status(status)
        OSS_BRIDGE_CACHE["expires_at"] = now + OSS_STATUS_CACHE_TTL_SECONDS

    return clone_oss_status(status)


def ensure_bucket(config: OssConfig | None = None) -> dict[str, Any]:
    active_config = config or load_oss_config()
    if not active_config.is_ready:
        raise RuntimeError("阿里云 OSS 凭证尚未配置完成。")

    candidate_names = [active_config.resolved_bucket_name]
    if not active_config.bucket_name:
        suffix_seed = hashlib.sha1(f"{active_config.app_key}:{active_config.access_key_id}".encode("utf-8")).hexdigest()
        candidate_names.extend(
            f"{active_config.resolved_bucket_name}-{suffix_seed[:length]}"
            for length in (6, 10)
        )

    seen: set[str] = set()
    for bucket_name in candidate_names:
        if bucket_name in seen:
            continue
        seen.add(bucket_name)

        bucket = create_bucket_client(active_config, bucket_name=bucket_name)
        try:
            bucket.get_bucket_info()
            return {
                "bucket": bucket,
                "bucket_name": bucket_name,
                "region_id": active_config.region_id,
                "endpoint": active_config.endpoint,
                "created": False,
            }
        except NoSuchBucket:
            pass
        except OssError as exc:
            if getattr(exc, "status", None) != 404:
                raise RuntimeError(humanize_oss_exception(exc)) from exc

        try:
            bucket.create_bucket(oss2.BUCKET_ACL_PRIVATE)
            return {
                "bucket": bucket,
                "bucket_name": bucket_name,
                "region_id": active_config.region_id,
                "endpoint": active_config.endpoint,
                "created": True,
            }
        except OssError as exc:
            if getattr(exc, "status", None) == 409:
                continue
            raise RuntimeError(humanize_oss_exception(exc)) from exc

    raise RuntimeError("自动准备 OSS Bucket 失败，请稍后重试或手动配置 ALIYUN_OSS_BUCKET。")


def sanitize_object_name(filename: str) -> str:
    raw_name = Path(filename).name.strip()
    if not raw_name:
        return "meeting-recording.bin"

    suffix = Path(raw_name).suffix.lower()
    stem = Path(raw_name).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    safe_stem = safe_stem[:80] or "meeting-recording"
    return f"{safe_stem}{suffix}" if suffix else safe_stem


def build_object_key(*, transcript_id: str, original_name: str) -> str:
    now = datetime.utcnow()
    safe_name = sanitize_object_name(original_name)
    return (
        f"transcripts/{now:%Y}/{now:%m}/{now:%d}/"
        f"{transcript_id}/{datetime.utcnow():%H%M%S}-{safe_name}"
    )


def build_signed_url(*, bucket_name: str, object_key: str, config: OssConfig | None = None) -> dict[str, str]:
    active_config = config or load_oss_config()
    if not active_config.is_ready:
        raise RuntimeError("阿里云 OSS 凭证尚未配置完成。")

    bucket = create_bucket_client(active_config, bucket_name=bucket_name)
    expires = active_config.signed_url_expires
    signed_url = bucket.sign_url("GET", object_key, expires, slash_safe=True)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires)).replace(microsecond=0).isoformat() + "Z"

    return {
        "file_url": signed_url,
        "expires_at": expires_at,
    }


def normalize_browser_upload_origin(value: str) -> str:
    origin = str(value or "").strip().rstrip("/")
    if not re.fullmatch(r"https?://[^/\s]+", origin):
        raise RuntimeError("浏览器上传来源地址无效。")
    return origin


def ensure_browser_upload_cors(
    bucket: oss2.Bucket,
    *,
    bucket_name: str,
    origin: str,
) -> None:
    normalized_origin = normalize_browser_upload_origin(origin)
    cache_key = (bucket_name, normalized_origin)
    with OSS_CORS_CACHE_LOCK:
        if cache_key in OSS_CORS_READY_ORIGINS:
            return

    try:
        current_rules = list(bucket.get_bucket_cors().rules or [])
    except NoSuchCors:
        current_rules = []
    except OssError as exc:
        if getattr(exc, "status", None) == 404:
            current_rules = []
        else:
            raise RuntimeError(humanize_oss_exception(exc)) from exc

    for rule in current_rules:
        allowed_origins = set(getattr(rule, "allowed_origins", []) or [])
        allowed_methods = {str(method).upper() for method in (getattr(rule, "allowed_methods", []) or [])}
        if normalized_origin in allowed_origins and "PUT" in allowed_methods:
            with OSS_CORS_CACHE_LOCK:
                OSS_CORS_READY_ORIGINS.add(cache_key)
            return

    current_rules.append(
        CorsRule(
            allowed_origins=[normalized_origin],
            allowed_methods=["PUT", "GET", "HEAD"],
            allowed_headers=["*"],
            expose_headers=["ETag", "x-oss-request-id"],
            max_age_seconds=3600,
        )
    )
    try:
        bucket.put_bucket_cors(BucketCors(rules=current_rules))
    except OssError as exc:
        raise RuntimeError(humanize_oss_exception(exc)) from exc

    with OSS_CORS_CACHE_LOCK:
        OSS_CORS_READY_ORIGINS.add(cache_key)


def prepare_browser_upload(
    *,
    original_name: str,
    transcript_id: str,
    content_type: str | None,
    origin: str,
    config: OssConfig | None = None,
) -> dict[str, Any]:
    active_config = config or load_oss_config()
    if not active_config.is_ready:
        raise RuntimeError("阿里云 OSS 凭证尚未配置完成。")

    bucket_info = ensure_bucket(active_config)
    bucket = bucket_info["bucket"]
    ensure_browser_upload_cors(
        bucket,
        bucket_name=bucket_info["bucket_name"],
        origin=origin,
    )

    object_key = build_object_key(transcript_id=transcript_id, original_name=original_name)
    resolved_content_type = content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    headers = {"Content-Type": resolved_content_type}
    expires = OSS_BROWSER_UPLOAD_URL_EXPIRES
    upload_url = bucket.sign_url(
        "PUT",
        object_key,
        expires,
        headers=headers,
        slash_safe=True,
    )
    expires_at = (datetime.utcnow() + timedelta(seconds=expires)).replace(microsecond=0).isoformat() + "Z"
    return {
        "bucket_name": bucket_info["bucket_name"],
        "object_key": object_key,
        "endpoint": active_config.endpoint,
        "region_id": active_config.region_id,
        "upload_url": upload_url,
        "upload_headers": headers,
        "expires_at": expires_at,
    }


def inspect_uploaded_object(
    *,
    bucket_name: str,
    object_key: str,
    config: OssConfig | None = None,
) -> dict[str, Any]:
    active_config = config or load_oss_config()
    if not active_config.is_ready:
        raise RuntimeError("阿里云 OSS 凭证尚未配置完成。")

    bucket = create_bucket_client(active_config, bucket_name=bucket_name)
    try:
        metadata = bucket.get_object_meta(object_key)
    except OssError as exc:
        raise RuntimeError(humanize_oss_exception(exc)) from exc

    return {
        "content_length": int(getattr(metadata, "content_length", 0) or 0),
        "etag": str(getattr(metadata, "etag", "") or "").strip('"'),
        "content_type": str(getattr(metadata, "content_type", "") or ""),
        "last_modified": int(getattr(metadata, "last_modified", 0) or 0),
    }


def download_uploaded_object(
    *,
    bucket_name: str,
    object_key: str,
    target_path: str | Path,
    expected_size: int = 0,
    config: OssConfig | None = None,
) -> dict[str, Any]:
    active_config = config or load_oss_config()
    if not active_config.is_ready:
        raise RuntimeError("阿里云 OSS 凭证尚未配置完成。")

    destination = Path(target_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination.with_name(f".{destination.name}.oss-download.part")
    checkpoint_store = oss2.ResumableStore(root=str(OSS_CHECKPOINT_DIR))
    OSS_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    bucket = create_bucket_client(active_config, bucket_name=bucket_name)

    last_exception: BaseException | None = None
    for attempt in range(1, OSS_DOWNLOAD_RETRIES + 1):
        try:
            oss2.resumable_download(
                bucket,
                object_key,
                str(partial_path),
                store=checkpoint_store,
                multiget_threshold=OSS_MULTIPART_THRESHOLD,
                part_size=OSS_PART_SIZE,
                num_threads=1,
            )
            actual_size = partial_path.stat().st_size
            if expected_size and actual_size != expected_size:
                raise RuntimeError(
                    f"OSS 回存文件大小不一致：预期 {expected_size} 字节，实际 {actual_size} 字节。"
                )
            os.replace(partial_path, destination)
            return {
                "content_length": actual_size,
                "path": str(destination),
            }
        except Exception as exc:
            last_exception = exc
            if attempt >= OSS_DOWNLOAD_RETRIES:
                break
            time.sleep(attempt)

    if last_exception is not None:
        raise RuntimeError(humanize_oss_exception(last_exception)) from last_exception
    raise RuntimeError("从 OSS 回存源文件失败。")


def delete_uploaded_object(*, bucket_name: str, object_key: str, config: OssConfig | None = None) -> None:
    active_config = config or load_oss_config()
    if not active_config.is_ready or not bucket_name or not object_key:
        return

    bucket = create_bucket_client(active_config, bucket_name=bucket_name)
    try:
        bucket.delete_object(object_key)
    except NoSuchBucket:
        return
    except OssError as exc:
        if getattr(exc, "status", None) == 404:
            return
        raise RuntimeError(humanize_oss_exception(exc)) from exc


def upload_file_for_tingwu(
    local_path: str | Path,
    *,
    original_name: str,
    transcript_id: str,
    content_type: str | None = None,
    config: OssConfig | None = None,
) -> dict[str, str]:
    active_config = config or load_oss_config()
    path = Path(local_path)
    if not path.exists():
        raise RuntimeError(f"找不到待上传的源文件：{path}")
    if not active_config.is_ready:
        raise RuntimeError("阿里云 OSS 凭证尚未配置完成。")

    bucket_info = ensure_bucket(active_config)
    bucket = bucket_info["bucket"]
    object_key = build_object_key(transcript_id=transcript_id, original_name=original_name)

    guessed_content_type = content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    headers = {"Content-Type": guessed_content_type}

    checkpoint_store = oss2.ResumableStore(root=str(OSS_CHECKPOINT_DIR))
    OSS_CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    last_exception: BaseException | None = None
    for attempt in range(1, OSS_UPLOAD_RETRIES + 1):
        try:
            oss2.resumable_upload(
                bucket,
                object_key,
                str(path),
                store=checkpoint_store,
                headers=headers,
                multipart_threshold=OSS_MULTIPART_THRESHOLD,
                part_size=OSS_PART_SIZE,
                num_threads=1,
            )
            last_exception = None
            break
        except Exception as exc:
            last_exception = exc
            if attempt >= OSS_UPLOAD_RETRIES:
                break
            time.sleep(attempt)

    if last_exception is not None:
        raise RuntimeError(humanize_oss_exception(last_exception)) from last_exception

    signed = build_signed_url(bucket_name=bucket_info["bucket_name"], object_key=object_key, config=active_config)
    return {
        "bucket_name": bucket_info["bucket_name"],
        "object_key": object_key,
        "endpoint": active_config.endpoint,
        "region_id": active_config.region_id,
        "file_url": signed["file_url"],
        "expires_at": signed["expires_at"],
    }
