from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


REPORT_SUFFIXES = {".md", ".markdown"}
PREVIOUS_REPORT_MAX_CHARS = 16_000
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_WINDOW_DAYS = 7
MIN_SOURCE_SCAN_INTERVAL_HOURS = 6
X_TIMELINE_PAGE_SIZE = 40
X_TIMELINE_MAX_PAGES = 4

X_USER_BY_SCREEN_NAME_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}
X_USER_BY_SCREEN_NAME_FIELD_TOGGLES = {"withAuxiliaryUserLabels": False}
X_USER_TWEETS_FEATURES = {
    "rweb_video_screen_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": False,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": False,
    "responsive_web_enhance_cards_enabled": False,
}
X_USER_TWEETS_FIELD_TOGGLES = {
    "withAuxiliaryUserLabels": False,
    "withArticleRichContentState": True,
    "withArticlePlainText": False,
    "withArticleSummaryText": False,
    "withArticleVoiceOver": False,
    "withGrokAnalyze": False,
    "withDisallowedReplyControls": False,
}


@dataclass
class RunnerConfig:
    config_path: Path
    state_path: Path
    codex_path: str
    workdir: str
    timeout_seconds: int
    output_dir: Path
    prompt_dir: Path
    log_dir: Path
    trigger: str
    run_id: str
    meta_path: Path
    runtime_path: Path | None


def beijing_now() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Shanghai"))
    return datetime.now(timezone(timedelta(hours=8)))


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_runtime_status(meta_status: str) -> str:
    normalized = str(meta_status or "").strip().lower()
    if normalized == "success":
        return "completed"
    if normalized in {"timeout"}:
        return "timeout"
    if normalized in {"failed", "error"}:
        return "failed"
    return normalized or "idle"


def sync_runtime_snapshot(
    runtime_path: Path | None,
    *,
    run_id: str,
    source_ids: list[str],
    meta: dict[str, Any],
    meta_path: Path,
) -> None:
    if runtime_path is None:
        return

    current = load_json(runtime_path)
    current_run_id = str(current.get("run_id") or "").strip()
    if current_run_id and run_id and current_run_id != run_id:
        return

    report_path = str(meta.get("report_path") or current.get("report_path") or "").strip()
    runtime_status = resolve_runtime_status(str(meta.get("status") or ""))
    current.update(
        {
            "run_id": run_id or current_run_id,
            "status": runtime_status,
            "pid": 0,
            "source_ids": source_ids,
            "started_at": str(current.get("started_at") or meta.get("started_at") or "").strip(),
            "finished_at": str(meta.get("finished_at") or current.get("finished_at") or "").strip(),
            "report_path": report_path,
            "report_filename": Path(report_path).name if report_path else "",
            "meta_path": str(meta_path),
            "stdout_path": str(current.get("stdout_path") or meta.get("stdout_log_path") or "").strip(),
            "stderr_path": str(current.get("stderr_path") or meta.get("stderr_log_path") or "").strip(),
            "window_start": str(meta.get("window_start") or current.get("window_start") or "").strip(),
            "window_end": str(meta.get("window_end") or current.get("window_end") or "").strip(),
            "message": "信息监控结果已写入独立归档。" if runtime_status == "completed" else "",
            "error": str(meta.get("error_message") or "").strip(),
            "termination_requested": False,
        }
    )
    save_json(runtime_path, current)


def read_report_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def latest_previous_report(output_dir: Path) -> Path | None:
    candidates = [
        path for path in output_dir.iterdir() if path.is_file() and path.suffix.lower() in REPORT_SUFFIXES
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime_ns, reverse=True)
    return candidates[0]


