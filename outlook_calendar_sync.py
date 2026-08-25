from __future__ import annotations

import hashlib
import html
import json
import os
import quopri
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from expert_interview_linker import interview_sequence_map


MAX_ICS_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 5000
MIN_POLL_SECONDS = 15 * 60
DEFAULT_POLL_SECONDS = 4 * 60 * 60
MATCHER_VERSION = "20260813-semantic-grounded-v3"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
ALLOWED_OUTLOOK_HOSTS = {
    "outlook.live.com",
    "outlook.office.com",
    "outlook.office365.com",
}
WINDOWS_TIMEZONES = {
    "china standard time": "Asia/Shanghai",
    "utc": "UTC",
    "eastern standard time": "America/New_York",
    "central standard time": "America/Chicago",
    "mountain standard time": "America/Denver",
    "pacific standard time": "America/Los_Angeles",
    "gmt standard time": "Europe/London",
    "w. europe standard time": "Europe/Berlin",
    "south africa standard time": "Africa/Johannesburg",
    "india standard time": "Asia/Kolkata",
}


class CalendarSyncError(RuntimeError):
    """Safe, user-facing read-only calendar sync error."""


def _clean_text(value: Any, limit: int) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_secret_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def validate_outlook_ics_url(value: Any) -> str:
    url = _clean_text(value, 4000)
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or hostname not in ALLOWED_OUTLOOK_HOSTS:
        raise CalendarSyncError("只接受 Outlook 官方 HTTPS 日历订阅地址。")
    if parsed.username or parsed.password or not parsed.path:
        raise CalendarSyncError("Outlook 日历订阅地址格式不正确。")
    return url


