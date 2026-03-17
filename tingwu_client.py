from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_openapi.exceptions._client import ClientException
from alibabacloud_tingwu20230930.client import Client as TingwuSdkClient
from alibabacloud_tingwu20230930 import models as tingwu_models

TINGWU_REGION_ID = "cn-beijing"
TINGWU_ENDPOINT = "tingwu.cn-beijing.aliyuncs.com"
TINGWU_CREATE_TASK_API_VERSION = "2023-09-30"
TINGWU_REQUIRED_ENV_VARS = [
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "ALIYUN_TINGWU_APP_KEY",
]
TINGWU_RESULT_KEYS = [
    "transcription",
    "meeting_assistance",
    "summarization",
    "auto_chapters",
    "text_polish",
    "ppt_extraction",
    "custom_prompt",
    "content_extraction",
    "identity_recognition",
    "service_inspection",
    "translation",
]
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(slots=True)
class TingwuConfig:
    access_key_id: str
    access_key_secret: str
    app_key: str
    endpoint: str = TINGWU_ENDPOINT
    region_id: str = TINGWU_REGION_ID
    api_version: str = TINGWU_CREATE_TASK_API_VERSION

    @property
    def is_ready(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret and self.app_key)


def normalize_openapi_endpoint(value: str | None, *, fallback: str = TINGWU_ENDPOINT) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return fallback

    if "://" in raw_value:
        parsed = urlparse(raw_value)
        candidate = parsed.netloc or parsed.path
    else:
        candidate = raw_value

    normalized = candidate.strip().strip("/")
    return normalized or fallback


def humanize_tingwu_exception(exc: BaseException) -> str:
    raw_text = str(exc).strip()

    if isinstance(exc, ClientException):
        code = str(exc.code or "").strip()
        message = str(exc.message or "").strip()

        if code == "BRK.InvalidAppKey":
            return "听悟返回 `InvalidAppKey`。当前 `.env.local` 里的 `ALIYUN_TINGWU_APP_KEY` 无效，通常是 AppKey 复制时有字符看错了，请从听悟控制台点“复制”后重新填入。"
        if code in {"InvalidParameter", "MissingParameter"}:
            return f"听悟参数校验失败：{message or code}"
        if code in {"Unauthorized", "AccessDenied"}:
            return "当前阿里云凭证没有调用听悟的权限，请检查 RAM 权限和项目授权。"

        if message:
            return f"听悟接口返回错误：{message}"

    if "Failed to parse the value as json format" in raw_text and "server_name:28443" in raw_text:
        return "听悟接口地址配置不正确。现在代码已经兼容修复，但旧进程重启前仍可能继续报这个错。"

    return raw_text or "听悟接口调用失败，请稍后重试。"


def create_tingwu_client(config: TingwuConfig | None = None) -> TingwuSdkClient:
    active_config = config or load_tingwu_config()
    openapi_config = open_api_models.Config(
        access_key_id=active_config.access_key_id,
        access_key_secret=active_config.access_key_secret,
        endpoint=active_config.endpoint,
        region_id=active_config.region_id,
    )
    return TingwuSdkClient(openapi_config)


def load_tingwu_config() -> TingwuConfig:
    return TingwuConfig(
        access_key_id=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "").strip(),
        access_key_secret=os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "").strip(),
        app_key=os.getenv("ALIYUN_TINGWU_APP_KEY", "").strip(),
        endpoint=normalize_openapi_endpoint(os.getenv("ALIYUN_TINGWU_ENDPOINT", TINGWU_ENDPOINT)),
        region_id=os.getenv("ALIYUN_TINGWU_REGION_ID", TINGWU_REGION_ID).strip() or TINGWU_REGION_ID,
        api_version=os.getenv("ALIYUN_TINGWU_API_VERSION", TINGWU_CREATE_TASK_API_VERSION).strip()
        or TINGWU_CREATE_TASK_API_VERSION,
    )


