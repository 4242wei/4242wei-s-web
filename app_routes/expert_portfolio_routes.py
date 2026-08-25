from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from flask import abort, flash, jsonify, redirect, render_template, request, send_file, url_for

from interview_summary import (
    MAX_TRANSCRIPT_CHARS,
    InterviewSummaryError,
    generate_interview_summary,
    transcript_digest,
)
from interview_quota_export import (
    QUOTA_STATUS_OPTIONS,
    build_interview_quota_workbook,
    build_interview_quota_view,
    normalize_quota_status,
)
from region_normalization import normalize_region_label
from outlook_calendar_sync import (
    CalendarSyncError,
    calendar_connection_status,
    calendar_view_payload,
    configure_calendar_source,
    import_calendar_content,
    synchronize_calendar,
)
from expert_interview_linker import (
    apply_safe_links,
    build_link_scan,
    cache_fresh as link_cache_fresh,
    load_link_cache,
    save_link_cache,
    interview_sequence_map,
)


EXPERT_PORTFOLIO_LOCK = threading.RLock()
INTERVIEW_SUMMARY_LOCK = threading.RLock()
INTERVIEW_SUMMARY_SEMAPHORE = threading.Semaphore(1)
INTERVIEW_SUMMARY_ACTIVE: set[tuple[str, str]] = set()
INTERVIEW_SUMMARY_TRANSCRIPT_CACHE_LOCK = threading.RLock()
INTERVIEW_SUMMARY_TRANSCRIPT_CACHE: dict[str, Any] = {"signature": None, "items": {}}
OUTLOOK_CALENDAR_WORKER_LOCK = threading.RLock()
OUTLOOK_CALENDAR_WORKER_STARTED = False
OUTLOOK_CALENDAR_SYNC_ACTIVE = threading.Lock()
EXPERT_LINK_SCAN_LOCK = threading.RLock()

STATUS_META = {
    "not-reviewed": {"label": "待审核", "tone": "pending", "order": 10},
    "maybe-not": {"label": "暂不考虑", "tone": "pending", "order": 20},
    "scheduling": {"label": "安排中", "tone": "info", "order": 30},
    "completed": {"label": "已完成访谈", "tone": "success", "order": 40},
    "scheduling-followup": {"label": "安排追访", "tone": "purple", "order": 50},
    "followup-in-progress": {"label": "追访中", "tone": "warning", "order": 60},
}

LEGACY_STATUS_MAP = {
    "interested": "scheduling",
    "maybe": "maybe-not",
    "considering": "scheduling",
    "scheduled": "scheduling",
    "declined-interview": "maybe-not",
    "low-fitness": "maybe-not",
    "low-quality": "maybe-not",
    "duplicate": "maybe-not",
}

DEFAULT_CATEGORIES = [
    "Token economics",
    "企业 AI 应用",
    "未分类",
]

CATEGORY_TRANSLATIONS = {
    "Lumentum & Coherent": "Lumentum 与 Coherent",
    "Other Laser Experts": "其他激光专家",
    "General InP Industry": "通用 InP 产业",
    "OIO Startups": "光互连初创公司",
    "InP Production Equipment": "InP 生产设备",
    "Uncategorized": "未分类",
}

CATEGORY_RULES = [
    (
        "Token economics",
        re.compile(r"token\s*economics|enterprise\s+ai\s+economics|model\s+routing|ai\s+spend|cost\s+optimization", re.I),
    ),
    (
        "企业 AI 应用",
        re.compile(
            r"\b(?:ai|genai|artificial\s+intelligence|machine\s+learning|llm|agentic|copilot)\b",
            re.I,
        ),
    ),
]