def save_calendar_config(path: Path, ics_url: str) -> dict[str, Any]:
    validated = validate_outlook_ics_url(ics_url)
    payload = {
        "version": 1,
        "ics_url": validated,
        "source_host": urlparse(validated).hostname or "",
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    _write_secret_json(path, payload)
    return payload


def calendar_connection_status(config_path: Path, cache_path: Path) -> dict[str, Any]:
    config = _load_json(config_path)
    cache = _load_json(cache_path)
    raw_events = cache.get("events", []) if isinstance(cache.get("events"), list) else []
    matched_events = [
        item
        for item in raw_events
        if isinstance(item, dict)
        and item.get("expert_id")
        and item.get("match_status") in {"matched_local", "matched_model"}
    ]
    return {
        "configured": bool(config.get("ics_url")),
        "source_host": _clean_text(config.get("source_host"), 200),
        "status": _clean_text(cache.get("status"), 40) or ("idle" if config.get("ics_url") else "not_configured"),
        "message": _clean_text(cache.get("message"), 300),
        "last_synced_at": _clean_text(cache.get("last_synced_at"), 50),
        "event_count": len(matched_events),
        "filtered_count": max(0, int(cache.get("filtered_count") or 0), len(raw_events) - len(matched_events)),
    }


def calendar_view_payload(
    config_path: Path,
    cache_path: Path,
    *,
    allowed_expert_ids: set[str] | None = None,
) -> dict[str, Any]:
    status = calendar_connection_status(config_path, cache_path)
    cache = _load_json(cache_path)
    events = []
    for raw in cache.get("events", []) if isinstance(cache.get("events"), list) else []:
        if not isinstance(raw, dict):
            continue
        expert_id = _clean_text(raw.get("expert_id"), 80)
        match_status = _clean_text(raw.get("match_status"), 40)
        # The interview calendar is a strict expert whitelist, not a general
        # Outlook agenda.  This also removes unmatched items from older caches
        # immediately, before the next four-hour refresh rewrites the cache.
        if not expert_id or match_status not in {"matched_local", "matched_model"}:
            continue
        if allowed_expert_ids is not None and expert_id not in allowed_expert_ids:
            continue
        events.append(
            {
                "event_id": _clean_text(raw.get("event_id"), 80),
                "title": _clean_text(raw.get("title"), 240),
                "start": _clean_text(raw.get("start"), 50),
                "end": _clean_text(raw.get("end"), 50),
                "location": _clean_text(raw.get("location"), 180),
                "match_status": match_status,
                "expert_id": expert_id,
                "expert_name": _clean_text(raw.get("expert_name"), 160),
                "expert_company": _clean_text(raw.get("expert_company"), 220),
                "confidence": float(raw.get("confidence") or 0),
                "interview_id": _clean_text(raw.get("interview_id"), 80),
                "interview_sequence": max(0, int(raw.get("interview_sequence") or 0)),
                "record_status": _clean_text(raw.get("record_status"), 40) or "pending_review",
            }
        )
    return {
        **status,
        "event_count": len(events),
        "filtered_count": max(status.get("filtered_count", 0), status.get("event_count", 0) - len(events)),
        "events": events,
    }


def _unfold_ics(text: str) -> list[str]:
    result: list[str] = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw_line.startswith((" ", "\t")) and result:
            result[-1] += raw_line[1:]
        else:
            result.append(raw_line)
    return result


def _decode_ics_text(value: str, parameters: dict[str, str]) -> str:
    decoded = value
    if parameters.get("ENCODING", "").upper() == "QUOTED-PRINTABLE":
        decoded = quopri.decodestring(decoded).decode(parameters.get("CHARSET") or "utf-8", errors="replace")
    decoded = re.sub(r"\\[nN]", "\n", decoded)
    decoded = decoded.replace(r"\,", ",").replace(r"\;", ";").replace(r"\\", "\\")
    return decoded


def _parse_property(line: str) -> tuple[str, dict[str, str], str] | None:
    if ":" not in line:
        return None
    prefix, value = line.split(":", 1)
    pieces = prefix.split(";")
    name = pieces[0].upper()
    parameters: dict[str, str] = {}
    for piece in pieces[1:]:
        if "=" in piece:
            key, item = piece.split("=", 1)
            parameters[key.upper()] = item.strip('"')
    return name, parameters, _decode_ics_text(value, parameters)


def _zone_from_tzid(tzid: str) -> ZoneInfo:
    normalized = tzid.strip().strip('"')
    mapped = WINDOWS_TIMEZONES.get(normalized.casefold(), normalized)
    try:
        return ZoneInfo(mapped)
    except ZoneInfoNotFoundError:
        return BEIJING_TZ


def _parse_ics_datetime(value: str, parameters: dict[str, str]) -> datetime | None:
    compact = value.strip()
    if not compact:
        return None
    if parameters.get("VALUE", "").upper() == "DATE" or re.fullmatch(r"\d{8}", compact):
        parsed = datetime.strptime(compact[:8], "%Y%m%d")
        return parsed.replace(tzinfo=BEIJING_TZ)
    is_utc = compact.endswith("Z")
    source = compact[:-1] if is_utc else compact
    pattern = "%Y%m%dT%H%M%S" if len(source) >= 15 else "%Y%m%dT%H%M"
    try:
        parsed = datetime.strptime(source[:15] if pattern.endswith("%S") else source[:13], pattern)
    except ValueError:
        return None
    if is_utc:
        return parsed.replace(tzinfo=timezone.utc).astimezone(BEIJING_TZ)
    return parsed.replace(tzinfo=_zone_from_tzid(parameters.get("TZID", "Asia/Shanghai"))).astimezone(BEIJING_TZ)


def sanitize_calendar_text(value: Any, limit: int = 1200) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    text = re.sub(r"(?i)\b(?:https?|webcal)://\S+", "[链接已移除]", text)
    text = re.sub(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", "[邮箱已移除]", text)
    text = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", "[号码已移除]", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _clean_text(text, limit)


def parse_ics_events(content: bytes | str, *, now: datetime | None = None) -> list[dict[str, Any]]:
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    if len(raw) > MAX_ICS_BYTES:
        raise CalendarSyncError("日历文件超过 2 MB，已停止读取。")
    text = raw.decode("utf-8-sig", errors="replace")
    event_blocks: list[list[tuple[str, dict[str, str], str]]] = []
    current: list[tuple[str, dict[str, str], str]] | None = None
    for line in _unfold_ics(text):
        if line.upper() == "BEGIN:VEVENT":
            current = []
            continue
        if line.upper() == "END:VEVENT":
            if current is not None:
                event_blocks.append(current)
            current = None
            if len(event_blocks) >= MAX_EVENTS:
                break
            continue
        if current is not None and (parsed := _parse_property(line)) is not None:
            current.append(parsed)

    reference = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    earliest = reference - timedelta(days=60)
    latest = reference + timedelta(days=365)
    events: list[dict[str, Any]] = []
    seen_event_ids: set[str] = set()
    seen_event_signatures: set[str] = set()
    for properties in event_blocks:
        by_name: dict[str, tuple[dict[str, str], str]] = {}
        for name, parameters, value in properties:
            by_name.setdefault(name, (parameters, value))
        if by_name.get("STATUS", ({}, ""))[1].upper() == "CANCELLED":
            continue
        start_params, start_value = by_name.get("DTSTART", ({}, ""))
        start = _parse_ics_datetime(start_value, start_params)
        if start is None or start < earliest or start > latest:
            continue
        end_params, end_value = by_name.get("DTEND", ({}, ""))
        end = _parse_ics_datetime(end_value, end_params) or (start + timedelta(hours=1))
        if end <= start:
            end = start + timedelta(hours=1)
        uid = by_name.get("UID", ({}, ""))[1] or f"{start.isoformat()}|{by_name.get('SUMMARY', ({}, ''))[1]}"
        title = sanitize_calendar_text(by_name.get("SUMMARY", ({}, ""))[1], 240) or "Outlook 日历事件"
        event_id = hashlib.sha256(uid.encode("utf-8", errors="ignore")).hexdigest()[:24]
        if event_id in seen_event_ids:
            continue
        event_signature = hashlib.sha256(
            "|".join(
                [
                    start.replace(microsecond=0).isoformat(),
                    end.replace(microsecond=0).isoformat(),
                    _match_blob(title),
                    _match_blob(by_name.get("LOCATION", ({}, ""))[1]),
                ]
            ).encode("utf-8", errors="ignore")
        ).hexdigest()[:24]
        if event_signature in seen_event_signatures:
            continue
        seen_event_ids.add(event_id)
        seen_event_signatures.add(event_signature)
        events.append(
            {
                "event_id": event_id,
                "title": title,
                "start": start.replace(microsecond=0).isoformat(),
                "end": end.replace(microsecond=0).isoformat(),
                "location": sanitize_calendar_text(by_name.get("LOCATION", ({}, ""))[1], 180),
                "description": sanitize_calendar_text(by_name.get("DESCRIPTION", ({}, ""))[1], 1200),
                "source": "outlook_ics",
            }
        )
    events.sort(key=lambda item: (item["start"], item["title"].casefold()))
    return events


def _match_blob(value: Any) -> str:
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", str(value or "").casefold())
    return re.sub(r"\s+", " ", text).strip()


def _event_blob(event: dict[str, Any]) -> str:
    return _match_blob(" ".join([event.get("title", ""), event.get("location", ""), event.get("description", "")]))


def _event_revision(event: dict[str, Any]) -> str:
    payload = {
        key: _clean_text(event.get(key), 1600)
        for key in ("event_id", "title", "start", "end", "location", "description")
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]


def _expert_roster_revision(experts: list[dict[str, Any]]) -> str:
    roster = [
        {
            "id": _clean_text(item.get("id"), 80),
            "name": _clean_text(item.get("name"), 160),
            "company": _clean_text(item.get("current_employer") or item.get("main_company"), 220),
            "title": _clean_text(item.get("current_title"), 220),
        }
        for item in experts
        if _clean_text(item.get("id"), 80)
    ]
    payload = {"matcher_version": MATCHER_VERSION, "experts": roster}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]


def _identity_grounded(event: dict[str, Any], expert: dict[str, Any]) -> bool:
    """Require a literal identity clue even when the model resolves aliases semantically."""
    blob = _event_blob(event)
    if not blob:
        return False
    name = _match_blob(expert.get("name"))
    company = _match_blob(expert.get("current_employer") or expert.get("main_company"))
    source_number = re.sub(r"\D+", "", _clean_text(expert.get("source_record_id"), 80))
    raw_identity_text = " ".join(
        _clean_text(event.get(key), 1600)
        for key in ("title", "location", "description")
    )
    title_identity_text = _clean_text(event.get("title"), 500)
    explicit_numbers = set(re.findall(r"#\s*(\d+)", raw_identity_text))
    if explicit_numbers and (not source_number or source_number not in explicit_numbers):
        return False
    name_tokens = {token for token in name.split() if len(token) >= 3 and token not in {"mr", "mrs", "ms", "dr"}}
    person_tags = {
        _match_blob(item)
        for item in re.findall(r"\b([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ.'-]{1,40})\s*@", title_identity_text)
    }
    if person_tags and not any(tag in name_tokens or any(tag == token or tag in token or token in tag for token in name_tokens) for tag in person_tags):
        return False
    if (len(name) >= 3 and name in blob) or (len(company) >= 3 and company in blob):
        return True
    if source_number and source_number in explicit_numbers:
        return True
    generic_tokens = {"chief", "officer", "director", "head", "global", "group", "bank", "technology", "data", "expert", "funda"}
    identity_tokens = [
        token
        for token in (name + " " + company).split()
        if len(token) >= 4 and token not in generic_tokens
    ]
    return any(re.search(rf"(?<![0-9a-z]){re.escape(token)}(?![0-9a-z])", blob) for token in identity_tokens)


def _local_candidates(event: dict[str, Any], experts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blob = _event_blob(event)
    candidates: list[dict[str, Any]] = []
    for expert in experts:
        name = _clean_text(expert.get("name"), 160)
        company = _clean_text(expert.get("current_employer") or expert.get("main_company"), 220)
        name_match = len(_match_blob(name)) >= 3 and _match_blob(name) in blob
        company_match = len(_match_blob(company)) >= 3 and _match_blob(company) in blob
        # Company-only hits are too broad for a personal interview calendar.
        # Require the name of an expert already present in the portfolio.
        matched = [label for label, matched_value in (("姓名", name_match), ("公司", company_match)) if matched_value]
        if name_match:
            candidates.append(
                {
                    "id": _clean_text(expert.get("id"), 80),
                    "name": name,
                    "company": company,
                    "title": _clean_text(expert.get("current_title"), 220),
                    "matched": matched,
                }
            )
    return [item for item in candidates if item["id"]][:8]


def _json_from_response(text: Any) -> dict[str, Any]:
    compact = _clean_text(text, 8000)
    compact = re.sub(r"^```(?:json)?\s*|\s*```$", "", compact, flags=re.I)
    try:
        value = json.loads(compact)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _model_verify_batch(
    events: list[dict[str, Any]],
    experts: list[dict[str, Any]],
    provider_config_path: Path,
    *,
    http_post: Callable[..., Any] = requests.post,
) -> dict[str, dict[str, Any]]:
    if not events:
        return {}
    try:
        providers = _load_json(provider_config_path).get("providers", {})
        config = providers.get("deepseek") if isinstance(providers, dict) else None
    except AttributeError:
        config = None
    if not isinstance(config, dict) or config.get("enabled") is False:
        raise CalendarSyncError("DeepSeek 日历核对未配置，已保留上次同步结果。")
    key_env = _clean_text(config.get("api_key_env"), 120)
    api_key = os.getenv(key_env, "").strip() if key_env else ""
    base_url = _clean_text(config.get("base_url"), 500).rstrip("/")
    model = _clean_text(config.get("model"), 160)
    if not api_key or not base_url.startswith("https://") or not model:
        raise CalendarSyncError("DeepSeek 日历核对暂不可用，已保留上次同步结果。")
    safe_events = [
        {
            "event_id": event.get("event_id", ""),
            "title": event.get("title", ""),
            "start": event.get("start", ""),
            "end": event.get("end", ""),
            "location": event.get("location", ""),
            "description": _clean_text(event.get("description"), 700),
        }
        for event in events
    ]
    safe_candidates = [
        {
            "id": _clean_text(item.get("id"), 80),
            "name": _clean_text(item.get("name"), 160),
            "company": _clean_text(item.get("current_employer") or item.get("main_company"), 220),
            "title": _clean_text(item.get("current_title"), 220),
        }
        for item in experts
        if _clean_text(item.get("id"), 80)
    ]
    prompt = (
        "核对这些已脱敏日历事件是否为候选清单中专家的约访、访谈或追访。"
        "允许综合专家姓名、公司全称或简称、职位、FUNDA/Expert Interview 等语义判断，不要求机械完整关键词。"
        "普通项目会、内部讨论、行情更新、与专家访谈无关的会议必须排除，不得猜测。"
        "只输出 JSON 对象，格式为 {\"matches\":[{\"event_id\":\"...\",\"expert_id\":\"...\","
        "\"is_interview\":true,\"confidence\":0.0,\"evidence\":\"事件原文中的短证据\"}]}。"
        "只返回确认的访谈；expert_id 必须来自候选清单；confidence 至少 0.90；evidence 必须原样来自对应事件。"
        f"\n事件：{json.dumps(safe_events, ensure_ascii=False)}"
        f"\n系统现有专家：{json.dumps(safe_candidates, ensure_ascii=False)}"
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是保守的只读专家访谈日历匹配器。不能提出或执行任何写操作。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": min(4000, max(700, len(events) * 130)),
        "stream": False,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    try:
        response = http_post(
            urljoin(base_url + "/", _clean_text(config.get("chat_path"), 200).lstrip("/") or "chat/completions"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(8, 50),
        )
        if response.status_code >= 400:
            raise CalendarSyncError("DeepSeek 日历核对失败，已保留上次同步结果。")
        response_json = response.json()
        content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")
    except CalendarSyncError:
        raise
    except (requests.RequestException, ValueError, KeyError, IndexError, AttributeError) as exc:
        raise CalendarSyncError("DeepSeek 日历核对失败，已保留上次同步结果。") from exc
    result = _json_from_response(content)
    candidate_ids = {item["id"] for item in safe_candidates}
    event_by_id = {_clean_text(item.get("event_id"), 80): item for item in events}
    verified: dict[str, dict[str, Any]] = {}
    for item in result.get("matches", []) if isinstance(result.get("matches"), list) else []:
        if not isinstance(item, dict) or item.get("is_interview") is not True:
            continue
        event_id = _clean_text(item.get("event_id"), 80)
        expert_id = _clean_text(item.get("expert_id"), 80)
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        evidence = _clean_text(item.get("evidence"), 240)
        event = event_by_id.get(event_id)
        if not event or expert_id not in candidate_ids or confidence < 0.90:
            continue
        if not evidence or _match_blob(evidence) not in _event_blob(event):
            continue
        verified[event_id] = {"expert_id": expert_id, "confidence": min(confidence, 1.0), "evidence": evidence}
    return verified


def _portfolio_datetime(value: Any) -> datetime | None:
    compact = _clean_text(value, 100)
    match = re.search(r"(20\d{2})[-./年]?(\d{2})[-./月]?(\d{2})(?:[T\s]+(\d{1,2})[:.](\d{2}))?", compact)
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            int(match.group(4) or 12),
            int(match.group(5) or 0),
            tzinfo=BEIJING_TZ,
        )
    except ValueError:
        return None


def _communication_context(event: dict[str, Any], expert: dict[str, Any]) -> dict[str, Any]:
    try:
        event_start = datetime.fromisoformat(_clean_text(event.get("start"), 60)).astimezone(BEIJING_TZ)
    except ValueError:
        return {"interview_sequence": 0, "record_status": "new_communication", "interview_id": ""}
    interviews = [
        item
        for item in expert.get("interviews", [])
        if isinstance(item, dict) and _clean_text(item.get("status"), 40) != "cancelled"
    ]
    sequences = interview_sequence_map(expert)
    exact: list[dict[str, Any]] = []
    earlier_count = 0
    for interview in interviews:
        interview_time = _portfolio_datetime(interview.get("occurred_at") or interview.get("display_time"))
        if interview_time is None:
            continue
        if interview_time < event_start:
            earlier_count += 1
        if interview_time.date() == event_start.date() and abs((interview_time - event_start).total_seconds()) <= 15 * 60:
            exact.append(interview)
    if len(exact) == 1:
        interview_id = _clean_text(exact[0].get("id"), 80)
        return {
            "interview_sequence": sequences.get(interview_id, max(1, earlier_count)),
            "record_status": "linked_existing",
            "interview_id": interview_id,
        }
    if len(exact) > 1:
        return {
            "interview_sequence": 0,
            "record_status": "duplicate_conflict",
            "interview_id": "",
        }
    return {
        "interview_sequence": earlier_count + 1,
        "record_status": "new_communication",
        "interview_id": "",
    }


def match_calendar_events(
    events: list[dict[str, Any]],
    experts: list[dict[str, Any]],
    provider_config_path: Path,
    *,
    allow_model: bool = True,
    previous_events: list[dict[str, Any]] | None = None,
    reviewed_revisions: set[str] | None = None,
    http_post: Callable[..., Any] = requests.post,
) -> list[dict[str, Any]]:
    expert_by_id = {str(item.get("id") or ""): item for item in experts}
    previous_by_revision = {
        _event_revision(item): item
        for item in (previous_events or [])
        if isinstance(item, dict) and _clean_text(item.get("expert_id"), 80) in expert_by_id
    }
    reviewed = reviewed_revisions or set()
    model_matches: dict[str, dict[str, Any]] = {}
    if allow_model:
        changed_events = [
            event
            for event in events
            if _event_revision(event) not in previous_by_revision and _event_revision(event) not in reviewed
        ]
        model_matches = _model_verify_batch(changed_events, experts, provider_config_path, http_post=http_post)
    matched_events: list[dict[str, Any]] = []
    seen_expert_slots: set[str] = set()
    new_communication_offsets: dict[str, int] = {}
    for source_event in events:
        event = dict(source_event)
        revision = _event_revision(event)
        previous = previous_by_revision.get(revision)
        candidates = _local_candidates(event, experts) if not allow_model else []
        match: dict[str, Any] | None = None
        method = "pending_review"
        if previous:
            match = {
                "expert_id": _clean_text(previous.get("expert_id"), 80),
                "confidence": float(previous.get("confidence") or 1.0),
                "evidence": _clean_text(previous.get("match_evidence"), 240) or "上次核对结果",
            }
            method = _clean_text(previous.get("match_status"), 40) or "matched_model"
        elif allow_model and _clean_text(event.get("event_id"), 80) in model_matches:
            match = model_matches[_clean_text(event.get("event_id"), 80)]
            method = "matched_model"
        elif not allow_model and len(candidates) == 1:
            match = {"expert_id": candidates[0]["id"], "confidence": 1.0, "evidence": "、".join(candidates[0]["matched"])}
            method = "matched_local"
        expert = expert_by_id.get(str((match or {}).get("expert_id") or ""), {})
        # Never cache or display unrelated Outlook meetings.  Ambiguous and
        # unmatched events stay outside the website until they can be tied to
        # one expert already present in the portfolio.
        if not match or not expert or method not in {"matched_local", "matched_model"} or not _identity_grounded(event, expert):
            continue
        communication = _communication_context(event, expert) if expert else {
            "interview_sequence": 0,
            "record_status": "pending_review",
            "interview_id": "",
        }
        expert_id = _clean_text((match or {}).get("expert_id"), 80)
        if expert_id:
            # Outlook may republish the same meeting under another UID or with
            # a changed location.  Once an expert and time slot are known, keep
            # only one display event and one communication number.
            slot_key = "|".join([expert_id, str(event.get("start") or ""), str(event.get("end") or "")])
            if slot_key in seen_expert_slots:
                continue
            seen_expert_slots.add(slot_key)
            if communication.get("record_status") == "new_communication":
                communication["interview_sequence"] = int(communication.get("interview_sequence") or 1) + new_communication_offsets.get(expert_id, 0)
                new_communication_offsets[expert_id] = new_communication_offsets.get(expert_id, 0) + 1
        event.update(
            {
                "match_status": method,
                "expert_id": expert_id,
                "confidence": float((match or {}).get("confidence", 0)),
                "match_evidence": _clean_text((match or {}).get("evidence"), 240),
                "expert_name": _clean_text(expert.get("name"), 160),
                "expert_company": _clean_text(expert.get("current_employer") or expert.get("main_company"), 220),
                **communication,
            }
        )
        matched_events.append(event)
    return matched_events


def configure_calendar_source(
    ics_url: str,
    config_path: Path,
    cache_path: Path,
    experts: list[dict[str, Any]],
    provider_config_path: Path,
    *,
    now: datetime | None = None,
    http_get: Callable[..., Any] = requests.get,
) -> dict[str, Any]:
    """Validate and parse a new feed before replacing any working configuration."""
    validated = validate_outlook_ics_url(ics_url)
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    content, _validators = fetch_outlook_ics(validated, http_get=http_get)
    if content is None:
        raise CalendarSyncError("Outlook 日历没有返回可读取的内容。")
    parsed_events = parse_ics_events(content, now=reference.astimezone(BEIJING_TZ))
    events = match_calendar_events(
        parsed_events,
        experts,
        provider_config_path,
        allow_model=False,
    )
    cache = {
        "version": 1,
        "status": "ready",
        "message": "只读日历连接已验证",
        "last_checked_at": reference.replace(microsecond=0).isoformat(),
        "last_synced_at": reference.replace(microsecond=0).isoformat(),
        "etag": "",
        "last_modified": "",
        "filtered_count": max(0, len(parsed_events) - len(events)),
        "events": events,
    }
    previous_cache = cache_path.read_bytes() if cache_path.exists() else None
    _write_secret_json(cache_path, cache)
    try:
        save_calendar_config(config_path, validated)
    except Exception:
        if previous_cache is None:
            cache_path.unlink(missing_ok=True)
        else:
            cache_path.write_bytes(previous_cache)
            os.chmod(cache_path, 0o600)
        raise
    return {**calendar_connection_status(config_path, cache_path), "events": events}


def fetch_outlook_ics(
    ics_url: str,
    *,
    etag: str = "",
    last_modified: str = "",
    http_get: Callable[..., Any] = requests.get,
) -> tuple[bytes | None, dict[str, str]]:
    url = validate_outlook_ics_url(ics_url)
    headers = {"Accept": "text/calendar", "User-Agent": "4242wei-calendar-sync/1.0"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    for _ in range(4):
        try:
            response = http_get(url, headers=headers, timeout=(8, 20), allow_redirects=False)
        except requests.RequestException as exc:
            raise CalendarSyncError("Outlook 日历暂时连接失败，已保留上次同步结果。") from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            next_url = response.headers.get("Location", "")
            url = validate_outlook_ics_url(urljoin(url, next_url))
            continue
        if response.status_code == 304:
            return None, {"etag": etag, "last_modified": last_modified}
        if response.status_code >= 400:
            raise CalendarSyncError(f"Outlook 日历返回 HTTP {response.status_code}，已保留上次同步结果。")
        content = bytes(response.content)
        if len(content) > MAX_ICS_BYTES:
            raise CalendarSyncError("Outlook 日历内容超过 2 MB，已停止读取。")
        return content, {
            "etag": _clean_text(response.headers.get("ETag"), 300),
            "last_modified": _clean_text(response.headers.get("Last-Modified"), 300),
        }
    raise CalendarSyncError("Outlook 日历重定向次数过多，已停止读取。")


def _cache_fresh(cache: dict[str, Any], now: datetime, poll_seconds: int) -> bool:
    try:
        fetched = datetime.fromisoformat(str(cache.get("last_checked_at") or ""))
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return now.astimezone(timezone.utc) - fetched.astimezone(timezone.utc) < timedelta(seconds=poll_seconds)


def calendar_poll_seconds() -> int:
    raw_value = os.getenv("OUTLOOK_CALENDAR_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))
    try:
        configured = int(raw_value)
    except (TypeError, ValueError):
        configured = DEFAULT_POLL_SECONDS
    return max(MIN_POLL_SECONDS, configured)


def synchronize_calendar(
    config_path: Path,
    cache_path: Path,
    experts: list[dict[str, Any]],
    provider_config_path: Path,
    *,
    force: bool = False,
    now: datetime | None = None,
    http_get: Callable[..., Any] = requests.get,
    http_post: Callable[..., Any] = requests.post,
) -> dict[str, Any]:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    config = _load_json(config_path)
    ics_url = _clean_text(config.get("ics_url"), 4000)
    cache = _load_json(cache_path)
    if not ics_url:
        return {**calendar_connection_status(config_path, cache_path), "events": cache.get("events", [])}
    poll_seconds = calendar_poll_seconds()
    if not force and _cache_fresh(cache, reference, poll_seconds):
        return {**calendar_connection_status(config_path, cache_path), "events": cache.get("events", [])}
    try:
        roster_revision = _expert_roster_revision(experts)
        roster_changed = _clean_text(cache.get("expert_roster_revision"), 80) != roster_revision
        content, validators = fetch_outlook_ics(
            ics_url,
            etag="" if roster_changed else _clean_text(cache.get("etag"), 300),
            last_modified="" if roster_changed else _clean_text(cache.get("last_modified"), 300),
            http_get=http_get,
        )
        filtered_count = max(0, int(cache.get("filtered_count") or 0))
        if content is None:
            events = cache.get("events", []) if isinstance(cache.get("events"), list) else []
            reviewed_revisions = cache.get("reviewed_revisions", []) if isinstance(cache.get("reviewed_revisions"), list) else []
        else:
            parsed_events = parse_ics_events(content, now=reference.astimezone(BEIJING_TZ))
            previous_roster_revision = _clean_text(cache.get("expert_roster_revision"), 80)
            reviewed_before = {
                _clean_text(item, 80)
                for item in cache.get("reviewed_revisions", [])
                if isinstance(item, str)
            } if previous_roster_revision == roster_revision else set()
            events = match_calendar_events(
                parsed_events,
                experts,
                provider_config_path,
                previous_events=cache.get("events", []) if previous_roster_revision == roster_revision else [],
                reviewed_revisions=reviewed_before,
                http_post=http_post,
            )
            reviewed_revisions = sorted({_event_revision(item) for item in parsed_events})
            filtered_count = max(0, len(parsed_events) - len(events))
        next_cache = {
            "version": 1,
            "status": "ready",
            "message": "只读日历已同步",
            "last_checked_at": reference.replace(microsecond=0).isoformat(),
            "last_synced_at": reference.replace(microsecond=0).isoformat(),
            "etag": validators.get("etag", ""),
            "last_modified": validators.get("last_modified", ""),
            "filtered_count": filtered_count,
            "expert_roster_revision": _expert_roster_revision(experts),
            "reviewed_revisions": reviewed_revisions,
            "events": events,
        }
        _write_secret_json(cache_path, next_cache)
    except CalendarSyncError as exc:
        cache.update(
            {
                "status": "error",
                "message": str(exc),
                "last_checked_at": reference.replace(microsecond=0).isoformat(),
            }
        )
        _write_secret_json(cache_path, cache)
    return {**calendar_connection_status(config_path, cache_path), "events": _load_json(cache_path).get("events", [])}


def import_calendar_content(
    content: bytes,
    cache_path: Path,
    experts: list[dict[str, Any]],
    provider_config_path: Path,
    *,
    now: datetime | None = None,
    http_post: Callable[..., Any] = requests.post,
) -> dict[str, Any]:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    parsed_events = parse_ics_events(content, now=reference.astimezone(BEIJING_TZ))
    events = match_calendar_events(
        parsed_events,
        experts,
        provider_config_path,
        allow_model=False,
        http_post=http_post,
    )
    cache = {
        "version": 1,
        "status": "ready",
        "message": "本地日历文件已读取",
        "last_checked_at": reference.replace(microsecond=0).isoformat(),
        "last_synced_at": reference.replace(microsecond=0).isoformat(),
        "filtered_count": max(0, len(parsed_events) - len(events)),
        "events": events,
    }
    _write_secret_json(cache_path, cache)
    return {"configured": False, "source_host": "本地 ICS", "status": "ready", "message": cache["message"], "last_synced_at": cache["last_synced_at"], "event_count": len(events), "events": events}