def build_offline_task_payload(job: dict[str, Any], *, file_url: str, app_key: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "AppKey": app_key,
        "Input": {
            "SourceLanguage": job["source_language"],
            "FileUrl": file_url,
            "TaskKey": job["id"],
        },
        "Transcription": {
            "OutputLevel": int(job["output_level"]),
            "AudioEventDetectionEnabled": False,
        },
        "AutoChaptersEnabled": bool(job["auto_chapters_enabled"]),
        "MeetingAssistanceEnabled": bool(job["meeting_assistance_enabled"]),
        "SummarizationEnabled": bool(job["summarization_enabled"]),
        "TextPolishEnabled": bool(job["text_polish_enabled"]),
        "PptExtractionEnabled": bool(job["ppt_extraction_enabled"]),
        "CustomPromptEnabled": bool(job["custom_prompt_enabled"]),
    }

    if job["diarization_enabled"]:
        payload["Transcription"]["DiarizationEnabled"] = True
        payload["Transcription"]["Diarization"] = {
            "SpeakerCount": int(job["speaker_count"]),
        }

    if job["phrase_id"]:
        payload["Transcription"]["PhraseId"] = job["phrase_id"]

    if job["meeting_assistance_enabled"]:
        payload["MeetingAssistance"] = {
            "Types": list(job["meeting_assistance_types"]),
        }

    if job["summarization_enabled"]:
        payload["Summarization"] = {
            "Types": list(job["summarization_types"]),
        }

    if job["custom_prompt_enabled"] and job["custom_prompt_text"]:
        payload["CustomPrompt"] = {
            "Contents": [
                {
                    "Name": job["custom_prompt_name"] or "custom-prompt",
                    "Prompt": job["custom_prompt_text"],
                }
            ]
        }

    return payload


def build_create_task_request(job: dict[str, Any], *, file_url: str, app_key: str) -> tingwu_models.CreateTaskRequest:
    transcription = tingwu_models.CreateTaskRequestParametersTranscription(
        output_level=int(job["output_level"]),
        audio_event_detection_enabled=False,
    )

    if job["diarization_enabled"]:
        transcription.diarization_enabled = True
        transcription.diarization = tingwu_models.CreateTaskRequestParametersTranscriptionDiarization(
            speaker_count=int(job["speaker_count"])
        )

    if job["phrase_id"]:
        transcription.phrase_id = job["phrase_id"]

    parameters = tingwu_models.CreateTaskRequestParameters(
        transcription=transcription,
        auto_chapters_enabled=bool(job["auto_chapters_enabled"]),
        meeting_assistance_enabled=bool(job["meeting_assistance_enabled"]),
        summarization_enabled=bool(job["summarization_enabled"]),
        text_polish_enabled=bool(job["text_polish_enabled"]),
        ppt_extraction_enabled=bool(job["ppt_extraction_enabled"]),
        custom_prompt_enabled=bool(job["custom_prompt_enabled"]),
    )

    if job["meeting_assistance_enabled"]:
        parameters.meeting_assistance = tingwu_models.CreateTaskRequestParametersMeetingAssistance(
            types=list(job["meeting_assistance_types"])
        )

    if job["summarization_enabled"]:
        parameters.summarization = tingwu_models.CreateTaskRequestParametersSummarization(
            types=list(job["summarization_types"])
        )

    if job["custom_prompt_enabled"] and job["custom_prompt_text"]:
        parameters.custom_prompt = tingwu_models.CreateTaskRequestParametersCustomPrompt(
            contents=[
                tingwu_models.CreateTaskRequestParametersCustomPromptContents(
                    name=job["custom_prompt_name"] or "custom-prompt",
                    prompt=job["custom_prompt_text"],
                )
            ]
        )

    return tingwu_models.CreateTaskRequest(
        app_key=app_key,
        type="offline",
        input=tingwu_models.CreateTaskRequestInput(
            file_url=file_url,
            source_language=job["source_language"],
            task_key=job["id"],
            progressive_callbacks_enabled=False,
        ),
        parameters=parameters,
    )


