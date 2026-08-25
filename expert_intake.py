from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests

from region_normalization import normalize_region_label


MAX_SOURCE_CHARS = 40_000
MAX_EXPERTS_PER_PARSE = 20


class ExpertIntakeError(RuntimeError):
    """A safe, user-facing expert intake error."""


EXPERT_JSON_EXAMPLE = {
    "experts": [
        {
            "name": "",
            "vendors": [],
            "vendor_index": {},
            "current_title": "",
            "current_employer": "",
            "main_company": "",
            "category": "未分类",
            "industry": "",
            "company_scale": "",
            "region": "",
            "source_record_id": "",
            "description": "",
            "job_history": [{"title": "", "company": "", "dates": ""}],
            "status": "not-reviewed",
            "notes": "",
            "expert_comment": "",
            "research_feedback": "",
            "future_tracking": "",
            "data_quality_status": "needs-review",
            "source_label": "智能录入",
            "source_emails": [],
            "duplicate_note": "",
        }
    ],
    "warnings": [],
}


SYSTEM_PROMPT = """你是研究机构的专家资料结构化助手。把用户提供的原始专家信息转换为 JSON。
要求：
1. 只能提取原文明确支持的信息，不得猜测姓名、公司、职位、地区、时间、费率或状态。
2. 原文存在转录错误、冲突或不确定信息时，不要擅自纠正或猜测；只写入 warnings，专家字段保持原文明确支持的内容。
3. 可识别多位专家；每位专家一个对象。没有信息的字段使用空字符串、空数组或空对象。
4. status 固定使用 not-reviewed（前端显示“待审核”）；data_quality_status 固定使用 needs-review，必须由人确认后才能入库。
5. category 不确定时使用“未分类”。job_history 必须是 title/company/dates 对象数组。
6. expert_comment 只记录原文明确属于专家的引述、观点或 Comment，尽量忠实保留原意和措辞；不得补充、推断、评价或添加 AI 自己的评论。
7. description 只写客观履历与身份信息。所有专家字段都禁止出现“AI认为”“可能说明”等模型评论。
8. 遇到“#12【金融-大型-非洲】”格式时，依次提取 source_record_id、industry、company_scale、region；Base 是具体所在地，不能覆盖方括号中的地区分类。
9. region 使用稳定的地区分类，不要把城市和国家混写；例如 Boston, USA、USA、United States 统一为“美国”。若原文已有方括号地区分类，以该分类为准。
10. Language、Rate、Availability 等没有独立字段的客观信息逐行放入 notes，保留原标签和值。
11. 只输出 JSON，不要 Markdown，不要解释。JSON 结构示例：
""" + json.dumps(EXPERT_JSON_EXAMPLE, ensure_ascii=False)


def _clean_text(value: Any, limit: int = 12_000) -> str:
    return str(value or "").strip()[:limit]


def _clean_string_list(value: Any, *, max_items: int = 30) -> list[str]:
    raw = value if isinstance(value, list) else re.split(r"[,，;；\n]+", str(value or ""))
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = _clean_text(item, 240)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
        if len(result) >= max_items:
            break
    return result


def _normalize_job_history(value: Any) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = {
            "title": _clean_text(item.get("title"), 220),
            "company": _clean_text(item.get("company"), 220),
            "dates": _clean_text(item.get("dates"), 120),
        }
        if any(normalized.values()):
            result.append(normalized)
        if len(result) >= 80:
            break
    return result