def read_previous_report_excerpt(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    try:
        text = read_report_text(path)
    except OSError:
        return ""
    return text[-PREVIOUS_REPORT_MAX_CHARS:]


def discover_codex_path(preferred: str = "") -> str | None:
    candidates: list[Path] = []

    if preferred:
        preferred_path = Path(preferred)
        if preferred_path.exists():
            return str(preferred_path)
        preferred_which = shutil.which(preferred)
        if preferred_which:
            return preferred_which

    system_which = shutil.which("codex")
    if system_which:
        return system_which

    vscode_extensions = Path.home() / ".vscode" / "extensions"
    if vscode_extensions.exists():
        candidates.extend(
            sorted(
                vscode_extensions.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"),
                reverse=True,
            )
        )
        candidates.extend(
            sorted(
                vscode_extensions.glob("openai.chatgpt-*/bin/windows-arm64/codex.exe"),
                reverse=True,
            )
        )

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


def resolve_codex_path(preferred: str) -> str:
    found = discover_codex_path(preferred)
    if found:
        return found
    raise FileNotFoundError("Could not find codex.exe. Checked PATH and the local VS Code extension directory.")


def check_codex_login(codex_path: str) -> None:
    result = subprocess.run(
        [codex_path, "login", "status"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 or "Logged in" not in output:
        raise RuntimeError("Codex is not logged in. Run `codex login` first.")


def write_failure_report(report_path: Path, reason: str, *, trigger: str, created_at: str, sources: list[dict[str, Any]]) -> None:
    source_lines = "\n".join(
        [
            f"- {source.get('display_name') or source.get('handle') or source.get('query')}"
            for source in sources
        ]
    )
    report_path.write_text(
        (
            "# Signal Monitor Report\n\n"
            f"- Trigger: `{trigger}`\n"
            f"- Run time: {created_at}\n"
            "- Sources:\n"
            f"{source_lines or '- None'}\n"
            "- Result: failed\n\n"
            "Reason:\n"
            f"{reason}\n"
        ),
        encoding="utf-8",
    )


def build_report_stem(created_at: str, trigger: str) -> str:
    timestamp = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_signal_{trigger}"


def parse_timestamp(raw_value: str) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        try:
            value = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if value.tzinfo is None:
        if ZoneInfo is not None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        else:
            value = value.replace(tzinfo=timezone(timedelta(hours=8)))
    return value


def normalize_source(raw_source: Any) -> dict[str, Any] | None:
    if not isinstance(raw_source, dict):
        return None

    source_id = str(raw_source.get("id") or "").strip()
    display_name = str(raw_source.get("display_name") or "").strip()
    if not source_id or not display_name:
        return None

    source_type = str(raw_source.get("source_type") or "x").strip().lower() or "x"
    handle = str(raw_source.get("handle") or "").strip()
    profile_url = str(raw_source.get("profile_url") or "").strip()
    query = str(raw_source.get("query") or profile_url or handle or display_name).strip()

    return {
        "id": source_id,
        "display_name": display_name,
        "source_type": source_type,
        "handle": handle,
        "profile_url": profile_url,
        "query": query,
        "notes": str(raw_source.get("notes") or "").strip(),
        "enabled": bool(raw_source.get("enabled", True)),
    }


def load_sources(config_path: Path) -> tuple[list[dict[str, Any]], int]:
    config = load_json(config_path)
    sources = [
        source
        for raw_source in config.get("sources", [])
        if (source := normalize_source(raw_source)) is not None and source.get("enabled", True)
    ]
    try:
        default_window_days = min(max(int(config.get("default_window_days") or DEFAULT_WINDOW_DAYS), 1), 30)
    except (TypeError, ValueError):
        default_window_days = DEFAULT_WINDOW_DAYS
    return sources, default_window_days


def json_compact(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(str(value or ""))).strip()


def parse_x_created_at(raw_value: str) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        value = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo("Asia/Shanghai") if ZoneInfo is not None else timezone(timedelta(hours=8)))


def format_beijing_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def extract_query_id(js_text: str, operation_name: str) -> str:
    match = re.search(rf'queryId:"([^"]+)",operationName:"{re.escape(operation_name)}"', js_text)
    if not match:
        raise RuntimeError(f"Could not locate X query id for {operation_name}.")
    return match.group(1)


def build_x_public_client() -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    bootstrap = session.get("https://x.com/", timeout=30)
    bootstrap.raise_for_status()
    main_match = re.search(r'https://abs\.twimg\.com/responsive-web/client-web/main\.[^"\']+\.js', bootstrap.text)
    if not main_match:
        raise RuntimeError("Could not locate the X web bootstrap script.")

    main_js = session.get(main_match.group(0), timeout=30).text
    bearer_match = re.search(r'AAAAAAAAAAAAAAAAAAAAA[^"\']+', main_js)
    if not bearer_match:
        raise RuntimeError("Could not locate the public X bearer token.")

    bearer_token = unquote(bearer_match.group(0))
    guest_response = session.post(
        "https://api.x.com/1.1/guest/activate.json",
        headers={"Authorization": f"Bearer {bearer_token}", "User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    guest_response.raise_for_status()
    guest_token = guest_response.json().get("guest_token")
    if not guest_token:
        raise RuntimeError("Could not activate an anonymous X guest session.")

    api_headers = {
        "User-Agent": "Mozilla/5.0",
        "Authorization": f"Bearer {bearer_token}",
        "x-guest-token": str(guest_token),
        "x-twitter-active-user": "yes",
        "x-twitter-client-language": "en",
    }
    return {
        "session": session,
        "api_headers": api_headers,
        "user_by_screen_name_query_id": extract_query_id(main_js, "UserByScreenName"),
        "user_tweets_query_id": extract_query_id(main_js, "UserTweets"),
    }


def x_graphql_get(
    client: dict[str, Any],
    *,
    query_id: str,
    operation_name: str,
    variables: dict[str, Any],
    features: dict[str, Any],
    field_toggles: dict[str, Any],
) -> dict[str, Any]:
    response = client["session"].get(
        f"https://x.com/i/api/graphql/{query_id}/{operation_name}",
        params={
            "variables": json_compact(variables),
            "features": json_compact(features),
            "fieldToggles": json_compact(field_toggles),
        },
        headers=client["api_headers"],
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def resolve_x_user(client: dict[str, Any], handle: str) -> dict[str, Any]:
    payload = x_graphql_get(
        client,
        query_id=client["user_by_screen_name_query_id"],
        operation_name="UserByScreenName",
        variables={"screen_name": handle, "withSafetyModeUserFields": True},
        features=X_USER_BY_SCREEN_NAME_FEATURES,
        field_toggles=X_USER_BY_SCREEN_NAME_FIELD_TOGGLES,
    )
    result = (((payload.get("data") or {}).get("user") or {}).get("result") or {})
    rest_id = str(result.get("rest_id") or "").strip()
    if not rest_id:
        raise RuntimeError(f"Could not resolve X handle @{handle}.")
    return result


def iter_nested_tweet_results(node: Any):
    if isinstance(node, dict):
        tweet_results = node.get("tweet_results")
        if isinstance(tweet_results, dict):
            result = tweet_results.get("result")
            if isinstance(result, dict):
                yield result
        for value in node.values():
            if isinstance(value, (dict, list)):
                yield from iter_nested_tweet_results(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_nested_tweet_results(item)


def extract_bottom_cursor(payload: dict[str, Any]) -> str:
    instructions = ((((payload.get("data") or {}).get("user") or {}).get("result") or {}).get("timeline") or {}).get("timeline", {}).get("instructions", [])
    for instruction in instructions:
        if instruction.get("type") != "TimelineAddEntries":
            continue
        for entry in instruction.get("entries", []):
            content = entry.get("content") or {}
            if content.get("cursorType") == "Bottom" and content.get("value"):
                return str(content["value"])
    return ""


def expand_tweet_text(full_text: str, legacy: dict[str, Any]) -> str:
    text = str(full_text or "")
    entities = legacy.get("entities") if isinstance(legacy.get("entities"), dict) else {}
    for url_entry in entities.get("urls", []) if isinstance(entities.get("urls"), list) else []:
        url = str(url_entry.get("url") or "")
        expanded = str(url_entry.get("expanded_url") or url_entry.get("display_url") or url)
        if url:
            text = text.replace(url, expanded)
    for media_entry in entities.get("media", []) if isinstance(entities.get("media"), list) else []:
        media_url = str(media_entry.get("url") or "")
        if media_url:
            text = text.replace(media_url, "")
    return collapse_text(text)


def extract_author_handle(tweet_result: dict[str, Any]) -> str:
    user_result = ((((tweet_result.get("core") or {}).get("user_results") or {}).get("result")) or {})
    core = user_result.get("core") if isinstance(user_result.get("core"), dict) else {}
    if core.get("screen_name"):
        return str(core["screen_name"]).strip()
    legacy = user_result.get("legacy") if isinstance(user_result.get("legacy"), dict) else {}
    return str(legacy.get("screen_name") or "").strip()


def normalize_x_tweet(tweet_result: dict[str, Any]) -> dict[str, Any] | None:
    if tweet_result.get("__typename") != "Tweet":
        return None
    rest_id = str(tweet_result.get("rest_id") or "").strip()
    legacy = tweet_result.get("legacy") if isinstance(tweet_result.get("legacy"), dict) else {}
    created_at = parse_x_created_at(str(legacy.get("created_at") or ""))
    if not rest_id or created_at is None or not legacy:
        return None

    author_handle = extract_author_handle(tweet_result)
    full_text = expand_tweet_text(str(legacy.get("full_text") or ""), legacy)
    if not full_text:
        return None

    return {
        "rest_id": rest_id,
        "author_handle": author_handle,
        "created_at": created_at,
        "created_at_label": format_beijing_timestamp(created_at),
        "url": f"https://x.com/{author_handle or 'i'}/status/{rest_id}",
        "text": full_text,
        "is_retweet": bool(tweet_result.get("retweeted_status_result")) or full_text.startswith("RT @"),
        "reply_count": int(legacy.get("reply_count") or 0),
        "retweet_count": int(legacy.get("retweet_count") or 0),
        "favorite_count": int(legacy.get("favorite_count") or 0),
        "quote_count": int(legacy.get("quote_count") or 0),
    }


def fetch_x_public_posts(
    client: dict[str, Any],
    *,
    handle: str,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    user = resolve_x_user(client, handle)
    rest_id = str(user.get("rest_id") or "")
    if not rest_id:
        raise RuntimeError(f"Could not resolve X handle @{handle}.")

    seen_ids: set[str] = set()
    collected: list[dict[str, Any]] = []
    cursor = ""
    oldest_seen: datetime | None = None

    for _ in range(X_TIMELINE_MAX_PAGES):
        variables = {
            "userId": rest_id,
            "count": X_TIMELINE_PAGE_SIZE,
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        if cursor:
            variables["cursor"] = cursor

        payload = x_graphql_get(
            client,
            query_id=client["user_tweets_query_id"],
            operation_name="UserTweets",
            variables=variables,
            features=X_USER_TWEETS_FEATURES,
            field_toggles=X_USER_TWEETS_FIELD_TOGGLES,
        )

        page_items = 0
        for tweet_result in iter_nested_tweet_results(payload):
            tweet = normalize_x_tweet(tweet_result)
            if tweet is None:
                continue
            if tweet["rest_id"] in seen_ids:
                continue
            seen_ids.add(tweet["rest_id"])
            collected.append(tweet)
            page_items += 1
            if oldest_seen is None or tweet["created_at"] < oldest_seen:
                oldest_seen = tweet["created_at"]

        cursor = extract_bottom_cursor(payload)
        if not cursor or page_items == 0:
            break
        if oldest_seen is not None and oldest_seen <= window_start:
            break

    collected.sort(key=lambda item: item["created_at"], reverse=True)
    in_window = [item for item in collected if window_start < item["created_at"] <= window_end]
    reference_posts = [item for item in collected if item["created_at"] <= window_start][:3]
    return {
        "collection_status": "ok",
        "collection_method": "x_public_guest_api",
        "all_posts": collected,
        "posts": in_window,
        "reference_posts": reference_posts,
        "fetched_count": len(collected),
        "latest_visible_post_at": format_beijing_timestamp(collected[0]["created_at"]) if collected else "",
        "oldest_visible_post_at": format_beijing_timestamp(collected[-1]["created_at"]) if collected else "",
    }


def build_source_windows(
    sources: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    now_value: datetime,
    default_window_days: int,
) -> list[dict[str, Any]]:
    state_sources = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    windows: list[dict[str, Any]] = []

    for source in sources:
        state_entry = state_sources.get(source["id"], {}) if isinstance(state_sources.get(source["id"]), dict) else {}
        last_end = parse_timestamp(str(state_entry.get("last_window_end") or ""))
        cooldown_until = None
        should_scan = True
        if last_end is None:
            start_value = now_value - timedelta(days=default_window_days)
        else:
            start_value = last_end
            cooldown_until = last_end + timedelta(hours=MIN_SOURCE_SCAN_INTERVAL_HOURS)
            if cooldown_until > now_value:
                should_scan = False
        if start_value >= now_value:
            start_value = now_value - timedelta(hours=1)

        windows.append(
            {
                **source,
                "window_start": start_value,
                "window_end": now_value,
                "window_start_label": start_value.strftime("%Y-%m-%d %H:%M:%S"),
                "window_end_label": now_value.strftime("%Y-%m-%d %H:%M:%S"),
                "should_scan": should_scan,
                "cooldown_until": cooldown_until,
                "cooldown_until_label": format_beijing_timestamp(cooldown_until) if cooldown_until else "",
            }
        )

    return windows


def build_prompt(
    sources: list[dict[str, Any]],
    *,
    trigger: str,
    created_at: str,
    previous_excerpt: str,
    allow_live_search: bool,
) -> str:
    source_lines: list[str] = []
    collected_lines: list[str] = []
    for source in sources:
        if source.get("source_type") == "x" and source.get("handle"):
            primary_label = f"@{source['handle']}"
            search_hint = source.get("profile_url") or f"https://x.com/{source['handle']}"
        else:
            primary_label = source.get("display_name") or source.get("query") or source["id"]
            search_hint = source.get("query") or source.get("display_name") or source["id"]

        source_lines.extend(
            [
                f"- Source: {source.get('display_name') or primary_label}",
                f"  - Type: {source.get('source_type') or 'name'}",
                f"  - Search hint: {search_hint}",
                f"  - Window: strictly after {source['window_start_label']} and up to {source['window_end_label']} (Beijing time)",
                f"  - Notes: {source.get('notes') or 'None'}",
            ]
        )

        collected_lines.append(f"### {source.get('display_name') or primary_label}")
        if not source.get("should_scan", True):
            collected_lines.append(
                f"- Scan status: skipped for cooldown. Next recommended scan time: {source.get('cooldown_until_label') or 'unknown'} (Beijing time)."
            )
            continue

        collected_lines.append(f"- Direct collection status: {source.get('collection_status') or 'unknown'}")
        collected_lines.append(f"- Direct collection method: {source.get('collection_method') or 'unknown'}")
        if source.get("collection_error"):
            collected_lines.append(f"- Direct collection error: {source['collection_error']}")

        posts = source.get("posts") if isinstance(source.get("posts"), list) else []
        if posts:
            collected_lines.append("- Statements collected inside the exact window:")
            for post in posts[:24]:
                collected_lines.append(
                    f"  - {post.get('created_at_label') or ''} | {collapse_text(post.get('text') or '')[:360]} | {post.get('url') or ''}"
                )
        else:
            collected_lines.append("- Statements collected inside the exact window: none")

        reference_posts = source.get("reference_posts") if isinstance(source.get("reference_posts"), list) else []
        if reference_posts:
            collected_lines.append("- Closest visible posts before the anti-overlap baseline:")
            for post in reference_posts[:3]:
                collected_lines.append(
                    f"  - {post.get('created_at_label') or ''} | {collapse_text(post.get('text') or '')[:240]} | {post.get('url') or ''}"
                )

    previous_report_text = previous_excerpt if previous_excerpt else "No previous signal-monitor report."
    return f"""
You are an information-monitoring analyst focused on public statements from influential industry voices.
Write the final report in Simplified Chinese.

Current Beijing time: {created_at}
Trigger: {trigger}

Important requirements:
1. This monitor is isolated from the formal research archive. Do not mix it with the main stock-monitor reports.
2. For each source, search only within the exact time window provided. Treat the window start as an anti-overlap baseline and focus on content strictly after that time.
3. Treat the pre-collected statements below as the primary source of truth. If pre-collected statements exist in the window, you must reflect them accurately and must not claim there were no new statements.
4. Only use live web search for sources that are explicitly marked as fallback/error or if the collected evidence is clearly incomplete.
5. Separate sourced statements from your interpretation. Do not invent posts, URLs, timestamps, or quotes.
6. If a source has no new public statements in the window, say so clearly.
7. If the exact window has no new statements but there are visible posts immediately before the baseline, explain that distinction clearly so the user understands the account is active but this window is empty.

Sources and windows:
{chr(10).join(source_lines)}

Pre-collected public statements and direct evidence:
{chr(10).join(collected_lines)}

Live web search availability:
{"Allowed only as fallback." if allow_live_search else "Not needed. Use only the pre-collected evidence above."}

Output format:
# Signal Monitor Report
## Run Summary
- Trigger:
- Coverage:
- Anti-overlap baseline:

## Source Windows
- List each source and its exact collection window.

## Big Voices
### Source Name
- Window:
- New statements:
  - YYYY-MM-DD HH:MM | concise statement | URL
- What changed vs previous run:
- Potential opportunity / signal change:
- What to keep watching:

## Cross-source Patterns

## Follow-up Questions

Previous report excerpt:
<<<PREVIOUS_REPORT
{previous_report_text}
PREVIOUS_REPORT>>>
""".strip()


def write_updated_state(
    state_path: Path,
    *,
    state: dict[str, Any],
    run_id: str,
    report_filename: str,
    created_at: str,
    finished_at: str,
    sources: list[dict[str, Any]],
) -> None:
    state_sources = state.get("sources") if isinstance(state.get("sources"), dict) else {}
    for source in sources:
        state_sources[source["id"]] = {
            "source_id": source["id"],
            "display_name": source.get("display_name") or "",
            "source_type": source.get("source_type") or "x",
            "handle": source.get("handle") or "",
            "profile_url": source.get("profile_url") or "",
            "last_window_start": source["window_start"].isoformat(timespec="seconds"),
            "last_window_end": source["window_end"].isoformat(timespec="seconds"),
            "last_run_id": run_id,
            "last_report_filename": report_filename,
            "updated_at": finished_at,
        }

    history = state.get("history") if isinstance(state.get("history"), list) else []
    history.insert(
        0,
        {
            "run_id": run_id,
            "created_at": created_at,
            "finished_at": finished_at,
            "report_filename": report_filename,
            "source_ids": [source["id"] for source in sources],
            "window_label": f"{sources[0]['window_start_label']} 至 {sources[0]['window_end_label']}" if sources else "",
        },
    )
    state["sources"] = state_sources
    state["history"] = history[:160]
    save_json(state_path, state)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one manual signal-monitor task for the web workspace.")
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--codex-path", default="codex")
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--prompt-dir", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--trigger", default="manual_run")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--meta-path", required=True)
    parser.add_argument("--runtime-path", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config_path)
    state_path = Path(args.state_path)
    output_dir = Path(args.output_dir)
    prompt_dir = Path(args.prompt_dir)
    log_dir = Path(args.log_dir)
    meta_path = Path(args.meta_path)
    runtime_path = Path(args.runtime_path) if args.runtime_path else None

    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config = RunnerConfig(
        config_path=config_path,
        state_path=state_path,
        codex_path=args.codex_path,
        workdir=args.workdir,
        timeout_seconds=max(120, int(args.timeout_seconds or DEFAULT_TIMEOUT_SECONDS)),
        output_dir=output_dir,
        prompt_dir=prompt_dir,
        log_dir=log_dir,
        trigger=args.trigger,
        run_id=args.run_id,
        meta_path=meta_path,
        runtime_path=runtime_path,
    )

    enabled_sources, default_window_days = load_sources(config.config_path)
    if not enabled_sources:
        raise SystemExit("At least one enabled source is required.")

    state = load_json(config.state_path)
    now_value = beijing_now()
    created_at = now_value.strftime("%Y-%m-%d %H:%M:%S")
    sources = build_source_windows(enabled_sources, state, now_value=now_value, default_window_days=default_window_days)

    stem = build_report_stem(created_at, config.trigger)
    report_path = config.output_dir / f"{stem}.md"
    prompt_path = config.prompt_dir / f"{stem}.txt"
    stdout_log_path = config.log_dir / f"{stem}.stdout.log"
    stderr_log_path = config.log_dir / f"{stem}.stderr.log"
    meta: dict[str, Any] = {
        "run_id": config.run_id,
        "trigger": config.trigger,
        "created_at": created_at,
        "source_ids": [source["id"] for source in sources],
        "status": "running",
        "report_path": str(report_path),
        "prompt_path": str(prompt_path),
        "stdout_log_path": str(stdout_log_path),
        "stderr_log_path": str(stderr_log_path),
        "previous_report_path": str(previous_report_path) if previous_report_path else "",
        "started_at": created_at,
        "finished_at": "",
        "window_start": min(source["window_start_label"] for source in sources),
        "window_end": max(source["window_end_label"] for source in sources),
        "error_message": "",
    }
    save_json(meta_path, meta)

    x_client: dict[str, Any] | None = None
    needs_live_search = False
    scanned_sources: list[dict[str, Any]] = []
    for source in sources:
        if not source.get("should_scan", True):
            source["collection_status"] = "cooldown"
            source["collection_method"] = "cooldown_skip"
            source["posts"] = []
            source["reference_posts"] = []
            continue

        if source.get("source_type") == "x" and source.get("handle"):
            try:
                if x_client is None:
                    x_client = build_x_public_client()
                source.update(
                    fetch_x_public_posts(
                        x_client,
                        handle=str(source.get("handle") or "").strip(),
                        window_start=source["window_start"],
                        window_end=source["window_end"],
                    )
                )
            except Exception as exc:
                source["collection_status"] = "error"
                source["collection_method"] = "x_public_guest_api"
                source["collection_error"] = str(exc)
                source["posts"] = []
                source["reference_posts"] = []
                needs_live_search = True
        else:
            source["collection_status"] = "search_fallback"
            source["collection_method"] = "codex_live_search"
            source["posts"] = []
            source["reference_posts"] = []
            source["collection_error"] = "Direct collection is not implemented for this source type."
            needs_live_search = True

        scanned_sources.append(source)

    previous_report_path = latest_previous_report(config.output_dir)
    previous_excerpt = read_previous_report_excerpt(previous_report_path)
    prompt = build_prompt(
        sources,
        trigger=config.trigger,
        created_at=created_at,
        previous_excerpt=previous_excerpt,
        allow_live_search=needs_live_search,
    )
    prompt_path.write_text(prompt, encoding="utf-8")

    try:
        codex_path = resolve_codex_path(config.codex_path)
        check_codex_login(codex_path)
    except Exception as exc:
        write_failure_report(report_path, f"Startup failed: {exc}", trigger=config.trigger, created_at=created_at, sources=sources)
        meta["status"] = "failed"
        meta["finished_at"] = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        meta["error_message"] = str(exc)
        save_json(meta_path, meta)
        sync_runtime_snapshot(runtime_path, run_id=config.run_id, source_ids=[source["id"] for source in sources], meta=meta, meta_path=meta_path)
        return 1

    if not scanned_sources:
        write_failure_report(
            report_path,
            "All enabled sources are still inside the cooldown window, so this run was skipped.",
            trigger=config.trigger,
            created_at=created_at,
            sources=sources,
        )
        meta["status"] = "failed"
        meta["finished_at"] = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
        meta["error_message"] = "All enabled sources are still inside the cooldown window."
        save_json(meta_path, meta)
        sync_runtime_snapshot(runtime_path, run_id=config.run_id, source_ids=[source["id"] for source in sources], meta=meta, meta_path=meta_path)
        return 1

    command = [codex_path]
    if needs_live_search:
        command.append("--search")
    command.extend(
        [
            "exec",
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "--color",
            "never",
            "-C",
            config.workdir,
            "-o",
            str(report_path),
            "-",
        ]
    )

    try:
        with prompt_path.open("rb") as prompt_handle:
            result = subprocess.run(
                command,
                stdin=prompt_handle,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=config.timeout_seconds,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        stdout_log_path.write_text(result.stdout or "", encoding="utf-8")
        stderr_log_path.write_text(result.stderr or "", encoding="utf-8")

        if result.returncode != 0:
            write_failure_report(
                report_path,
                f"Codex exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}",
                trigger=config.trigger,
                created_at=created_at,
                sources=sources,
            )
            meta["status"] = "failed"
            meta["error_message"] = f"Codex exit code: {result.returncode}"
            exit_code = result.returncode or 1
        elif not report_path.exists() or not read_report_text(report_path).strip():
            write_failure_report(
                report_path,
                "Codex did not generate a valid report.",
                trigger=config.trigger,
                created_at=created_at,
                sources=sources,
            )
            meta["status"] = "failed"
            meta["error_message"] = "Codex did not generate a valid report."
            exit_code = 1
        else:
            meta["status"] = "success"
            exit_code = 0
    except subprocess.TimeoutExpired as exc:
        stdout_log_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_log_path.write_text(exc.stderr or "", encoding="utf-8")
        write_failure_report(
            report_path,
            "Codex execution timed out.",
            trigger=config.trigger,
            created_at=created_at,
            sources=sources,
        )
        meta["status"] = "timeout"
        meta["error_message"] = "Codex execution timed out."
        exit_code = 124
    except Exception as exc:  # pragma: no cover
        stderr_log_path.write_text(str(exc), encoding="utf-8")
        write_failure_report(
            report_path,
            f"Runtime error: {exc}",
            trigger=config.trigger,
            created_at=created_at,
            sources=sources,
        )
        meta["status"] = "error"
        meta["error_message"] = str(exc)
        exit_code = 1

    meta["finished_at"] = beijing_now().strftime("%Y-%m-%d %H:%M:%S")
    save_json(meta_path, meta)

    if meta["status"] == "success":
        write_updated_state(
            state_path=config.state_path,
            state=state,
            run_id=config.run_id,
            report_filename=report_path.name,
            created_at=created_at,
            finished_at=meta["finished_at"],
            sources=scanned_sources,
        )

    sync_runtime_snapshot(
        runtime_path,
        run_id=config.run_id,
        source_ids=[source["id"] for source in sources],
        meta=meta,
        meta_path=meta_path,
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
