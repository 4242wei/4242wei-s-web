from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_SCAN_SECONDS = 4 * 60 * 60
MIN_SCAN_SECONDS = 15 * 60


def _clean(value: Any, limit: int = 500) -> str:
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()[:limit]


def _blob(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_blob(value: Any) -> str:
    return _blob(value).replace(" ", "")


def _date_key(value: Any) -> str:
    text = _clean(value, 80)
    match = re.search(r"(20\d{2})[-./年]?([01]\d)[-./月]?([0-3]\d)", text)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _company_aliases(expert: dict[str, Any]) -> list[str]:
    source = " | ".join(
        _clean(expert.get(key), 240)
        for key in ("current_employer", "main_company")
        if _clean(expert.get(key), 240)
    )
    aliases: list[str] = []
    for item in [source, *re.split(r"[|/／()（）]+", source)]:
        normalized = _blob(item)
        if len(normalized.replace(" ", "")) >= 3 and normalized not in aliases:
            aliases.append(normalized)
    return aliases[:10]


def _interview_datetime(interview: dict[str, Any]) -> datetime | None:
    value = _clean(interview.get("occurred_at") or interview.get("display_time"), 100)
    date_key = _date_key(value)
    if not date_key:
        return None
    time_match = re.search(r"(?:T|\s)([0-2]\d)[:.]([0-5]\d)", value)
    hour = int(time_match.group(1)) if time_match else 12
    minute = int(time_match.group(2)) if time_match else 0
    try:
        return datetime.fromisoformat(f"{date_key}T{hour:02d}:{minute:02d}")
    except ValueError:
        return None


def interview_sequence_map(expert: dict[str, Any]) -> dict[str, int]:
    interviews = [
        item
        for item in expert.get("interviews", [])
        if isinstance(item, dict) and _clean(item.get("status"), 40) != "cancelled"
    ]
    ordered = sorted(
        interviews,
        key=lambda item: (
            _interview_datetime(item) or datetime.max,
            _clean(item.get("created_at"), 50),
            _clean(item.get("id"), 80),
        ),
    )
    return {
        _clean(item.get("id"), 80): index
        for index, item in enumerate(ordered, start=1)
        if _clean(item.get("id"), 80)
    }


def _transcript_fingerprint(transcript: dict[str, Any]) -> str:
    original = _blob(transcript.get("original_name") or transcript.get("title"))
    date_key = _date_key(transcript.get("meeting_date") or transcript.get("created_at"))
    size = _clean(transcript.get("source_file_size"), 30)
    return "|".join([date_key, original, size]) if original else ""


def scan_seconds() -> int:
    raw = os.getenv("EXPERT_LINK_SCAN_SECONDS", str(DEFAULT_SCAN_SECONDS))
    try:
        configured = int(raw)
    except (TypeError, ValueError):
        configured = DEFAULT_SCAN_SECONDS
    return max(MIN_SCAN_SECONDS, configured)


def _match_experts(transcript: dict[str, Any], experts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _blob(
        " ".join(
            [
                _clean(transcript.get("title"), 240),
                _clean(transcript.get("original_name"), 240),
            ]
        )
    )
    compact_text = text.replace(" ", "")
    candidates: list[dict[str, Any]] = []
    for expert in experts:
        expert_id = _clean(expert.get("id"), 80)
        name = _blob(expert.get("name"))
        aliases = _company_aliases(expert)
        compact_name = name.replace(" ", "")
        name_match = bool(name and len(compact_name) >= 4 and (name in text or compact_name in compact_text))
        company_matches = [
            alias
            for alias in aliases
            if alias in text or (len(alias.replace(" ", "")) >= 3 and alias.replace(" ", "") in compact_text)
        ]
        if not name_match and not company_matches:
            continue
        candidates.append(
            {
                "expert": expert,
                "expert_id": expert_id,
                "name_match": name_match,
                "company_matches": company_matches,
                "score": (100 if name_match else 0) + min(40, len(company_matches) * 20),
            }
        )
    if not candidates:
        return []
    top_score = max(item["score"] for item in candidates)
    return [item for item in candidates if item["score"] == top_score and item["expert_id"]]


def _load_provider(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    providers = payload.get("providers") if isinstance(payload, dict) else None
    provider = providers.get("deepseek") if isinstance(providers, dict) else None
    return provider if isinstance(provider, dict) and provider.get("enabled") is not False else {}


def _model_suggest(
    transcript: dict[str, Any],
    candidates: list[dict[str, Any]],
    provider_config_path: Path,
    *,
    http_post=requests.post,
) -> dict[str, Any] | None:
    config = _load_provider(provider_config_path)
    key_env = _clean(config.get("api_key_env"), 120)
    api_key = os.getenv(key_env, "").strip() if key_env else ""
    base_url = _clean(config.get("base_url"), 500).rstrip("/")
    chat_path = _clean(config.get("chat_path"), 200).lstrip("/") or "chat/completions"
    model = _clean(config.get("model"), 160)
    if not api_key or not base_url.startswith("https://") or not model or not candidates:
        return None
    safe_source = {
        "title": _clean(transcript.get("title"), 240),
        "original_name": _clean(transcript.get("original_name"), 240),
        "meeting_date": _date_key(transcript.get("meeting_date") or transcript.get("created_at")),
    }
    safe_candidates = [
        {
            "expert_id": _clean(item.get("id"), 80),
            "name": _clean(item.get("name"), 160),
            "company": _clean(item.get("current_employer") or item.get("main_company"), 220),
        }
        for item in candidates[:12]
    ]
    prompt = (
        "核对这条语音转录文件名是否明确属于某位候选专家。只允许使用标题中的姓名、公司或明确缩写；"
        "不得凭日期或常识猜测。只输出 JSON：expert_id、confidence、evidence。evidence 必须逐字来自标题或原文件名。"
        f"\n转录：{json.dumps(safe_source, ensure_ascii=False)}"
        f"\n候选：{json.dumps(safe_candidates, ensure_ascii=False)}"
    )
    try:
        response = http_post(
            f"{base_url}/{chat_path}",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是只读访谈资料匹配器。不得创建、修改或删除记录。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
                "max_tokens": 300,
                "stream": False,
                "response_format": {"type": "json_object"},
                "thinking": {"type": "disabled"},
            },
            timeout=(8, 30),
        )
        if response.status_code >= 400:
            return None
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", _clean(content, 4000), flags=re.I)
        result = json.loads(content)
    except (requests.RequestException, ValueError, KeyError, IndexError, AttributeError):
        return None
    candidate_ids = {item["expert_id"] for item in safe_candidates if item["expert_id"]}
    expert_id = _clean(result.get("expert_id"), 80) if isinstance(result, dict) else ""
    evidence = _clean(result.get("evidence"), 240) if isinstance(result, dict) else ""
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError, AttributeError):
        confidence = 0.0
    source_blob = _compact_blob(" ".join([safe_source["title"], safe_source["original_name"]]))
    if expert_id not in candidate_ids or confidence < 0.90 or not evidence or _compact_blob(evidence) not in source_blob:
        return None
    return {"expert_id": expert_id, "confidence": min(1.0, confidence), "evidence": evidence}


def build_link_scan(
    experts: list[dict[str, Any]],
    transcripts: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    provider_config_path: Path | None = None,
    allow_model: bool = True,
    http_post=requests.post,
) -> dict[str, Any]:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    linked_by_transcript: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    sequence_by_expert: dict[str, dict[str, int]] = {}
    for expert in experts:
        expert_id = _clean(expert.get("id"), 80)
        sequence_by_expert[expert_id] = interview_sequence_map(expert)
        for interview in expert.get("interviews", []):
            if not isinstance(interview, dict):
                continue
            transcript_id = _clean(interview.get("transcript_id"), 80)
            if transcript_id:
                linked_by_transcript[transcript_id] = (expert, interview)

    primary_by_fingerprint: dict[str, str] = {}
    transcript_by_id = {
        _clean(item.get("id"), 80): item
        for item in transcripts
        if isinstance(item, dict) and _clean(item.get("id"), 80)
    }
    ordered_ids = sorted(
        transcript_by_id,
        key=lambda item_id: (0 if item_id in linked_by_transcript else 1, item_id),
    )
    duplicate_of: dict[str, str] = {}
    for transcript_id in ordered_ids:
        fingerprint = _transcript_fingerprint(transcript_by_id[transcript_id])
        if not fingerprint:
            continue
        if fingerprint in primary_by_fingerprint:
            duplicate_of[transcript_id] = primary_by_fingerprint[fingerprint]
        else:
            primary_by_fingerprint[fingerprint] = transcript_id

    results: list[dict[str, Any]] = []
    actions: list[dict[str, str | int]] = []
    for transcript_id, transcript in transcript_by_id.items():
        title = _clean(transcript.get("title") or transcript.get("original_name"), 240) or "未命名转录"
        meeting_date = _date_key(transcript.get("meeting_date") or transcript.get("created_at") or title)
        if transcript_id in linked_by_transcript:
            expert, interview = linked_by_transcript[transcript_id]
            expert_id = _clean(expert.get("id"), 80)
            interview_id = _clean(interview.get("id"), 80)
            results.append(
                {
                    "transcript_id": transcript_id,
                    "title": title,
                    "meeting_date": meeting_date,
                    "status": "linked",
                    "expert_id": expert_id,
                    "expert_name": _clean(expert.get("name"), 160),
                    "interview_id": interview_id,
                    "interview_sequence": sequence_by_expert.get(expert_id, {}).get(interview_id, 0),
                    "confidence": 1.0,
                    "evidence": "已有访谈记录已关联",
                }
            )
            continue
        if transcript_id in duplicate_of:
            primary_id = duplicate_of[transcript_id]
            primary_link = linked_by_transcript.get(primary_id)
            results.append(
                {
                    "transcript_id": transcript_id,
                    "title": title,
                    "meeting_date": meeting_date,
                    "status": "duplicate_transcript",
                    "duplicate_of_transcript_id": primary_id,
                    "expert_id": _clean((primary_link or ({}, {}))[0].get("id"), 80),
                    "interview_id": _clean((primary_link or ({}, {}))[1].get("id"), 80),
                    "confidence": 1.0,
                    "evidence": "同日期、同原始文件名和文件大小",
                }
            )
            continue

        candidates = _match_experts(transcript, experts)
        model_match: dict[str, Any] | None = None
        if len(candidates) > 1 and provider_config_path is not None and allow_model:
            # Local normalization found several equally plausible records.  A
            # model may narrow these to one review suggestion, but can never
            # produce an automatic write action.
            model_match = _model_suggest(
                transcript,
                [item["expert"] for item in candidates],
                provider_config_path,
                http_post=http_post,
            )
            if model_match:
                candidates = [item for item in candidates if item["expert_id"] == model_match["expert_id"]]
        elif not candidates and meeting_date and provider_config_path is not None and allow_model:
            dated_candidates = [
                expert
                for expert in experts
                if any(
                    isinstance(interview, dict)
                    and not _clean(interview.get("transcript_id"), 80)
                    and _date_key(interview.get("occurred_at") or interview.get("display_time")) == meeting_date
                    for interview in expert.get("interviews", [])
                )
            ]
            model_match = _model_suggest(
                transcript,
                dated_candidates,
                provider_config_path,
                http_post=http_post,
            )
            if model_match:
                model_expert = next(
                    (item for item in dated_candidates if _clean(item.get("id"), 80) == model_match["expert_id"]),
                    None,
                )
                if model_expert:
                    candidates = [
                        {
                            "expert": model_expert,
                            "expert_id": model_match["expert_id"],
                            "name_match": False,
                            "company_matches": [],
                            "score": 1,
                        }
                    ]
        if len(candidates) != 1:
            results.append(
                {
                    "transcript_id": transcript_id,
                    "title": title,
                    "meeting_date": meeting_date,
                    "status": "pending_review" if candidates else "unmatched",
                    "confidence": 0.0,
                    "evidence": "多个专家候选" if candidates else "文件名未唯一命中专家姓名或公司",
                }
            )
            continue

        candidate = candidates[0]
        expert = candidate["expert"]
        expert_id = candidate["expert_id"]
        dated_interviews = [
            item
            for item in expert.get("interviews", [])
            if isinstance(item, dict)
            and meeting_date
            and _date_key(item.get("occurred_at") or item.get("display_time")) == meeting_date
        ]
        empty_interviews = [item for item in dated_interviews if not _clean(item.get("transcript_id"), 80)]
        confidence = float(model_match.get("confidence", 0)) if model_match else (1.0 if candidate["name_match"] else 0.96)
        evidence = _clean(model_match.get("evidence"), 240) if model_match else ("专家姓名＋日期" if candidate["name_match"] else "唯一公司＋日期")
        status = "suggested"
        interview_id = ""
        sequence = 0
        if not model_match and len(empty_interviews) == 1 and len(dated_interviews) == 1:
            interview_id = _clean(empty_interviews[0].get("id"), 80)
            sequence = sequence_by_expert.get(expert_id, {}).get(interview_id, 0)
            status = "safe_auto_link"
            actions.append(
                {
                    "transcript_id": transcript_id,
                    "expert_id": expert_id,
                    "interview_id": interview_id,
                    "interview_sequence": sequence,
                }
            )
        elif model_match and len(empty_interviews) == 1 and len(dated_interviews) == 1:
            interview_id = _clean(empty_interviews[0].get("id"), 80)
            sequence = sequence_by_expert.get(expert_id, {}).get(interview_id, 0)
            status = "suggested"
            evidence = f"DeepSeek 核对：{evidence}"
        elif len(dated_interviews) > 1:
            status = "pending_review"
            evidence = "同日存在多条访谈记录，不能自动选择"
        elif not dated_interviews:
            status = "suggested_new_interview"
            sequence = 1 + sum(
                1
                for item in expert.get("interviews", [])
                if (_interview_datetime(item) or datetime.max).date()
                <= (datetime.fromisoformat(meeting_date).date() if meeting_date else datetime.min.date())
            )
        results.append(
            {
                "transcript_id": transcript_id,
                "title": title,
                "meeting_date": meeting_date,
                "status": status,
                "expert_id": expert_id,
                "expert_name": _clean(expert.get("name"), 160),
                "expert_company": _clean(expert.get("current_employer") or expert.get("main_company"), 220),
                "interview_id": interview_id,
                "interview_sequence": sequence,
                "confidence": confidence,
                "evidence": evidence,
            }
        )

    # Suggested new records participate in the same chronological sequence as
    # existing interviews.  This is display metadata only: suggestions never
    # create or modify a portfolio record.
    suggested_by_expert: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        if item.get("status") == "suggested_new_interview" and item.get("expert_id") and item.get("meeting_date"):
            suggested_by_expert.setdefault(str(item["expert_id"]), []).append(item)
    for expert_id, suggestions in suggested_by_expert.items():
        expert = next((item for item in experts if _clean(item.get("id"), 80) == expert_id), {})
        existing_dates = sorted(
            interview_time.date()
            for interview in expert.get("interviews", [])
            if isinstance(interview, dict)
            and _clean(interview.get("status"), 40) != "cancelled"
            and (interview_time := _interview_datetime(interview)) is not None
        )
        suggestion_dates = sorted({datetime.fromisoformat(str(item["meeting_date"])).date() for item in suggestions})
        timeline = sorted({*existing_dates, *suggestion_dates})
        for item in suggestions:
            suggestion_date = datetime.fromisoformat(str(item["meeting_date"])).date()
            item["interview_sequence"] = timeline.index(suggestion_date) + 1

    return {
        "version": 1,
        "status": "ready",
        "message": "语音转录关联已核对",
        "last_checked_at": reference.isoformat(),
        "transcript_count": len(results),
        "linked_count": sum(1 for item in results if item["status"] == "linked"),
        "suggestion_count": sum(1 for item in results if item["status"] in {"suggested", "suggested_new_interview", "safe_auto_link"}),
        "duplicate_count": sum(1 for item in results if item["status"] == "duplicate_transcript"),
        "results": results,
        "actions": actions,
    }


def apply_safe_links(experts: list[dict[str, Any]], actions: list[dict[str, Any]], *, now_iso: str) -> list[dict[str, Any]]:
    expert_by_id = {_clean(item.get("id"), 80): item for item in experts}
    used_transcripts = {
        _clean(interview.get("transcript_id"), 80)
        for expert in experts
        for interview in expert.get("interviews", [])
        if isinstance(interview, dict) and _clean(interview.get("transcript_id"), 80)
    }
    applied: list[dict[str, Any]] = []
    for action in actions:
        transcript_id = _clean(action.get("transcript_id"), 80)
        expert = expert_by_id.get(_clean(action.get("expert_id"), 80))
        if not transcript_id or transcript_id in used_transcripts or not expert:
            continue
        interview = next(
            (
                item
                for item in expert.get("interviews", [])
                if isinstance(item, dict) and _clean(item.get("id"), 80) == _clean(action.get("interview_id"), 80)
            ),
            None,
        )
        if not interview or _clean(interview.get("transcript_id"), 80):
            continue
        interview["transcript_id"] = transcript_id
        interview["updated_at"] = now_iso
        expert["updated_at"] = now_iso
        used_transcripts.add(transcript_id)
        applied.append(dict(action))
    return applied


def cache_fresh(cache: dict[str, Any], *, now: datetime | None = None) -> bool:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        checked = datetime.fromisoformat(_clean(cache.get("last_checked_at"), 60))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return reference - checked.astimezone(timezone.utc) < timedelta(seconds=scan_seconds())


def load_link_cache(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_link_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)