def _extract_line_value(block: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", block)
    return _clean_text(match.group(1), 500) if match else ""


def _extract_labeled_section(block: str, label: str, stop_labels: tuple[str, ...]) -> str:
    stops = "|".join(re.escape(item) for item in stop_labels)
    pattern = rf"(?ims)^\s*[【\[]?{re.escape(label)}[】\]]?\s*:\s*(.*?)(?=^\s*[【\[]?(?:{stops})[】\]]?\s*:|\Z)"
    match = re.search(pattern, block)
    return _clean_text(match.group(1), 12_000) if match else ""


def extract_source_hints(source_text: str) -> list[dict[str, str]]:
    """Read stable labels locally so the model cannot drop or reinterpret them."""
    header_pattern = re.compile(r"(?m)^\s*#\s*(\d+)\s*【([^】]+)】\s*$")
    matches = list(header_pattern.finditer(source_text))
    hints: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(source_text)
        block = source_text[match.end():block_end]
        categories = [item.strip() for item in re.split(r"\s*[-—–]\s*", match.group(2))]
        comment = _extract_labeled_section(block, "Comment", ("Availability",))
        availability = _extract_labeled_section(block, "Availability", ("Comment",))
        hints.append(
            {
                "source_record_id": f"#{match.group(1)}",
                "industry": categories[0] if len(categories) > 0 else "",
                "company_scale": categories[1] if len(categories) > 1 else "",
                "region": categories[2] if len(categories) > 2 else "",
                "base": _extract_line_value(block, "Base"),
                "language": _extract_line_value(block, "Language"),
                "rate": _extract_line_value(block, "Rate"),
                "availability": availability,
                "expert_comment": comment,
            }
        )
    return hints


def apply_source_hints(experts: list[dict[str, Any]], source_text: str) -> list[dict[str, Any]]:
    hints = extract_source_hints(source_text)
    if not hints:
        return experts
    by_record_id = {hint["source_record_id"]: hint for hint in hints}
    for index, expert in enumerate(experts):
        hint = by_record_id.get(_clean_text(expert.get("source_record_id"), 80))
        if hint is None and index < len(hints):
            hint = hints[index]
        if hint is None:
            continue
        for field in ("source_record_id", "industry", "company_scale", "region"):
            if hint.get(field):
                expert[field] = (
                    normalize_region_label(hint[field])
                    if field == "region"
                    else hint[field]
                )
        if hint.get("expert_comment"):
            expert["expert_comment"] = hint["expert_comment"]
        objective_lines = [
            f"Base: {hint['base']}" if hint.get("base") else "",
            f"Language: {hint['language']}" if hint.get("language") else "",
            f"Rate: {hint['rate']}" if hint.get("rate") else "",
            f"Availability: {hint['availability']}" if hint.get("availability") else "",
        ]
        notes = _clean_text(expert.get("notes"), 8_000)
        for line in objective_lines:
            if line and line.casefold() not in notes.casefold():
                notes = f"{notes}\n{line}".strip()
        expert["notes"] = notes
    return experts


def normalize_intake_expert(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    name = _clean_text(value.get("name"), 160)
    if not name:
        return None
    vendor_index = value.get("vendor_index") if isinstance(value.get("vendor_index"), dict) else {}
    return {
        "name": name,
        "vendors": _clean_string_list(value.get("vendors")),
        "vendor_index": {
            _clean_text(key, 80): _clean_text(item, 80)
            for key, item in list(vendor_index.items())[:20]
            if _clean_text(key, 80) and _clean_text(item, 80)
        },
        "current_title": _clean_text(value.get("current_title"), 220),
        "current_employer": _clean_text(value.get("current_employer"), 220),
        "main_company": _clean_text(value.get("main_company"), 180),
        "category": _clean_text(value.get("category"), 120) or "未分类",
        "industry": _clean_text(value.get("industry"), 120),
        "company_scale": _clean_text(value.get("company_scale"), 80),
        "region": normalize_region_label(_clean_text(value.get("region"), 120)),
        "source_record_id": _clean_text(value.get("source_record_id"), 80),
        "description": _clean_text(value.get("description"), 12_000),
        "job_history": _normalize_job_history(value.get("job_history")),
        "status": "not-reviewed",
        "notes": _clean_text(value.get("notes"), 8_000),
        "expert_comment": _clean_text(value.get("expert_comment"), 12_000),
        "research_feedback": _clean_text(value.get("research_feedback"), 8_000),
        "future_tracking": _clean_text(value.get("future_tracking"), 8_000),
        "data_quality_status": "needs-review",
        "data_quality_notes": "",
        "source_label": _clean_text(value.get("source_label"), 240) or "智能录入",
        "source_emails": _clean_string_list(value.get("source_emails")),
        "duplicate_note": _clean_text(value.get("duplicate_note"), 1_200),
    }


def load_provider_config(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExpertIntakeError("专家智能录入的接口配置文件不存在。") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ExpertIntakeError("专家智能录入的接口配置文件无法读取。") from exc
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, dict):
        raise ExpertIntakeError("专家智能录入的接口配置格式不正确。")
    return {str(key): value for key, value in providers.items() if isinstance(value, dict)}


def provider_catalog(path: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for provider_id, config in load_provider_config(path).items():
        if config.get("enabled") is False:
            continue
        key_env = _clean_text(config.get("api_key_env"), 120)
        reasoning_efforts = [
            item
            for item in _clean_string_list(config.get("reasoning_efforts"), max_items=8)
            if item in {"low", "medium", "high", "xhigh", "max"}
        ]
        result.append(
            {
                "id": provider_id,
                "label": _clean_text(config.get("label"), 120) or provider_id,
                "adapter": _clean_text(config.get("adapter"), 80) or "openai_compatible",
                "model": _clean_text(config.get("model"), 160),
                "configured": bool(key_env and os.getenv(key_env, "").strip()),
                "supports_thinking": config.get("supports_thinking") is True,
                "default_thinking": _clean_text(config.get("thinking"), 20).lower() == "enabled",
                "reasoning_efforts": reasoning_efforts,
                "default_reasoning_effort": _clean_text(config.get("reasoning_effort"), 20).lower()
                if _clean_text(config.get("reasoning_effort"), 20).lower() in reasoning_efforts
                else (reasoning_efforts[0] if reasoning_efforts else ""),
            }
        )
    return result


def _json_from_model_text(value: Any) -> dict[str, Any]:
    text = _clean_text(value, 100_000)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExpertIntakeError("模型返回的不是有效 JSON，请重试或更换模型。") from exc
    if isinstance(payload, list):
        payload = {"experts": payload, "warnings": []}
    if not isinstance(payload, dict):
        raise ExpertIntakeError("模型返回结构不正确。")
    return payload


def _deep_get(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _openai_compatible_parse(
    config: dict[str, Any],
    source_text: str,
    *,
    http_post: Callable[..., Any] = requests.post,
) -> tuple[dict[str, Any], dict[str, Any]]:
    key_env = _clean_text(config.get("api_key_env"), 120)
    api_key = os.getenv(key_env, "").strip() if key_env else ""
    if not api_key:
        raise ExpertIntakeError(f"接口尚未配置密钥，请先设置 {key_env or 'API Key 环境变量'}。")
    base_url = _clean_text(config.get("base_url"), 500).rstrip("/") + "/"
    endpoint = _clean_text(config.get("chat_path"), 200) or "chat/completions"
    model = _clean_text(config.get("model"), 160)
    if not base_url.startswith("https://") or not model:
        raise ExpertIntakeError("接口配置缺少有效的 HTTPS 地址或模型名。")
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": source_text},
        ],
        "temperature": float(config.get("temperature", 0.1)),
        "max_tokens": int(config.get("max_tokens", 6000)),
        "stream": False,
    }
    if config.get("json_mode", True):
        payload["response_format"] = {"type": "json_object"}
    thinking_mode = _clean_text(config.get("thinking"), 20).lower()
    if thinking_mode in {"enabled", "disabled"}:
        payload["thinking"] = {"type": thinking_mode}
    reasoning_effort = _clean_text(config.get("reasoning_effort"), 20).lower()
    if thinking_mode == "enabled" and reasoning_effort in {"low", "medium", "high", "xhigh", "max"}:
        payload["reasoning_effort"] = reasoning_effort
    timeout = max(10, min(int(config.get("timeout_seconds", 75)), 180))
    try:
        response = http_post(
            urljoin(base_url, endpoint.lstrip("/")),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=(10, timeout),
        )
    except requests.RequestException as exc:
        raise ExpertIntakeError("模型接口连接失败；专家数据没有被修改。") from exc
    if response.status_code >= 400:
        messages = {
            401: "API Key 无效或没有权限。",
            402: "接口余额不足。",
            429: "接口请求过于频繁，请稍后重试。",
            500: "模型服务暂时异常。",
            503: "模型服务当前繁忙。",
        }
        raise ExpertIntakeError(messages.get(response.status_code, f"模型接口返回错误（HTTP {response.status_code}）。"))
    try:
        response_payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ExpertIntakeError("模型接口响应无法解析。") from exc
    content_path = _clean_text(config.get("response_path"), 240) or "choices.0.message.content"
    model_payload = _json_from_model_text(_deep_get(response_payload, content_path))
    usage = response_payload.get("usage") if isinstance(response_payload, dict) else {}
    return model_payload, usage if isinstance(usage, dict) else {}


ADAPTERS: dict[str, Callable[..., tuple[dict[str, Any], dict[str, Any]]]] = {
    "openai_compatible": _openai_compatible_parse,
}


def register_provider_adapter(name: str, adapter: Callable[..., tuple[dict[str, Any], dict[str, Any]]]) -> None:
    """Allow a provider-specific adapter without changing the portfolio module."""
    ADAPTERS[str(name)] = adapter


def parse_expert_source(
    provider_config_path: Path,
    *,
    provider_id: str,
    source_text: str,
    thinking_mode: str = "",
    reasoning_effort: str = "",
    http_post: Callable[..., Any] = requests.post,
) -> dict[str, Any]:
    text = _clean_text(source_text, MAX_SOURCE_CHARS + 1)
    if len(text) < 10:
        raise ExpertIntakeError("请粘贴更完整的专家信息。")
    if len(text) > MAX_SOURCE_CHARS:
        raise ExpertIntakeError(f"单次输入不能超过 {MAX_SOURCE_CHARS:,} 个字符。")
    providers = load_provider_config(provider_config_path)
    config = providers.get(provider_id)
    if not config or config.get("enabled") is False:
        raise ExpertIntakeError("所选模型接口不存在或已停用。")
    config = dict(config)
    requested_thinking = _clean_text(thinking_mode, 20).lower()
    if config.get("supports_thinking") is True and requested_thinking in {"enabled", "disabled"}:
        config["thinking"] = requested_thinking
    allowed_efforts = {
        item
        for item in _clean_string_list(config.get("reasoning_efforts"), max_items=8)
        if item in {"low", "medium", "high", "xhigh", "max"}
    }
    requested_effort = _clean_text(reasoning_effort, 20).lower()
    if requested_effort in allowed_efforts:
        config["reasoning_effort"] = requested_effort
    adapter_name = _clean_text(config.get("adapter"), 80) or "openai_compatible"
    adapter = ADAPTERS.get(adapter_name)
    if adapter is None:
        raise ExpertIntakeError(f"尚未安装接口适配器：{adapter_name}")
    raw_payload, usage = adapter(config, text, http_post=http_post)
    raw_experts = raw_payload.get("experts")
    if isinstance(raw_experts, dict):
        raw_experts = [raw_experts]
    experts = [
        expert
        for item in (raw_experts if isinstance(raw_experts, list) else [])[:MAX_EXPERTS_PER_PARSE]
        if (expert := normalize_intake_expert(item)) is not None
    ]
    experts = apply_source_hints(experts, text)
    warnings = _clean_string_list(raw_payload.get("warnings"), max_items=50)
    if not experts:
        raise ExpertIntakeError("模型没有识别到包含姓名的专家资料；没有写入任何数据。")
    return {
        "experts": experts,
        "warnings": warnings,
        "usage": usage,
        "provider": {
            "id": provider_id,
            "label": _clean_text(config.get("label"), 120) or provider_id,
            "model": _clean_text(config.get("model"), 160),
        },
    }