def normalize_result_urls(result_data: Any) -> dict[str, str]:
    if result_data is None:
        return {}

    if hasattr(result_data, "to_map"):
        raw_map = result_data.to_map()
    elif isinstance(result_data, dict):
        raw_map = result_data
    else:
        raw_map = {}

    urls: dict[str, str] = {}
    for key in TINGWU_RESULT_KEYS:
        camel_key = "".join(part.capitalize() for part in key.split("_"))
        value = raw_map.get(camel_key) if isinstance(raw_map, dict) else None
        if value is None and isinstance(raw_map, dict):
            value = raw_map.get(key)
        value_text = str(value or "").strip()
        if value_text:
            urls[key] = value_text

    return urls


def get_task_info(task_id: str) -> dict[str, Any]:
    config = load_tingwu_config()
    if not config.is_ready:
        raise RuntimeError("听悟接入配置尚未完成。")

    client = create_tingwu_client(config)
    try:
        response = client.get_task_info(task_id)
    except Exception as exc:
        raise RuntimeError(humanize_tingwu_exception(exc)) from exc
    body = response.body
    data = body.data if body else None
    result_data = data.result if data else None
    result_urls = normalize_result_urls(result_data)

    return {
        "code": getattr(body, "code", "") or "",
        "message": getattr(body, "message", "") or "",
        "request_id": getattr(body, "request_id", "") or "",
        "task_id": getattr(data, "task_id", "") or task_id,
        "task_key": getattr(data, "task_key", "") or "",
        "task_status": getattr(data, "task_status", "") or "",
        "error_code": getattr(data, "error_code", "") or "",
        "error_message": getattr(data, "error_message", "") or "",
        "result_urls": result_urls,
        "raw": body.to_map() if body else {},
    }


def fetch_result_document(url: str, *, timeout: int = 30) -> Any:
    stripped = url.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)

    response: requests.Response | None = None
    last_exception: BaseException | None = None

    for verify_tls in (True, False):
        try:
            response = requests.get(url, timeout=timeout, verify=verify_tls)
            response.raise_for_status()
            break
        except requests.exceptions.SSLError as exc:
            last_exception = exc
            response = None
            continue
        except requests.RequestException as exc:
            last_exception = exc
            response = None
            if not verify_tls:
                break

    if response is None:
        raise RuntimeError(f"拉取听悟结果文件失败：{last_exception}") from last_exception

    content_type = response.headers.get("Content-Type", "")
    text = response.text

    if "json" in content_type.lower():
        return response.json()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def fetch_result_documents(result_urls: dict[str, str]) -> dict[str, Any]:
    documents: dict[str, Any] = {}
    for key, url in result_urls.items():
        documents[key] = fetch_result_document(url)
    return documents


def build_tingwu_status() -> dict[str, Any]:
    config = load_tingwu_config()
    missing = [
        variable
        for variable in TINGWU_REQUIRED_ENV_VARS
        if not getattr(
            config,
            {
                "ALIBABA_CLOUD_ACCESS_KEY_ID": "access_key_id",
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "access_key_secret",
                "ALIYUN_TINGWU_APP_KEY": "app_key",
            }[variable],
        )
    ]

    return {
        "is_ready": config.is_ready,
        "missing_variables": missing,
        "endpoint": config.endpoint,
        "region_id": config.region_id,
        "api_version": config.api_version,
        "required_variables": TINGWU_REQUIRED_ENV_VARS,
        "config": config,
        "submission_mode": "本地直传 + 主动轮询",
    }


def submit_offline_task(job: dict[str, Any], *, file_url: str) -> dict[str, Any]:
    config = load_tingwu_config()
    if not config.is_ready:
        raise RuntimeError("听悟接入配置尚未完成。")

    client = create_tingwu_client(config)
    request_model = build_create_task_request(job, file_url=file_url, app_key=config.app_key)
    try:
        response = client.create_task(request_model)
    except Exception as exc:
        raise RuntimeError(humanize_tingwu_exception(exc)) from exc
    body = response.body
    data = body.data if body else None

    return {
        "code": getattr(body, "code", "") or "",
        "message": getattr(body, "message", "") or "",
        "request_id": getattr(body, "request_id", "") or "",
        "task_id": getattr(data, "task_id", "") or "",
        "task_key": getattr(data, "task_key", "") or "",
        "task_status": getattr(data, "task_status", "") or "",
        "meeting_join_url": getattr(data, "meeting_join_url", "") or "",
        "raw": body.to_map() if body else {},
    }