INTERVIEW_STATUS_META = {
    "planned": {"label": "待安排", "tone": "pending", "order": 10},
    "scheduled": {"label": "已安排", "tone": "info", "order": 20},
    "completed": {"label": "已完成", "tone": "success", "order": 30},
    "cancelled": {"label": "已取消", "tone": "danger", "order": 40},
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        compact = str(data or "").strip()
        if compact:
            self.parts.append(compact)


def _clean_text(value: Any, *, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _unique_strings(value: Any, *, limit: int = 120, max_items: int = 30) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[,，;；\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []

    items: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        item = _clean_text(raw_item, limit=limit)
        key = item.casefold()
        if not item or key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= max_items:
            break
    return items


def _normalize_vendor_index(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        entries = value.items()
    else:
        parsed_entries: list[tuple[str, str]] = []
        for part in re.split(r"[,，;；\n]+", str(value or "")):
            match = re.match(r"^\s*(.+?)\s*[:：]\s*(.+?)\s*$", part)
            if match:
                parsed_entries.append((match.group(1), match.group(2)))
        entries = parsed_entries

    result: dict[str, str] = {}
    for raw_key, raw_value in entries:
        key = _clean_text(raw_key, limit=80)
        item_value = _clean_text(raw_value, limit=80)
        if key and item_value:
            result[key] = item_value
        if len(result) >= 20:
            break
    return result


def _normalize_job_history(value: Any) -> list[dict[str, str]]:
    raw_items: list[Any]
    if isinstance(value, str):
        raw_items = []
        for line in value.splitlines():
            parts = [part.strip() for part in line.split("|")]
            if any(parts):
                raw_items.append(
                    {
                        "title": parts[0] if parts else "",
                        "company": parts[1] if len(parts) > 1 else "",
                        "dates": parts[2] if len(parts) > 2 else "",
                    }
                )
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    items: list[dict[str, str]] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        item = {
            "title": _clean_text(raw_item.get("title"), limit=180),
            "company": _clean_text(raw_item.get("company"), limit=180),
            "dates": _clean_text(raw_item.get("dates"), limit=120),
        }
        if any(item.values()):
            items.append(item)
        if len(items) >= 80:
            break
    return items


def _normalize_interview_summary(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    status = _clean_text(raw.get("status"), limit=40) or "not-generated"
    if status not in {"not-generated", "queued", "generating", "ready", "failed"}:
        status = "not-generated"
    conclusions: list[dict[str, str]] = []
    for raw_item in raw.get("conclusions", []) if isinstance(raw.get("conclusions"), list) else []:
        if not isinstance(raw_item, dict):
            continue
        item = {
            "title": _clean_text(raw_item.get("title"), limit=180),
            "conclusion": _clean_text(raw_item.get("conclusion"), limit=1600),
            "evidence": _clean_text(raw_item.get("evidence"), limit=1800),
            "uncertainty": _clean_text(raw_item.get("uncertainty"), limit=1000),
            "source_ref": _clean_text(raw_item.get("source_ref"), limit=300),
        }
        if item["title"] or item["conclusion"]:
            conclusions.append(item)
        if len(conclusions) >= 16:
            break
    follow_ups = _unique_strings(raw.get("follow_ups"), limit=500, max_items=12)
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    return {
        "status": status,
        "overview": _clean_text(raw.get("overview"), limit=2400),
        "conclusions": conclusions,
        "follow_ups": follow_ups,
        "provider_id": _clean_text(raw.get("provider_id"), limit=80),
        "provider_label": _clean_text(raw.get("provider_label"), limit=120),
        "model": _clean_text(raw.get("model"), limit=160),
        "source_transcript_id": _clean_text(raw.get("source_transcript_id"), limit=80),
        "source_digest": _clean_text(raw.get("source_digest"), limit=80),
        "generated_at": _clean_text(raw.get("generated_at"), limit=40),
        "updated_at": _clean_text(raw.get("updated_at"), limit=40),
        "error": _clean_text(raw.get("error"), limit=500),
        "usage": {
            key: max(0, int(number))
            for key, number in usage.items()
            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and isinstance(number, (int, float))
        },
    }


def _job_history_text(value: Any) -> str:
    return "\n".join(
        " | ".join([item.get("title", ""), item.get("company", ""), item.get("dates", "")]).rstrip(" |")
        for item in _normalize_job_history(value)
    )


def _normalize_interviews(value: Any, *, now_iso: str = "") -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    interviews: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        status = _clean_text(raw_item.get("status"), limit=40) or "planned"
        if status not in INTERVIEW_STATUS_META:
            status = "planned"
        interview_id = _clean_text(raw_item.get("id"), limit=80) or f"int-{uuid.uuid4().hex[:12]}"
        while interview_id in used_ids:
            interview_id = f"int-{uuid.uuid4().hex[:12]}"
        used_ids.add(interview_id)
        interview = {
            "id": interview_id,
            "occurred_at": _clean_text(raw_item.get("occurred_at") or raw_item.get("date"), limit=50),
            "ended_at": _clean_text(raw_item.get("ended_at") or raw_item.get("end_date"), limit=50),
            "display_time": _clean_text(raw_item.get("display_time"), limit=120),
            "title": _clean_text(raw_item.get("title"), limit=220) or "专家访谈",
            "interviewer": _clean_text(raw_item.get("interviewer"), limit=180),
            "status": status,
            "quota_status": normalize_quota_status(raw_item.get("quota_status")),
            "transcript_id": _clean_text(raw_item.get("transcript_id"), limit=80),
            "notes": _clean_text(raw_item.get("notes"), limit=8000),
            "research_feedback": _clean_text(raw_item.get("research_feedback"), limit=8000),
            "future_tracking": _clean_text(raw_item.get("future_tracking"), limit=8000),
            "transcription_quality": _clean_text(raw_item.get("transcription_quality"), limit=40)
            or "needs-review",
            "transcription_notes": _clean_text(raw_item.get("transcription_notes"), limit=2000),
            "source_label": _clean_text(raw_item.get("source_label"), limit=240),
            "outlook_event_id": _clean_text(raw_item.get("outlook_event_id"), limit=80),
            "outlook_managed": raw_item.get("outlook_managed") is True,
            "ai_summary": _normalize_interview_summary(raw_item.get("ai_summary")),
            "created_at": _clean_text(raw_item.get("created_at") or now_iso, limit=40),
            "updated_at": _clean_text(raw_item.get("updated_at") or now_iso, limit=40),
        }
        interviews.append(interview)
        if len(interviews) >= 100:
            break
    interviews.sort(
        key=lambda item: (item.get("occurred_at") or item.get("created_at") or "", item.get("id") or ""),
        reverse=True,
    )
    return interviews


def _calendar_event_time(value: Any) -> datetime | None:
    compact = _clean_text(value, limit=80)
    if not compact:
        return None
    try:
        parsed = datetime.fromisoformat(compact.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return parsed


def _materialize_calendar_events(
    store: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    now_iso: str,
    now: datetime | None = None,
) -> dict[str, int]:
    """Idempotently copy verified Outlook matches into expert interview records."""
    experts = store.get("experts", []) if isinstance(store.get("experts"), list) else []
    expert_by_id = {
        _clean_text(item.get("id"), limit=80): item
        for item in experts
        if isinstance(item, dict) and _clean_text(item.get("id"), limit=80)
    }
    event_owner: dict[str, tuple[str, dict[str, Any]]] = {}
    for expert in experts:
        for interview in expert.get("interviews", []) if isinstance(expert.get("interviews"), list) else []:
            event_id = _clean_text(interview.get("outlook_event_id"), limit=80)
            if event_id:
                event_owner[event_id] = (_clean_text(expert.get("id"), limit=80), interview)

    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    beijing = ZoneInfo("Asia/Shanghai")
    created = linked = updated = conflicts = 0
    changed_experts: set[str] = set()
    ordered = sorted(
        [item for item in events if isinstance(item, dict)],
        key=lambda item: (_clean_text(item.get("start"), limit=80), _clean_text(item.get("event_id"), limit=80)),
    )
    for event in ordered:
        if event.get("match_status") not in {"matched_local", "matched_model"}:
            continue
        expert_id = _clean_text(event.get("expert_id"), limit=80)
        event_id = _clean_text(event.get("event_id"), limit=80)
        expert = expert_by_id.get(expert_id)
        start = _calendar_event_time(event.get("start"))
        end = _calendar_event_time(event.get("end"))
        if not expert or not event_id or start is None:
            continue
        expert_created = _calendar_event_time(expert.get("created_at"))
        if expert_created and start < expert_created:
            continue
        owned = event_owner.get(event_id)
        if owned and owned[0] != expert_id:
            conflicts += 1
            continue

        interviews = expert.setdefault("interviews", [])
        target = owned[1] if owned else None
        preferred_id = _clean_text(event.get("interview_id"), limit=80)
        if target is None and preferred_id:
            target = next((item for item in interviews if item.get("id") == preferred_id), None)
        if target is None:
            time_candidates = []
            for item in interviews:
                existing_start = _calendar_event_time(item.get("occurred_at") or item.get("display_time"))
                if existing_start and abs((existing_start - start).total_seconds()) <= 15 * 60:
                    time_candidates.append(item)
            if len(time_candidates) == 1:
                target = time_candidates[0]
            elif len(time_candidates) > 1:
                conflicts += 1
                continue

        previous_interviews = []
        for item in interviews:
            if item is target or _clean_text(item.get("status"), limit=40) == "cancelled":
                continue
            item_time = _calendar_event_time(item.get("occurred_at") or item.get("display_time"))
            if item_time and item_time < start:
                previous_interviews.append(item)
        is_followup = bool(previous_interviews)
        local_start = start.astimezone(beijing).replace(tzinfo=None)
        local_end = end.astimezone(beijing).replace(tzinfo=None) if end else None
        if target is None:
            target = {
                "id": f"int-outlook-{event_id[:12]}",
                "occurred_at": local_start.isoformat(timespec="minutes"),
                "ended_at": local_end.isoformat(timespec="minutes") if local_end else "",
                "display_time": f"{local_start:%Y-%m-%d %H:%M}–{local_end:%H:%M}" if local_end else f"{local_start:%Y-%m-%d %H:%M}",
                "title": _clean_text(event.get("title"), limit=220) or "专家访谈",
                "interviewer": "",
                "status": "scheduled",
                "quota_status": "scheduled",
                "transcript_id": "",
                "notes": "",
                "research_feedback": "",
                "future_tracking": "",
                "transcription_quality": "needs-review",
                "transcription_notes": "",
                "source_label": "Outlook 日历自动同步",
                "outlook_event_id": event_id,
                "outlook_managed": True,
                "created_at": now_iso,
                "updated_at": now_iso,
            }
            interviews.append(target)
            event_owner[event_id] = (expert_id, target)
            created += 1
            event_changed = True
        else:
            event_changed = False
            if not target.get("outlook_event_id"):
                target["outlook_event_id"] = event_id
                linked += 1
                event_changed = True
            if target.get("outlook_managed") is True:
                next_values = {
                    "occurred_at": local_start.isoformat(timespec="minutes"),
                    "ended_at": local_end.isoformat(timespec="minutes") if local_end else "",
                    "display_time": f"{local_start:%Y-%m-%d %H:%M}–{local_end:%H:%M}" if local_end else f"{local_start:%Y-%m-%d %H:%M}",
                    "title": _clean_text(event.get("title"), limit=220) or target.get("title") or "专家访谈",
                }
                if any(target.get(key) != value for key, value in next_values.items()):
                    target.update(next_values)
                    target["updated_at"] = now_iso
                    updated += 1
                    event_changed = True

        if start > reference and target.get("status") == "scheduled":
            if is_followup:
                if expert.get("status") != "followup-in-progress":
                    expert["status"] = "followup-in-progress"
                    event_changed = True
            elif expert.get("status") in {"not-reviewed", "maybe-not"}:
                expert["status"] = "scheduling"
                event_changed = True
        if event_changed:
            expert["interviews"] = _normalize_interviews(interviews, now_iso=now_iso)
            expert["updated_at"] = now_iso
            changed_experts.add(expert_id)

    return {
        "created": created,
        "linked": linked,
        "updated": updated,
        "conflicts": conflicts,
        "changed_experts": len(changed_experts),
    }


def _infer_category(text: str) -> str:
    for category, pattern in CATEGORY_RULES:
        if pattern.search(text or ""):
            return category
    return "未分类"


def _extract_main_company(expert: dict[str, Any]) -> str:
    description = _clean_text(expert.get("description"), limit=12000).casefold()
    self_employed = re.compile(r"self.?employed|independent|consulting|freelance|advisor|自雇|独立顾问", re.I)
    scores: dict[str, dict[str, Any]] = {}
    for job in _normalize_job_history(expert.get("job_history") or expert.get("jobHistory")):
        company = job.get("company", "")
        if not company or self_employed.search(company):
            continue
        normalized = re.sub(r"\s*(?:Inc\.?|Corp\.?|Ltd\.?|LLC|Holdings|,.*)$", "", company, flags=re.I).strip()
        if not normalized:
            continue
        key = normalized.casefold()
        entry = scores.setdefault(key, {"name": normalized, "mentions": 0, "in_description": False})
        entry["mentions"] += 1
        if key in description:
            entry["in_description"] = True

    if scores:
        best = max(scores.values(), key=lambda item: (10 if item["in_description"] else 0) + item["mentions"] * 2)
        return _clean_text(best["name"], limit=160)

    current_employer = _clean_text(expert.get("current_employer") or expert.get("currentEmployer"), limit=160)
    if current_employer and not self_employed.search(current_employer):
        return current_employer
    return ""


def normalize_expert_portfolio_entry(raw_entry: Any, *, now_iso: str = "") -> dict[str, Any] | None:
    if not isinstance(raw_entry, dict):
        return None
    name = _clean_text(raw_entry.get("name"), limit=160)
    if not name:
        return None

    vendors = _unique_strings(raw_entry.get("vendors") or raw_entry.get("vendor") or "") or ["未知来源"]
    status = _clean_text(raw_entry.get("status"), limit=60) or "not-reviewed"
    status = LEGACY_STATUS_MAP.get(status, status)
    if status not in STATUS_META:
        status = "not-reviewed"
    category = _clean_text(raw_entry.get("category"), limit=120) or "未分类"
    category = CATEGORY_TRANSLATIONS.get(category, category)
    job_history = _normalize_job_history(raw_entry.get("job_history") or raw_entry.get("jobHistory"))
    interviews = _normalize_interviews(raw_entry.get("interviews"), now_iso=now_iso)
    created_at = _clean_text(raw_entry.get("created_at") or raw_entry.get("dateAdded") or now_iso, limit=40)
    updated_at = _clean_text(raw_entry.get("updated_at") or now_iso or created_at, limit=40)

    normalized = {
        "id": _clean_text(raw_entry.get("id"), limit=80) or f"exp-{uuid.uuid4().hex[:12]}",
        "name": name,
        "vendors": vendors,
        "vendor_index": _normalize_vendor_index(raw_entry.get("vendor_index") or raw_entry.get("vendorIndex")),
        "current_title": _clean_text(raw_entry.get("current_title") or raw_entry.get("currentTitle"), limit=220),
        "current_employer": _clean_text(raw_entry.get("current_employer") or raw_entry.get("currentEmployer"), limit=220),
        "main_company": _clean_text(raw_entry.get("main_company") or raw_entry.get("mainCompany"), limit=180),
        "category": category,
        "industry": _clean_text(raw_entry.get("industry"), limit=120),
        "company_scale": _clean_text(raw_entry.get("company_scale") or raw_entry.get("companyScale"), limit=80),
        "region": normalize_region_label(_clean_text(raw_entry.get("region"), limit=120)),
        "source_record_id": _clean_text(raw_entry.get("source_record_id") or raw_entry.get("sourceRecordId"), limit=80),
        "description": _clean_text(raw_entry.get("description"), limit=12000),
        "job_history": job_history,
        "interviews": interviews,
        "status": status,
        "notes": _clean_text(raw_entry.get("notes"), limit=8000),
        "expert_comment": _clean_text(raw_entry.get("expert_comment") or raw_entry.get("expertComment"), limit=12000),
        "research_feedback": _clean_text(raw_entry.get("research_feedback") or raw_entry.get("researchFeedback"), limit=8000),
        "future_tracking": _clean_text(raw_entry.get("future_tracking") or raw_entry.get("futureTracking"), limit=8000),
        "data_quality_status": _clean_text(raw_entry.get("data_quality_status"), limit=40) or "source-recorded",
        "data_quality_notes": _clean_text(raw_entry.get("data_quality_notes"), limit=2400),
        "source_label": _clean_text(raw_entry.get("source_label"), limit=240),
        "source_emails": _unique_strings(raw_entry.get("source_emails") or raw_entry.get("sourceEmails"), limit=240),
        "duplicate_note": _clean_text(raw_entry.get("duplicate_note") or raw_entry.get("duplicateNote"), limit=1200),
        "date_added": _clean_text(raw_entry.get("date_added") or raw_entry.get("dateAdded") or created_at[:10], limit=20),
        "created_at": created_at,
        "updated_at": updated_at,
    }
    if not normalized["main_company"]:
        normalized["main_company"] = _extract_main_company(normalized)
    return normalized


def normalize_expert_portfolio_store(raw_store: Any, *, now_iso: str = "") -> dict[str, Any]:
    if isinstance(raw_store, list):
        source = {"experts": raw_store}
    elif isinstance(raw_store, dict):
        source = raw_store
    else:
        source = {}

    categories = _unique_strings(source.get("categories"), limit=120, max_items=80)
    if not categories:
        categories = list(DEFAULT_CATEGORIES)
    categories = [CATEGORY_TRANSLATIONS.get(item, item) for item in categories]
    if "未分类" not in categories:
        categories.append("未分类")

    experts: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for raw_entry in source.get("experts", []):
        entry = normalize_expert_portfolio_entry(raw_entry, now_iso=now_iso)
        if entry is None:
            continue
        while entry["id"] in used_ids:
            entry["id"] = f"exp-{uuid.uuid4().hex[:12]}"
        used_ids.add(entry["id"])
        experts.append(entry)
        if entry["category"] not in categories:
            categories.append(entry["category"])

    return {"version": 1, "categories": categories, "experts": experts}


def _load_store(path: Path, *, now_iso: str) -> dict[str, Any]:
    try:
        raw_store = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw_store = {}
    return normalize_expert_portfolio_store(raw_store, now_iso=now_iso)


def _save_store(path: Path, store: dict[str, Any], *, now_iso: str, write_json_atomic) -> dict[str, Any]:
    normalized = normalize_expert_portfolio_store(store, now_iso=now_iso)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, normalized)
    return normalized


def _get_expert(store: dict[str, Any], expert_id: str) -> dict[str, Any]:
    expert = next((item for item in store.get("experts", []) if item.get("id") == expert_id), None)
    if expert is None:
        abort(404)
    return expert


def _get_interview(expert: dict[str, Any], interview_id: str) -> dict[str, Any]:
    interview = next(
        (item for item in expert.get("interviews", []) if item.get("id") == interview_id),
        None,
    )
    if interview is None:
        abort(404)
    return interview


def _status_options() -> list[dict[str, Any]]:
    return [
        {"value": value, **meta}
        for value, meta in sorted(STATUS_META.items(), key=lambda item: item[1]["order"])
    ]


def _build_transcript_options(
    stock_store: dict[str, Any],
    link_scan: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    suggestions = {
        _clean_text(item.get("transcript_id"), limit=80): item
        for item in (link_scan or {}).get("results", [])
        if isinstance(item, dict)
        and item.get("status") in {"suggested", "suggested_new_interview", "duplicate_transcript"}
    }
    options: list[dict[str, str]] = []
    for item in stock_store.get("transcripts", []):
        transcript_id = _clean_text(item.get("id"), limit=80)
        if not transcript_id:
            continue
        title = _clean_text(item.get("title") or item.get("original_name"), limit=180) or "未命名转录"
        meeting_date = _clean_text(item.get("meeting_date") or item.get("created_at"), limit=40)
        suggestion = suggestions.get(transcript_id, {})
        hint = ""
        if suggestion.get("status") == "duplicate_transcript":
            hint = " · 疑似重复上传"
        elif suggestion.get("expert_name"):
            sequence = int(suggestion.get("interview_sequence") or 0)
            hint = f" · 建议：{suggestion['expert_name']}{f'（第 {sequence} 次）' if sequence else ''}"
        options.append(
            {
                "id": transcript_id,
                "title": title,
                "meeting_date": meeting_date,
                "label": f"{meeting_date or '日期待补充'} · {title}{hint}",
                "url": url_for("transcripts_page") + f"#transcript-{transcript_id}",
            }
        )
    options.sort(key=lambda item: (item["meeting_date"], item["title"].casefold()), reverse=True)
    return options


def _expert_sequence_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    match = re.search(r"\d+", str(item.get("source_record_id") or ""))
    return (
        int(match.group()) if match else 999999,
        str(item.get("name") or "").casefold(),
    )


def _build_context(
    store: dict[str, Any],
    *,
    stock_store: dict[str, Any] | None = None,
    link_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    transcript_options = _build_transcript_options(stock_store or {}, link_scan)
    transcripts_by_id = {item["id"]: item for item in transcript_options}
    sorted_experts = sorted(store.get("experts", []), key=_expert_sequence_sort_key)
    quota_view = build_interview_quota_view(store.get("experts", []))
    experts = []
    for item in sorted_experts:
        status_meta = STATUS_META.get(item.get("status"), STATUS_META["not-reviewed"])
        sequence_by_id = interview_sequence_map(item)
        interviews = []
        for interview in _normalize_interviews(item.get("interviews")):
            transcript = transcripts_by_id.get(interview.get("transcript_id"), {})
            summary = _normalize_interview_summary(interview.get("ai_summary"))
            interview_view = {key: value for key, value in interview.items() if key != "ai_summary"}
            interviews.append(
                {
                    **interview_view,
                    "ai_summary_status": summary.get("status") or "not-generated",
                    "status_label": INTERVIEW_STATUS_META[interview["status"]]["label"],
                    "status_tone": INTERVIEW_STATUS_META[interview["status"]]["tone"],
                    "transcript_title": transcript.get("title", ""),
                    "transcript_url": transcript.get("url", ""),
                    "interview_sequence": sequence_by_id.get(interview.get("id"), 0),
                }
            )
        experts.append(
            {
                **item,
                "interviews": interviews,
                "interview_count": len(interviews),
                "last_interview_label": (interviews[0].get("display_time") or interviews[0].get("occurred_at")) if interviews else "",
                "has_multiple_interviews": len(interviews) > 1,
                "needs_review": item.get("data_quality_status") == "needs-review",
                "status_label": status_meta["label"],
                "status_tone": status_meta["tone"],
                "vendor_index_text": ", ".join(
                    f"{key}: {value}" for key, value in item.get("vendor_index", {}).items()
                ),
                "job_history_text": _job_history_text(item.get("job_history")),
                "is_duplicate": bool(
                    len(item.get("vendors", [])) > 1
                    or item.get("status") == "duplicate"
                    or item.get("duplicate_note")
                ),
            }
        )
    vendor_counts: dict[str, int] = {}
    status_counts = {key: 0 for key in STATUS_META}
    category_counts = {category: 0 for category in store.get("categories", [])}
    industry_counts: dict[str, int] = {}
    region_counts: dict[str, int] = {}
    scale_counts: dict[str, int] = {}
    for expert in experts:
        for vendor in expert.get("vendors", []):
            vendor_counts[vendor] = vendor_counts.get(vendor, 0) + 1
        status_counts[expert.get("status", "not-reviewed")] = status_counts.get(expert.get("status", "not-reviewed"), 0) + 1
        category = expert.get("category", "未分类")
        category_counts[category] = category_counts.get(category, 0) + 1
        for field, counts in (
            ("industry", industry_counts),
            ("region", region_counts),
            ("company_scale", scale_counts),
        ):
            value = _clean_text(expert.get(field), limit=120)
            if value:
                counts[value] = counts.get(value, 0) + 1

    duplicate_count = sum(
        1
        for expert in experts
        if len(expert.get("vendors", [])) > 1 or expert.get("status") == "duplicate" or expert.get("duplicate_note")
    )
    stats = {
        "total": len(experts),
        "reviewed": sum(1 for item in experts if item.get("status") != "not-reviewed"),
        "interested": sum(
            1
            for item in experts
            if item.get("status") in {"scheduling", "scheduling-followup", "followup-in-progress"}
        ),
        "completed": sum(
            1 for item in experts for interview in item.get("interviews", []) if interview.get("status") == "completed"
        ),
        "vendors": len(vendor_counts),
        "duplicates": duplicate_count,
        "interviews": sum(len(item.get("interviews", [])) for item in experts),
        "scheduled": sum(
            1 for item in experts for interview in item.get("interviews", []) if interview.get("status") == "scheduled"
        ),
        "industries": len(industry_counts),
        "regions": len(region_counts),
        "needs_review": sum(1 for item in experts if item.get("needs_review")),
        "multiple_interviews": sum(1 for item in experts if item.get("has_multiple_interviews")),
    }
    return {
        "portfolio_experts": experts,
        "portfolio_categories": store.get("categories", []),
        "portfolio_status_options": _status_options(),
        "portfolio_vendor_counts": sorted(vendor_counts.items(), key=lambda item: item[0].casefold()),
        "portfolio_status_counts": status_counts,
        "portfolio_category_counts": category_counts,
        "portfolio_industry_counts": sorted(industry_counts.items(), key=lambda item: item[0].casefold()),
        "portfolio_region_counts": sorted(region_counts.items(), key=lambda item: item[0].casefold()),
        "portfolio_scale_counts": sorted(scale_counts.items(), key=lambda item: item[0].casefold()),
        "portfolio_interview_status_options": [
            {"value": key, **meta}
            for key, meta in sorted(INTERVIEW_STATUS_META.items(), key=lambda item: item[1]["order"])
        ],
        "portfolio_quota_status_options": QUOTA_STATUS_OPTIONS,
        "portfolio_quota_groups": quota_view["groups"],
        "portfolio_quota_stats": {
            "completed": quota_view["completed"],
            "scheduled": quota_view["scheduled"],
            "total": quota_view["total"],
        },
        "portfolio_transcript_options": transcript_options,
        "portfolio_stats": stats,
    }


def _expert_from_form(form, *, existing: dict[str, Any] | None, now_iso: str) -> dict[str, Any] | None:
    source = dict(existing or {})
    source.update(
        {
            "name": form.get("name"),
            "vendors": form.get("vendors"),
            "vendor_index": form.get("vendor_index"),
            "current_title": form.get("current_title"),
            "current_employer": form.get("current_employer"),
            "main_company": form.get("main_company"),
            "category": form.get("category"),
            "industry": form.get("industry"),
            "company_scale": form.get("company_scale"),
            "region": form.get("region"),
            "source_record_id": form.get("source_record_id"),
            "description": form.get("description"),
            "job_history": form.get("job_history"),
            "status": form.get("status"),
            "notes": form.get("notes"),
            "expert_comment": form.get("expert_comment"),
            "data_quality_status": form.get("data_quality_status"),
            "data_quality_notes": form.get("data_quality_notes"),
            "source_label": form.get("source_label"),
            "source_emails": form.get("source_emails"),
            "duplicate_note": form.get("duplicate_note"),
            "date_added": form.get("date_added"),
            "updated_at": now_iso,
        }
    )
    # These legacy expert-level fields are now maintained per interview. Keep
    # existing/imported values intact, but do not let the cleaner expert form
    # erase them merely because it no longer renders those inputs.
    for legacy_field in ("research_feedback", "future_tracking"):
        if legacy_field in form:
            source[legacy_field] = form.get(legacy_field)
    source.setdefault("created_at", now_iso)
    return normalize_expert_portfolio_entry(source, now_iso=now_iso)


def _interview_from_form(form, *, existing: dict[str, Any] | None, now_iso: str) -> dict[str, Any]:
    source = dict(existing or {})
    source.update(
        {
            "occurred_at": form.get("occurred_at"),
            "ended_at": form.get("ended_at"),
            "display_time": form.get("display_time"),
            "title": form.get("title"),
            "interviewer": form.get("interviewer"),
            "status": form.get("status"),
            "quota_status": form.get("quota_status"),
            "transcript_id": form.get("transcript_id"),
            "notes": form.get("notes"),
            "research_feedback": form.get("research_feedback"),
            "future_tracking": form.get("future_tracking"),
            "transcription_quality": form.get("transcription_quality"),
            "transcription_notes": form.get("transcription_notes"),
            "source_label": form.get("source_label"),
            "updated_at": now_iso,
        }
    )
    source.setdefault("created_at", now_iso)
    return _normalize_interviews([source], now_iso=now_iso)[0]


def _merge_experts(store: dict[str, Any], incoming: list[Any], *, now_iso: str) -> tuple[int, int, list[str]]:
    by_name = {
        str(expert.get("name") or "").casefold(): expert
        for expert in store.get("experts", [])
        if str(expert.get("name") or "").strip()
    }
    added = 0
    merged = 0
    categories: list[str] = store.setdefault("categories", list(DEFAULT_CATEGORIES))
    errors: list[str] = []

    for index, raw_entry in enumerate(incoming):
        entry = normalize_expert_portfolio_entry(raw_entry, now_iso=now_iso)
        if entry is None:
            errors.append(f"第 {index + 1} 条缺少姓名")
            continue
        key = entry["name"].casefold()
        existing = by_name.get(key)
        if existing is None:
            existing_ids = {item.get("id") for item in store.get("experts", [])}
            if entry["id"] in existing_ids:
                entry["id"] = f"exp-{uuid.uuid4().hex[:12]}"
            store.setdefault("experts", []).append(entry)
            by_name[key] = entry
            added += 1
        else:
            existing["vendors"] = _unique_strings(existing.get("vendors", []) + entry.get("vendors", []))
            existing["source_emails"] = _unique_strings(
                existing.get("source_emails", []) + entry.get("source_emails", []),
                limit=240,
            )
            existing["vendor_index"] = {
                **_normalize_vendor_index(existing.get("vendor_index")),
                **_normalize_vendor_index(entry.get("vendor_index")),
            }
            existing_jobs = _normalize_job_history(existing.get("job_history"))
            known_jobs = {(item["title"].casefold(), item["company"].casefold(), item["dates"].casefold()) for item in existing_jobs}
            for job in _normalize_job_history(entry.get("job_history")):
                key_job = (job["title"].casefold(), job["company"].casefold(), job["dates"].casefold())
                if key_job not in known_jobs:
                    existing_jobs.append(job)
                    known_jobs.add(key_job)
            existing["job_history"] = existing_jobs
            for field in (
                "current_title",
                "current_employer",
                "main_company",
                "industry",
                "company_scale",
                "region",
                "source_record_id",
                "description",
                "notes",
                "expert_comment",
                "research_feedback",
                "future_tracking",
                "data_quality_notes",
                "source_label",
                "duplicate_note",
            ):
                if not existing.get(field) and entry.get(field):
                    existing[field] = entry[field]
            existing_interviews = _normalize_interviews(existing.get("interviews"), now_iso=now_iso)
            known_interviews = {
                (item.get("occurred_at"), item.get("title"), item.get("source_label")) for item in existing_interviews
            }
            for interview in _normalize_interviews(entry.get("interviews"), now_iso=now_iso):
                interview_key = (
                    interview.get("occurred_at"),
                    interview.get("title"),
                    interview.get("source_label"),
                )
                if interview_key not in known_interviews:
                    existing_interviews.append(interview)
                    known_interviews.add(interview_key)
            existing["interviews"] = _normalize_interviews(existing_interviews, now_iso=now_iso)
            if existing.get("status") == "not-reviewed" and entry.get("status") != "not-reviewed":
                existing["status"] = entry["status"]
            if existing.get("category") in {"", "未分类"} and entry.get("category") not in {"", "未分类"}:
                existing["category"] = entry["category"]
            existing["updated_at"] = now_iso
            merged += 1

        category = entry.get("category") or "未分类"
        if category not in categories:
            categories.append(category)

    return added, merged, errors


def _extract_email_text(raw_bytes: bytes) -> tuple[str, str]:
    message = BytesParser(policy=policy.default).parsebytes(raw_bytes)
    sender = _clean_text(message.get("from"), limit=300)
    text_parts: list[str] = []
    html_parts: list[str] = []
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            try:
                content = part.get_content()
            except Exception:
                continue
            if content_type == "text/plain" and isinstance(content, str):
                text_parts.append(content)
            elif content_type == "text/html" and isinstance(content, str):
                html_parts.append(content)
    else:
        try:
            content = message.get_content()
        except Exception:
            content = ""
        if isinstance(content, str):
            if message.get_content_type() == "text/html":
                html_parts.append(content)
            else:
                text_parts.append(content)

    if text_parts:
        return sender, "\n".join(text_parts)
    extractor = _TextExtractor()
    for html_text in html_parts:
        extractor.feed(html_text)
    return sender, "\n".join(extractor.parts)


def _decode_msg_fallback(raw_bytes: bytes) -> str:
    candidates: list[str] = []
    for encoding in ("utf-8", "utf-16le", "latin-1"):
        try:
            decoded = raw_bytes.decode(encoding, errors="ignore")
        except Exception:
            continue
        candidates.append("\n".join(part.strip() for part in re.split(r"[\x00\r\n]+", decoded) if len(part.strip()) > 2))
    return max(candidates, key=len, default="")


def _detect_vendor(text: str) -> str:
    folded = text.casefold()
    checks = [
        ("GLG", ("glgroup.com", "glginsights", "glg")),
        ("Third Bridge", ("thirdbridge", "third bridge")),
        ("Guidepoint", ("guidepoint",)),
        ("AlphaSights", ("alphasights",)),
        ("Prosapient", ("prosapient",)),
        ("Tegus", ("tegus",)),
        ("Coleman", ("coleman",)),
    ]
    for vendor, markers in checks:
        if any(marker in folded for marker in markers):
            return vendor
    return "未知来源"


def _parse_email_profiles(text: str, *, filename: str, sender: str = "") -> list[dict[str, Any]]:
    compact_text = str(text or "").replace("=3D", "=").replace("=20", " ")
    vendor = _detect_vendor("\n".join([sender, compact_text]))
    results: list[dict[str, Any]] = []
    patterns = [
        re.compile(
            r"(?:^|\n)\s*(?:#?\d[\d.]*[\s\-–]+|Advisor\s+#?\d+\s*[:：]?\s*)([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){1,4})\s*[-–:]\s*((?:Former|Current|Ex-)?[^\n]{3,180}?(?:\s+at\s+|\s+@\s+)[^\n]{2,160})",
            re.I,
        ),
        re.compile(
            r"(?:Name|Expert|Advisor)\s*[:：]\s*([^\n]{3,100})\n(?:Title|Role|Position)\s*[:：]\s*([^\n]{2,160})(?:\n(?:Company|Employer)\s*[:：]\s*([^\n]{2,160}))?",
            re.I,
        ),
    ]
    seen_names: set[str] = set()
    for pattern_index, pattern in enumerate(patterns):
        for match in pattern.finditer(compact_text):
            name = _clean_text(match.group(1), limit=120)
            if not name or name.casefold() in seen_names:
                continue
            seen_names.add(name.casefold())
            if pattern_index == 0:
                title_company = _clean_text(match.group(2), limit=320)
                parts = re.split(r"\s+at\s+|\s+@\s+", title_company, maxsplit=1, flags=re.I)
                title = parts[0] if parts else ""
                employer = parts[1] if len(parts) > 1 else ""
            else:
                title = _clean_text(match.group(2), limit=180)
                employer = _clean_text(match.group(3) if match.lastindex and match.lastindex >= 3 else "", limit=180)
            start = match.start()
            description = re.sub(r"\s+", " ", compact_text[start : start + 1600]).strip()[:800]
            blob = " ".join([name, title, employer, description])
            results.append(
                {
                    "name": name,
                    "vendors": [vendor],
                    "vendor_index": {},
                    "current_title": title,
                    "current_employer": employer,
                    "main_company": employer,
                    "category": _infer_category(blob),
                    "description": description,
                    "job_history": [],
                    "status": "not-reviewed",
                    "notes": f"由邮件“{filename}”自动解析，请核对后再使用。",
                    "source_emails": [filename],
                    "duplicate_note": "",
                }
            )
    return results[:80]


def register_expert_portfolio_routes(app, deps: SimpleNamespace) -> None:
    get_store_path = deps.get_expert_portfolio_store_path
    write_json_atomic = deps.write_json_atomic
    build_navigation_context = deps.build_navigation_context
    load_stock_store = deps.load_stock_store
    get_stock_store_signature = deps.get_stock_store_signature
    get_stock_store_path = deps.get_stock_store_path
    get_provider_config_path = deps.get_expert_intake_provider_config_path
    get_calendar_config_path = deps.get_outlook_calendar_config_path
    get_calendar_cache_path = deps.get_outlook_calendar_cache_path
    get_link_cache_path = deps.get_expert_interview_link_cache_path
    now_iso = deps.now_iso
    safe_next_url = deps.safe_next_url
    is_visitor_mode = deps.is_visitor_mode

    def load_store() -> dict[str, Any]:
        with EXPERT_PORTFOLIO_LOCK:
            return _load_store(Path(get_store_path()), now_iso=now_iso())

    def save_store(store: dict[str, Any]) -> dict[str, Any]:
        with EXPERT_PORTFOLIO_LOCK:
            return _save_store(Path(get_store_path()), store, now_iso=now_iso(), write_json_atomic=write_json_atomic)

    def run_calendar_sync(*, force: bool = False) -> dict[str, Any]:
        if not OUTLOOK_CALENDAR_SYNC_ACTIVE.acquire(blocking=False):
            return {**calendar_connection_status(Path(get_calendar_config_path()), Path(get_calendar_cache_path())), "syncing": True}
        try:
            store = load_store()
            result = synchronize_calendar(
                Path(get_calendar_config_path()),
                Path(get_calendar_cache_path()),
                store.get("experts", []),
                Path(get_provider_config_path()),
                force=force,
            )
            if result.get("status") == "ready":
                with EXPERT_PORTFOLIO_LOCK:
                    latest_store = load_store()
                    materialized = _materialize_calendar_events(
                        latest_store,
                        result.get("events", []),
                        now_iso=now_iso(),
                    )
                    if materialized["changed_experts"]:
                        save_store(latest_store)
                result["materialized"] = materialized
            return result
        finally:
            OUTLOOK_CALENDAR_SYNC_ACTIVE.release()

    def run_interview_link_scan(*, force: bool = False) -> dict[str, Any]:
        cache_path = Path(get_link_cache_path())
        with EXPERT_LINK_SCAN_LOCK:
            current_cache = load_link_cache(cache_path)
            if not force and current_cache and link_cache_fresh(current_cache):
                return current_cache
            store = load_store()
            stock_store = load_stock_store()
            result = build_link_scan(
                store.get("experts", []),
                stock_store.get("transcripts", []),
                provider_config_path=Path(get_provider_config_path()),
                allow_model=True,
            )
            result.pop("actions", None)
            # The optional model check can take several seconds.  Reload and
            # revalidate the small, deterministic action set under the store
            # lock so a concurrent manual edit can never be overwritten.
            with EXPERT_PORTFOLIO_LOCK:
                latest_store = load_store()
                latest_scan = build_link_scan(
                    latest_store.get("experts", []),
                    stock_store.get("transcripts", []),
                    allow_model=False,
                )
                applied = apply_safe_links(
                    latest_store.get("experts", []),
                    latest_scan.pop("actions", []),
                    now_iso=now_iso(),
                )
                if applied:
                    save_store(latest_store)
            if applied:
                # Rebuild after applying, so repeated runs report `linked` and
                # never count the same transcript or communication twice.
                refreshed_result = build_link_scan(
                    latest_store.get("experts", []),
                    stock_store.get("transcripts", []),
                    allow_model=False,
                )
                refreshed_result.pop("actions", None)
                # Preserve model-only review suggestions from the earlier
                # snapshot; they remain non-mutating and cannot affect links.
                model_suggestions = {
                    str(item.get("transcript_id") or ""): item
                    for item in result.get("results", [])
                    if item.get("status") == "suggested" and str(item.get("evidence") or "").startswith("DeepSeek 核对：")
                }
                for index, item in enumerate(refreshed_result.get("results", [])):
                    suggestion = model_suggestions.get(str(item.get("transcript_id") or ""))
                    if suggestion and item.get("status") in {"unmatched", "pending_review"}:
                        refreshed_result["results"][index] = suggestion
                refreshed_result["suggestion_count"] = sum(
                    1
                    for item in refreshed_result.get("results", [])
                    if item.get("status") in {"suggested", "suggested_new_interview", "safe_auto_link"}
                )
                result = refreshed_result
            result["auto_linked_count"] = len(applied)
            save_link_cache(cache_path, result)
            for action in applied:
                try:
                    # A newly linked, completed transcript can immediately use
                    # the existing isolated summary queue.  Failure here never
                    # rolls back or damages the verified transcript link.
                    queue_summary_job(str(action["expert_id"]), str(action["interview_id"]))
                except Exception:
                    pass
            return result

    def start_calendar_worker() -> None:
        global OUTLOOK_CALENDAR_WORKER_STARTED
        if app.config.get("TESTING"):
            return
        calendar_background_enabled = os.getenv("OUTLOOK_CALENDAR_BACKGROUND_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
        link_scan_enabled = os.getenv("EXPERT_LINK_BACKGROUND_ENABLED", "1").strip().lower() not in {"0", "false", "off", "no"}
        if not calendar_background_enabled and not link_scan_enabled:
            return
        with OUTLOOK_CALENDAR_WORKER_LOCK:
            if OUTLOOK_CALENDAR_WORKER_STARTED:
                return
            OUTLOOK_CALENDAR_WORKER_STARTED = True

        def worker() -> None:
            while True:
                try:
                    if (
                        calendar_background_enabled
                        and calendar_connection_status(Path(get_calendar_config_path()), Path(get_calendar_cache_path()))["configured"]
                    ):
                        run_calendar_sync(force=False)
                except Exception:
                    # The last known-good cache remains available; the worker must never take down Flask.
                    pass
                try:
                    if link_scan_enabled:
                        run_interview_link_scan(force=False)
                except Exception:
                    # Link suggestions are isolated from the portfolio; a scan
                    # failure must never affect the website or prior links.
                    pass
                time.sleep(60)

        threading.Thread(target=worker, name="outlook-calendar-readonly", daemon=True).start()

    def find_transcript(transcript_id: str, stock_store: dict[str, Any] | None = None) -> dict[str, Any] | None:
        normalized_id = _clean_text(transcript_id, limit=80)
        if not normalized_id:
            return None
        if isinstance(stock_store, dict):
            return next(
                (item for item in stock_store.get("transcripts", []) if str(item.get("id") or "") == normalized_id),
                None,
            )

        signature = (str(Path(get_stock_store_path()).resolve()), get_stock_store_signature())
        with INTERVIEW_SUMMARY_TRANSCRIPT_CACHE_LOCK:
            cached_signature = INTERVIEW_SUMMARY_TRANSCRIPT_CACHE.get("signature")
            cached_items = INTERVIEW_SUMMARY_TRANSCRIPT_CACHE.get("items")
            if cached_signature == signature and isinstance(cached_items, dict):
                return cached_items.get(normalized_id)

        source = load_stock_store()
        items: dict[str, dict[str, Any]] = {}
        for item in source.get("transcripts", []):
            item_id = _clean_text(item.get("id"), limit=80)
            if not item_id:
                continue
            items[item_id] = {
                "id": item_id,
                "title": item.get("title"),
                "original_name": item.get("original_name"),
                "status": item.get("status"),
                "transcript_text": item.get("transcript_text"),
            }
        with INTERVIEW_SUMMARY_TRANSCRIPT_CACHE_LOCK:
            INTERVIEW_SUMMARY_TRANSCRIPT_CACHE["signature"] = signature
            INTERVIEW_SUMMARY_TRANSCRIPT_CACHE["items"] = items
        return items.get(normalized_id)

    def update_summary_record(expert_id: str, interview_id: str, values: dict[str, Any]) -> bool:
        with EXPERT_PORTFOLIO_LOCK:
            store = load_store()
            expert = next((item for item in store.get("experts", []) if item.get("id") == expert_id), None)
            if expert is None:
                return False
            interview = next(
                (item for item in expert.get("interviews", []) if item.get("id") == interview_id),
                None,
            )
            if interview is None:
                return False
            summary = _normalize_interview_summary(interview.get("ai_summary"))
            summary.update(values)
            summary["updated_at"] = now_iso()
            interview["ai_summary"] = _normalize_interview_summary(summary)
            expert["updated_at"] = now_iso()
            save_store(store)
            return True

    def run_summary_job(expert_id: str, interview_id: str) -> None:
        key = (expert_id, interview_id)
        INTERVIEW_SUMMARY_SEMAPHORE.acquire()
        try:
            store = load_store()
            expert = _get_expert(store, expert_id)
            interview = _get_interview(expert, interview_id)
            transcript_id = _clean_text(interview.get("transcript_id"), limit=80)
            transcript = find_transcript(transcript_id)
            transcript_text = str((transcript or {}).get("transcript_text") or "").strip()
            if transcript is None:
                raise InterviewSummaryError("关联的语音转录不存在，请重新关联。")
            if len(transcript_text) < 80:
                raise InterviewSummaryError("关联转录尚未完成，摘要会在正文可用后才能生成。")

            update_summary_record(
                expert_id,
                interview_id,
                {
                    "status": "generating",
                    "source_transcript_id": transcript_id,
                    "error": "",
                },
            )
            result = generate_interview_summary(
                Path(get_provider_config_path()),
                provider_id="deepseek",
                transcript_text=transcript_text,
                expert_name=str(expert.get("name") or ""),
                company=str(expert.get("current_employer") or expert.get("main_company") or ""),
                interview_title=str(interview.get("title") or ""),
                interview_time=str(interview.get("display_time") or interview.get("occurred_at") or ""),
            )
            update_summary_record(
                expert_id,
                interview_id,
                {
                    **result,
                    "status": "ready",
                    "source_transcript_id": transcript_id,
                    "generated_at": now_iso(),
                    "error": "",
                },
            )
        except InterviewSummaryError as exc:
            update_summary_record(
                expert_id,
                interview_id,
                {"status": "failed", "error": str(exc)[:500]},
            )
        except Exception:
            update_summary_record(
                expert_id,
                interview_id,
                {"status": "failed", "error": "摘要生成遇到内部错误，可稍后重新生成。"},
            )
        finally:
            INTERVIEW_SUMMARY_SEMAPHORE.release()
            with INTERVIEW_SUMMARY_LOCK:
                INTERVIEW_SUMMARY_ACTIVE.discard(key)

    def queue_summary_job(expert_id: str, interview_id: str, *, force: bool = False) -> tuple[bool, str]:
        key = (expert_id, interview_id)
        with INTERVIEW_SUMMARY_LOCK:
            if key in INTERVIEW_SUMMARY_ACTIVE:
                return False, "摘要正在后台生成。"

            store = load_store()
            expert = _get_expert(store, expert_id)
            interview = _get_interview(expert, interview_id)
            transcript_id = _clean_text(interview.get("transcript_id"), limit=80)
            if not transcript_id:
                return False, "请先关联一条语音转录。"
            transcript = find_transcript(transcript_id)
            transcript_text = str((transcript or {}).get("transcript_text") or "").strip()
            if transcript is None:
                return False, "关联的语音转录不存在，请重新关联。"
            if len(transcript_text) < 80:
                return False, "关联转录尚未完成，暂时不能生成摘要。"
            summary = _normalize_interview_summary(interview.get("ai_summary"))
            current_digest = transcript_digest(transcript_text[:MAX_TRANSCRIPT_CHARS])
            if (
                not force
                and summary.get("status") == "ready"
                and summary.get("source_transcript_id") == transcript_id
                and summary.get("source_digest") == current_digest
            ):
                return False, "摘要已经是最新版本。"

            summary.update(
                {
                    "status": "queued",
                    "source_transcript_id": transcript_id,
                    "error": "",
                    "updated_at": now_iso(),
                }
            )
            interview["ai_summary"] = _normalize_interview_summary(summary)
            expert["updated_at"] = now_iso()
            save_store(store)
            INTERVIEW_SUMMARY_ACTIVE.add(key)

        if app.config.get("TESTING"):
            # Deterministic tests must not leave a writer thread racing with
            # temporary-directory cleanup.
            run_summary_job(expert_id, interview_id)
        else:
            worker = threading.Thread(
                target=run_summary_job,
                args=(expert_id, interview_id),
                daemon=True,
                name=f"interview-summary-{interview_id}",
            )
            worker.start()
        return True, "摘要已进入后台生成队列。"

    def summary_response(expert: dict[str, Any], interview: dict[str, Any]) -> dict[str, Any]:
        transcript_id = _clean_text(interview.get("transcript_id"), limit=80)
        summary = _normalize_interview_summary(interview.get("ai_summary"))
        key = (str(expert.get("id") or ""), str(interview.get("id") or ""))
        with INTERVIEW_SUMMARY_LOCK:
            active = key in INTERVIEW_SUMMARY_ACTIVE
        transcript = find_transcript(transcript_id) if transcript_id else None
        transcript_text = str((transcript or {}).get("transcript_text") or "").strip()
        status = str(summary.get("status") or "not-generated")
        message = "这次访谈还没有生成摘要。"
        can_generate = False

        if not transcript_id:
            status = "unavailable"
            message = "请先为这次访谈关联语音转录。"
        elif transcript is None:
            status = "unavailable"
            message = "关联的语音转录不存在，请重新关联。"
        elif len(transcript_text) < 80:
            status = "waiting-transcript"
            message = "语音转录尚未完成，正文生成后才能制作摘要。"
        elif active and status in {"queued", "generating"}:
            message = "摘要正在后台生成，稍后会自动加载。"
        elif status in {"queued", "generating"}:
            status = "interrupted"
            message = "上次摘要任务未完成，可以重新生成。"
            can_generate = True
        elif status == "ready":
            current_digest = transcript_digest(transcript_text[:MAX_TRANSCRIPT_CHARS])
            if summary.get("source_transcript_id") != transcript_id or summary.get("source_digest") != current_digest:
                status = "stale"
                message = "转录内容已变化，当前显示旧摘要，建议重新生成。"
                can_generate = True
            else:
                message = "摘要已生成。"
                can_generate = True
        elif status == "failed":
            message = summary.get("error") or "摘要生成失败，可以重新尝试。"
            can_generate = True
        else:
            status = "not-generated"
            can_generate = True

        return {
            "ok": True,
            "status": status,
            "message": message,
            "can_generate": can_generate,
            "expert": {"id": expert.get("id"), "name": expert.get("name")},
            "interview": {
                "id": interview.get("id"),
                "title": interview.get("title"),
                "display_time": interview.get("display_time") or interview.get("occurred_at"),
            },
            "transcript": {
                "id": transcript_id,
                "title": str((transcript or {}).get("title") or (transcript or {}).get("original_name") or ""),
                "status": str((transcript or {}).get("status") or ""),
            },
            "summary": summary,
        }

    @app.get("/expert-portfolio")
    def expert_portfolio_page() -> str:
        portfolio_store = load_store()
        stock_store = load_stock_store()
        link_scan = load_link_cache(Path(get_link_cache_path()))
        return render_template(
            "expert_portfolio.html",
            page_return_url=request.full_path if request.query_string else request.path,
            portfolio_calendar_sync=calendar_view_payload(
                Path(get_calendar_config_path()),
                Path(get_calendar_cache_path()),
                allowed_expert_ids={
                    str(item.get("id") or "")
                    for item in portfolio_store.get("experts", [])
                    if item.get("id")
                },
            ),
            portfolio_link_scan=link_scan,
            **_build_context(portfolio_store, stock_store=stock_store, link_scan=link_scan),
            **build_navigation_context(active_page="expert_portfolio", stock_store=stock_store),
        )

    @app.get("/expert-portfolio/calendar-sync/status")
    def expert_portfolio_calendar_sync_status():
        return jsonify({"ok": True, **calendar_connection_status(Path(get_calendar_config_path()), Path(get_calendar_cache_path()))})

    @app.get("/expert-portfolio/link-scan/status")
    def expert_portfolio_link_scan_status():
        result = load_link_cache(Path(get_link_cache_path()))
        return jsonify(
            {
                "ok": True,
                "status": result.get("status", "idle"),
                "message": result.get("message", "尚未扫描"),
                "last_checked_at": result.get("last_checked_at", ""),
                "linked_count": result.get("linked_count", 0),
                "suggestion_count": result.get("suggestion_count", 0),
                "duplicate_count": result.get("duplicate_count", 0),
            }
        )

    @app.post("/expert-portfolio/link-scan/refresh")
    def expert_portfolio_link_scan_refresh():
        if is_visitor_mode():
            abort(403)
        threading.Thread(
            target=run_interview_link_scan,
            kwargs={"force": True},
            name="expert-interview-link-scan",
            daemon=True,
        ).start()
        return jsonify({"ok": True, "message": "正在后台核对语音转录关联。"})

    @app.post("/expert-portfolio/calendar-sync/configure")
    def expert_portfolio_calendar_sync_configure():
        if is_visitor_mode():
            abort(403)
        payload = request.get_json(silent=True) if request.is_json else request.form
        try:
            result = configure_calendar_source(
                (payload or {}).get("ics_url", ""),
                Path(get_calendar_config_path()),
                Path(get_calendar_cache_path()),
                load_store().get("experts", []),
                Path(get_provider_config_path()),
            )
        except CalendarSyncError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        start_calendar_worker()
        threading.Thread(target=run_calendar_sync, kwargs={"force": True}, name="outlook-calendar-initial-sync", daemon=True).start()
        return jsonify({"ok": True, "message": f"只读连接已验证，识别到 {result['event_count']} 条专家访谈日程。"})

    @app.post("/expert-portfolio/calendar-sync/import")
    def expert_portfolio_calendar_sync_import():
        if is_visitor_mode():
            abort(403)
        upload = request.files.get("calendar_file")
        if upload is None or not str(upload.filename or "").lower().endswith(".ics"):
            return jsonify({"ok": False, "message": "请选择 .ics 日历文件。"}), 400
        content = upload.stream.read(2 * 1024 * 1024 + 1)
        try:
            result = import_calendar_content(
                content,
                Path(get_calendar_cache_path()),
                load_store().get("experts", []),
                Path(get_provider_config_path()),
            )
            with EXPERT_PORTFOLIO_LOCK:
                store = load_store()
                materialized = _materialize_calendar_events(
                    store,
                    result.get("events", []),
                    now_iso=now_iso(),
                )
                if materialized["changed_experts"]:
                    save_store(store)
        except CalendarSyncError as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400
        return jsonify({"ok": True, "message": result["message"], "event_count": result["event_count"], "materialized": materialized})

    @app.post("/expert-portfolio/calendar-sync/refresh")
    def expert_portfolio_calendar_sync_refresh():
        if is_visitor_mode():
            abort(403)
        status = calendar_connection_status(Path(get_calendar_config_path()), Path(get_calendar_cache_path()))
        if not status["configured"]:
            return jsonify({"ok": False, "message": "尚未配置 Outlook 只读日历地址。"}), 400
        threading.Thread(target=run_calendar_sync, kwargs={"force": True}, name="outlook-calendar-manual-sync", daemon=True).start()
        return jsonify({"ok": True, "message": "正在后台同步；旧日程会保留到新结果验证完成。"})

    @app.before_request
    def ensure_expert_link_worker_started() -> None:
        # Start lazily after the production app is serving requests. This keeps
        # imports and tests side-effect free while retaining four-hour scans.
        start_calendar_worker()

    @app.post("/expert-portfolio/experts")
    def create_expert_portfolio_entry():
        timestamp = now_iso()
        entry = _expert_from_form(request.form, existing=None, now_iso=timestamp)
        if entry is None:
            flash("请至少填写专家姓名。", "error")
            return redirect(url_for("expert_portfolio_page"))
        store = load_store()
        store.setdefault("experts", []).append(entry)
        if entry["category"] not in store.setdefault("categories", list(DEFAULT_CATEGORIES)):
            store["categories"].append(entry["category"])
        save_store(store)
        flash(f'专家“{entry["name"]}”已加入专家组合。', "success")
        return redirect(url_for("expert_portfolio_page", expert=entry["id"]))

    @app.post("/expert-portfolio/experts/<expert_id>/update")
    def update_expert_portfolio_entry(expert_id: str):
        store = load_store()
        expert = _get_expert(store, expert_id)
        updated = _expert_from_form(request.form, existing=expert, now_iso=now_iso())
        if updated is None:
            flash("专家资料没有保存，请检查姓名。", "error")
            return redirect(url_for("expert_portfolio_page"))
        expert.update(updated)
        if expert["category"] not in store.setdefault("categories", list(DEFAULT_CATEGORIES)):
            store["categories"].append(expert["category"])
        save_store(store)
        flash(f'专家“{expert["name"]}”资料已更新。', "success")
        return redirect(safe_next_url(request.form.get("next_url"), url_for("expert_portfolio_page")))

    @app.post("/expert-portfolio/experts/<expert_id>/interviews")
    def create_expert_portfolio_interview(expert_id: str):
        store = load_store()
        expert = _get_expert(store, expert_id)
        timestamp = now_iso()
        interview = _interview_from_form(request.form, existing=None, now_iso=timestamp)
        expert.setdefault("interviews", []).append(interview)
        expert["interviews"] = _normalize_interviews(expert["interviews"], now_iso=timestamp)
        expert["updated_at"] = timestamp
        if interview["status"] == "completed":
            expert["status"] = "completed"
        elif interview["status"] == "scheduled" and expert.get("status") in {"not-reviewed", "maybe-not"}:
            expert["status"] = "scheduling"
        save_store(store)
        if interview.get("transcript_id"):
            queue_summary_job(expert_id, str(interview.get("id") or ""))
        flash(f'已为“{expert["name"]}”添加一条访谈记录。', "success")
        return redirect(url_for("expert_portfolio_page", expert=expert_id))

    @app.post("/expert-portfolio/experts/<expert_id>/interviews/<interview_id>/update")
    def update_expert_portfolio_interview(expert_id: str, interview_id: str):
        store = load_store()
        expert = _get_expert(store, expert_id)
        existing = next(
            (item for item in expert.get("interviews", []) if item.get("id") == interview_id),
            None,
        )
        if existing is None:
            abort(404)
        previous_transcript_id = str(existing.get("transcript_id") or "")
        previous_summary_status = str(
            _normalize_interview_summary(existing.get("ai_summary")).get("status") or ""
        )
        updated = _interview_from_form(request.form, existing=existing, now_iso=now_iso())
        existing.update(updated)
        expert["interviews"] = _normalize_interviews(expert.get("interviews"), now_iso=now_iso())
        expert["updated_at"] = now_iso()
        save_store(store)
        current_transcript_id = str(updated.get("transcript_id") or "")
        if current_transcript_id and (
            current_transcript_id != previous_transcript_id or previous_summary_status != "ready"
        ):
            queue_summary_job(expert_id, interview_id)
        flash("访谈记录已更新。", "success")
        return redirect(url_for("expert_portfolio_page", expert=expert_id))

    @app.post("/expert-portfolio/experts/<expert_id>/interviews/<interview_id>/delete")
    def delete_expert_portfolio_interview(expert_id: str, interview_id: str):
        store = load_store()
        expert = _get_expert(store, expert_id)
        before = len(expert.get("interviews", []))
        expert["interviews"] = [
            item for item in expert.get("interviews", []) if item.get("id") != interview_id
        ]
        if len(expert["interviews"]) == before:
            abort(404)
        expert["updated_at"] = now_iso()
        save_store(store)
        flash("访谈记录已删除。", "success")
        return redirect(url_for("expert_portfolio_page", expert=expert_id))

    @app.get("/expert-portfolio/experts/<expert_id>/interviews/<interview_id>/summary")
    def get_expert_portfolio_interview_summary(expert_id: str, interview_id: str):
        store = load_store()
        expert = _get_expert(store, expert_id)
        interview = _get_interview(expert, interview_id)
        return jsonify(summary_response(expert, interview))

    @app.post("/expert-portfolio/experts/<expert_id>/interviews/<interview_id>/summary/generate")
    def generate_expert_portfolio_interview_summary(expert_id: str, interview_id: str):
        payload = request.get_json(silent=True) or {}
        force = payload.get("force") is True or str(request.form.get("force") or "").lower() in {
            "1", "true", "yes", "on"
        }
        queued, message = queue_summary_job(expert_id, interview_id, force=force)
        store = load_store()
        expert = _get_expert(store, expert_id)
        interview = _get_interview(expert, interview_id)
        response_payload = summary_response(expert, interview)
        response_payload["message"] = message
        if queued or response_payload["status"] in {"queued", "generating"}:
            return jsonify(response_payload), 202
        if response_payload["status"] == "ready":
            return jsonify(response_payload)
        return jsonify(response_payload), 409

    @app.post("/expert-portfolio/interview-summaries/backfill")
    def backfill_expert_portfolio_interview_summaries():
        store = load_store()
        queued_count = 0
        skipped_count = 0
        for expert in store.get("experts", []):
            expert_id = str(expert.get("id") or "")
            for interview in expert.get("interviews", []):
                interview_id = str(interview.get("id") or "")
                if not expert_id or not interview_id or not interview.get("transcript_id"):
                    continue
                queued, _ = queue_summary_job(expert_id, interview_id, force=False)
                if queued:
                    queued_count += 1
                else:
                    skipped_count += 1
        return jsonify(
            {
                "ok": True,
                "queued": queued_count,
                "skipped": skipped_count,
                "message": f"已加入 {queued_count} 条摘要任务，跳过 {skipped_count} 条。",
            }
        ), 202 if queued_count else 200

    @app.post("/expert-portfolio/experts/<expert_id>/field")
    def update_expert_portfolio_field(expert_id: str):
        payload = request.get_json(silent=True) or {}
        field = _clean_text(payload.get("field"), limit=80)
        allowed_fields = {"main_company", "category", "status"}
        if field not in allowed_fields:
            return jsonify({"ok": False, "message": "不支持修改这个字段。"}), 400
        store = load_store()
        expert = _get_expert(store, expert_id)
        value = _clean_text(payload.get("value"), limit=180)
        if field == "status" and value not in STATUS_META:
            return jsonify({"ok": False, "message": "状态值无效。"}), 400
        if field == "category":
            value = value or "未分类"
            if value not in store.setdefault("categories", list(DEFAULT_CATEGORIES)):
                store["categories"].append(value)
        expert[field] = value
        expert["updated_at"] = now_iso()
        save_store(store)
        return jsonify({"ok": True, "message": "已保存", "expert": expert, "stats": _build_context(store)["portfolio_stats"]})

    @app.post("/expert-portfolio/experts/<expert_id>/delete")
    def delete_expert_portfolio_entry(expert_id: str):
        store = load_store()
        expert = _get_expert(store, expert_id)
        store["experts"] = [item for item in store.get("experts", []) if item.get("id") != expert_id]
        save_store(store)
        flash(f'专家“{expert["name"]}”已从专家组合中删除。', "success")
        return redirect(url_for("expert_portfolio_page"))

    @app.post("/expert-portfolio/categories")
    def update_expert_portfolio_categories():
        store = load_store()
        action = _clean_text(request.form.get("action"), limit=20)
        categories = store.setdefault("categories", list(DEFAULT_CATEGORIES))
        if action == "add":
            new_name = _clean_text(request.form.get("new_name"), limit=120)
            if new_name and new_name not in categories:
                categories.append(new_name)
                flash(f'分类“{new_name}”已添加。', "success")
        elif action == "rename":
            old_name = _clean_text(request.form.get("old_name"), limit=120)
            new_name = _clean_text(request.form.get("new_name"), limit=120)
            if old_name in categories and new_name:
                categories[categories.index(old_name)] = new_name
                for expert in store.get("experts", []):
                    if expert.get("category") == old_name:
                        expert["category"] = new_name
                flash(f'分类“{old_name}”已改名为“{new_name}”。', "success")
        elif action == "delete":
            old_name = _clean_text(request.form.get("old_name"), limit=120)
            if old_name and old_name != "未分类" and old_name in categories:
                categories.remove(old_name)
                for expert in store.get("experts", []):
                    if expert.get("category") == old_name:
                        expert["category"] = "未分类"
                flash(f'分类“{old_name}”已删除，相关专家移至“未分类”。', "success")
        save_store(store)
        return redirect(url_for("expert_portfolio_page"))

    @app.get("/expert-portfolio/export.json")
    def export_expert_portfolio_json():
        payload = json.dumps(load_store(), ensure_ascii=False, indent=2).encode("utf-8")
        return send_file(
            BytesIO(payload),
            mimetype="application/json; charset=utf-8",
            as_attachment=True,
            download_name="专家组合备份.json",
        )

    @app.get("/expert-portfolio/interview-quota.xlsx")
    def export_expert_portfolio_interview_quota():
        timestamp = now_iso()
        workbook_bytes, _ = build_interview_quota_workbook(load_store().get("experts", []))
        date_label = (timestamp[:10] or "export").replace("-", "")
        return send_file(
            BytesIO(workbook_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"访谈配额进度_{date_label}.xlsx",
        )

    @app.post("/expert-portfolio/import.json")
    def import_expert_portfolio_json():
        uploaded = request.files.get("portfolio_json")
        if uploaded is None or not uploaded.filename:
            flash("请选择 JSON 文件。", "error")
            return redirect(url_for("expert_portfolio_page"))
        try:
            raw_payload = json.loads(uploaded.read().decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            flash(f"JSON 文件无法读取：{exc}", "error")
            return redirect(url_for("expert_portfolio_page"))

        incoming_store = normalize_expert_portfolio_store(raw_payload, now_iso=now_iso())
        mode = _clean_text(request.form.get("mode"), limit=20)
        if mode == "replace":
            save_store(incoming_store)
            flash(f'已用导入文件替换专家组合，共 {len(incoming_store["experts"])} 位专家。', "success")
        else:
            store = load_store()
            for category in incoming_store.get("categories", []):
                if category not in store.setdefault("categories", []):
                    store["categories"].append(category)
            added, merged, errors = _merge_experts(store, incoming_store.get("experts", []), now_iso=now_iso())
            save_store(store)
            message = f"JSON 导入完成：新增 {added} 位，合并 {merged} 位。"
            if errors:
                message += f" 跳过 {len(errors)} 条无效记录。"
            flash(message, "success")
        return redirect(url_for("expert_portfolio_page"))

    @app.post("/expert-portfolio/intake/import")
    def import_expert_intake_profiles():
        payload = request.get_json(silent=True) or {}
        incoming = payload.get("experts")
        if not isinstance(incoming, list) or not incoming:
            return jsonify({"ok": False, "message": "没有可导入的专家预览。"}), 400
        store = load_store()
        added, merged, errors = _merge_experts(store, incoming[:20], now_iso=now_iso())
        if not added and not merged:
            return jsonify({"ok": False, "message": "预览中没有有效的专家姓名。", "errors": errors}), 400
        save_store(store)
        return jsonify(
            {
                "ok": True,
                "added": added,
                "merged": merged,
                "errors": errors,
                "message": f"智能录入完成：新增 {added} 位，合并 {merged} 位。",
                "redirect_url": url_for("expert_portfolio_page"),
            }
        )
