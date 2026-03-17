from __future__ import annotations

import calendar
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import unicodedata
import uuid
import zipfile
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import bleach
import markdown
from bleach.css_sanitizer import CSSSanitizer
from docx import Document
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)
from pypdf import PdfReader
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.local", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

from oss_client import (
    build_oss_status,
    build_signed_url,
    delete_uploaded_object,
    probe_oss_bridge,
    upload_file_for_tingwu,
)
from monitor_runner import check_codex_login as check_monitor_codex_login
from monitor_runner import discover_codex_path as discover_monitor_codex_path
from tingwu_client import (
    build_tingwu_status,
    fetch_result_documents,
    get_task_info,
    submit_offline_task,
)
REPORT_SUFFIXES = {".md", ".markdown"}
MARKDOWN_EXTENSIONS = ["extra", "toc", "sane_lists", "nl2br"]
FILENAME_DATETIME_PATTERNS = [
    (re.compile(r"(?P<date>\d{8})_(?P<time>\d{6})"), "%Y%m%d%H%M%S", True),
    (re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})"), "%Y-%m-%d", False),
    (re.compile(r"(?P<date>\d{8})"), "%Y%m%d", False),
]
DEFAULT_EXTERNAL_REPORTS_DIR = Path(r"D:\工作\FTAI\reports")
STOCK_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
SYMBOL_SPLIT_PATTERN = re.compile(r"[\s,，;；/]+")
TEXT_PREVIEW_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".log",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".py",
}
IMAGE_PREVIEW_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
}
TEXT_EXTRACTION_SUFFIXES = TEXT_PREVIEW_SUFFIXES | {".pdf", ".docx"}
MAX_TEXT_PREVIEW_CHARS = 200_000
MAX_NOTE_CONTENT_CHARS = 120_000
NOTE_TRUNCATION_NOTICE = "\n\n[内容过长，已截断以保证笔记显示流畅。]"
IMAGE_ONLY_NOTE_PLACEHOLDER = "[含图片内容]"
FILE_TYPE_LABELS = {
    ".pdf": "PDF",
    ".doc": "Word",
    ".docx": "Word",
    ".xls": "Excel",
    ".xlsx": "Excel",
    ".xlsm": "Excel",
    ".csv": "表格",
    ".ppt": "演示",
    ".pptx": "演示",
    ".txt": "文本",
    ".md": "Markdown",
    ".markdown": "Markdown",
    ".json": "JSON",
    ".log": "日志",
    ".py": "代码",
    ".png": "图片",
    ".jpg": "图片",
    ".jpeg": "图片",
    ".gif": "图片",
    ".webp": "图片",
    ".bmp": "图片",
    ".svg": "图片",
    ".zip": "压缩包",
    ".rar": "压缩包",
    ".7z": "压缩包",
}
TAG_SPLIT_PATTERN = re.compile(r"[\n,，;；]+")
SEARCH_KIND_META = {
    "note": {"label": "研究笔记", "tone": "note"},
    "file": {"label": "研究资料", "tone": "file"},
    "transcript": {"label": "会议转录", "tone": "transcript"},
    "report": {"label": "关联日报", "tone": "report"},
    "group": {"label": "股票分组", "tone": "group"},
}
AI_SCOPE_CONTENT_KIND_META = {
    "report": "日报",
    "note": "笔记",
    "file": "文件",
    "transcript": "转录",
}
AI_SCOPE_DEFAULT_CONTENT_KINDS = tuple(AI_SCOPE_CONTENT_KIND_META.keys())
TRASH_KIND_META = {
    "note": {"label": "研究笔记", "description": "可恢复到原股票页"},
    "file": {"label": "研究资料", "description": "会保留原来的文件与说明"},
    "transcript": {"label": "会议转录", "description": "恢复后仍可继续查看与同步"},
    "group": {"label": "股票分组", "description": "恢复后会带回原有股票列表"},
    "monitor_report": {"label": "Monitor 报告", "description": "恢复后会重新回到报告归档和 Monitor 页面"},
}
TRANSCRIPT_AUDIO_SUFFIXES = {
    ".mp3",
    ".wav",
    ".m4a",
    ".wma",
    ".aac",
    ".ogg",
    ".amr",
    ".flac",
    ".aiff",
}
TRANSCRIPT_VIDEO_SUFFIXES = {
    ".mp4",
    ".wmv",
    ".m4v",
    ".flv",
    ".rmvb",
    ".dat",
    ".mov",
    ".mkv",
    ".webm",
    ".avi",
    ".mpeg",
    ".3gp",
}
TRANSCRIPT_SUPPORTED_SUFFIXES = TRANSCRIPT_AUDIO_SUFFIXES | TRANSCRIPT_VIDEO_SUFFIXES
TRANSCRIPT_SOURCE_LANGUAGE_OPTIONS = [
    {"value": "cn", "label": "中文"},
    {"value": "en", "label": "英文"},
    {"value": "ja", "label": "日语"},
    {"value": "yue", "label": "粤语"},
    {"value": "fspk", "label": "自由说话场景"},
]
TRANSCRIPT_OUTPUT_LEVEL_OPTIONS = [
    {"value": "1", "label": "标准输出"},
    {"value": "2", "label": "增强输出"},
]
TRANSCRIPT_SPEAKER_COUNT_OPTIONS = [
    {"value": str(count), "label": f"{count} 人"}
    for count in range(2, 9)
]
TRANSCRIPT_MEETING_ASSISTANCE_OPTIONS = [
    {"value": "Actions", "label": "待办事项"},
    {"value": "KeyInformation", "label": "关键信息"},
]
TRANSCRIPT_SUMMARIZATION_OPTIONS = [
    {"value": "Paragraph", "label": "段落摘要"},
    {"value": "Conversational", "label": "对话摘要"},
    {"value": "QuestionsAnswering", "label": "问答提炼"},
]
TRANSCRIPT_MEDIA_KIND_LABELS = {
    "audio": "音频",
    "video": "视频",
    "media": "媒体",
}
TRANSCRIPT_STATUS_META = {
    "pending_api": {"label": "待提交", "tone": "pending"},
    "queued": {"label": "排队中", "tone": "info"},
    "processing": {"label": "转录中", "tone": "info"},
    "completed": {"label": "已完成", "tone": "success"},
    "failed": {"label": "转录失败", "tone": "danger"},
}
TRANSCRIPT_CAPABILITY_CARDS = [
    {
        "eyebrow": "离线转写",
        "title": "音视频文件转录",
        "copy": "页面已经预留了音频/视频上传和后续 CreateTask 的参数结构，等你拿到凭证后可以直接接通。",
    },
    {
        "eyebrow": "会议信息",
        "title": "说话人分离与章节",
        "copy": "支持预设说话人分离、说话人数和自动章节分段，方便更接近正式会议记录场景。",
    },
    {
        "eyebrow": "AI 增强",
        "title": "摘要、会议提炼、润色",
        "copy": "已经把待办事项、关键信息、摘要类型、文字润色、自定义 Prompt 这些常用选项放进表单。",
    },
]
TRANSCRIPT_REQUIREMENT_NOTES = [
    "本地上传的音视频会先自动同步到阿里云 OSS，再由系统生成听悟可访问的临时 FileUrl，不需要你手动准备公网地址。",
    "说话人分离、会议提炼、摘要、PPT 提取、自定义 Prompt 都已经保留成独立选项，后续可直接映射到官方参数。",
    "当前项目按“本地直传 + 主动轮询”设计，不必额外配置回调；任务提交后由本地后端主动刷新状态即可。",
    "如果你把任务关联到某只股票，转录结果会同步出现在个股页的“会议转录”模块里。",
]
TRANSCRIPT_PLACEHOLDER_COPY = (
    "当前已保存源文件和转录参数。系统会优先尝试自动上传到 OSS 并提交到听悟；"
    "如果项目不设置回调，页面会通过主动轮询把结果同步回来。"
)
TRANSCRIPT_RESULT_SECTION_LABELS = {
    "transcription": "整理对话（保留原始内容）",
    "meeting_assistance": "会议提炼",
    "summarization": "摘要结果",
    "auto_chapters": "章节提要",
    "text_polish": "听悟润色版（可能调整措辞）",
    "ppt_extraction": "PPT 提取",
    "custom_prompt": "自定义 Prompt 输出",
    "content_extraction": "内容提取",
    "identity_recognition": "身份识别",
    "service_inspection": "质检",
    "translation": "翻译",
}
TRANSCRIPT_SOURCE_LANGUAGE_LABELS = {
    item["value"]: item["label"]
    for item in TRANSCRIPT_SOURCE_LANGUAGE_OPTIONS
}
TRANSCRIPT_OUTPUT_LEVEL_LABELS = {
    item["value"]: item["label"]
    for item in TRANSCRIPT_OUTPUT_LEVEL_OPTIONS
}
TRANSCRIPT_MEETING_ASSISTANCE_LABELS = {
    item["value"]: item["label"]
    for item in TRANSCRIPT_MEETING_ASSISTANCE_OPTIONS
}
TRANSCRIPT_SUMMARIZATION_LABELS = {
    item["value"]: item["label"]
    for item in TRANSCRIPT_SUMMARIZATION_OPTIONS
}
TRASH_KIND_META["signal_report"] = {
    "label": "信息监控报告",
    "description": "恢复后会重新回到独立的信息监控工作台。",
}
NOTE_ALLOWED_TAGS = [
    "p",
    "br",
    "div",
    "span",
    "h2",
    "h3",
    "h4",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "mark",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "img",
]
NOTE_ALLOWED_ATTRIBUTES = {
    "*": ["style"],
    "img": ["src", "alt", "title"],
}
NOTE_CSS_SANITIZER = CSSSanitizer(
    allowed_css_properties=[
        "color",
        "background-color",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "text-align",
        "text-decoration",
    ]
)
NOTE_ALLOWED_PROTOCOLS = set(bleach.sanitizer.ALLOWED_PROTOCOLS) | {"data"}


def resolve_app_path(env_name: str, fallback: Path) -> Path:
    configured = os.getenv(env_name)
    if not configured:
        return fallback

    candidate = Path(configured).expanduser()
    return candidate if candidate.is_absolute() else (BASE_DIR / candidate).resolve()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


FALLBACK_REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR = resolve_app_path(
    "REPORTS_DIR",
    DEFAULT_EXTERNAL_REPORTS_DIR if DEFAULT_EXTERNAL_REPORTS_DIR.exists() else FALLBACK_REPORTS_DIR,
)
STOCK_STORE_PATH = resolve_app_path("STOCKS_DATA_PATH", BASE_DIR / "data" / "stocks.json")
STOCK_UPLOADS_DIR = resolve_app_path("STOCKS_UPLOADS_DIR", BASE_DIR / "uploads" / "stocks")
TRANSCRIPT_UPLOADS_DIR = resolve_app_path("TRANSCRIPT_UPLOADS_DIR", BASE_DIR / "uploads" / "transcripts")
AI_CHAT_STORE_PATH = resolve_app_path("AI_CHAT_DATA_PATH", BASE_DIR / "data" / "ai_chats.json")
AI_CONTEXT_DIR = resolve_app_path("AI_CONTEXT_DIR", BASE_DIR / "data" / "ai_context")
CODEX_CONFIG_DIR = Path.home() / ".codex"
CODEX_MODELS_CACHE_PATH = CODEX_CONFIG_DIR / "models_cache.json"
AI_CODEX_TIMEOUT_SECONDS = int(os.getenv("AI_CODEX_TIMEOUT_SECONDS", "900"))
AI_POLL_INTERVAL_SECONDS = int(os.getenv("AI_POLL_INTERVAL_SECONDS", "5"))
AI_PROMPT_KNOWLEDGE_CHAR_LIMIT = int(os.getenv("AI_PROMPT_KNOWLEDGE_CHAR_LIMIT", "40000"))
AI_SESSION_LOCK = threading.RLock()
AI_PROCESS_LOCK = threading.RLock()
AI_RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
AI_STOP_REQUESTS: set[str] = set()
REPORT_CACHE_LOCK = threading.RLock()
REPORT_INDEX_CACHE: dict[str, Any] = {
    "signature": None,
    "items": [],
    "by_filename": {},
}
REPORT_HTML_CACHE: dict[tuple[str, int, int], str] = {}
REPORT_HTML_RENDER_VERSION = 3
DEFAULT_MONITOR_SOURCE_DIR = Path(r"D:\工作\FTAI")
ORIGINAL_MONITOR_CONFIG_PATH = DEFAULT_MONITOR_SOURCE_DIR / "stock_monitor_config.json"
MONITOR_DATA_DIR = BASE_DIR / "data" / "monitor"
MONITOR_CONFIG_PATH = MONITOR_DATA_DIR / "config.json"
MONITOR_RUNTIME_PATH = MONITOR_DATA_DIR / "runtime.json"
MONITOR_RUNNER_PATH = BASE_DIR / "monitor_runner.py"
MONITOR_LOGS_DIR = BASE_DIR / "logs" / "monitor"
MONITOR_PROMPTS_DIR = MONITOR_DATA_DIR / "prompts"
MONITOR_TRASH_DIR = MONITOR_DATA_DIR / "trash_reports"
MONITOR_PROCESS_LOCK = threading.RLock()
MONITOR_STATUS_POLL_INTERVAL_SECONDS = 4
SIGNAL_MONITOR_DATA_DIR = BASE_DIR / "data" / "signal_monitor"
SIGNAL_MONITOR_CONFIG_PATH = SIGNAL_MONITOR_DATA_DIR / "config.json"
SIGNAL_MONITOR_RUNTIME_PATH = SIGNAL_MONITOR_DATA_DIR / "runtime.json"
SIGNAL_MONITOR_STATE_PATH = SIGNAL_MONITOR_DATA_DIR / "state.json"
SIGNAL_MONITOR_RUNNER_PATH = BASE_DIR / "signal_monitor_runner.py"
SIGNAL_MONITOR_LOGS_DIR = BASE_DIR / "logs" / "signal_monitor"
SIGNAL_MONITOR_PROMPTS_DIR = SIGNAL_MONITOR_DATA_DIR / "prompts"
SIGNAL_MONITOR_REPORTS_DIR = SIGNAL_MONITOR_DATA_DIR / "reports"
SIGNAL_MONITOR_TRASH_DIR = SIGNAL_MONITOR_DATA_DIR / "trash_reports"
SIGNAL_MONITOR_PROCESS_LOCK = threading.RLock()
SIGNAL_MONITOR_STATUS_POLL_INTERVAL_SECONDS = 5
SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS = 7
SIGNAL_MONITOR_MIN_INTERVAL_HOURS = 6
SIGNAL_MONITOR_DEFAULT_SOURCES = [
    {
        "id": "semianalysis-x",
        "display_name": "SemiAnalysis",
        "source_type": "x",
        "handle": "SemiAnalysis_",
        "profile_url": "https://x.com/SemiAnalysis_",
        "notes": "先作为大 V 言论监控的默认示例。",
        "enabled": True,
    }
]
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_KEEP_COUNT = int(os.getenv("BACKUP_KEEP_COUNT", "20"))
BACKUP_EXCLUDED_DIR_NAMES = {".git", ".venv", "__pycache__", "backups"}
BACKUP_EXCLUDED_FILE_NAMES = {".env", ".env.local"}
BACKUP_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "stock-daily-analysis-local-secret")


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def current_port() -> int:
    return int(os.getenv("PORT", "5000"))


def current_local_url() -> str:
    return f"http://127.0.0.1:{current_port()}"


def path_is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def should_skip_backup_path(path: Path) -> bool:
    try:
        relative_parts = path.relative_to(BASE_DIR).parts
    except ValueError:
        relative_parts = ()

    if any(part in BACKUP_EXCLUDED_DIR_NAMES for part in relative_parts):
        return True

    if path.name in BACKUP_EXCLUDED_FILE_NAMES:
        return True

    if path.suffix.lower() in BACKUP_EXCLUDED_SUFFIXES:
        return True

    return False


def add_directory_to_zip(
    archive: zipfile.ZipFile,
    source_dir: Path,
    archive_root: str,
    skip_predicate: Any | None = None,
) -> int:
    if not source_dir.exists():
        return 0

    written = 0
    for path in source_dir.rglob("*"):
        if path.is_dir():
            continue
        if skip_predicate and skip_predicate(path):
            continue
        archive_name = Path(archive_root) / path.relative_to(source_dir)
        archive.write(path, str(archive_name).replace("\\", "/"))
        written += 1
    return written


def next_backup_archive_path() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stem = datetime.now().strftime("stock-web-backup-%Y%m%d-%H%M%S")
    candidate = BACKUP_DIR / f"{stem}.zip"
    duplicate_index = 1
    while candidate.exists():
        candidate = BACKUP_DIR / f"{stem}-{duplicate_index:02d}.zip"
        duplicate_index += 1
    return candidate


def prune_old_backups() -> None:
    backups = sorted(
        BACKUP_DIR.glob("stock-web-backup-*.zip"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for stale_path in backups[BACKUP_KEEP_COUNT:]:
        try:
            stale_path.unlink()
        except OSError:
            continue


def create_workspace_backup_archive() -> Path:
    backup_path = next_backup_archive_path()
    reports_outside_project = REPORTS_DIR.exists() and not path_is_within(REPORTS_DIR, BASE_DIR)

    readme_lines = [
        "# Workspace Backup",
        "",
        f"- Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Project root: {BASE_DIR}",
        f"- Reports directory: {REPORTS_DIR}",
        "- This backup includes project code, templates, static assets, user data, uploads, and monitor data.",
        "- Secret files such as .env and .env.local are intentionally excluded.",
    ]

    if reports_outside_project:
        readme_lines.append("- External reports are included under `external_reports/`.")
    else:
        readme_lines.append("- Reports are already inside the project archive under `web_app/`.")

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("00_BACKUP_README.md", "\n".join(readme_lines) + "\n")
        add_directory_to_zip(archive, BASE_DIR, "web_app", should_skip_backup_path)
        if reports_outside_project:
            add_directory_to_zip(archive, REPORTS_DIR, "external_reports")

    prune_old_backups()
    return backup_path


def fallback_title(path: Path) -> str:
    cleaned = path.stem.replace("_", " ").replace("-", " ").strip()
    return cleaned or path.name


def extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue

        candidate = stripped.lstrip("#").strip()
        if candidate:
            return candidate

    return fallback


def extract_summary(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith(("- ", "* ")):
            stripped = stripped[2:].strip()

        return stripped[:110] + ("..." if len(stripped) > 110 else "")

    return "在报告前几段补一小段摘要，这里就会自动显示预览。"


def format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def format_iso_timestamp(value: str | None) -> str:
    if not value:
        return "刚刚"

    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def coerce_sort_timestamp(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    raw_value = str(value).strip()
    if not raw_value:
        return 0.0
    try:
        return datetime.fromisoformat(raw_value).timestamp()
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        return 0.0


def iso_to_date(value: str | None) -> str | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        return None


def today_date_iso() -> str:
    return datetime.now().date().isoformat()


def build_recorded_timestamp(
    record_date: str | None,
    *,
    fallback_timestamp: str | None = None,
) -> tuple[str, str]:
    base_timestamp = str(fallback_timestamp or now_iso())
    try:
        base_value = datetime.fromisoformat(base_timestamp)
    except ValueError:
        base_value = datetime.now().replace(microsecond=0)

    normalized_date = normalize_date_field(record_date) or base_value.date().isoformat()
    selected_value = parse_iso_date_value(normalized_date) or base_value
    resolved_value = datetime.combine(
        selected_value.date(),
        base_value.time().replace(microsecond=0),
    )
    return resolved_value.isoformat(timespec="seconds"), normalized_date


def format_record_date_label(record_date: str | None, fallback_timestamp: str | None) -> str:
    normalized_date = normalize_date_field(record_date)
    if normalized_date:
        return normalized_date
    return format_iso_timestamp(fallback_timestamp)


def note_display_time(note: dict[str, Any]) -> str:
    return format_record_date_label(note.get("record_date"), note.get("created_at"))


def file_display_time(file_entry: dict[str, Any]) -> str:
    return format_record_date_label(file_entry.get("record_date"), file_entry.get("uploaded_at"))


def read_report_text(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    return path.read_text(encoding="utf-8", errors="replace")


def iter_report_paths() -> list[Path]:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            report_path
            for report_path in REPORTS_DIR.iterdir()
            if report_path.is_file() and report_path.suffix.lower() in REPORT_SUFFIXES
        ],
        key=lambda path: path.name.lower(),
    )


def build_report_directory_signature(report_paths: list[Path]) -> tuple[tuple[str, int, int], ...]:
    signature_entries: list[tuple[str, int, int]] = []
    for report_path in report_paths:
        stat_result = report_path.stat()
        signature_entries.append((report_path.name, stat_result.st_mtime_ns, stat_result.st_size))
    return tuple(signature_entries)


def build_report_catalog_entry(report_path: Path) -> dict[str, Any]:
    stat_result = report_path.stat()
    content = read_report_text(report_path)
    report_datetime, has_time = parse_report_datetime(report_path)
    if report_datetime is None:
        report_datetime = datetime.fromtimestamp(stat_result.st_mtime)
        has_time = True
    return {
        "filename": report_path.name,
        "title": extract_title(content, fallback_title(report_path)),
        "summary": extract_summary(content),
        "report_date": format_report_datetime(report_datetime, has_time),
        "updated_at": format_timestamp(stat_result.st_mtime),
        "sort_key": report_datetime.timestamp(),
        "content": content,
        "mtime_ns": stat_result.st_mtime_ns,
    }


def serialize_report_entry(entry: dict[str, Any], *, include_html: bool = False) -> dict[str, Any]:
    payload = {
        "filename": entry["filename"],
        "title": entry["title"],
        "summary": entry["summary"],
        "report_date": entry["report_date"],
        "updated_at": entry["updated_at"],
        "sort_key": entry["sort_key"],
    }
    if include_html:
        cache_key = (entry["filename"], int(entry["mtime_ns"]), REPORT_HTML_RENDER_VERSION)
        with REPORT_CACHE_LOCK:
            html = REPORT_HTML_CACHE.get(cache_key)
        if html is None:
            html = markdown.markdown(
                entry["content"],
                extensions=MARKDOWN_EXTENSIONS,
                output_format="html5",
            )
            html = collapse_report_source_blocks(html)
            with REPORT_CACHE_LOCK:
                REPORT_HTML_CACHE[cache_key] = html
        payload["html"] = html
    return payload


def collapse_report_source_blocks(html: str) -> str:
    def replace_source(match: re.Match[str]) -> str:
        source_content = match.group(1).strip()
        return (
            '<li class="report-source-item">'
            '<details class="report-source-disclosure">'
            '<summary>'
            '<span class="report-source-title">Sources</span>'
            '<span class="report-source-open-button">点击展开</span>'
            "</summary>"
            f'<div class="report-source-content">{source_content}'
            '<div class="report-source-footer">'
            '<button class="report-source-close" type="button" data-report-source-close>(点击收起)</button>'
            "</div>"
            "</div>"
            "</details>"
            "</li>"
        )

    return re.sub(
        r"<li>\s*Sources:\s*(.*?)</li>",
        replace_source,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def get_report_catalog() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    report_paths = iter_report_paths()
    signature = build_report_directory_signature(report_paths)

    with REPORT_CACHE_LOCK:
        cached_signature = REPORT_INDEX_CACHE.get("signature")
        cached_items = REPORT_INDEX_CACHE.get("items")
        cached_by_filename = REPORT_INDEX_CACHE.get("by_filename")
        if cached_signature == signature and isinstance(cached_items, list) and isinstance(cached_by_filename, dict):
            return cached_items, cached_by_filename

    items = [build_report_catalog_entry(report_path) for report_path in report_paths]
    items.sort(key=lambda item: (item["sort_key"], item["filename"]), reverse=True)
    by_filename = {item["filename"]: item for item in items}
    valid_html_keys = {
        (item["filename"], int(item["mtime_ns"]), REPORT_HTML_RENDER_VERSION)
        for item in items
    }

    with REPORT_CACHE_LOCK:
        REPORT_INDEX_CACHE["signature"] = signature
        REPORT_INDEX_CACHE["items"] = items
        REPORT_INDEX_CACHE["by_filename"] = by_filename
        stale_html_keys = [key for key in REPORT_HTML_CACHE.keys() if key not in valid_html_keys]
        for cache_key in stale_html_keys:
            REPORT_HTML_CACHE.pop(cache_key, None)

    return items, by_filename


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "utf-16"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    return path.read_text(encoding="utf-8", errors="replace")


def is_text_previewable(filename: str) -> bool:
    return Path(filename).suffix.lower() in TEXT_PREVIEW_SUFFIXES


def is_image_previewable(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_PREVIEW_SUFFIXES


def is_file_previewable(filename: str) -> bool:
    return is_text_previewable(filename) or is_image_previewable(filename)


def trim_note_content(value: str, limit: int = MAX_NOTE_CONTENT_CHARS) -> str:
    content = value.strip()
    if len(content) <= limit:
        return content

    if limit <= len(NOTE_TRUNCATION_NOTICE):
        return content[:limit]

    cutoff = limit - len(NOTE_TRUNCATION_NOTICE)
    return content[:cutoff].rstrip() + NOTE_TRUNCATION_NOTICE


def summarize_text_block(value: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", value).strip()
    if len(compact) <= limit:
        return compact

    return compact[: limit - 3].rstrip() + "..."


def plain_text_to_html(value: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n{2,}", value.strip()) if block.strip()]
    if not blocks:
        return ""

    return "".join(f"<p>{escape(block).replace(chr(10), '<br>')}</p>" for block in blocks)


def sanitize_note_html(value: str) -> str:
    return bleach.clean(
        value,
        tags=NOTE_ALLOWED_TAGS,
        attributes=NOTE_ALLOWED_ATTRIBUTES,
        protocols=NOTE_ALLOWED_PROTOCOLS,
        css_sanitizer=NOTE_CSS_SANITIZER,
        strip=True,
    ).strip()


def note_html_to_text(value: str) -> str:
    text = bleach.clean(value, tags=[], strip=True)
    return re.sub(r"\s+", " ", text).strip()


def note_html_has_image(value: str) -> bool:
    return "<img" in value.lower()


def derive_note_content_text(content_html: str) -> str:
    content_text = trim_note_content(note_html_to_text(content_html))
    if content_text:
        return content_text
    if note_html_has_image(content_html):
        return IMAGE_ONLY_NOTE_PLACEHOLDER
    return ""


def prepare_note_payload(html_value: str, fallback_text: str) -> tuple[str, str]:
    raw_html = html_value.strip()
    if raw_html:
        content_html = sanitize_note_html(raw_html)
    else:
        content_html = plain_text_to_html(trim_note_content(fallback_text))

    content_text = derive_note_content_text(content_html)
    return content_html, content_text


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            chunks.append(text)

    return "\n\n".join(chunks).strip()


def extract_docx_text(path: Path) -> str:
    document = Document(str(path))
    chunks: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            chunks.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                chunks.append(" | ".join(cells))

    return "\n\n".join(chunks).strip()


def try_extract_file_text(path: Path, original_name: str) -> tuple[str | None, bool]:
    suffix = Path(original_name).suffix.lower()

    try:
        if suffix in TEXT_PREVIEW_SUFFIXES:
            text = read_text_file(path).strip()
        elif suffix == ".pdf":
            text = extract_pdf_text(path)
        elif suffix == ".docx":
            text = extract_docx_text(path)
        else:
            return None, False
    except Exception:
        return None, False

    return (text or None), bool(text)


def build_file_note_content(comment: str, extracted_text: str | None, original_name: str) -> str:
    parts: list[str] = []

    if comment.strip():
        parts.append(comment.strip())

    if extracted_text:
        if parts:
            parts.append(f"[Extracted Text · {original_name}]\n{extracted_text.strip()}")
        else:
            parts.append(extracted_text.strip())

    return "\n\n---\n\n".join(parts).strip()


def build_file_note_content(comment: str, extracted_text: str | None, original_name: str) -> str:
    parts: list[str] = []

    if comment.strip():
        parts.append(comment.strip())

    if extracted_text:
        parts.append(f"[Extracted Text | {original_name}]\n{extracted_text.strip()}")

    return trim_note_content("\n\n---\n\n".join(parts))


def build_file_note_payload(
    comment_html: str,
    comment_text: str,
    extracted_text: str | None,
    original_name: str,
) -> tuple[str, str]:
    html_parts: list[str] = []

    if comment_html.strip():
        html_parts.append(sanitize_note_html(comment_html))
    elif comment_text.strip():
        html_parts.append(plain_text_to_html(trim_note_content(comment_text)))

    if extracted_text:
        html_parts.append(
            "<p><strong>[抽取文字 | {name}]</strong></p><pre>{content}</pre>".format(
                name=escape(original_name),
                content=escape(extracted_text.strip()),
            )
        )

    content_html = sanitize_note_html("".join(html_parts))
    content_text = derive_note_content_text(content_html)
    return content_html, content_text


def load_text_preview(path: Path) -> tuple[str, bool]:
    preview_text = read_text_file(path)
    is_truncated = len(preview_text) > MAX_TEXT_PREVIEW_CHARS
    if is_truncated:
        preview_text = preview_text[:MAX_TEXT_PREVIEW_CHARS].rstrip() + "\n\n[Preview truncated]"

    return preview_text, is_truncated


def shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = (year * 12) + (month - 1) + offset
    return month_index // 12, (month_index % 12) + 1


def parse_iso_date_value(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def parse_month_value(value: str | None, fallback: datetime | None = None) -> datetime:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m").replace(day=1)
        except ValueError:
            pass

    base = fallback or datetime.now()
    return base.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def resolve_month_value(
    *,
    month_param: str | None,
    year_param: str | None,
    month_number_param: str | None,
    fallback: datetime | None = None,
) -> datetime:
    if year_param and month_number_param:
        try:
            year = int(year_param)
            month = int(month_number_param)
            if 1 <= month <= 12:
                return datetime(year, month, 1)
        except ValueError:
            pass

    return parse_month_value(month_param, fallback=fallback)


def detect_file_type_label(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in FILE_TYPE_LABELS:
        return FILE_TYPE_LABELS[suffix]
    if suffix:
        return suffix.lstrip(".").upper()
    return "未知类型"


def is_transcript_source_allowed(filename: str) -> bool:
    return Path(filename).suffix.lower() in TRANSCRIPT_SUPPORTED_SUFFIXES


def detect_transcript_media_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in TRANSCRIPT_AUDIO_SUFFIXES:
        return "audio"
    if suffix in TRANSCRIPT_VIDEO_SUFFIXES:
        return "video"
    return "media"


def normalize_date_field(value: str | None) -> str:
    raw_value = str(value or "").strip()
    parsed = parse_iso_date_value(raw_value)
    return parsed.date().isoformat() if parsed else ""


def normalize_choice_list(raw_values: Any, allowed_values: set[str]) -> list[str]:
    if isinstance(raw_values, (list, tuple, set)):
        values = raw_values
    elif raw_values is None:
        values = []
    else:
        values = [raw_values]

    normalized: list[str] = []
    for raw_value in values:
        value = str(raw_value).strip()
        if not value or value not in allowed_values or value in normalized:
            continue
        normalized.append(value)

    return normalized


def normalize_ai_scope_content_kinds(raw_values: Any) -> list[str]:
    if isinstance(raw_values, str):
        values = re.findall(r"report|note|file|transcript", raw_values.lower())
    elif isinstance(raw_values, (list, tuple, set)):
        values: list[Any] = []
        for raw_value in raw_values:
            if isinstance(raw_value, str):
                values.extend(re.findall(r"report|note|file|transcript", raw_value.lower()))
            else:
                values.append(raw_value)
    else:
        values = []

    return normalize_choice_list(values, set(AI_SCOPE_DEFAULT_CONTENT_KINDS))


def normalize_tag_value(raw_value: Any) -> str | None:
    value = str(raw_value or "").strip().lstrip("#")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[<>]", "", value).strip()
    if not value:
        return None
    return value[:28]


def normalize_tag_list(raw_values: Any) -> list[str]:
    if isinstance(raw_values, str):
        values = TAG_SPLIT_PATTERN.split(raw_values)
    elif isinstance(raw_values, (list, tuple, set)):
        values = raw_values
    else:
        values = []

    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        tag = normalize_tag_value(raw_value)
        if not tag:
            continue
        normalized_key = tag.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        ordered.append(tag)

    return ordered[:12]


def tag_match(tags: list[str], target: str | None) -> bool:
    if not target:
        return True
    normalized_target = target.casefold()
    return any(tag.casefold() == normalized_target for tag in tags)


def collect_tag_counts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    display_names: dict[str, str] = {}

    for item in items:
        for tag in normalize_tag_list(item.get("tags", [])):
            key = tag.casefold()
            counts[key] += 1
            display_names.setdefault(key, tag)

    return [
        {"value": display_names[key], "count": count}
        for key, count in counts.most_common()
    ]


def transcript_count_for_symbol(store: dict[str, Any], symbol: str) -> int:
    return sum(
        1
        for transcript in store.get("transcripts", [])
        if transcript_matches_symbol(transcript, symbol)
    )


def build_transcript_source_meta(entry: dict[str, Any]) -> dict[str, str]:
    source_bucket_name = str(entry.get("source_bucket_name") or "").strip()
    source_object_key = str(entry.get("source_object_key") or "").strip()
    manual_url = str(entry.get("file_url_hint") or "").strip()

    if source_bucket_name and source_object_key:
        return {
            "mode": "oss_auto",
            "label": "已自动上传到 OSS",
            "detail": f"Bucket {source_bucket_name}",
        }

    if manual_url:
        parsed = urlparse(manual_url)
        host = parsed.netloc or manual_url[:80]
        return {
            "mode": "manual_url",
            "label": "已填写自定义 FileUrl",
            "detail": host,
        }

    return {
        "mode": "local_only",
        "label": "仅本地保存",
        "detail": "尚未生成云端地址",
    }


def transcript_local_path(entry: dict[str, Any]) -> Path:
    return TRANSCRIPT_UPLOADS_DIR / str(entry.get("stored_name") or "").strip()


def refresh_transcript_source_url(entry: dict[str, Any]) -> str:
    bucket_name = str(entry.get("source_bucket_name") or "").strip()
    object_key = str(entry.get("source_object_key") or "").strip()
    if not bucket_name or not object_key:
        return str(entry.get("file_url_hint") or "").strip()

    signed_payload = build_signed_url(bucket_name=bucket_name, object_key=object_key)
    entry["file_url_hint"] = signed_payload["file_url"][:2000]
    entry["source_url_expires_at"] = signed_payload["expires_at"]
    entry["updated_at"] = now_iso()
    return entry["file_url_hint"]


def ensure_transcript_source_url(entry: dict[str, Any]) -> str:
    if entry.get("source_bucket_name") and entry.get("source_object_key"):
        return refresh_transcript_source_url(entry)

    manual_url = str(entry.get("file_url_hint") or "").strip()
    if manual_url:
        return manual_url

    local_path = transcript_local_path(entry)
    if not local_path.exists():
        raise RuntimeError("本地源文件不存在，请重新上传后再试。")

    upload_payload = upload_file_for_tingwu(
        local_path,
        original_name=str(entry.get("original_name") or "").strip(),
        transcript_id=str(entry.get("id") or "").strip(),
    )
    entry["source_bucket_name"] = upload_payload["bucket_name"]
    entry["source_object_key"] = upload_payload["object_key"]
    entry["source_endpoint"] = upload_payload["endpoint"]
    entry["source_region_id"] = upload_payload["region_id"]
    entry["file_url_hint"] = upload_payload["file_url"][:2000]
    entry["source_url_expires_at"] = upload_payload["expires_at"]
    entry["updated_at"] = now_iso()
    return entry["file_url_hint"]


def build_transcript_feature_chips(entry: dict[str, Any]) -> list[str]:
    chips = [
        TRANSCRIPT_MEDIA_KIND_LABELS.get(entry["media_kind"], "媒体"),
        TRANSCRIPT_SOURCE_LANGUAGE_LABELS.get(entry["source_language"], entry["source_language"]),
        TRANSCRIPT_OUTPUT_LEVEL_LABELS.get(entry["output_level"], entry["output_level"]),
    ]

    if entry["diarization_enabled"]:
        chips.append(f"说话人分离 · {entry['speaker_count']} 人")
    if entry["auto_chapters_enabled"]:
        chips.append("自动章节分段")
    if entry["meeting_assistance_enabled"]:
        assistance_labels = [
            TRANSCRIPT_MEETING_ASSISTANCE_LABELS[value]
            for value in entry["meeting_assistance_types"]
            if value in TRANSCRIPT_MEETING_ASSISTANCE_LABELS
        ]
        chips.append("会议提炼" + (f" · {' / '.join(assistance_labels)}" if assistance_labels else ""))
    if entry["summarization_enabled"]:
        summary_labels = [
            TRANSCRIPT_SUMMARIZATION_LABELS[value]
            for value in entry["summarization_types"]
            if value in TRANSCRIPT_SUMMARIZATION_LABELS
        ]
        chips.append("摘要" + (f" · {' / '.join(summary_labels)}" if summary_labels else ""))
    if entry["text_polish_enabled"]:
        chips.append("文字润色")
    if entry["ppt_extraction_enabled"]:
        chips.append("PPT 提取")
    if entry["custom_prompt_enabled"]:
        chips.append("自定义 Prompt")

    return chips


def build_transcript_card(entry: dict[str, Any]) -> dict[str, Any]:
    status_meta = TRANSCRIPT_STATUS_META.get(entry["status"], TRANSCRIPT_STATUS_META["pending_api"])
    transcript_html = entry.get("transcript_html", "")
    transcript_text = entry.get("transcript_text", "")
    has_transcript_content = bool(transcript_html and transcript_text)
    has_remote_task = bool(entry.get("provider_task_id"))
    has_file_url = bool(str(entry.get("file_url_hint") or "").strip())
    source_meta = build_transcript_source_meta(entry)
    linked_symbols = transcript_linked_symbols(entry)
    linked_symbol = linked_symbols[0] if linked_symbols else ""
    linked_search_symbol = linked_symbol if len(linked_symbols) == 1 else ""

    return {
        **entry,
        "linked_symbol": linked_symbol,
        "linked_symbols": linked_symbols,
        "linked_symbols_label": "；".join(linked_symbols),
        "linked_symbol_count": len(linked_symbols),
        "linked_search_symbol": linked_search_symbol,
        "display_title": entry["title"] or fallback_title(Path(entry["original_name"])),
        "display_created_at": format_iso_timestamp(entry["created_at"]),
        "display_updated_at": format_iso_timestamp(entry["updated_at"]),
        "meeting_date_label": entry["meeting_date"] or "未设置会议日期",
        "status_label": status_meta["label"],
        "status_tone": status_meta["tone"],
        "media_kind_label": TRANSCRIPT_MEDIA_KIND_LABELS.get(entry["media_kind"], "媒体"),
        "provider_status_label": build_provider_status_label(entry.get("provider_task_status")),
        "source_language_label": TRANSCRIPT_SOURCE_LANGUAGE_LABELS.get(
            entry["source_language"], entry["source_language"]
        ),
        "output_level_label": TRANSCRIPT_OUTPUT_LEVEL_LABELS.get(entry["output_level"], entry["output_level"]),
        "summary_excerpt": summarize_text_block(transcript_text) if transcript_text else TRANSCRIPT_PLACEHOLDER_COPY,
        "feature_chips": build_transcript_feature_chips(entry),
        "has_transcript_content": has_transcript_content,
        "reader_content_html": transcript_html or plain_text_to_html(TRANSCRIPT_PLACEHOLDER_COPY),
        "can_submit": not has_remote_task,
        "can_sync": has_remote_task and entry["status"] in {"queued", "processing", "completed"},
        "has_file_url_hint": has_file_url,
        "has_remote_task": has_remote_task,
        "display_submitted_at": format_iso_timestamp(entry["submitted_at"]) if entry.get("submitted_at") else "未提交",
        "display_last_synced_at": format_iso_timestamp(entry["last_synced_at"]) if entry.get("last_synced_at") else "尚未同步",
        "last_error": str(entry.get("last_error") or "").strip(),
        "source_mode": source_meta["mode"],
        "source_status_label": source_meta["label"],
        "source_status_detail": source_meta["detail"],
    }


def build_transcript_cards(
    store: dict[str, Any],
    *,
    symbol_filter: str | None = None,
) -> list[dict[str, Any]]:
    cards = [
        build_transcript_card(entry)
        for entry in store.get("transcripts", [])
        if not symbol_filter or transcript_matches_symbol(entry, symbol_filter)
    ]
    cards.sort(
        key=lambda item: (
            item.get("meeting_date") or item["created_at"],
            item["id"],
        ),
        reverse=True,
    )
    return cards


def build_transcript_stats_payload(transcript_cards: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(transcript_cards),
        "completed": sum(1 for item in transcript_cards if item["status"] == "completed"),
        "queue": sum(1 for item in transcript_cards if item["status"] != "completed"),
        "linked": sum(1 for item in transcript_cards if item.get("linked_symbols")),
        "active": sum(1 for item in transcript_cards if item["status"] in {"queued", "processing"}),
    }


def build_transcript_page_context(
    store: dict[str, Any],
    *,
    requested_symbol: str = "",
) -> dict[str, Any]:
    stock_options = build_stock_selector_options(store)
    available_symbols = {item["symbol"] for item in stock_options}
    preferred_symbol = requested_symbol if requested_symbol in available_symbols else ""
    transcript_cards = build_transcript_cards(store)
    transcript_stats = build_transcript_stats_payload(transcript_cards)

    return {
        "stock_options": stock_options,
        "preferred_symbol": preferred_symbol,
        "transcripts": transcript_cards,
        "completed_transcripts": [item for item in transcript_cards if item["status"] == "completed"],
        "queue_transcripts": [item for item in transcript_cards if item["status"] != "completed"],
        "transcript_stats": {
            "total_count": transcript_stats["total"],
            "linked_count": transcript_stats["linked"],
            "completed_count": transcript_stats["completed"],
            "active_count": transcript_stats["active"],
            "submittable_count": sum(1 for item in transcript_cards if item["can_submit"]),
        },
    }


def normalize_provider_task_status(value: str | None) -> str:
    raw = str(value or "").strip()
    upper = raw.upper()

    if not raw:
        return "pending_api"
    if any(token in upper for token in ("SUCCESS", "SUCCEEDED", "COMPLETE", "COMPLETED", "FINISH", "DONE")):
        return "completed"
    if any(token in upper for token in ("FAIL", "FAILED", "ERROR", "CANCEL", "ABORT", "REJECT")):
        return "failed"
    if any(token in upper for token in ("RUN", "PROCESS", "PROGRESS", "ONGOING", "EXECUTING")):
        return "processing"
    if any(token in upper for token in ("QUEUE", "PENDING", "CREATED", "INIT", "SUBMITTED", "WAIT")):
        return "queued"

    return "processing"


def build_provider_status_label(value: str | None) -> str:
    raw = str(value or "").strip()
    return raw or "未提交"


def format_media_timestamp(value: Any) -> str:
    try:
        total_seconds = max(int(value) // 1000, 0)
    except (TypeError, ValueError):
        return ""

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def should_insert_token_space(previous: str, current: str) -> bool:
    if not previous or not current:
        return False

    previous_last = previous[-1]
    current_first = current[0]
    no_space_before = set(",.!?;:%)]}，。！？；：）】》、")
    no_space_after = set("([{【《")

    if previous_last.isspace() or current_first.isspace():
        return False
    if current_first in no_space_before or previous_last in no_space_after:
        return False
    if len(previous) == 1 and len(current) == 1 and previous.isascii() and current.isascii():
        if previous.isalnum() and current.isalnum():
            return False
    if previous_last.isascii() and current_first.isascii():
        return previous_last.isalnum() and current_first.isalnum()
    return False


def join_transcript_tokens(tokens: list[str]) -> str:
    pieces: list[str] = []
    for raw_token in tokens:
        token = str(raw_token or "").strip()
        if not token:
            continue
        if not pieces:
            pieces.append(token)
            continue
        if should_insert_token_space(pieces[-1], token):
            pieces.append(" " + token)
        else:
            pieces.append(token)
    return trim_note_content("".join(pieces))


def render_html_paragraph(value: str) -> str:
    return escape(value).replace("\n", "<br>")


def build_transcription_dialogue_section(value: Any) -> tuple[str, str] | None:
    container = value.get("Transcription") if isinstance(value, dict) and isinstance(value.get("Transcription"), dict) else value
    paragraphs = container.get("Paragraphs") if isinstance(container, dict) else None
    if not isinstance(paragraphs, list):
        return None

    text_lines: list[str] = []
    html_parts = [f"<h3>{escape(TRANSCRIPT_RESULT_SECTION_LABELS['transcription'])}</h3>"]

    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            continue

        words = paragraph.get("Words")
        tokens: list[str] = []
        start_candidates: list[int] = []
        if isinstance(words, list):
            for word in words:
                if not isinstance(word, dict):
                    continue
                text_value = str(word.get("Text") or "").strip()
                if text_value:
                    tokens.append(text_value)
                try:
                    start_candidates.append(int(word.get("Start") or 0))
                except (TypeError, ValueError):
                    pass

        if not tokens:
            fallback_text = str(paragraph.get("Text") or paragraph.get("ParagraphText") or "").strip()
            if fallback_text:
                tokens = [fallback_text]

        paragraph_text = join_transcript_tokens(tokens)
        if not paragraph_text:
            continue

        speaker_id = str(paragraph.get("SpeakerId") or paragraph.get("Speaker") or "").strip()
        speaker_label = f"说话人 {speaker_id}" if speaker_id else "发言"
        paragraph_start = paragraph.get("Start")
        if not paragraph_start and start_candidates:
            paragraph_start = min(start_candidates)
        time_label = format_media_timestamp(paragraph_start)

        prefix_parts = [speaker_label]
        if time_label:
            prefix_parts.append(time_label)
        prefix = " · ".join(prefix_parts)

        text_lines.append(f"[{prefix}] {paragraph_text}")
        html_parts.append(f"<p><strong>{escape(prefix)}</strong><br>{render_html_paragraph(paragraph_text)}</p>")

    if not text_lines:
        return None

    return trim_note_content("\n\n".join(text_lines)), "".join(html_parts)


def build_text_polish_section(value: Any) -> tuple[str, str] | None:
    container = value.get("TextPolish") if isinstance(value, dict) and isinstance(value.get("TextPolish"), list) else value
    if not isinstance(container, list):
        return None

    paragraphs: list[str] = []
    html_parts = [f"<h3>{escape(TRANSCRIPT_RESULT_SECTION_LABELS['text_polish'])}</h3>"]
    for item in container:
        if not isinstance(item, dict):
            continue
        paragraph_text = trim_note_content(str(item.get("FormalParagraphText") or item.get("Text") or "").strip())
        if not paragraph_text:
            continue
        paragraphs.append(paragraph_text)
        html_parts.append(f"<p>{render_html_paragraph(paragraph_text)}</p>")

    if not paragraphs:
        return None

    return trim_note_content("\n\n".join(paragraphs)), "".join(html_parts)


def build_auto_chapters_section(value: Any) -> tuple[str, str] | None:
    container = value.get("AutoChapters") if isinstance(value, dict) and isinstance(value.get("AutoChapters"), list) else value
    if not isinstance(container, list):
        return None

    text_blocks: list[str] = []
    html_parts = [f"<h3>{escape(TRANSCRIPT_RESULT_SECTION_LABELS['auto_chapters'])}</h3>"]
    for index, item in enumerate(container, start=1):
        if not isinstance(item, dict):
            continue
        headline = trim_note_content(str(item.get("Headline") or f"章节 {index}").strip())
        summary = trim_note_content(str(item.get("Summary") or "").strip())
        start_label = format_media_timestamp(item.get("Start"))
        end_label = format_media_timestamp(item.get("End"))
        time_range = " - ".join(part for part in (start_label, end_label) if part)

        block_lines = [headline]
        if time_range:
            block_lines.append(time_range)
        if summary:
            block_lines.append(summary)
        text_blocks.append("\n".join(block_lines))

        html_parts.append(f"<h4>{escape(headline)}</h4>")
        if time_range:
            html_parts.append(f"<p><strong>{escape(time_range)}</strong></p>")
        if summary:
            html_parts.append(f"<p>{render_html_paragraph(summary)}</p>")

    if not text_blocks:
        return None

    return trim_note_content("\n\n".join(text_blocks)), "".join(html_parts)


def flatten_tingwu_result_content(value: Any) -> str:
    lines: list[str] = []
    seen: set[str] = set()

    def push(line: str) -> None:
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized or normalized in seen or normalized.startswith("http"):
            return
        seen.add(normalized)
        lines.append(normalized)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            speaker = ""
            for key in ("Speaker", "speaker", "SpeakerId", "speakerId", "Identity", "identity", "Role", "role"):
                value_text = str(node.get(key) or "").strip()
                if value_text:
                    speaker = value_text
                    break

            start_time = ""
            for key in ("BeginTime", "beginTime", "StartTime", "startTime"):
                value_text = str(node.get(key) or "").strip()
                if value_text:
                    start_time = value_text
                    break

            main_text = ""
            for key in (
                "Text",
                "text",
                "Content",
                "content",
                "Paragraph",
                "paragraph",
                "Sentence",
                "sentence",
                "Summary",
                "summary",
                "Question",
                "question",
                "Answer",
                "answer",
                "Title",
                "title",
            ):
                candidate = node.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    main_text = candidate.strip()
                    break

            if main_text:
                prefix_parts = []
                if start_time:
                    prefix_parts.append(start_time)
                if speaker:
                    prefix_parts.append(speaker)
                prefix = f"[{' | '.join(prefix_parts)}] " if prefix_parts else ""
                push(prefix + main_text)
                return

            for child in node.values():
                walk(child)
            return

        if isinstance(node, list):
            for item in node:
                walk(item)
            return

    walk(value)
    return trim_note_content("\n\n".join(lines))


def build_transcript_content_payload(result_documents: dict[str, Any]) -> tuple[str, str]:
    html_sections: list[str] = []
    text_sections: list[str] = []
    special_builders = {
        "transcription": build_transcription_dialogue_section,
        "text_polish": build_text_polish_section,
        "auto_chapters": build_auto_chapters_section,
    }

    for key, label in TRANSCRIPT_RESULT_SECTION_LABELS.items():
        if key not in result_documents:
            continue

        section_text = ""
        section_html = ""
        if key in special_builders:
            built = special_builders[key](result_documents[key])
            if built is not None:
                section_text, section_html = built

        if not section_text:
            flattened_text = flatten_tingwu_result_content(result_documents[key])
            if not flattened_text:
                raw_text = json.dumps(result_documents[key], ensure_ascii=False, indent=2)
                flattened_text = trim_note_content(raw_text)
            if flattened_text:
                section_text = flattened_text
                section_html = f"<h3>{escape(label)}</h3>{plain_text_to_html(flattened_text)}"

        if not section_text:
            continue

        text_sections.append(f"[{label}]\n{section_text}")
        html_sections.append(section_html)

    content_html = sanitize_note_html("".join(html_sections))
    content_text = trim_note_content("\n\n".join(text_sections))
    return content_html, content_text


def submit_transcript_job_to_tingwu(transcript: dict[str, Any]) -> dict[str, Any]:
    file_url = ensure_transcript_source_url(transcript)
    if not file_url:
        raise RuntimeError("当前还没有可提交到听悟的源文件地址，请稍后重试。")

    response = submit_offline_task(transcript, file_url=file_url)
    task_id = str(response.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("听悟返回成功，但没有拿到 TaskId。")

    transcript["provider_task_id"] = task_id
    transcript["provider_task_status"] = str(response.get("task_status") or "SUBMITTED")
    transcript["provider_request_id"] = str(response.get("request_id") or "").strip()[:120]
    transcript["submitted_at"] = now_iso()
    transcript["last_synced_at"] = now_iso()
    transcript["last_error"] = ""
    transcript["status"] = normalize_provider_task_status(transcript["provider_task_status"])
    transcript["updated_at"] = now_iso()
    return response


def sync_transcript_job_from_tingwu(transcript: dict[str, Any]) -> dict[str, Any]:
    task_id = str(transcript.get("provider_task_id") or "").strip()
    if not task_id:
        raise RuntimeError("当前任务还没有提交到听悟。")

    task_info = get_task_info(task_id)
    transcript["provider_task_status"] = str(task_info.get("task_status") or transcript.get("provider_task_status") or "")
    transcript["provider_request_id"] = str(task_info.get("request_id") or transcript.get("provider_request_id") or "")[:120]
    transcript["last_synced_at"] = now_iso()
    transcript["updated_at"] = now_iso()
    transcript["last_error"] = str(task_info.get("error_message") or task_info.get("message") or "").strip()[:2000]
    transcript["provider_result_urls"] = dict(task_info.get("result_urls") or {})
    transcript["status"] = normalize_provider_task_status(transcript["provider_task_status"])

    if transcript["status"] == "completed":
        result_documents = fetch_result_documents(transcript["provider_result_urls"])
        content_html, content_text = build_transcript_content_payload(result_documents)
        if content_text:
            transcript["transcript_html"] = content_html
            transcript["transcript_text"] = content_text
        elif transcript.get("last_error"):
            transcript["status"] = "failed"
        else:
            transcript["last_error"] = "任务已完成，但暂未拉取到可展示的结果内容。"

    if transcript["status"] == "failed" and not transcript.get("last_error"):
        transcript["last_error"] = "听悟任务返回失败状态，请检查 FileUrl、音视频格式或云端任务详情。"

    return task_info


def build_file_type_breakdown(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(
        str(item.get("file_type") or detect_file_type_label(str(item.get("title") or "")))
        for item in entries
    )
    return [
        {"label": label, "count": count}
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def build_period_activity_stats(entries: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    matched_entries = [item for item in entries if item["date"].startswith(prefix)]
    file_entries = [item for item in matched_entries if item["kind"] == "file"]
    note_entries = [item for item in matched_entries if item["kind"] == "note"]

    return {
        "total_count": len(matched_entries),
        "note_count": len(note_entries),
        "file_count": len(file_entries),
        "active_days": len({item["date"] for item in matched_entries}),
        "file_types": build_file_type_breakdown(file_entries),
    }


def build_available_years(entries: list[dict[str, Any]], selected_year: int) -> list[int]:
    years = {selected_year, datetime.now().year}
    for item in entries:
        try:
            years.add(int(str(item["date"])[:4]))
        except (TypeError, ValueError):
            continue

    return sorted(years, reverse=True)


def build_stock_activity(store: dict[str, Any], symbol_filter: str | None = None) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []

    symbols = [symbol_filter] if symbol_filter else sorted(list_stock_symbols(store))

    for symbol in symbols:
        entry = ensure_stock_entry(store, symbol)

        for note in entry["notes"]:
            activity_date = iso_to_date(note.get("created_at"))
            if not activity_date:
                continue

            note_id = str(note.get("id") or "").strip()
            detail_url = url_for("stock_detail", symbol=symbol)
            if note_id:
                detail_url = f"{detail_url}#note-{note_id}"

            entries.append(
                {
                    "date": activity_date,
                    "timestamp": str(note.get("created_at") or ""),
                    "kind": "note",
                    "kind_label": "笔记",
                    "symbol": symbol,
                    "title": note.get("title") or "未命名笔记",
                    "summary": (note.get("content_text") or "").strip()[:180],
                    "display_time": note_display_time(note),
                    "anchor": "notes-panel",
                    "detail_url": detail_url,
                    "detail_label": "打开笔记",
                    "item_id": note_id,
                }
            )

        for file_entry in entry["files"]:
            activity_date = iso_to_date(file_entry.get("uploaded_at"))
            if not activity_date:
                continue

            file_id = str(file_entry.get("id") or "").strip()
            detail_url = url_for("stock_detail", symbol=symbol)
            download_url = None
            if file_id:
                detail_url = f"{detail_url}#file-{file_id}"
                download_url = url_for("download_stock_file", symbol=symbol, file_id=file_id)

            entries.append(
                {
                    "date": activity_date,
                    "timestamp": str(file_entry.get("uploaded_at") or ""),
                    "kind": "file",
                    "kind_label": "文件",
                    "symbol": symbol,
                    "title": file_entry.get("original_name") or "已上传文件",
                    "summary": (file_entry.get("description") or "").strip()[:180],
                    "display_time": file_display_time(file_entry),
                    "file_type": detect_file_type_label(str(file_entry.get("original_name") or "")),
                    "anchor": "files-panel",
                    "detail_url": detail_url,
                    "detail_label": "打开资料",
                    "download_url": download_url,
                    "item_id": file_id,
                }
            )

    entries.sort(
        key=lambda item: (item["date"], item["timestamp"], item["symbol"], item["title"]),
        reverse=True,
    )

    summaries: dict[str, dict[str, Any]] = {}
    for item in entries:
        day = summaries.setdefault(
            item["date"],
            {
                "date": item["date"],
                "items": [],
                "note_count": 0,
                "file_count": 0,
                "file_type_counter": Counter(),
                "symbols": set(),
            },
        )
        day["items"].append(item)
        day["symbols"].add(item["symbol"])
        if item["kind"] == "note":
            day["note_count"] += 1
        else:
            day["file_count"] += 1
            day["file_type_counter"][str(item.get("file_type") or "未知类型")] += 1

    for day in summaries.values():
        day["items"].sort(
            key=lambda item: (item["timestamp"], item["symbol"], item["title"]),
            reverse=True,
        )
        day["stock_count"] = len(day["symbols"])
        day["total_count"] = day["note_count"] + day["file_count"]
        day["file_types"] = [
            {"label": label, "count": count}
            for label, count in sorted(day["file_type_counter"].items(), key=lambda item: (-item[1], item[0]))
        ]
        day.pop("file_type_counter", None)
        day.pop("symbols", None)

    return {
        "entries": entries,
        "summaries": summaries,
    }


def find_month_default_date(activity_summaries: dict[str, dict[str, Any]], month_value: datetime) -> str | None:
    month_prefix = month_value.strftime("%Y-%m")
    matching_dates = sorted(
        [date for date in activity_summaries.keys() if date.startswith(month_prefix)],
        reverse=True,
    )
    return matching_dates[0] if matching_dates else None


def build_activity_totals(activity: dict[str, Any]) -> dict[str, int]:
    return {
        "days": len(activity["summaries"]),
        "total_items": len(activity["entries"]),
        "notes": sum(day["note_count"] for day in activity["summaries"].values()),
        "files": sum(day["file_count"] for day in activity["summaries"].values()),
    }


def build_activity_calendar_context(
    activity: dict[str, Any],
    *,
    month_param: str | None,
    year_param: str | None = None,
    month_number_param: str | None = None,
    date_param: str | None,
) -> dict[str, Any]:
    selected_date_value = parse_iso_date_value(date_param)
    fallback_month = selected_date_value or (
        parse_iso_date_value(activity["entries"][0]["date"]) if activity["entries"] else None
    )
    month_value = resolve_month_value(
        month_param=month_param,
        year_param=year_param,
        month_number_param=month_number_param,
        fallback=fallback_month,
    )
    selected_date = selected_date_value.date().isoformat() if selected_date_value else None

    if not selected_date or not selected_date.startswith(month_value.strftime("%Y-%m")):
        selected_date = find_month_default_date(activity["summaries"], month_value)

    previous_year, previous_month = shift_month(month_value.year, month_value.month, -1)
    next_year, next_month = shift_month(month_value.year, month_value.month, 1)
    month_key = month_value.strftime("%Y-%m")
    year_key = f"{month_value.year:04d}"
    month_stats = build_period_activity_stats(activity["entries"], month_key)
    year_stats = build_period_activity_stats(activity["entries"], year_key)

    return {
        "month_value": month_value,
        "month_key": month_key,
        "month_label": month_value.strftime("%Y 年 %m 月"),
        "previous_month_key": f"{previous_year:04d}-{previous_month:02d}",
        "next_month_key": f"{next_year:04d}-{next_month:02d}",
        "current_month_key": datetime.now().strftime("%Y-%m"),
        "selected_year": month_value.year,
        "selected_month_number": month_value.month,
        "available_years": build_available_years(activity["entries"], month_value.year),
        "month_options": [{"value": month, "label": f"{month} 月"} for month in range(1, 13)],
        "selected_date": selected_date,
        "selected_summary": activity["summaries"].get(selected_date) if selected_date else None,
        "calendar_weeks": build_calendar_weeks(month_value, activity["summaries"], selected_date),
        "activity_totals": build_activity_totals(activity),
        "month_stats": month_stats,
        "year_stats": year_stats,
        "month_total": month_stats["total_count"],
        "month_active_days": month_stats["active_days"],
        "weekday_labels": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
    }


def build_calendar_weeks(
    month_value: datetime,
    activity_summaries: dict[str, dict[str, Any]],
    selected_date: str | None,
    *,
    range_start: str | None = None,
    range_end: str | None = None,
) -> list[list[dict[str, Any]]]:
    month_weeks: list[list[dict[str, Any]]] = []
    today = datetime.now().date().isoformat()
    calendar_builder = calendar.Calendar(firstweekday=0)

    for week in calendar_builder.monthdatescalendar(month_value.year, month_value.month):
        month_weeks.append(
            [
                {
                    "date": day.isoformat(),
                    "day_number": day.day,
                    "is_current_month": day.month == month_value.month,
                    "is_today": day.isoformat() == today,
                    "is_selected": day.isoformat() == selected_date,
                    "is_in_range": bool(
                        range_start
                        and range_end
                        and range_start <= day.isoformat() <= range_end
                    ),
                    "summary": activity_summaries.get(day.isoformat()),
                }
                for day in week
            ]
        )

    return month_weeks


def parse_report_datetime(path: Path) -> tuple[datetime | None, bool]:
    filename = path.stem

    for pattern, format_string, has_time in FILENAME_DATETIME_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue

        raw_value = "".join(value for value in match.groupdict().values() if value)
        try:
            return datetime.strptime(raw_value, format_string), has_time
        except ValueError:
            continue

    return None, False


def format_report_datetime(value: datetime, has_time: bool) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if has_time else value.strftime("%Y-%m-%d")


def validate_report_name(filename: str) -> Path:
    safe_name = Path(filename).name
    if safe_name != filename:
        abort(404)

    report_path = REPORTS_DIR / safe_name
    if not report_path.is_file() or report_path.suffix.lower() not in REPORT_SUFFIXES:
        abort(404)

    return report_path


def collect_reports() -> list[dict[str, Any]]:
    reports, _ = get_report_catalog()
    return [serialize_report_entry(report) for report in reports]


def load_report(filename: str) -> dict[str, Any]:
    validate_report_name(filename)
    _, reports_by_filename = get_report_catalog()
    report_entry = reports_by_filename.get(filename)
    if report_entry is None:
        abort(404)
    return serialize_report_entry(report_entry, include_html=True)


def iter_report_paths_in(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    return sorted(
        [
            report_path
            for report_path in directory.iterdir()
            if report_path.is_file() and report_path.suffix.lower() in REPORT_SUFFIXES
        ],
        key=lambda path: path.name.lower(),
    )


def collect_reports_from_directory(directory: Path) -> list[dict[str, Any]]:
    items = [build_report_catalog_entry(report_path) for report_path in iter_report_paths_in(directory)]
    items.sort(key=lambda item: (item["sort_key"], item["filename"]), reverse=True)
    return [serialize_report_entry(item) for item in items]


def validate_report_name_in_directory(filename: str, directory: Path) -> Path:
    safe_name = Path(filename).name
    if safe_name != filename:
        abort(404)

    report_path = directory / safe_name
    if not report_path.is_file() or report_path.suffix.lower() not in REPORT_SUFFIXES:
        abort(404)

    return report_path


def load_report_from_directory(filename: str, directory: Path) -> dict[str, Any]:
    report_path = validate_report_name_in_directory(filename, directory)
    return serialize_report_entry(build_report_catalog_entry(report_path), include_html=True)


def find_related_reports(symbol: str, limit: int = 6) -> list[dict[str, Any]]:
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", re.IGNORECASE)
    related: list[dict[str, Any]] = []

    reports, _ = get_report_catalog()
    for report in reports:
        if (
            pattern.search(report["title"])
            or pattern.search(report["summary"])
            or pattern.search(report["filename"])
            or pattern.search(report["content"])
        ):
            related.append(serialize_report_entry(report))

        if len(related) >= limit:
            break

    return related


def guess_lan_url(port: int) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        host = sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()

    return f"http://{host}:{port}"


def normalize_stock_symbol(raw: str | None) -> str | None:
    if not raw:
        return None

    cleaned = raw.strip().upper().lstrip("$")
    cleaned = re.sub(r"[^A-Z0-9.\-]", "", cleaned)
    if not cleaned or not STOCK_SYMBOL_PATTERN.fullmatch(cleaned):
        return None

    return cleaned


def parse_symbol_list(raw: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    normalized_raw = unicodedata.normalize("NFKC", str(raw or ""))

    for chunk in re.split(r"[\s,;]+", normalized_raw.strip()):
        symbol = normalize_stock_symbol(chunk)
        if not symbol or symbol in seen:
            continue

        seen.add(symbol)
        symbols.append(symbol)

    return symbols


def normalize_stock_symbol_list(raw_values: Any) -> list[str]:
    if isinstance(raw_values, str):
        return parse_symbol_list(raw_values)

    if not isinstance(raw_values, (list, tuple, set)):
        return []

    return ordered_unique(
        [
            symbol
            for raw_symbol in raw_values
            if (symbol := normalize_stock_symbol(str(raw_symbol)))
        ]
    )


def transcript_linked_symbols(entry: dict[str, Any]) -> list[str]:
    linked_symbols = normalize_stock_symbol_list(entry.get("linked_symbols"))
    if single_symbol := normalize_stock_symbol(str(entry.get("linked_symbol") or "")):
        linked_symbols = ordered_unique(linked_symbols + [single_symbol])
    return linked_symbols


def transcript_matches_symbol(entry: dict[str, Any], symbol: str | None) -> bool:
    normalized_symbol = normalize_stock_symbol(symbol)
    if not normalized_symbol:
        return False
    return normalized_symbol in transcript_linked_symbols(entry)


def touch_transcript_stocks(store: dict[str, Any], transcript: dict[str, Any]) -> None:
    for symbol in transcript_linked_symbols(transcript):
        touch_stock(store, symbol)


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        ordered.append(value)

    return ordered


def parse_monitor_stock_pool(raw: str) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()

    for chunk in re.split(r"[\s,;；]+", str(raw or "").strip()):
        symbol = normalize_stock_symbol(chunk)
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)

    return symbols


def default_monitor_config() -> dict[str, Any]:
    stock_pool = ["FTAI", "GE", "APP", "AXON"]
    codex_path = "codex"
    workdir = str(DEFAULT_MONITOR_SOURCE_DIR if DEFAULT_MONITOR_SOURCE_DIR.exists() else BASE_DIR)
    timeout_seconds = 900

    raw_original = load_json(ORIGINAL_MONITOR_CONFIG_PATH)
    if raw_original:
        stock_pool = normalize_stock_symbol_list(raw_original.get("stock_pool")) or stock_pool
        codex_path = str(raw_original.get("codex_path") or codex_path).strip() or codex_path
        raw_workdir = str(raw_original.get("workdir") or "").strip()
        if raw_workdir:
            workdir = raw_workdir
        try:
            timeout_seconds = max(120, int(raw_original.get("timeout_seconds") or timeout_seconds))
        except (TypeError, ValueError):
            timeout_seconds = 900

    if DEFAULT_MONITOR_SOURCE_DIR.exists():
        workdir = str(DEFAULT_MONITOR_SOURCE_DIR)

    return {
        "stock_pool": stock_pool,
        "codex_path": codex_path,
        "workdir": workdir,
        "timeout_seconds": timeout_seconds,
        "updated_at": now_iso(),
    }


def normalize_monitor_config(raw: Any) -> dict[str, Any]:
    baseline = default_monitor_config()
    source = raw if isinstance(raw, dict) else {}
    stock_pool = normalize_stock_symbol_list(source.get("stock_pool")) or baseline["stock_pool"]
    codex_path = str(source.get("codex_path") or baseline["codex_path"]).strip() or baseline["codex_path"]
    workdir = str(source.get("workdir") or baseline["workdir"]).strip() or baseline["workdir"]
    try:
        timeout_seconds = max(120, int(source.get("timeout_seconds") or baseline["timeout_seconds"]))
    except (TypeError, ValueError):
        timeout_seconds = baseline["timeout_seconds"]

    return {
        "stock_pool": stock_pool,
        "codex_path": codex_path,
        "workdir": workdir,
        "timeout_seconds": timeout_seconds,
        "updated_at": str(source.get("updated_at") or baseline["updated_at"]),
    }


def load_monitor_config() -> dict[str, Any]:
    MONITOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MONITOR_CONFIG_PATH.exists():
        config = normalize_monitor_config({})
        save_monitor_config(config)
        return config
    return normalize_monitor_config(load_json(MONITOR_CONFIG_PATH))


def save_monitor_config(config: dict[str, Any]) -> None:
    normalized = normalize_monitor_config(config)
    MONITOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MONITOR_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(MONITOR_CONFIG_PATH)


def normalize_monitor_runtime(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "run_id": str(source.get("run_id") or "").strip(),
        "status": str(source.get("status") or "idle").strip() or "idle",
        "pid": int(source.get("pid") or 0),
        "stock_pool": normalize_stock_symbol_list(source.get("stock_pool")),
        "started_at": str(source.get("started_at") or "").strip(),
        "finished_at": str(source.get("finished_at") or "").strip(),
        "report_path": str(source.get("report_path") or "").strip(),
        "report_filename": str(source.get("report_filename") or "").strip(),
        "meta_path": str(source.get("meta_path") or "").strip(),
        "stdout_path": str(source.get("stdout_path") or "").strip(),
        "stderr_path": str(source.get("stderr_path") or "").strip(),
        "message": str(source.get("message") or "").strip(),
        "error": str(source.get("error") or "").strip(),
        "termination_requested": bool(source.get("termination_requested")),
    }


def load_monitor_runtime() -> dict[str, Any]:
    MONITOR_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MONITOR_RUNTIME_PATH.exists():
        runtime = normalize_monitor_runtime({})
        save_monitor_runtime(runtime)
        return runtime
    return normalize_monitor_runtime(load_json(MONITOR_RUNTIME_PATH))


def save_monitor_runtime(runtime: dict[str, Any]) -> None:
    normalized = normalize_monitor_runtime(runtime)
    MONITOR_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MONITOR_RUNTIME_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(MONITOR_RUNTIME_PATH)


def monitor_runtime_status_label(status: str) -> str:
    mapping = {
        "idle": "待运行",
        "running": "运行中",
        "completed": "已完成",
        "failed": "运行失败",
        "terminated": "已终止",
        "timeout": "超时结束",
        "error": "运行异常",
    }
    return mapping.get(status, "待运行")


def monitor_runtime_status_tone(status: str) -> str:
    mapping = {
        "idle": "pending",
        "running": "info",
        "completed": "success",
        "failed": "danger",
        "terminated": "danger",
        "timeout": "danger",
        "error": "danger",
    }
    return mapping.get(status, "pending")


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def is_monitor_report_entry(report: dict[str, Any]) -> bool:
    title = str(report.get("title") or "").strip().lower()
    filename = str(report.get("filename") or "").strip().lower()
    if title == "stock monitor report":
        return True
    return "manual_run" in filename or "auto_0700" in filename


def collect_monitor_reports() -> list[dict[str, Any]]:
    return [report for report in collect_reports() if is_monitor_report_entry(report)]


def monitor_report_sort_datetime(report: dict[str, Any]) -> datetime:
    report_path = REPORTS_DIR / str(report.get("filename") or "")
    parsed_datetime, _ = parse_report_datetime(report_path)
    if parsed_datetime is not None:
        return parsed_datetime
    try:
        return datetime.fromtimestamp(report_path.stat().st_mtime)
    except OSError:
        return datetime.min


def collect_today_monitor_reports(reports: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    reports = reports if reports is not None else collect_monitor_reports()
    today_text = datetime.now().strftime("%Y-%m-%d")
    today_compact = datetime.now().strftime("%Y%m%d")
    items: list[dict[str, Any]] = []
    for report in reports:
        filename = str(report.get("filename") or "")
        report_date = str(report.get("report_date") or "")
        if filename.startswith(today_compact) or report_date.startswith(today_text):
            items.append(report)
    return items


def resolve_monitor_result_status(meta_status: str) -> str:
    normalized = str(meta_status or "").strip().lower()
    if normalized == "success":
        return "completed"
    if normalized in {"timeout"}:
        return "timeout"
    if normalized in {"failed", "error"}:
        return "failed"
    return normalized or "idle"


def sync_monitor_runtime(runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    with MONITOR_PROCESS_LOCK:
        current = normalize_monitor_runtime(runtime or load_monitor_runtime())
        if current["status"] != "running":
            save_monitor_runtime(current)
            return current

        if is_process_running(current["pid"]):
            save_monitor_runtime(current)
            return current

        meta_path = Path(current["meta_path"]) if current["meta_path"] else None
        meta = load_json(meta_path) if meta_path and meta_path.exists() else {}
        if meta:
            current["status"] = resolve_monitor_result_status(meta.get("status", ""))
            current["finished_at"] = str(meta.get("finished_at") or now_iso())
            current["report_path"] = str(meta.get("report_path") or current["report_path"])
            current["report_filename"] = Path(current["report_path"]).name if current["report_path"] else ""
            current["message"] = "监测结果已写入报告目录。" if current["status"] == "completed" else ""
            current["error"] = str(meta.get("error_message") or "")
        elif current["termination_requested"]:
            current["status"] = "terminated"
            current["finished_at"] = current["finished_at"] or now_iso()
            current["message"] = "监测任务已终止。"
        else:
            current["status"] = "failed"
            current["finished_at"] = now_iso()
            current["error"] = current["error"] or "进程提前退出，未找到完整的结果文件。"

        current["pid"] = 0
        current["termination_requested"] = False
        save_monitor_runtime(current)
        return current


def terminate_monitor_process(runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    with MONITOR_PROCESS_LOCK:
        current = sync_monitor_runtime(runtime)
        if current["status"] != "running":
            return current

        pid = int(current.get("pid") or 0)
        if pid > 0:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        current["status"] = "terminated"
        current["pid"] = 0
        current["termination_requested"] = False
        current["finished_at"] = now_iso()
        current["message"] = "监测任务已终止。"
        save_monitor_runtime(current)
        return current


def start_monitor_process(stock_pool: list[str]) -> dict[str, Any]:
    with MONITOR_PROCESS_LOCK:
        current = sync_monitor_runtime()
        if current["status"] == "running":
            raise RuntimeError("程序已在运行。")

        config = load_monitor_config()
        resolved_codex_path = discover_monitor_codex_path(config.get("codex_path", "")) or config.get("codex_path", "codex")
        check_monitor_codex_login(resolved_codex_path)

        MONITOR_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        MONITOR_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        MONITOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        run_id = uuid.uuid4().hex[:12]
        started_at = now_iso()
        stdout_path = MONITOR_LOGS_DIR / f"{run_id}.launcher.stdout.log"
        stderr_path = MONITOR_LOGS_DIR / f"{run_id}.launcher.stderr.log"
        meta_path = MONITOR_LOGS_DIR / f"{run_id}.meta.json"

        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(MONITOR_RUNNER_PATH),
                    "--stocks",
                    ";".join(stock_pool),
                    "--codex-path",
                    resolved_codex_path,
                    "--workdir",
                    str(config["workdir"]),
                    "--timeout-seconds",
                    str(config["timeout_seconds"]),
                    "--output-dir",
                    str(REPORTS_DIR),
                    "--prompt-dir",
                    str(MONITOR_PROMPTS_DIR),
                    "--log-dir",
                    str(MONITOR_LOGS_DIR),
                    "--trigger",
                    "manual_run",
                    "--run-id",
                    run_id,
                    "--meta-path",
                    str(meta_path),
                    "--runtime-path",
                    str(MONITOR_RUNTIME_PATH),
                ],
                stdout=stdout_handle,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                cwd=str(BASE_DIR),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

        runtime = {
            "run_id": run_id,
            "status": "running",
            "pid": process.pid,
            "stock_pool": stock_pool,
            "started_at": started_at,
            "finished_at": "",
            "report_path": "",
            "report_filename": "",
            "meta_path": str(meta_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "message": "",
            "error": "",
            "termination_requested": False,
        }
        save_monitor_runtime(runtime)

        config["stock_pool"] = stock_pool
        config["codex_path"] = resolved_codex_path
        config["updated_at"] = now_iso()
        save_monitor_config(config)
        return runtime


def build_monitor_suggestions(stock_store: dict[str, Any], config: dict[str, Any]) -> list[str]:
    suggestions = ordered_unique(
        normalize_stock_symbol_list(config.get("stock_pool"))
        + list_stock_symbols(stock_store)
        + ["FTAI", "GE", "APP", "AXON"]
    )
    return suggestions


def build_monitor_report_cards(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    today_compact = datetime.now().strftime("%Y%m%d")
    for report in reports:
        filename = str(report.get("filename") or "")
        cards.append(
            {
                **report,
                "is_today": filename.startswith(today_compact),
            }
        )
    return cards


def build_monitor_page_context(stock_store: dict[str, Any]) -> dict[str, Any]:
    config = load_monitor_config()
    runtime = sync_monitor_runtime()
    reports = collect_monitor_reports()
    today_reports = collect_today_monitor_reports(reports)
    latest_report = reports[0] if reports else None
    return {
        "monitor_config": config,
        "monitor_runtime": {
            **runtime,
            "status_label": monitor_runtime_status_label(runtime["status"]),
            "status_tone": monitor_runtime_status_tone(runtime["status"]),
            "is_running": runtime["status"] == "running",
            "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未运行",
            "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未完成",
        },
        "monitor_reports": build_monitor_report_cards(reports),
        "monitor_today_reports": today_reports,
        "monitor_latest_report": latest_report,
        "monitor_stock_suggestions": build_monitor_suggestions(stock_store, config),
        "monitor_status_poll_seconds": MONITOR_STATUS_POLL_INTERVAL_SECONDS,
    }


def get_monitor_report(report_name: str) -> dict[str, Any]:
    report = load_report(report_name)
    if not is_monitor_report_entry(report):
        abort(404)
    return report


def move_monitor_report_to_trash(store: dict[str, Any], report_name: str) -> dict[str, Any]:
    report = get_monitor_report(report_name)
    report_path = validate_report_name(report_name)
    MONITOR_TRASH_DIR.mkdir(parents=True, exist_ok=True)
    trash_file_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{report_path.name}"
    trash_path = MONITOR_TRASH_DIR / trash_file_name
    report_path.replace(trash_path)
    trash_entry = create_trash_entry(
        "monitor_report",
        {
            "filename": report_path.name,
            "trash_path": str(trash_path),
            "title": report["title"],
            "summary": report["summary"],
            "report_date": report["report_date"],
            "deleted_from": "monitor",
        },
        title=report["title"],
    )
    append_to_trash(store, trash_entry)
    return trash_entry


def build_signal_source_id(seed: str, existing_ids: set[str]) -> str:
    ascii_name = unicodedata.normalize("NFKD", seed).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "source"
    candidate = slug
    index = 2
    while candidate in existing_ids:
        candidate = f"{slug}-{index}"
        index += 1
    return candidate


def extract_signal_x_handle(raw_value: Any) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""

    parsed_text = text
    if "x.com/" in text.lower() or "twitter.com/" in text.lower():
        parsed = urlparse(text if "://" in text else f"https://{text}")
        parsed_text = parsed.path.strip("/").split("/")[0] if parsed.path.strip("/") else ""

    parsed_text = parsed_text.lstrip("@")
    candidate = re.sub(r"[^A-Za-z0-9_]", "", parsed_text)
    if not candidate:
        return ""
    return candidate[:15]


def normalize_signal_source(raw_source: Any, *, existing_ids: set[str] | None = None) -> dict[str, Any] | None:
    if not isinstance(raw_source, dict):
        return None

    existing_ids = existing_ids if existing_ids is not None else set()
    raw_display_name = str(raw_source.get("display_name") or raw_source.get("name") or "").strip()
    raw_query = str(
        raw_source.get("query")
        or raw_source.get("profile_url")
        or raw_source.get("handle")
        or raw_source.get("url")
        or ""
    ).strip()
    handle = extract_signal_x_handle(raw_query or raw_display_name)
    source_type = str(raw_source.get("source_type") or "").strip().lower()
    if source_type not in {"x", "name"}:
        source_type = "x" if handle else "name"
    if source_type == "x" and not handle:
        source_type = "name"

    profile_url = str(raw_source.get("profile_url") or "").strip()
    if source_type == "x" and handle:
        profile_url = f"https://x.com/{handle}"

    display_name = raw_display_name or (handle if handle else raw_query)
    display_name = display_name.strip()[:120]
    if not display_name:
        return None

    source_seed = handle or display_name or raw_query
    raw_id = str(raw_source.get("id") or "").strip()
    source_id = raw_id if raw_id and raw_id not in existing_ids else build_signal_source_id(source_seed, existing_ids)
    existing_ids.add(source_id)

    return {
        "id": source_id,
        "display_name": display_name,
        "source_type": source_type,
        "handle": handle,
        "profile_url": profile_url[:400],
        "query": (raw_query or display_name)[:400],
        "notes": str(raw_source.get("notes") or "").strip()[:240],
        "enabled": bool(raw_source.get("enabled", True)),
    }


def default_signal_monitor_config() -> dict[str, Any]:
    return {
        "sources": [dict(item) for item in SIGNAL_MONITOR_DEFAULT_SOURCES],
        "default_window_days": SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS,
        "codex_path": "codex",
        "workdir": str(BASE_DIR),
        "timeout_seconds": 900,
        "updated_at": now_iso(),
    }


def normalize_signal_monitor_config(raw: Any) -> dict[str, Any]:
    baseline = default_signal_monitor_config()
    source = raw if isinstance(raw, dict) else {}
    seen_ids: set[str] = set()
    sources = [
        normalized_source
        for raw_item in source.get("sources", [])
        if (normalized_source := normalize_signal_source(raw_item, existing_ids=seen_ids)) is not None
    ]
    if not sources:
        sources = [normalize_signal_source(item, existing_ids=seen_ids) for item in baseline["sources"]]
        sources = [item for item in sources if item is not None]

    try:
        default_window_days = min(max(int(source.get("default_window_days") or baseline["default_window_days"]), 1), 30)
    except (TypeError, ValueError):
        default_window_days = baseline["default_window_days"]

    try:
        timeout_seconds = max(120, int(source.get("timeout_seconds") or baseline["timeout_seconds"]))
    except (TypeError, ValueError):
        timeout_seconds = baseline["timeout_seconds"]

    codex_path = str(source.get("codex_path") or baseline["codex_path"]).strip() or baseline["codex_path"]
    workdir = str(source.get("workdir") or baseline["workdir"]).strip() or baseline["workdir"]

    return {
        "sources": sources,
        "default_window_days": default_window_days,
        "codex_path": codex_path,
        "workdir": workdir,
        "timeout_seconds": timeout_seconds,
        "updated_at": str(source.get("updated_at") or baseline["updated_at"]),
    }


def load_signal_monitor_config() -> dict[str, Any]:
    SIGNAL_MONITOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_MONITOR_CONFIG_PATH.exists():
        config = normalize_signal_monitor_config({})
        save_signal_monitor_config(config)
        return config
    return normalize_signal_monitor_config(load_json(SIGNAL_MONITOR_CONFIG_PATH))


def save_signal_monitor_config(config: dict[str, Any]) -> None:
    normalized = normalize_signal_monitor_config(config)
    SIGNAL_MONITOR_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SIGNAL_MONITOR_CONFIG_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SIGNAL_MONITOR_CONFIG_PATH)


def normalize_signal_state_entry(raw_state: Any) -> dict[str, Any] | None:
    if not isinstance(raw_state, dict):
        return None
    source_id = str(raw_state.get("source_id") or raw_state.get("id") or "").strip()
    if not source_id:
        return None
    return {
        "source_id": source_id,
        "display_name": str(raw_state.get("display_name") or "").strip()[:120],
        "source_type": str(raw_state.get("source_type") or "x").strip()[:20] or "x",
        "handle": str(raw_state.get("handle") or "").strip()[:80],
        "profile_url": str(raw_state.get("profile_url") or "").strip()[:400],
        "last_window_start": str(raw_state.get("last_window_start") or "").strip(),
        "last_window_end": str(raw_state.get("last_window_end") or "").strip(),
        "last_run_id": str(raw_state.get("last_run_id") or "").strip()[:80],
        "last_report_filename": str(raw_state.get("last_report_filename") or "").strip()[:240],
        "updated_at": str(raw_state.get("updated_at") or "").strip(),
    }


def normalize_signal_monitor_state(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    source_map: dict[str, dict[str, Any]] = {}
    raw_sources = source.get("sources") if isinstance(source.get("sources"), dict) else {}
    for source_id, raw_entry in raw_sources.items():
        normalized_entry = normalize_signal_state_entry({**(raw_entry if isinstance(raw_entry, dict) else {}), "source_id": source_id})
        if normalized_entry is not None:
            source_map[normalized_entry["source_id"]] = normalized_entry

    history: list[dict[str, Any]] = []
    for raw_item in source.get("history", []) if isinstance(source.get("history"), list) else []:
        if not isinstance(raw_item, dict):
            continue
        history.append(
            {
                "run_id": str(raw_item.get("run_id") or "").strip()[:80],
                "created_at": str(raw_item.get("created_at") or "").strip(),
                "finished_at": str(raw_item.get("finished_at") or "").strip(),
                "report_filename": str(raw_item.get("report_filename") or "").strip()[:240],
                "source_ids": ordered_unique([str(item).strip() for item in raw_item.get("source_ids", []) if str(item).strip()]),
                "window_label": str(raw_item.get("window_label") or "").strip()[:240],
            }
        )

    return {
        "sources": source_map,
        "history": history[:160],
    }


def load_signal_monitor_state() -> dict[str, Any]:
    SIGNAL_MONITOR_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_MONITOR_STATE_PATH.exists():
        state = normalize_signal_monitor_state({})
        save_signal_monitor_state(state)
        return state
    return normalize_signal_monitor_state(load_json(SIGNAL_MONITOR_STATE_PATH))


def save_signal_monitor_state(state: dict[str, Any]) -> None:
    normalized = normalize_signal_monitor_state(state)
    SIGNAL_MONITOR_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SIGNAL_MONITOR_STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SIGNAL_MONITOR_STATE_PATH)


def normalize_signal_monitor_runtime(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    return {
        "run_id": str(source.get("run_id") or "").strip(),
        "status": str(source.get("status") or "idle").strip() or "idle",
        "pid": int(source.get("pid") or 0),
        "source_ids": ordered_unique([str(item).strip() for item in source.get("source_ids", []) if str(item).strip()]),
        "started_at": str(source.get("started_at") or "").strip(),
        "finished_at": str(source.get("finished_at") or "").strip(),
        "report_path": str(source.get("report_path") or "").strip(),
        "report_filename": str(source.get("report_filename") or "").strip(),
        "meta_path": str(source.get("meta_path") or "").strip(),
        "stdout_path": str(source.get("stdout_path") or "").strip(),
        "stderr_path": str(source.get("stderr_path") or "").strip(),
        "window_start": str(source.get("window_start") or "").strip(),
        "window_end": str(source.get("window_end") or "").strip(),
        "message": str(source.get("message") or "").strip(),
        "error": str(source.get("error") or "").strip(),
        "termination_requested": bool(source.get("termination_requested")),
    }


def load_signal_monitor_runtime() -> dict[str, Any]:
    SIGNAL_MONITOR_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIGNAL_MONITOR_RUNTIME_PATH.exists():
        runtime = normalize_signal_monitor_runtime({})
        save_signal_monitor_runtime(runtime)
        return runtime
    return normalize_signal_monitor_runtime(load_json(SIGNAL_MONITOR_RUNTIME_PATH))


def save_signal_monitor_runtime(runtime: dict[str, Any]) -> None:
    normalized = normalize_signal_monitor_runtime(runtime)
    SIGNAL_MONITOR_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SIGNAL_MONITOR_RUNTIME_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(SIGNAL_MONITOR_RUNTIME_PATH)


def parse_signal_monitor_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def get_signal_monitor_cooldown_hits(
    sources: list[dict[str, Any]],
    state: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    current_state = state or load_signal_monitor_state()
    state_sources = current_state.get("sources") if isinstance(current_state.get("sources"), dict) else {}
    now_value = datetime.now()
    hits: list[dict[str, str]] = []
    for source in sources:
        state_entry = state_sources.get(source.get("id") or "")
        if not isinstance(state_entry, dict):
            continue
        last_end = parse_signal_monitor_datetime(state_entry.get("last_window_end"))
        if last_end is None:
            continue
        cooldown_until = last_end + timedelta(hours=SIGNAL_MONITOR_MIN_INTERVAL_HOURS)
        if cooldown_until <= now_value:
            continue
        hits.append(
            {
                "source_id": str(source.get("id") or ""),
                "display_name": str(
                    source.get("display_name")
                    or source.get("handle")
                    or source.get("query")
                    or "未命名来源"
                ),
                "cooldown_until": cooldown_until.strftime("%Y-%m-%d %H:%M"),
            }
        )
    return hits


def collect_signal_reports() -> list[dict[str, Any]]:
    return collect_reports_from_directory(SIGNAL_MONITOR_REPORTS_DIR)


def collect_today_signal_reports(reports: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    reports = reports if reports is not None else collect_signal_reports()
    today_text = datetime.now().strftime("%Y-%m-%d")
    today_compact = datetime.now().strftime("%Y%m%d")
    items: list[dict[str, Any]] = []
    for report in reports:
        filename = str(report.get("filename") or "")
        report_date = str(report.get("report_date") or "")
        if filename.startswith(today_compact) or report_date.startswith(today_text):
            items.append(report)
    return items


def sync_signal_monitor_runtime(runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    with SIGNAL_MONITOR_PROCESS_LOCK:
        current = normalize_signal_monitor_runtime(runtime or load_signal_monitor_runtime())
        if current["status"] != "running":
            save_signal_monitor_runtime(current)
            return current

        if is_process_running(current["pid"]):
            save_signal_monitor_runtime(current)
            return current

        meta_path = Path(current["meta_path"]) if current["meta_path"] else None
        meta = load_json(meta_path) if meta_path and meta_path.exists() else {}
        if meta:
            current["status"] = resolve_monitor_result_status(meta.get("status", ""))
            current["finished_at"] = str(meta.get("finished_at") or now_iso())
            current["report_path"] = str(meta.get("report_path") or current["report_path"])
            current["report_filename"] = Path(current["report_path"]).name if current["report_path"] else ""
            current["window_start"] = str(meta.get("window_start") or current["window_start"])
            current["window_end"] = str(meta.get("window_end") or current["window_end"])
            current["message"] = "信息监控结果已写入独立归档。" if current["status"] == "completed" else ""
            current["error"] = str(meta.get("error_message") or "")
        elif current["termination_requested"]:
            current["status"] = "terminated"
            current["finished_at"] = current["finished_at"] or now_iso()
            current["message"] = "信息监控任务已终止。"
        else:
            current["status"] = "failed"
            current["finished_at"] = now_iso()
            current["error"] = current["error"] or "进程提前退出，未找到完整的信息监控结果文件。"

        current["pid"] = 0
        current["termination_requested"] = False
        save_signal_monitor_runtime(current)
        return current


def terminate_signal_monitor_process(runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    with SIGNAL_MONITOR_PROCESS_LOCK:
        current = sync_signal_monitor_runtime(runtime)
        if current["status"] != "running":
            return current

        pid = int(current.get("pid") or 0)
        if pid > 0:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        current["status"] = "terminated"
        current["pid"] = 0
        current["termination_requested"] = False
        current["finished_at"] = now_iso()
        current["message"] = "信息监控任务已终止。"
        save_signal_monitor_runtime(current)
        return current


def start_signal_monitor_process(sources: list[dict[str, Any]]) -> dict[str, Any]:
    with SIGNAL_MONITOR_PROCESS_LOCK:
        current = sync_signal_monitor_runtime()
        if current["status"] == "running":
            raise RuntimeError("Signal monitor is already running.")

        config = load_signal_monitor_config()
        resolved_codex_path = discover_monitor_codex_path(config.get("codex_path", "")) or config.get("codex_path", "codex")
        check_monitor_codex_login(resolved_codex_path)

        SIGNAL_MONITOR_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        SIGNAL_MONITOR_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        SIGNAL_MONITOR_DATA_DIR.mkdir(parents=True, exist_ok=True)
        SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        run_id = uuid.uuid4().hex[:12]
        started_at = now_iso()
        stdout_path = SIGNAL_MONITOR_LOGS_DIR / f"{run_id}.launcher.stdout.log"
        stderr_path = SIGNAL_MONITOR_LOGS_DIR / f"{run_id}.launcher.stderr.log"
        meta_path = SIGNAL_MONITOR_LOGS_DIR / f"{run_id}.meta.json"

        stdout_handle = stdout_path.open("w", encoding="utf-8")
        stderr_handle = stderr_path.open("w", encoding="utf-8")
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    str(SIGNAL_MONITOR_RUNNER_PATH),
                    "--config-path",
                    str(SIGNAL_MONITOR_CONFIG_PATH),
                    "--state-path",
                    str(SIGNAL_MONITOR_STATE_PATH),
                    "--codex-path",
                    resolved_codex_path,
                    "--workdir",
                    str(config["workdir"]),
                    "--timeout-seconds",
                    str(config["timeout_seconds"]),
                    "--output-dir",
                    str(SIGNAL_MONITOR_REPORTS_DIR),
                    "--prompt-dir",
                    str(SIGNAL_MONITOR_PROMPTS_DIR),
                    "--log-dir",
                    str(SIGNAL_MONITOR_LOGS_DIR),
                    "--trigger",
                    "manual_run",
                    "--run-id",
                    run_id,
                    "--meta-path",
                    str(meta_path),
                    "--runtime-path",
                    str(SIGNAL_MONITOR_RUNTIME_PATH),
                ],
                stdout=stdout_handle,
                stderr=stderr_handle,
                stdin=subprocess.DEVNULL,
                cwd=str(BASE_DIR),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()

        runtime = {
            "run_id": run_id,
            "status": "running",
            "pid": process.pid,
            "source_ids": [item["id"] for item in sources if item.get("enabled", True)],
            "started_at": started_at,
            "finished_at": "",
            "report_path": "",
            "report_filename": "",
            "meta_path": str(meta_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "window_start": "",
            "window_end": "",
            "message": "",
            "error": "",
            "termination_requested": False,
        }
        save_signal_monitor_runtime(runtime)

        config["sources"] = sources
        config["codex_path"] = resolved_codex_path
        config["updated_at"] = now_iso()
        save_signal_monitor_config(config)
        return runtime


def build_signal_report_cards(reports: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    source_state_map = state.get("sources", {}) if isinstance(state.get("sources"), dict) else {}
    history_by_filename = {
        item.get("report_filename"): item
        for item in state.get("history", [])
        if str(item.get("report_filename") or "").strip()
    }
    today_compact = datetime.now().strftime("%Y%m%d")
    cards: list[dict[str, Any]] = []
    for report in reports:
        history_item = history_by_filename.get(report["filename"], {})
        cards.append(
            {
                **report,
                "is_today": str(report.get("filename") or "").startswith(today_compact),
                "source_ids": history_item.get("source_ids", []),
                "source_names": [
                    str(source_state_map.get(source_id, {}).get("display_name") or source_id)
                    for source_id in history_item.get("source_ids", [])
                ],
                "window_label": str(history_item.get("window_label") or "").strip(),
            }
        )
    return cards


def build_signal_source_cards(config: dict[str, Any], state: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    source_state_map = state.get("sources", {})
    for source in config.get("sources", []):
        state_entry = source_state_map.get(source["id"], {})
        cards.append(
            {
                **source,
                "source_label": "X / Twitter" if source.get("source_type") == "x" else "名称线索",
                "last_window_label": (
                    f"{state_entry.get('last_window_start')} 至 {state_entry.get('last_window_end')}"
                    if state_entry.get("last_window_start") and state_entry.get("last_window_end")
                    else "尚未运行"
                ),
                "last_report_filename": str(state_entry.get("last_report_filename") or "").strip(),
            }
        )
    return cards


def build_signal_monitor_page_context() -> dict[str, Any]:
    config = load_signal_monitor_config()
    state = load_signal_monitor_state()
    runtime = sync_signal_monitor_runtime()
    reports = collect_signal_reports()
    today_reports = collect_today_signal_reports(reports)
    latest_report = reports[0] if reports else None
    return {
        "signal_monitor_config": config,
        "signal_monitor_state": state,
        "signal_monitor_runtime": {
            **runtime,
            "status_label": monitor_runtime_status_label(runtime["status"]),
            "status_tone": monitor_runtime_status_tone(runtime["status"]),
            "is_running": runtime["status"] == "running",
            "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未运行",
            "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未完成",
        },
        "signal_reports": build_signal_report_cards(reports, state),
        "signal_today_reports": today_reports,
        "signal_latest_report": latest_report,
        "signal_sources": build_signal_source_cards(config, state),
        "signal_status_poll_seconds": SIGNAL_MONITOR_STATUS_POLL_INTERVAL_SECONDS,
    }


def get_signal_report(report_name: str) -> dict[str, Any]:
    return load_report_from_directory(report_name, SIGNAL_MONITOR_REPORTS_DIR)


def move_signal_report_to_trash(store: dict[str, Any], report_name: str) -> dict[str, Any]:
    report = get_signal_report(report_name)
    report_path = validate_report_name_in_directory(report_name, SIGNAL_MONITOR_REPORTS_DIR)
    SIGNAL_MONITOR_TRASH_DIR.mkdir(parents=True, exist_ok=True)
    trash_file_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{report_path.name}"
    trash_path = SIGNAL_MONITOR_TRASH_DIR / trash_file_name
    report_path.replace(trash_path)
    trash_entry = create_trash_entry(
        "signal_report",
        {
            "filename": report_path.name,
            "trash_path": str(trash_path),
            "title": report["title"],
            "summary": report["summary"],
            "report_date": report["report_date"],
            "deleted_from": "signal_monitor",
        },
        title=report["title"],
    )
    append_to_trash(store, trash_entry)
    return trash_entry


def stock_entry_template(symbol: str) -> dict[str, Any]:
    stamp = now_iso()
    return {
        "display_name": symbol,
        "created_at": stamp,
        "updated_at": stamp,
        "notes": [],
        "files": [],
    }


def normalize_note(raw_note: Any) -> dict[str, Any] | None:
    if not isinstance(raw_note, dict):
        return None

    raw_html = str(raw_note.get("content_html") or "").strip()
    legacy_content = str(raw_note.get("content") or "").strip()
    content_html = sanitize_note_html(raw_html) if raw_html else plain_text_to_html(trim_note_content(legacy_content))
    content_text = trim_note_content(
        str(raw_note.get("content_text") or "").strip() or note_html_to_text(content_html)
    )

    if not content_html or not content_text:
        return None

    return {
        "id": str(raw_note.get("id") or uuid.uuid4().hex[:10]),
        "title": str(raw_note.get("title") or "").strip()[:120],
        "content_html": content_html,
        "content_text": content_text,
        "created_at": str(raw_note.get("created_at") or now_iso()),
        "record_date": normalize_date_field(raw_note.get("record_date")) or iso_to_date(raw_note.get("created_at")) or today_date_iso(),
        "source_file_id": str(raw_note.get("source_file_id") or "").strip()[:40],
        "source_file_name": str(raw_note.get("source_file_name") or "").strip()[:240],
        "source_mode": str(raw_note.get("source_mode") or "").strip()[:40],
        "tags": normalize_tag_list(raw_note.get("tags", [])),
    }


def normalize_file_entry(raw_file: Any) -> dict[str, Any] | None:
    if not isinstance(raw_file, dict):
        return None

    stored_name = str(raw_file.get("stored_name") or "").strip()
    original_name = str(raw_file.get("original_name") or "").strip()
    if not stored_name or not original_name:
        return None

    return {
        "id": str(raw_file.get("id") or uuid.uuid4().hex[:10]),
        "stored_name": stored_name,
        "original_name": original_name,
        "description": str(raw_file.get("description") or "").strip()[:200],
        "uploaded_at": str(raw_file.get("uploaded_at") or now_iso()),
        "record_date": normalize_date_field(raw_file.get("record_date")) or iso_to_date(raw_file.get("uploaded_at")) or today_date_iso(),
        "linked_note_id": str(raw_file.get("linked_note_id") or "").strip()[:40],
        "linked_note_title": str(raw_file.get("linked_note_title") or "").strip()[:120],
        "extract_text": bool(raw_file.get("extract_text")),
        "tags": normalize_tag_list(raw_file.get("tags", [])),
    }


def normalize_transcript_entry(raw_transcript: Any) -> dict[str, Any] | None:
    if not isinstance(raw_transcript, dict):
        return None

    stored_name = str(raw_transcript.get("stored_name") or "").strip()
    original_name = str(raw_transcript.get("original_name") or "").strip()
    if not stored_name or not original_name:
        return None

    source_language = str(raw_transcript.get("source_language") or "cn").strip()
    if source_language not in TRANSCRIPT_SOURCE_LANGUAGE_LABELS:
        source_language = "cn"

    output_level = str(raw_transcript.get("output_level") or "2").strip()
    if output_level not in TRANSCRIPT_OUTPUT_LEVEL_LABELS:
        output_level = "2"

    try:
        speaker_count = int(raw_transcript.get("speaker_count") or 2)
    except (TypeError, ValueError):
        speaker_count = 2
    speaker_count = min(max(speaker_count, 2), 8)

    raw_transcript_html = str(raw_transcript.get("transcript_html") or "").strip()
    transcript_text = trim_note_content(str(raw_transcript.get("transcript_text") or "").strip())
    transcript_html = sanitize_note_html(raw_transcript_html) if raw_transcript_html else ""
    if not transcript_html and transcript_text:
        transcript_html = plain_text_to_html(transcript_text)
    if transcript_html and not transcript_text:
        transcript_text = trim_note_content(note_html_to_text(transcript_html))

    meeting_assistance_types = normalize_choice_list(
        raw_transcript.get("meeting_assistance_types", []),
        set(TRANSCRIPT_MEETING_ASSISTANCE_LABELS),
    )
    summarization_types = normalize_choice_list(
        raw_transcript.get("summarization_types", []),
        set(TRANSCRIPT_SUMMARIZATION_LABELS),
    )

    status = str(raw_transcript.get("status") or "pending_api").strip()
    if status not in TRANSCRIPT_STATUS_META:
        status = normalize_provider_task_status(status)

    linked_symbols = transcript_linked_symbols(
        {
            "linked_symbols": raw_transcript.get("linked_symbols", []),
            "linked_symbol": raw_transcript.get("linked_symbol", ""),
        }
    )
    linked_symbol = linked_symbols[0] if linked_symbols else ""

    return {
        "id": str(raw_transcript.get("id") or uuid.uuid4().hex[:10]),
        "title": str(raw_transcript.get("title") or "").strip()[:160],
        "meeting_date": normalize_date_field(raw_transcript.get("meeting_date")),
        "created_at": str(raw_transcript.get("created_at") or now_iso()),
        "updated_at": str(raw_transcript.get("updated_at") or now_iso()),
        "stored_name": stored_name,
        "original_name": original_name[:240],
        "media_kind": detect_transcript_media_kind(original_name),
        "provider": str(raw_transcript.get("provider") or "tingwu").strip()[:40],
        "status": status,
        "provider_task_id": str(raw_transcript.get("provider_task_id") or "").strip()[:120],
        "provider_task_status": str(raw_transcript.get("provider_task_status") or "").strip()[:120],
        "provider_request_id": str(raw_transcript.get("provider_request_id") or "").strip()[:120],
        "submitted_at": str(raw_transcript.get("submitted_at") or "").strip()[:40],
        "last_synced_at": str(raw_transcript.get("last_synced_at") or "").strip()[:40],
        "last_error": str(raw_transcript.get("last_error") or "").strip()[:2000],
        "provider_result_urls": {
            str(key).strip()[:80]: str(value).strip()[:1000]
            for key, value in dict(raw_transcript.get("provider_result_urls") or {}).items()
            if str(key).strip() and str(value).strip()
        },
        "file_url_hint": str(raw_transcript.get("file_url_hint") or "").strip()[:2000],
        "source_bucket_name": str(raw_transcript.get("source_bucket_name") or "").strip()[:120],
        "source_object_key": str(raw_transcript.get("source_object_key") or "").strip()[:400],
        "source_endpoint": str(raw_transcript.get("source_endpoint") or "").strip()[:200],
        "source_region_id": str(raw_transcript.get("source_region_id") or "").strip()[:40],
        "source_url_expires_at": str(raw_transcript.get("source_url_expires_at") or "").strip()[:40],
        "linked_symbol": linked_symbol or "",
        "linked_symbols": linked_symbols,
        "source_language": source_language,
        "output_level": output_level,
        "diarization_enabled": bool(raw_transcript.get("diarization_enabled")),
        "speaker_count": speaker_count,
        "phrase_id": str(raw_transcript.get("phrase_id") or "").strip()[:80],
        "auto_chapters_enabled": bool(raw_transcript.get("auto_chapters_enabled")),
        "meeting_assistance_enabled": bool(raw_transcript.get("meeting_assistance_enabled")),
        "meeting_assistance_types": meeting_assistance_types,
        "summarization_enabled": bool(raw_transcript.get("summarization_enabled")),
        "summarization_types": summarization_types,
        "text_polish_enabled": bool(raw_transcript.get("text_polish_enabled")),
        "ppt_extraction_enabled": bool(raw_transcript.get("ppt_extraction_enabled")),
        "custom_prompt_enabled": bool(raw_transcript.get("custom_prompt_enabled")),
        "custom_prompt_name": str(raw_transcript.get("custom_prompt_name") or "").strip()[:80],
        "custom_prompt_text": str(raw_transcript.get("custom_prompt_text") or "").strip()[:4000],
        "transcript_html": transcript_html,
        "transcript_text": transcript_text,
        "tags": normalize_tag_list(raw_transcript.get("tags", [])),
    }


def normalize_group_entry(raw_group: Any) -> dict[str, Any] | None:
    if not isinstance(raw_group, dict):
        return None

    name = str(raw_group.get("name") or "").strip()
    if not name:
        return None

    stocks = ordered_unique(
        [
            symbol
            for raw_symbol in raw_group.get("stocks", [])
            if (symbol := normalize_stock_symbol(str(raw_symbol)))
        ]
    )

    return {
        "id": str(raw_group.get("id") or uuid.uuid4().hex[:8]),
        "name": name[:80],
        "description": str(raw_group.get("description") or "").strip()[:240],
        "stocks": stocks,
        "created_at": str(raw_group.get("created_at") or now_iso()),
    }


def normalize_monitor_report_payload(raw_payload: Any) -> dict[str, Any] | None:
    if not isinstance(raw_payload, dict):
        return None

    filename = str(raw_payload.get("filename") or "").strip()
    trash_path = str(raw_payload.get("trash_path") or "").strip()
    if not filename or not trash_path:
        return None

    return {
        "filename": filename[:240],
        "trash_path": trash_path,
        "title": str(raw_payload.get("title") or "").strip()[:180],
        "summary": str(raw_payload.get("summary") or "").strip()[:240],
        "report_date": str(raw_payload.get("report_date") or "").strip()[:40],
        "deleted_from": str(raw_payload.get("deleted_from") or "monitor").strip()[:40],
    }


def normalize_signal_report_payload(raw_payload: Any) -> dict[str, Any] | None:
    if not isinstance(raw_payload, dict):
        return None

    filename = str(raw_payload.get("filename") or "").strip()
    trash_path = str(raw_payload.get("trash_path") or "").strip()
    if not filename or not trash_path:
        return None

    return {
        "filename": filename[:240],
        "trash_path": trash_path,
        "title": str(raw_payload.get("title") or "").strip()[:180],
        "summary": str(raw_payload.get("summary") or "").strip()[:240],
        "report_date": str(raw_payload.get("report_date") or "").strip()[:40],
        "deleted_from": str(raw_payload.get("deleted_from") or "signal_monitor").strip()[:40],
    }


def normalize_trash_entry(raw_entry: Any) -> dict[str, Any] | None:
    if not isinstance(raw_entry, dict):
        return None

    item_type = str(raw_entry.get("item_type") or "").strip()
    payload = raw_entry.get("payload")
    normalized_payload: dict[str, Any] | None = None

    if item_type == "note":
        normalized_payload = normalize_note(payload)
    elif item_type == "file":
        normalized_payload = normalize_file_entry(payload)
    elif item_type == "transcript":
        normalized_payload = normalize_transcript_entry(payload)
    elif item_type == "group":
        normalized_payload = normalize_group_entry(payload)
    elif item_type == "monitor_report":
        normalized_payload = normalize_monitor_report_payload(payload)
    elif item_type == "signal_report":
        normalized_payload = normalize_signal_report_payload(payload)

    if normalized_payload is None:
        return None

    title = str(raw_entry.get("title") or "").strip()
    if not title:
        if item_type == "group":
            title = str(normalized_payload.get("name") or "未命名分组")
        else:
            title = str(
                normalized_payload.get("title")
                or normalized_payload.get("original_name")
                or "未命名内容"
            )

    return {
        "id": str(raw_entry.get("id") or uuid.uuid4().hex[:12]),
        "item_type": item_type,
        "title": title[:180],
        "symbol": normalize_stock_symbol(str(raw_entry.get("symbol") or "")) or "",
        "deleted_at": str(raw_entry.get("deleted_at") or now_iso()),
        "tags": normalize_tag_list(raw_entry.get("tags", normalized_payload.get("tags", []))),
        "payload": normalized_payload,
    }


def normalize_stock_store(data: Any) -> dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    groups: list[dict[str, Any]] = []

    for raw_group in source.get("groups", []):
        if normalized_group := normalize_group_entry(raw_group):
            groups.append(normalized_group)

    favorites = ordered_unique(
        [
            symbol
            for raw_symbol in source.get("favorites", [])
            if (symbol := normalize_stock_symbol(str(raw_symbol)))
        ]
    )
    raw_transcripts = source.get("transcripts", [])
    if not isinstance(raw_transcripts, list):
        raw_transcripts = []

    transcripts = [
        transcript
        for raw_transcript in raw_transcripts
        if (transcript := normalize_transcript_entry(raw_transcript)) is not None
    ]
    trash = [
        trash_entry
        for raw_entry in source.get("trash", [])
        if (trash_entry := normalize_trash_entry(raw_entry)) is not None
    ]

    stocks: dict[str, dict[str, Any]] = {}
    raw_stocks = source.get("stocks")
    if isinstance(raw_stocks, dict):
        for raw_symbol, raw_entry in raw_stocks.items():
            symbol = normalize_stock_symbol(str(raw_symbol))
            if not symbol:
                continue

            entry = stock_entry_template(symbol)
            if isinstance(raw_entry, dict):
                entry["display_name"] = str(raw_entry.get("display_name") or symbol).strip() or symbol
                entry["created_at"] = str(raw_entry.get("created_at") or entry["created_at"])
                entry["updated_at"] = str(raw_entry.get("updated_at") or entry["updated_at"])
                entry["notes"] = [
                    note
                    for raw_note in raw_entry.get("notes", [])
                    if (note := normalize_note(raw_note)) is not None
                ]
                entry["files"] = [
                    file_entry
                    for raw_file in raw_entry.get("files", [])
                    if (file_entry := normalize_file_entry(raw_file)) is not None
                ]

            stocks[symbol] = entry

    for transcript in transcripts:
        for linked_symbol in transcript_linked_symbols(transcript):
            stocks.setdefault(linked_symbol, stock_entry_template(linked_symbol))

    for symbol in list_stock_symbols({"groups": groups, "favorites": favorites, "stocks": stocks}):
        stocks.setdefault(symbol, stock_entry_template(symbol))

    return {
        "groups": groups,
        "favorites": favorites,
        "stocks": stocks,
        "transcripts": transcripts,
        "trash": trash,
    }


def load_stock_store() -> dict[str, Any]:
    STOCK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STOCK_STORE_PATH.exists():
        return normalize_stock_store({})

    try:
        raw_data = json.loads(STOCK_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return normalize_stock_store({})

    return normalize_stock_store(raw_data)


def save_stock_store(store: dict[str, Any]) -> None:
    normalized = normalize_stock_store(store)
    STOCK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STOCK_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(STOCK_STORE_PATH)


def list_stock_symbols(store: dict[str, Any]) -> list[str]:
    symbols: list[str] = []

    for symbol in store.get("favorites", []):
        symbols.append(symbol)

    for group in store.get("groups", []):
        for symbol in group.get("stocks", []):
            symbols.append(symbol)

    for symbol in store.get("stocks", {}).keys():
        symbols.append(symbol)

    return ordered_unique(symbols)


def ensure_stock_entry(store: dict[str, Any], symbol: str) -> dict[str, Any]:
    stocks = store.setdefault("stocks", {})
    if symbol not in stocks:
        stocks[symbol] = stock_entry_template(symbol)

    return stocks[symbol]


def touch_stock(store: dict[str, Any], symbol: str) -> None:
    entry = ensure_stock_entry(store, symbol)
    entry["updated_at"] = now_iso()


def slugify_group_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "group"


def create_group_id(name: str, existing_ids: set[str]) -> str:
    base = slugify_group_name(name)
    candidate = base
    index = 2

    while candidate in existing_ids:
        candidate = f"{base}-{index}"
        index += 1

    return candidate


def get_group(store: dict[str, Any], group_id: str) -> dict[str, Any]:
    for group in store["groups"]:
        if group["id"] == group_id:
            return group

    abort(404)


def require_stock_symbol(symbol_value: str) -> str:
    symbol = normalize_stock_symbol(symbol_value)
    if not symbol:
        abort(404)

    return symbol


def safe_next_url(value: str | None, default: str) -> str:
    if value and value.startswith("/"):
        return value

    return default


def expects_json_response() -> bool:
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True

    accept_mimetypes = request.accept_mimetypes
    return accept_mimetypes["application/json"] > accept_mimetypes["text/html"]


def stock_memberships(store: dict[str, Any], symbol: str) -> list[dict[str, str]]:
    memberships = [
        {"id": group["id"], "name": group["name"]}
        for group in store["groups"]
        if symbol in group["stocks"]
    ]
    memberships.sort(key=lambda item: item["name"].lower())
    return memberships


def build_stock_card(store: dict[str, Any], symbol: str) -> dict[str, Any]:
    entry = ensure_stock_entry(store, symbol)
    memberships = stock_memberships(store, symbol)
    return {
        "symbol": symbol,
        "display_name": entry.get("display_name") or symbol,
        "is_favorite": symbol in store["favorites"],
        "note_count": len(entry.get("notes", [])),
        "file_count": len(entry.get("files", [])),
        "transcript_count": transcript_count_for_symbol(store, symbol),
        "updated_label": format_iso_timestamp(entry.get("updated_at")),
        "groups": memberships,
    }


def build_group_cards(store: dict[str, Any], *, focus_group: str = "") -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []

    for group in store["groups"]:
        stocks = [build_stock_card(store, symbol) for symbol in group["stocks"]]
        description = str(group.get("description") or "").strip()
        fallback_copy = "把一个策略、行业、主题或阶段观察放进这个分组里。"
        cards.append(
            {
                "id": group["id"],
                "name": group["name"],
                "description": description,
                "description_preview": summarize_text_block(description or fallback_copy, limit=92),
                "stock_count": len(stocks),
                "preview_symbols": [stock["symbol"] for stock in stocks[:4]],
                "more_stock_count": max(len(stocks) - 4, 0),
                "is_focus": bool(focus_group and group["id"] == focus_group),
                "stock_list_scrollable": len(stocks) > 6,
                "stocks": stocks,
            }
        )

    return cards


def build_stock_selector_options(store: dict[str, Any]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for symbol in sorted(list_stock_symbols(store)):
        entry = ensure_stock_entry(store, symbol)
        options.append(
            {
                "symbol": symbol,
                "display_name": entry.get("display_name") or symbol,
            }
        )

    return options


def build_stock_tag_summary(store: dict[str, Any], symbol: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    symbols = [symbol] if symbol else sorted(list_stock_symbols(store))
    for item_symbol in symbols:
        entry = ensure_stock_entry(store, item_symbol)
        items.extend(entry["notes"])
        items.extend(entry["files"])

    transcripts = [
        transcript
        for transcript in store.get("transcripts", [])
        if not symbol or transcript_matches_symbol(transcript, symbol)
    ]
    items.extend(transcripts)

    return collect_tag_counts(items)


def build_stock_timeline(
    store: dict[str, Any],
    symbol: str,
    *,
    related_reports: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entry = ensure_stock_entry(store, symbol)
    events: list[dict[str, Any]] = []

    for note in entry["notes"]:
        events.append(
            {
                "kind": "note",
                "kind_label": SEARCH_KIND_META["note"]["label"],
                "kind_tone": SEARCH_KIND_META["note"]["tone"],
                "title": note.get("title") or "未命名笔记",
                "summary": summarize_text_block(note.get("content_text") or ""),
                "timestamp": str(note.get("created_at") or ""),
                "sort_value": coerce_sort_timestamp(note.get("created_at")),
                "display_time": note_display_time(note),
                "tags": normalize_tag_list(note.get("tags", [])),
                "reader_template_id": f"note-reader-{note['id']}",
                "anchor": "notes-panel",
            }
        )

    for file_entry in entry["files"]:
        events.append(
            {
                "kind": "file",
                "kind_label": SEARCH_KIND_META["file"]["label"],
                "kind_tone": SEARCH_KIND_META["file"]["tone"],
                "title": file_entry.get("original_name") or "未命名文件",
                "summary": summarize_text_block(
                    file_entry.get("description")
                    or f"{detect_file_type_label(str(file_entry.get('original_name') or ''))} 文件"
                ),
                "timestamp": str(file_entry.get("uploaded_at") or ""),
                "sort_value": coerce_sort_timestamp(file_entry.get("uploaded_at")),
                "display_time": file_display_time(file_entry),
                "tags": normalize_tag_list(file_entry.get("tags", [])),
                "file_type_label": detect_file_type_label(str(file_entry.get("original_name") or "")),
                "action_url": url_for("stock_detail", symbol=symbol) + "#files-panel",
                "action_label": "查看文件",
                "download_url": url_for("download_stock_file", symbol=symbol, file_id=file_entry["id"]),
                "anchor": "files-panel",
            }
        )

    for transcript in build_transcript_cards(store, symbol_filter=symbol):
        events.append(
            {
                "kind": "transcript",
                "kind_label": SEARCH_KIND_META["transcript"]["label"],
                "kind_tone": SEARCH_KIND_META["transcript"]["tone"],
                "title": transcript["display_title"],
                "summary": transcript["summary_excerpt"],
                "timestamp": str(transcript.get("meeting_date") or transcript.get("created_at") or ""),
                "sort_value": coerce_sort_timestamp(transcript.get("meeting_date") or transcript.get("created_at")),
                "display_time": transcript.get("meeting_date_label") or transcript.get("display_created_at"),
                "tags": normalize_tag_list(transcript.get("tags", [])),
                "status_label": transcript.get("status_label"),
                "reader_template_id": f"stock-transcript-reader-{transcript['id']}",
                "anchor": "transcripts-panel",
            }
        )

    for report in related_reports or []:
        events.append(
            {
                "kind": "report",
                "kind_label": SEARCH_KIND_META["report"]["label"],
                "kind_tone": SEARCH_KIND_META["report"]["tone"],
                "title": report["title"],
                "summary": report["summary"],
                "timestamp": str(report.get("sort_key") or 0),
                "sort_value": float(report.get("sort_key") or 0),
                "display_time": report["report_date"],
                "tags": [],
                "action_url": url_for("index", report=report["filename"]),
                "action_label": "打开日报",
                "anchor": "related-reports",
            }
        )

    events.sort(key=lambda item: (float(item["sort_value"]), item["title"]), reverse=True)
    return events


def build_workspace_recent_timeline(
    store: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    limit: int = 36,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for report in reports[:24]:
        events.append(
            {
                "kind_label": "关联日报",
                "symbol_label": "首页归档",
                "title": report["title"],
                "summary": report["summary"],
                "display_time": report["report_date"],
                "sort_value": float(report.get("sort_key") or 0),
            }
        )

    for symbol in sorted(list_stock_symbols(store)):
        entry = ensure_stock_entry(store, symbol)
        for note in entry["notes"]:
            events.append(
                {
                    "kind_label": SEARCH_KIND_META["note"]["label"],
                    "symbol_label": symbol,
                    "title": note.get("title") or "未命名笔记",
                    "summary": summarize_text_block(note.get("content_text") or ""),
                    "display_time": note_display_time(note),
                    "sort_value": coerce_sort_timestamp(note.get("created_at")),
                }
            )
        for file_entry in entry["files"]:
            events.append(
                {
                    "kind_label": SEARCH_KIND_META["file"]["label"],
                    "symbol_label": symbol,
                    "title": file_entry.get("original_name") or "未命名文件",
                    "summary": summarize_text_block(
                        file_entry.get("description")
                        or f"{detect_file_type_label(str(file_entry.get('original_name') or ''))} 文件"
                    ),
                    "display_time": file_display_time(file_entry),
                    "sort_value": coerce_sort_timestamp(file_entry.get("uploaded_at")),
                }
            )

    for transcript in store.get("transcripts", []):
        linked_symbols = transcript_linked_symbols(transcript)
        events.append(
            {
                "kind_label": SEARCH_KIND_META["transcript"]["label"],
                "symbol_label": "；".join(linked_symbols) or "未关联股票",
                "title": transcript.get("title") or transcript.get("original_name") or "会议转录",
                "summary": summarize_text_block(transcript.get("transcript_text") or TRANSCRIPT_PLACEHOLDER_COPY),
                "display_time": str(transcript.get("meeting_date") or "") or format_iso_timestamp(transcript.get("created_at")),
                "sort_value": coerce_sort_timestamp(transcript.get("meeting_date") or transcript.get("created_at")),
            }
        )

    events.sort(key=lambda item: (float(item["sort_value"]), item["title"]), reverse=True)
    return events[:limit]


def build_timeline_digest_lines(
    timeline: list[dict[str, Any]],
    *,
    heading: str,
    empty_message: str,
    limit: int = 18,
) -> list[str]:
    lines = [heading]
    if not timeline:
        lines.extend([f"- {empty_message}", ""])
        return lines

    lines.append("- 按时间倒序整理，方便直接比较某一段时间里的变化。")
    for item in timeline[:limit]:
        meta_bits = []
        if item.get("symbol_label"):
            meta_bits.append(f"股票 {item['symbol_label']}")
        if item.get("status_label"):
            meta_bits.append(str(item["status_label"]))
        if item.get("file_type_label"):
            meta_bits.append(str(item["file_type_label"]))
        if item.get("tags"):
            meta_bits.append("标签 " + ", ".join(item["tags"][:6]))

        lines.append(
            f"- {item.get('display_time') or '未知时间'} | {item.get('kind_label') or '记录'} | {item.get('title') or '未命名内容'}"
        )
        if meta_bits:
            lines.append(f"  - 元信息: {' · '.join(meta_bits)}")
        if item.get("summary"):
            lines.append(f"  - 摘要: {summarize_text_block(str(item['summary']), limit=220)}")

    lines.append("")
    return lines


def split_search_terms(query: str) -> list[str]:
    compact = re.sub(r"\s+", " ", query).strip()
    if not compact:
        return []
    parts = [part for part in compact.split(" ") if part]
    return parts if len(parts) > 1 else [compact]


def build_stock_detail_deep_link(
    *,
    symbol: str,
    panel: str,
    item_kind: str = "",
    item_id: str = "",
    anchor: str = "",
) -> str:
    params: dict[str, str] = {}
    if panel:
        params["panel"] = panel
    if item_kind:
        params["open_kind"] = item_kind
    if item_id:
        params["open_id"] = item_id

    target = url_for("stock_detail", symbol=symbol, **params)
    if anchor:
        return f"{target}#{anchor}"
    return target


def text_contains_all_terms(text: str, terms: list[str]) -> bool:
    haystack = text.casefold()
    return all(term.casefold() in haystack for term in terms)


def build_match_excerpt(text: str, terms: list[str], fallback: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return fallback
    if not terms:
        return summarize_text_block(compact, limit=limit)

    lower_compact = compact.casefold()
    first_index = min(
        (lower_compact.find(term.casefold()) for term in terms if lower_compact.find(term.casefold()) >= 0),
        default=-1,
    )
    if first_index < 0:
        return summarize_text_block(compact, limit=limit)

    start = max(first_index - 60, 0)
    end = min(start + limit, len(compact))
    snippet = compact[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(compact):
        snippet = snippet + "..."
    return snippet


def build_global_search_context(
    store: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    query: str,
    kind_filter: str,
    symbol_filter: str,
    tag_filter: str,
) -> dict[str, Any]:
    terms = split_search_terms(query)
    normalized_symbol = normalize_stock_symbol(symbol_filter or "") or ""
    normalized_tag = normalize_tag_value(tag_filter) or ""
    selected_kind = kind_filter if kind_filter in SEARCH_KIND_META else ""
    results: list[dict[str, Any]] = []

    for symbol in sorted(list_stock_symbols(store)):
        entry = ensure_stock_entry(store, symbol)
        for note in entry["notes"]:
            if selected_kind and selected_kind != "note":
                continue
            tags = normalize_tag_list(note.get("tags", []))
            search_text = " ".join(
                [
                    symbol,
                    note.get("title") or "",
                    note.get("content_text") or "",
                    " ".join(tags),
                ]
            )
            if normalized_symbol and symbol != normalized_symbol:
                continue
            if normalized_tag and not tag_match(tags, normalized_tag):
                continue
            if terms and not text_contains_all_terms(search_text, terms):
                continue

            results.append(
                {
                    "kind": "note",
                    "kind_label": SEARCH_KIND_META["note"]["label"],
                    "kind_tone": SEARCH_KIND_META["note"]["tone"],
                    "title": note.get("title") or "未命名笔记",
                    "summary": build_match_excerpt(
                        note.get("content_text") or "",
                        terms,
                        summarize_text_block(note.get("content_text") or ""),
                    ),
                    "symbol": symbol,
                    "display_time": note_display_time(note),
                    "sort_value": coerce_sort_timestamp(note.get("created_at")),
                    "tags": tags,
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="notes",
                        item_kind="note",
                        item_id=str(note.get("id") or ""),
                        anchor=f"note-{note.get('id')}",
                    ),
                }
            )

        for file_entry in entry["files"]:
            if selected_kind and selected_kind != "file":
                continue
            tags = normalize_tag_list(file_entry.get("tags", []))
            search_text = " ".join(
                [
                    symbol,
                    file_entry.get("original_name") or "",
                    file_entry.get("description") or "",
                    file_entry.get("linked_note_title") or "",
                    " ".join(tags),
                ]
            )
            if normalized_symbol and symbol != normalized_symbol:
                continue
            if normalized_tag and not tag_match(tags, normalized_tag):
                continue
            if terms and not text_contains_all_terms(search_text, terms):
                continue

            results.append(
                {
                    "kind": "file",
                    "kind_label": SEARCH_KIND_META["file"]["label"],
                    "kind_tone": SEARCH_KIND_META["file"]["tone"],
                    "title": file_entry.get("original_name") or "未命名文件",
                    "summary": build_match_excerpt(
                        " ".join(
                            [
                                file_entry.get("description") or "",
                                file_entry.get("linked_note_title") or "",
                            ]
                        ),
                        terms,
                        summarize_text_block(file_entry.get("description") or file_entry.get("original_name") or ""),
                    ),
                    "symbol": symbol,
                    "display_time": file_display_time(file_entry),
                    "sort_value": coerce_sort_timestamp(file_entry.get("uploaded_at")),
                    "tags": tags,
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="files",
                        item_kind="file",
                        item_id=str(file_entry.get("id") or ""),
                        anchor=f"file-{file_entry.get('id')}",
                    ),
                    "secondary_url": url_for("download_stock_file", symbol=symbol, file_id=file_entry["id"]),
                    "secondary_label": "下载文件",
                }
            )

    for transcript in build_transcript_cards(store):
        if selected_kind and selected_kind != "transcript":
            continue
        symbols = transcript.get("linked_symbols", [])
        symbol = (
            normalized_symbol
            if normalized_symbol and normalized_symbol in symbols
            else (symbols[0] if len(symbols) == 1 else "")
        )
        tags = normalize_tag_list(transcript.get("tags", []))
        search_text = " ".join(
            [
                transcript.get("linked_symbols_label") or "",
                transcript.get("display_title") or "",
                transcript.get("transcript_text") or "",
                transcript.get("original_name") or "",
                " ".join(tags),
            ]
        )
        if normalized_symbol and normalized_symbol not in symbols:
            continue
        if normalized_tag and not tag_match(tags, normalized_tag):
            continue
        if terms and not text_contains_all_terms(search_text, terms):
            continue

        results.append(
            {
                "kind": "transcript",
                "kind_label": SEARCH_KIND_META["transcript"]["label"],
                "kind_tone": SEARCH_KIND_META["transcript"]["tone"],
                "title": transcript["display_title"],
                "summary": build_match_excerpt(
                    transcript.get("transcript_text") or "",
                    terms,
                    transcript["summary_excerpt"],
                ),
                "symbol": symbol,
                "symbols": symbols,
                "display_time": transcript.get("meeting_date_label") or transcript.get("display_created_at"),
                "sort_value": coerce_sort_timestamp(transcript.get("meeting_date") or transcript.get("created_at")),
                "tags": tags,
                "url": (
                    build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="transcripts",
                        item_kind="transcript",
                        item_id=str(transcript.get("id") or ""),
                        anchor=f"transcript-{transcript.get('id')}",
                    )
                    if symbol
                    else url_for("transcripts_page")
                ),
            }
        )

    report_symbol_pattern = (
        re.compile(rf"(?<![A-Z0-9]){re.escape(normalized_symbol)}(?![A-Z0-9])", re.IGNORECASE)
        if normalized_symbol
        else None
    )
    for report in reports:
        if selected_kind and selected_kind != "report":
            continue
        content = read_report_text(REPORTS_DIR / report["filename"])
        combined_text = " ".join([report["title"], report["summary"], report["filename"], content])
        if normalized_symbol and report_symbol_pattern and not report_symbol_pattern.search(combined_text):
            continue
        if terms and not text_contains_all_terms(combined_text, terms):
            continue
        if normalized_tag:
            continue

        results.append(
            {
                "kind": "report",
                "kind_label": SEARCH_KIND_META["report"]["label"],
                "kind_tone": SEARCH_KIND_META["report"]["tone"],
                "title": report["title"],
                "summary": build_match_excerpt(content, terms, report["summary"]),
                "symbol": normalized_symbol if normalized_symbol else "",
                "display_time": report["report_date"],
                "sort_value": float(report["sort_key"]),
                "tags": [],
                "url": url_for("index", report=report["filename"]),
            }
        )

    results.sort(key=lambda item: (float(item["sort_value"]), item["title"]), reverse=True)
    counts = Counter(item["kind"] for item in results)

    return {
        "query": query.strip(),
        "selected_kind": selected_kind,
        "selected_symbol": normalized_symbol,
        "selected_tag": normalized_tag,
        "results": results,
        "result_count": len(results),
        "result_counts": counts,
        "kind_options": [{"value": "", "label": "全部"}]
        + [
            {"value": key, "label": meta["label"]}
            for key, meta in SEARCH_KIND_META.items()
            if key != "group"
        ],
        "stock_options": build_stock_selector_options(store),
        "popular_tags": build_stock_tag_summary(store)[:14],
    }


def create_trash_entry(
    item_type: str,
    payload: dict[str, Any],
    *,
    symbol: str = "",
    title: str = "",
) -> dict[str, Any]:
    normalized = normalize_trash_entry(
        {
            "id": uuid.uuid4().hex[:12],
            "item_type": item_type,
            "title": title,
            "symbol": symbol,
            "deleted_at": now_iso(),
            "tags": payload.get("tags", []),
            "payload": deepcopy(payload),
        }
    )
    if normalized is None:
        raise ValueError("无法创建回收站条目")
    return normalized


def get_trash_entry(store: dict[str, Any], trash_id: str) -> dict[str, Any]:
    for entry in store.get("trash", []):
        if entry["id"] == trash_id:
            return entry
    abort(404)


def append_to_trash(store: dict[str, Any], trash_entry: dict[str, Any]) -> None:
    store.setdefault("trash", []).append(trash_entry)


def ensure_unique_id(candidate: str, existing_ids: set[str], *, length: int = 10) -> str:
    cleaned = str(candidate or "").strip()
    if cleaned and cleaned not in existing_ids:
        return cleaned
    while True:
        generated = uuid.uuid4().hex[:length]
        if generated not in existing_ids:
            return generated


def build_trash_cards(store: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for entry in store.get("trash", []):
        meta = TRASH_KIND_META.get(entry["item_type"], {"label": "已删除内容", "description": ""})
        payload = entry["payload"]
        title = entry["title"] or str(payload.get("title") or payload.get("original_name") or "未命名内容")
        symbol = str(entry.get("symbol") or "")
        cards.append(
            {
                **entry,
                "kind_label": meta["label"],
                "kind_description": meta["description"],
                "display_title": title,
                "display_deleted_at": format_iso_timestamp(entry.get("deleted_at")),
                "display_symbol": symbol,
                "tags": normalize_tag_list(entry.get("tags", [])),
            }
        )

    cards.sort(key=lambda item: (str(item["deleted_at"]), item["display_title"]), reverse=True)
    return cards


def build_trash_stats(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_count": len(entries),
        "note_count": sum(1 for item in entries if item["item_type"] == "note"),
        "file_count": sum(1 for item in entries if item["item_type"] == "file"),
        "transcript_count": sum(1 for item in entries if item["item_type"] == "transcript"),
        "group_count": sum(1 for item in entries if item["item_type"] == "group"),
        "monitor_report_count": sum(1 for item in entries if item["item_type"] == "monitor_report"),
        "signal_report_count": sum(1 for item in entries if item["item_type"] == "signal_report"),
    }


def permanently_delete_trash_entry(trash_entry: dict[str, Any]) -> None:
    payload = trash_entry["payload"]
    if trash_entry["item_type"] == "file":
        symbol = str(trash_entry.get("symbol") or "")
        if symbol:
            target_path = stock_upload_dir(symbol) / str(payload.get("stored_name") or "")
            if target_path.exists():
                target_path.unlink()
    elif trash_entry["item_type"] == "transcript":
        target_path = transcript_local_path(payload)
        if target_path.exists():
            target_path.unlink()
        bucket_name = str(payload.get("source_bucket_name") or "").strip()
        object_key = str(payload.get("source_object_key") or "").strip()
        if bucket_name and object_key:
            delete_uploaded_object(
                bucket_name=bucket_name,
                object_key=object_key,
            )
    elif trash_entry["item_type"] == "monitor_report":
        trash_path = Path(str(payload.get("trash_path") or ""))
        if trash_path.exists():
            trash_path.unlink()
    elif trash_entry["item_type"] == "signal_report":
        trash_path = Path(str(payload.get("trash_path") or ""))
        if trash_path.exists():
            trash_path.unlink()

def build_stock_detail(store: dict[str, Any], symbol: str) -> dict[str, Any]:
    if symbol not in list_stock_symbols(store):
        abort(404)

    entry = ensure_stock_entry(store, symbol)
    notes = sorted(entry["notes"], key=lambda item: item["created_at"], reverse=True)
    files = sorted(entry["files"], key=lambda item: item["uploaded_at"], reverse=True)
    transcripts = build_transcript_cards(store, symbol_filter=symbol)
    file_lookup = {file_entry["id"]: file_entry for file_entry in files}
    related_reports = find_related_reports(symbol)

    return {
        **build_stock_card(store, symbol),
        "notes": [
            {
                **note,
                "display_title": note["title"] or "未命名笔记",
                "display_created_at": note_display_time(note),
                "summary_excerpt": summarize_text_block(note["content_text"]),
                "source_file": file_lookup.get(note.get("source_file_id", "")),
                "source_file_name_display": note.get("source_file_name")
                or (
                    file_lookup.get(note.get("source_file_id", ""), {}).get("original_name", "")
                    if note.get("source_file_id")
                    else ""
                ),
                "tags": normalize_tag_list(note.get("tags", [])),
            }
            for note in notes
        ],
        "files": [
            {
                **file_entry,
                "display_uploaded_at": file_display_time(file_entry),
                "is_text_previewable": is_text_previewable(file_entry["original_name"]),
                "is_image_previewable": is_image_previewable(file_entry["original_name"]),
                "is_previewable": is_file_previewable(file_entry["original_name"]),
                "preview_label": "查看图片" if is_image_previewable(file_entry["original_name"]) else "在线预览",
                "has_linked_note": bool(file_entry.get("linked_note_id")),
                "summary_excerpt": summarize_text_block(file_entry.get("description") or file_entry["original_name"]),
                "tags": normalize_tag_list(file_entry.get("tags", [])),
            }
            for file_entry in files
        ],
        "transcripts": transcripts,
        "related_reports": related_reports,
        "timeline": build_stock_timeline(store, symbol, related_reports=related_reports),
        "tag_summary": build_stock_tag_summary(store, symbol)[:12],
        "created_label": format_iso_timestamp(entry.get("created_at")),
    }


def stock_upload_dir(symbol: str) -> Path:
    return STOCK_UPLOADS_DIR / symbol


def get_transcript_entry(store: dict[str, Any], transcript_id: str) -> dict[str, Any]:
    for transcript in store.get("transcripts", []):
        if transcript["id"] == transcript_id:
            return transcript

    abort(404)


def build_navigation_context(
    *,
    active_page: str,
    reports: list[dict[str, Any]] | None = None,
    stock_store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reports = reports if reports is not None else collect_reports()
    stock_store = stock_store if stock_store is not None else load_stock_store()

    return {
        "active_page": active_page,
        "nav_reports_count": len(reports),
        "nav_stock_count": len(list_stock_symbols(stock_store)),
        "nav_group_count": len(stock_store["groups"]),
        "nav_favorites_count": len(stock_store["favorites"]),
        "nav_transcript_count": len(stock_store.get("transcripts", [])),
        "nav_trash_count": len(stock_store.get("trash", [])),
    }


def load_codex_model_catalog() -> list[dict[str, Any]]:
    fallback = [
        {
            "slug": str(os.getenv("AI_CODEX_DEFAULT_MODEL", "gpt-5.4")),
            "display_name": str(os.getenv("AI_CODEX_DEFAULT_MODEL", "gpt-5.4")),
            "reasoning_levels": ["low", "medium", "high", "xhigh"],
            "default_reasoning": str(os.getenv("AI_CODEX_DEFAULT_REASONING", "medium")),
        }
    ]

    try:
        raw_data = json.loads(CODEX_MODELS_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback

    raw_models = raw_data.get("models") if isinstance(raw_data, dict) else []
    if not isinstance(raw_models, list):
        return fallback

    models: list[dict[str, Any]] = []
    for raw_model in raw_models:
        if not isinstance(raw_model, dict):
            continue
        slug = str(raw_model.get("slug") or "").strip()
        if not slug:
            continue
        reasoning_levels = [
            str(item.get("effort") or "").strip()
            for item in raw_model.get("supported_reasoning_levels", [])
            if isinstance(item, dict) and str(item.get("effort") or "").strip()
        ]
        models.append(
            {
                "slug": slug,
                "display_name": str(raw_model.get("display_name") or slug).strip(),
                "reasoning_levels": reasoning_levels or ["medium"],
                "default_reasoning": str(raw_model.get("default_reasoning_level") or "medium").strip() or "medium",
                "supports_verbosity": bool(raw_model.get("support_verbosity")),
                "default_verbosity": str(raw_model.get("default_verbosity") or "low").strip() or "low",
            }
        )

    return models or fallback


def normalize_ai_message(raw_message: Any) -> dict[str, Any] | None:
    if not isinstance(raw_message, dict):
        return None

    role = str(raw_message.get("role") or "").strip()
    if role not in {"user", "assistant"}:
        return None

    status = str(raw_message.get("status") or "completed").strip()
    if status not in {"pending", "running", "completed", "error", "cancelled"}:
        status = "completed"

    content = str(raw_message.get("content") or "").strip()
    if not content and status in {"completed", "error", "cancelled"}:
        return None

    return {
        "id": str(raw_message.get("id") or uuid.uuid4().hex[:12]),
        "role": role,
        "content": content,
        "created_at": str(raw_message.get("created_at") or now_iso()),
        "status": status,
        "model": str(raw_message.get("model") or "").strip()[:80],
        "reasoning_effort": str(raw_message.get("reasoning_effort") or "").strip()[:20],
        "response_style": str(raw_message.get("response_style") or "平衡").strip()[:20],
    }


def normalize_ai_session(raw_session: Any) -> dict[str, Any] | None:
    if not isinstance(raw_session, dict):
        return None

    session_id = str(raw_session.get("id") or uuid.uuid4().hex[:12]).strip()
    if not session_id:
        return None

    messages = [
        message
        for raw_message in raw_session.get("messages", [])
        if (message := normalize_ai_message(raw_message)) is not None
    ]
    created_at = str(raw_session.get("created_at") or now_iso())
    updated_at = str(raw_session.get("updated_at") or created_at)
    title = str(raw_session.get("title") or "").strip()[:120]
    if not title:
        first_user_message = next((item for item in messages if item["role"] == "user"), None)
        title = summarize_text_block(first_user_message["content"], 48) if first_user_message else "新对话"

    scope_settings = normalize_ai_scope_settings(raw_session.get("scope_settings", {}))

    return {
        "id": session_id,
        "title": title,
        "created_at": created_at,
        "updated_at": updated_at,
        "messages": messages,
        "scope_settings": scope_settings,
    }


def normalize_ai_chat_store(data: Any) -> dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    sessions = [
        session
        for raw_session in source.get("sessions", [])
        if (session := normalize_ai_session(raw_session)) is not None
    ]
    sessions.sort(key=lambda item: (item["updated_at"], item["id"]), reverse=True)
    return {"sessions": sessions}


def load_ai_chat_store() -> dict[str, Any]:
    AI_CHAT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not AI_CHAT_STORE_PATH.exists():
        return normalize_ai_chat_store({})

    try:
        raw_data = json.loads(AI_CHAT_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return normalize_ai_chat_store({})

    return normalize_ai_chat_store(raw_data)


def save_ai_chat_store(store: dict[str, Any]) -> None:
    normalized = normalize_ai_chat_store(store)
    AI_CHAT_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = AI_CHAT_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(AI_CHAT_STORE_PATH)


def generate_ai_session_title(source_text: str) -> str:
    compact = re.sub(r"\s+", " ", str(source_text or "")).strip()
    if not compact:
        return "新对话"

    prefixes = [
        "请帮我",
        "帮我",
        "看一下",
        "看下",
        "总结一下",
        "总结下",
        "请你",
        "请",
        "麻烦你",
        "能不能",
        "可以帮我",
        "可以",
    ]
    for prefix in prefixes:
        if compact.startswith(prefix):
            compact = compact[len(prefix):].strip(" ，,：:。")
            break

    compact = re.split(r"[。！？\n]", compact, maxsplit=1)[0].strip()
    if len(compact) > 20:
        compact = summarize_text_block(compact, limit=20)
    return compact or "新对话"


def get_ai_session(store: dict[str, Any], session_id: str) -> dict[str, Any]:
    for session in store.get("sessions", []):
        if session["id"] == session_id:
            return session
    abort(404)


def touch_ai_session(session: dict[str, Any]) -> None:
    session["updated_at"] = now_iso()


def build_ai_session_cards(store: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for session in store.get("sessions", []):
        last_message = session["messages"][-1] if session["messages"] else None
        pending_count = sum(1 for item in session["messages"] if item["status"] in {"pending", "running"})
        display_title = shorten_ai_session_title(session["title"])
        cards.append(
            {
                "id": session["id"],
                "title": session["title"],
                "display_title": display_title,
                "updated_label": format_iso_timestamp(session["updated_at"]),
                "preview": summarize_text_block(last_message["content"], 72) if last_message else "等待第一条问题",
                "pending_count": pending_count,
            }
        )
    return cards


def shorten_ai_session_title(source_text: str) -> str:
    compact = re.sub(r"\s+", " ", str(source_text or "")).strip()
    if not compact:
        return "新对话"

    prefixes = [
        "请帮我",
        "帮我",
        "帮忙",
        "请你",
        "请",
        "麻烦你",
        "可以帮我",
        "可以",
        "能不能",
        "看一下",
        "看下",
        "总结一下",
        "总结下",
        "分析一下",
        "分析下",
        "继续帮我",
        "继续",
        "再帮我",
        "再",
    ]
    leading_fillers = [
        "关于",
        "结合",
        "基于",
        "根据",
        "针对",
        "围绕",
        "对于",
        "把",
        "从",
        "就",
        "给我",
    ]

    changed = True
    while changed and compact:
        changed = False
        for prefix in prefixes:
            if compact.startswith(prefix):
                compact = compact[len(prefix) :].strip(" ，。、！？：:；;,.!?`\"'")
                changed = True
                break

    while compact:
        trimmed = compact
        for filler in leading_fillers:
            if trimmed.startswith(filler):
                trimmed = trimmed[len(filler) :].strip(" ，。、！？：:；;,.!?`\"'")
                break
        if trimmed == compact:
            break
        compact = trimmed

    compact = re.split(r"[\r\n]+", compact, maxsplit=1)[0].strip()
    compact = re.split(r"[。！？!?]", compact, maxsplit=1)[0].strip()

    parts = [part.strip() for part in re.split(r"[，,；;]", compact) if part.strip()]
    if parts:
        compact = parts[0]
        if len(compact) < 5 and len(parts) > 1:
            compact = f"{compact} {parts[1]}".strip()

    compact = compact.strip(" ，。、！？：:；;,.!?`\"'")
    if len(compact) > 18:
        compact = compact[:18].rstrip() + "…"
    return compact or "新对话"


def is_truthy_flag(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "on", "yes"}


def normalize_ai_scope_settings(
    raw_scope: Any,
    *,
    known_symbols: set[str] | None = None,
) -> dict[str, Any]:
    source = raw_scope if isinstance(raw_scope, dict) else {}

    if "symbols" in source:
        raw_symbols = source.get("symbols")
    elif "scope_symbols" in source:
        raw_symbols = source.get("scope_symbols")
    elif "scope_symbols_text" in source:
        raw_symbols = source.get("scope_symbols_text")
    else:
        raw_symbols = source.get("symbols_text", "")

    symbols = normalize_stock_symbol_list(raw_symbols)
    use_stock_scope = (
        is_truthy_flag(source.get("use_stock_scope"))
        if "use_stock_scope" in source
        else bool(symbols)
    )
    if use_stock_scope and known_symbols is not None:
        missing_symbols = [symbol for symbol in symbols if symbol not in known_symbols]
        if missing_symbols:
            raise ValueError(f"未找到对应股票：{'；'.join(missing_symbols)}")
    if use_stock_scope and not symbols:
        raise ValueError("请至少选择一只股票。")
    if not use_stock_scope:
        symbols = []

    if "content_kinds" in source:
        raw_content_kinds = source.get("content_kinds")
    elif "scope_content_kinds" in source:
        raw_content_kinds = source.get("scope_content_kinds")
    elif "content_kind" in source:
        raw_content_kinds = source.get("content_kind")
    else:
        raw_content_kinds = source.get("content_types", [])

    content_scope_explicit = any(
        key in source for key in ["content_kinds", "scope_content_kinds", "content_kind", "content_types"]
    )
    content_kinds = normalize_ai_scope_content_kinds(raw_content_kinds)
    if not content_kinds:
        if content_scope_explicit:
            raise ValueError("至少选择一种资料类型。")
        content_kinds = list(AI_SCOPE_DEFAULT_CONTENT_KINDS)

    start_date = normalize_date_field(source.get("start_date"))
    end_date = normalize_date_field(source.get("end_date"))
    use_date_scope = (
        is_truthy_flag(source.get("use_date_scope"))
        if "use_date_scope" in source
        else bool(start_date or end_date)
    )
    if use_date_scope:
        if not start_date or not end_date:
            raise ValueError("请选择完整的起始日期和终止日期。")
        if start_date > end_date:
            raise ValueError("起始日期不能晚于终止日期。")
    else:
        start_date = ""
        end_date = ""

    preview_month = str(source.get("preview_month") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", preview_month):
        preview_month = end_date[:7] if end_date else (start_date[:7] if start_date else "")

    selected_date = normalize_date_field(source.get("selected_date"))
    if use_date_scope and selected_date:
        if selected_date < start_date or selected_date > end_date:
            selected_date = ""

    return {
        "use_stock_scope": use_stock_scope,
        "symbols": symbols,
        "symbols_text": "；".join(symbols),
        "content_kinds": content_kinds,
        "content_kinds_text": "；".join(content_kinds),
        "content_labels": [AI_SCOPE_CONTENT_KIND_META[key] for key in content_kinds],
        "use_date_scope": use_date_scope,
        "start_date": start_date,
        "end_date": end_date,
        "preview_month": preview_month,
        "selected_date": selected_date,
    }


def build_ai_scope_time_bounds(scope_settings: dict[str, Any]) -> tuple[float | None, float | None]:
    if not scope_settings.get("use_date_scope"):
        return None, None

    start_dt = parse_iso_date_value(str(scope_settings.get("start_date") or ""))
    end_dt = parse_iso_date_value(str(scope_settings.get("end_date") or ""))
    start_timestamp = start_dt.timestamp() if start_dt else None
    end_timestamp = ((end_dt + timedelta(days=1)).timestamp() - 1) if end_dt else None
    return start_timestamp, end_timestamp


def report_matches_symbol(report: dict[str, Any], symbol: str) -> bool:
    pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", re.IGNORECASE)
    haystack = "\n".join(
        [
            str(report.get("title") or ""),
            str(report.get("summary") or ""),
            str(report.get("filename") or ""),
            str(report.get("content") or ""),
        ]
    )
    return bool(pattern.search(haystack))


def resolve_report_activity_date(report: dict[str, Any]) -> str:
    report_date = str(report.get("report_date") or "").strip()
    if len(report_date) >= 10:
        normalized = normalize_date_field(report_date[:10])
        if normalized:
            return normalized

    sort_value = float(report.get("sort_key") or 0)
    if sort_value > 0:
        try:
            return datetime.fromtimestamp(sort_value).date().isoformat()
        except (OSError, OverflowError, ValueError):
            pass

    return ""


def collect_ai_scope_materials(
    store: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    scope_settings: dict[str, Any],
) -> dict[str, Any]:
    selected_symbols = (
        ordered_unique(normalize_stock_symbol_list(scope_settings.get("symbols")))
        if scope_settings.get("use_stock_scope")
        else []
    )
    selected_symbol_set = set(selected_symbols)
    selected_kind_set = set(normalize_ai_scope_content_kinds(scope_settings.get("content_kinds")) or AI_SCOPE_DEFAULT_CONTENT_KINDS)
    range_start_timestamp, range_end_timestamp = build_ai_scope_time_bounds(scope_settings)

    def in_scope_range(sort_value: float) -> bool:
        if range_start_timestamp is not None and sort_value < range_start_timestamp:
            return False
        if range_end_timestamp is not None and sort_value > range_end_timestamp:
            return False
        return True

    report_items: list[dict[str, Any]] = []
    if "report" in selected_kind_set:
        for report in reports:
            matched_symbols = [symbol for symbol in selected_symbols if report_matches_symbol(report, symbol)]
            if selected_symbols and not matched_symbols:
                continue

            sort_value = float(report.get("sort_key") or 0)
            if not in_scope_range(sort_value):
                continue

            report_items.append(
                {
                    **report,
                    "sort_value": sort_value,
                    "activity_date": resolve_report_activity_date(report),
                    "matched_symbols": matched_symbols,
                    "detail_url": url_for("index", report=report["filename"]),
                    "detail_label": "打开报告",
                }
            )

    notes: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []

    symbols = selected_symbols if selected_symbols else sorted(list_stock_symbols(store))
    for item_symbol in symbols:
        entry = ensure_stock_entry(store, item_symbol)

        if "note" in selected_kind_set:
            for note in entry["notes"]:
                sort_value = coerce_sort_timestamp(note.get("created_at"))
                if not in_scope_range(sort_value):
                    continue

                note_id = str(note.get("id") or "").strip()
                detail_url = url_for("stock_detail", symbol=item_symbol)
                if note_id:
                    detail_url = f"{detail_url}#note-{note_id}"

                notes.append(
                    {
                        "symbol": item_symbol,
                        "id": note_id,
                        "title": note.get("title") or "未命名笔记",
                        "content_text": note.get("content_text") or "",
                        "created_at": str(note.get("created_at") or ""),
                        "display_time": note_display_time(note),
                        "sort_value": sort_value,
                        "tags": normalize_tag_list(note.get("tags", [])),
                        "summary": summarize_text_block(note.get("content_text") or ""),
                        "detail_url": detail_url,
                        "detail_label": "打开笔记",
                        "activity_date": iso_to_date(note.get("created_at")) or "",
                    }
                )

        if "file" in selected_kind_set:
            for file_entry in entry["files"]:
                sort_value = coerce_sort_timestamp(file_entry.get("uploaded_at"))
                if not in_scope_range(sort_value):
                    continue

                file_id = str(file_entry.get("id") or "").strip()
                detail_url = url_for("stock_detail", symbol=item_symbol)
                download_url = None
                if file_id:
                    detail_url = f"{detail_url}#file-{file_id}"
                    download_url = url_for("download_stock_file", symbol=item_symbol, file_id=file_id)

                files.append(
                    {
                        "symbol": item_symbol,
                        "id": file_id,
                        "title": file_entry.get("original_name") or "已上传文件",
                        "description": file_entry.get("description") or "",
                        "uploaded_at": str(file_entry.get("uploaded_at") or ""),
                        "display_time": file_display_time(file_entry),
                        "sort_value": sort_value,
                        "tags": normalize_tag_list(file_entry.get("tags", [])),
                        "summary": summarize_text_block(file_entry.get("description") or file_entry.get("original_name") or ""),
                        "detail_url": detail_url,
                        "detail_label": "打开资料",
                        "download_url": download_url,
                        "file_type": detect_file_type_label(str(file_entry.get("original_name") or "")),
                        "activity_date": iso_to_date(file_entry.get("uploaded_at")) or "",
                    }
                )

    if "transcript" in selected_kind_set:
        for transcript in store.get("transcripts", []):
            linked_symbols = transcript_linked_symbols(transcript)
            if selected_symbol_set and not selected_symbol_set.intersection(linked_symbols):
                continue

            sort_source = transcript.get("meeting_date") or transcript.get("created_at")
            sort_value = coerce_sort_timestamp(sort_source)
            if not in_scope_range(sort_value):
                continue

            primary_symbol = linked_symbols[0] if linked_symbols else ""
            detail_url = url_for("transcripts_page")
            if primary_symbol:
                detail_url = url_for("stock_detail", symbol=primary_symbol) + "#transcripts-panel"

            transcripts.append(
                {
                    "id": str(transcript.get("id") or "").strip(),
                    "title": transcript.get("title") or transcript.get("original_name") or "会议转录",
                    "meeting_date": str(transcript.get("meeting_date") or ""),
                    "created_at": str(transcript.get("created_at") or ""),
                    "display_time": str(transcript.get("meeting_date") or "") or format_iso_timestamp(transcript.get("created_at")),
                    "sort_value": sort_value,
                    "tags": normalize_tag_list(transcript.get("tags", [])),
                    "transcript_text": transcript.get("transcript_text") or "",
                    "summary": summarize_text_block(transcript.get("transcript_text") or TRANSCRIPT_PLACEHOLDER_COPY),
                    "status": str(transcript.get("status") or ""),
                    "status_label": TRANSCRIPT_STATUS_META.get(
                        str(transcript.get("status") or ""),
                        TRANSCRIPT_STATUS_META["pending_api"],
                    )["label"],
                    "linked_symbols": linked_symbols,
                    "linked_symbols_label": "；".join(linked_symbols),
                    "detail_url": detail_url,
                    "detail_label": "打开转录",
                    "activity_date": normalize_date_field(transcript.get("meeting_date")) or iso_to_date(transcript.get("created_at")) or "",
                }
            )

    report_items.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    notes.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    files.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    transcripts.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)

    included_symbols = ordered_unique(
        selected_symbols
        + [item["symbol"] for item in notes if item.get("symbol")]
        + [item["symbol"] for item in files if item.get("symbol")]
        + [linked_symbol for item in transcripts for linked_symbol in item.get("linked_symbols", [])]
    )

    return {
        "selected_symbols": selected_symbols,
        "reports": report_items,
        "notes": notes,
        "files": files,
        "transcripts": transcripts,
        "included_symbols": included_symbols,
        "report_count": len(report_items),
        "note_count": len(notes),
        "file_count": len(files),
        "transcript_count": len(transcripts),
    }


def build_ai_scope_activity(materials: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []

    for report in materials["reports"]:
        activity_date = str(report.get("activity_date") or "")
        if not activity_date:
            continue
        entries.append(
            {
                "date": activity_date,
                "timestamp": f"{float(report.get('sort_value') or 0):.6f}",
                "kind": "report",
                "kind_label": "日报",
                "symbol": "；".join(report.get("matched_symbols") or []),
                "title": report["title"],
                "summary": report["summary"],
                "display_time": report["report_date"],
                "detail_url": report["detail_url"],
                "detail_label": report["detail_label"],
            }
        )

    for note in materials["notes"]:
        activity_date = str(note.get("activity_date") or "")
        if not activity_date:
            continue
        entries.append(
            {
                "date": activity_date,
                "timestamp": note["created_at"],
                "kind": "note",
                "kind_label": "笔记",
                "symbol": note["symbol"],
                "title": note["title"],
                "summary": note["summary"],
                "display_time": note["display_time"],
                "detail_url": note["detail_url"],
                "detail_label": note["detail_label"],
            }
        )

    for file_entry in materials["files"]:
        activity_date = str(file_entry.get("activity_date") or "")
        if not activity_date:
            continue
        entries.append(
            {
                "date": activity_date,
                "timestamp": file_entry["uploaded_at"],
                "kind": "file",
                "kind_label": "文件",
                "symbol": file_entry["symbol"],
                "title": file_entry["title"],
                "summary": file_entry["summary"],
                "display_time": file_entry["display_time"],
                "detail_url": file_entry["detail_url"],
                "detail_label": file_entry["detail_label"],
                "download_url": file_entry["download_url"],
                "file_type": file_entry["file_type"],
            }
        )

    for transcript in materials["transcripts"]:
        activity_date = str(transcript.get("activity_date") or "")
        if not activity_date:
            continue
        entries.append(
            {
                "date": activity_date,
                "timestamp": transcript["meeting_date"] or transcript["created_at"],
                "kind": "transcript",
                "kind_label": "转录",
                "symbol": transcript["linked_symbols_label"],
                "title": transcript["title"],
                "summary": transcript["summary"],
                "display_time": transcript["display_time"],
                "detail_url": transcript["detail_url"],
                "detail_label": transcript["detail_label"],
            }
        )

    entries.sort(
        key=lambda item: (item["date"], item["timestamp"], item["symbol"], item["title"]),
        reverse=True,
    )

    summaries: dict[str, dict[str, Any]] = {}
    for item in entries:
        day = summaries.setdefault(
            item["date"],
            {
                "date": item["date"],
                "items": [],
                "symbols": set(),
                "kind_counter": Counter(),
            },
        )
        day["items"].append(item)
        if item.get("symbol"):
            day["symbols"].add(str(item["symbol"]))
        day["kind_counter"][str(item["kind"])] += 1

    for day in summaries.values():
        day["items"].sort(
            key=lambda item: (item["timestamp"], item["symbol"], item["title"]),
            reverse=True,
        )
        day["stock_count"] = len(day["symbols"])
        day["total_count"] = len(day["items"])
        day["note_count"] = day["kind_counter"].get("note", 0)
        day["file_count"] = day["kind_counter"].get("file", 0)
        day["transcript_count"] = day["kind_counter"].get("transcript", 0)
        day["report_count"] = day["kind_counter"].get("report", 0)
        day["kind_summary"] = [
            {"label": "笔记", "count": day["note_count"]},
            {"label": "文件", "count": day["file_count"]},
            {"label": "转录", "count": day["transcript_count"]},
            {"label": "日报", "count": day["report_count"]},
        ]
        day.pop("symbols", None)
        day.pop("kind_counter", None)

    return {
        "entries": entries,
        "summaries": summaries,
    }


def build_ai_scope_period_stats(entries: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    matched_entries = [item for item in entries if item["date"].startswith(prefix)]
    return {
        "total_count": len(matched_entries),
        "active_days": len({item["date"] for item in matched_entries}),
        "note_count": sum(1 for item in matched_entries if item["kind"] == "note"),
        "file_count": sum(1 for item in matched_entries if item["kind"] == "file"),
        "transcript_count": sum(1 for item in matched_entries if item["kind"] == "transcript"),
        "report_count": sum(1 for item in matched_entries if item["kind"] == "report"),
    }


def build_ai_scope_entry_totals(entries: list[dict[str, Any]]) -> dict[str, Any]:
    symbol_values: set[str] = set()
    active_days: set[str] = set()
    kind_counter: Counter[str] = Counter()

    for item in entries:
        day_value = str(item.get("date") or "").strip()
        if day_value:
            active_days.add(day_value)

        kind_counter[str(item.get("kind") or "")] += 1

        symbol_label = str(item.get("symbol") or "").strip()
        if not symbol_label:
            continue
        for chunk in re.split(r"[；;,\s]+", symbol_label):
            candidate = chunk.strip()
            if candidate:
                symbol_values.add(candidate)

    kind_summary = [
        {"key": "report", "label": "日报", "count": kind_counter.get("report", 0)},
        {"key": "note", "label": "笔记", "count": kind_counter.get("note", 0)},
        {"key": "file", "label": "文件", "count": kind_counter.get("file", 0)},
        {"key": "transcript", "label": "转录", "count": kind_counter.get("transcript", 0)},
    ]

    structure_parts = [f"{item['label']} {item['count']}" for item in kind_summary if item["count"]]
    return {
        "total_count": len(entries),
        "stock_count": len(symbol_values),
        "days_count": len(active_days),
        "note_count": kind_counter.get("note", 0),
        "file_count": kind_counter.get("file", 0),
        "transcript_count": kind_counter.get("transcript", 0),
        "report_count": kind_counter.get("report", 0),
        "kind_summary": kind_summary,
        "structure_label": " / ".join(structure_parts) if structure_parts else "当前没有资料",
    }


def build_ai_scope_preview_groups(
    entries: list[dict[str, Any]],
    *,
    detail_mode: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {
        "report": [],
        "note": [],
        "file": [],
        "transcript": [],
    }
    for entry in entries:
        kind = str(entry.get("kind") or "")
        if kind in grouped:
            grouped[kind].append(entry)

    preferred_open_key = ""
    if detail_mode == "day":
        for key in ["note", "file", "transcript", "report"]:
            if grouped[key]:
                preferred_open_key = key
                break

    groups: list[dict[str, Any]] = []
    for key, label in [
        ("note", "笔记"),
        ("file", "文件"),
        ("transcript", "转录"),
        ("report", "日报"),
    ]:
        items = grouped[key]
        if not items:
            continue
        groups.append(
            {
                "key": key,
                "label": label,
                "count": len(items),
                "items": items,
                "default_open": key == preferred_open_key,
            }
        )
    return groups


def build_ai_scope_summary(
    scope_settings: dict[str, Any],
    materials: dict[str, Any],
) -> dict[str, Any]:
    stock_scope_active = bool(scope_settings.get("use_stock_scope") and scope_settings.get("symbols"))
    date_scope_active = bool(
        scope_settings.get("use_date_scope")
        and scope_settings.get("start_date")
        and scope_settings.get("end_date")
    )
    selected_content_kinds = normalize_ai_scope_content_kinds(scope_settings.get("content_kinds")) or list(
        AI_SCOPE_DEFAULT_CONTENT_KINDS
    )
    content_scope_active = set(selected_content_kinds) != set(AI_SCOPE_DEFAULT_CONTENT_KINDS)
    has_filters = stock_scope_active or date_scope_active or content_scope_active

    if stock_scope_active:
        headline = "当前只读取选定股票的资料"
        stock_label = "股票范围：" + "；".join(scope_settings["symbols"])
    else:
        headline = "当前读取全站资料库"
        stock_label = "股票范围：全站"

    time_label = (
        f"时间窗口：{scope_settings['start_date']} 至 {scope_settings['end_date']}"
        if date_scope_active
        else "时间窗口：不限"
    )

    content_label = "资料类型：" + "；".join(AI_SCOPE_CONTENT_KIND_META[key] for key in selected_content_kinds)

    return {
        "headline": headline,
        "description": "提问时只会把这里定义范围内的报告、笔记、文件和转录交给 Codex。",
        "stock_label": stock_label,
        "time_label": time_label,
        "content_label": content_label,
        "has_filters": has_filters,
        "metrics": [
            {"label": "报告", "value": materials["report_count"]},
            {"label": "笔记", "value": materials["note_count"]},
            {"label": "文件", "value": materials["file_count"]},
            {"label": "转录", "value": materials["transcript_count"]},
        ],
    }


def build_ai_scope_preview_context(
    stock_store: dict[str, Any],
    reports: list[dict[str, Any]],
    scope_settings: dict[str, Any],
    *,
    month_param: str | None,
    year_param: str | None = None,
    month_number_param: str | None = None,
    date_param: str | None = None,
) -> dict[str, Any]:
    materials = collect_ai_scope_materials(stock_store, reports, scope_settings=scope_settings)
    activity = build_ai_scope_activity(materials)
    range_scope_active = bool(
        scope_settings.get("use_date_scope")
        and scope_settings.get("start_date")
        and scope_settings.get("end_date")
    )
    range_start = str(scope_settings.get("start_date") or "") if range_scope_active else ""
    range_end = str(scope_settings.get("end_date") or "") if range_scope_active else ""

    selected_date_value = parse_iso_date_value(date_param)
    fallback_month = (
        selected_date_value
        or (parse_iso_date_value(activity["entries"][0]["date"]) if activity["entries"] else None)
        or parse_iso_date_value(str(scope_settings.get("end_date") or ""))
        or parse_iso_date_value(str(scope_settings.get("start_date") or ""))
        or datetime.now()
    )
    month_value = resolve_month_value(
        month_param=month_param,
        year_param=year_param,
        month_number_param=month_number_param,
        fallback=fallback_month,
    )
    selected_date = normalize_date_field(date_param)
    month_key = month_value.strftime("%Y-%m")

    if range_scope_active:
        if not selected_date.startswith(month_key):
            selected_date = ""
        if selected_date and not (range_start <= selected_date <= range_end):
            selected_date = ""
    else:
        if not selected_date or not selected_date.startswith(month_key):
            selected_date = find_month_default_date(activity["summaries"], month_value)

    previous_year, previous_month = shift_month(month_value.year, month_value.month, -1)
    next_year, next_month = shift_month(month_value.year, month_value.month, 1)
    month_stats = build_ai_scope_period_stats(activity["entries"], month_key)
    if range_scope_active:
        detail_entries = [
            item
            for item in activity["entries"]
            if range_start <= item["date"] <= range_end
        ]
    else:
        detail_entries = [item for item in activity["entries"] if item["date"].startswith(month_key)]

    selected_summary = activity["summaries"].get(selected_date) if selected_date else None
    detail_mode = "range" if range_scope_active else "month"
    detail_eyebrow = "范围资料" if range_scope_active else "本月资料"
    detail_heading = (
        f"{range_start} 至 {range_end}" if range_scope_active else month_value.strftime("%Y 年 %m 月")
    )
    detail_description = (
        "当前时间范围内的资料会集中列在右侧；单击某一天后，只看那一天，再点一次可恢复整个范围。"
        if range_scope_active
        else "当前月份内的资料会列在右侧；点某一天后可以切到单天视图。"
    )
    if selected_summary:
        detail_entries = list(selected_summary["items"])
        detail_mode = "day"
        detail_eyebrow = "当天资料"
        detail_heading = selected_summary["date"]
        detail_description = "当前聚焦到这一天。再次点击同一天，会恢复显示当前时间范围内的全部资料。"

    detail_totals = build_ai_scope_entry_totals(detail_entries)
    detail_groups = build_ai_scope_preview_groups(detail_entries, detail_mode=detail_mode)
    content_kind_options = [
        {
            "key": key,
            "label": AI_SCOPE_CONTENT_KIND_META[key],
            "count": materials[f"{key}_count"],
            "checked": key in (scope_settings.get("content_kinds") or []),
        }
        for key in AI_SCOPE_DEFAULT_CONTENT_KINDS
    ]

    return {
        "scope_settings": scope_settings,
        "materials": materials,
        "summary": build_ai_scope_summary(scope_settings, materials),
        "month_value": month_value,
        "month_key": month_key,
        "month_label": month_value.strftime("%Y 年 %m 月"),
        "previous_month_key": f"{previous_year:04d}-{previous_month:02d}",
        "next_month_key": f"{next_year:04d}-{next_month:02d}",
        "current_month_key": datetime.now().strftime("%Y-%m"),
        "selected_year": month_value.year,
        "selected_month_number": month_value.month,
        "available_years": build_available_years(activity["entries"], month_value.year),
        "month_options": [{"value": month, "label": f"{month} 月"} for month in range(1, 13)],
        "selected_date": selected_date,
        "selected_summary": selected_summary,
        "calendar_weeks": build_calendar_weeks(
            month_value,
            activity["summaries"],
            selected_date,
            range_start=range_start,
            range_end=range_end,
        ),
        "range_scope_active": range_scope_active,
        "range_start": range_start,
        "range_end": range_end,
        "detail_mode": detail_mode,
        "detail_eyebrow": detail_eyebrow,
        "detail_heading": detail_heading,
        "detail_description": detail_description,
        "detail_totals": detail_totals,
        "detail_groups": detail_groups,
        "content_kind_options": content_kind_options,
        "month_stats": month_stats,
    }


def build_ai_workspace_timeline(materials: dict[str, Any], *, limit: int = 36) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for report in materials["reports"][:24]:
        events.append(
            {
                "kind_label": "关联日报",
                "symbol_label": "；".join(report.get("matched_symbols") or []) or "全站归档",
                "title": report["title"],
                "summary": report["summary"],
                "display_time": report["report_date"],
                "sort_value": float(report.get("sort_value") or 0),
            }
        )

    for note in materials["notes"]:
        events.append(
            {
                "kind_label": SEARCH_KIND_META["note"]["label"],
                "symbol_label": note["symbol"],
                "title": note["title"],
                "summary": note["summary"],
                "display_time": note["display_time"],
                "sort_value": float(note["sort_value"]),
            }
        )

    for file_entry in materials["files"]:
        events.append(
            {
                "kind_label": SEARCH_KIND_META["file"]["label"],
                "symbol_label": file_entry["symbol"],
                "title": file_entry["title"],
                "summary": file_entry["summary"],
                "display_time": file_entry["display_time"],
                "sort_value": float(file_entry["sort_value"]),
            }
        )

    for transcript in materials["transcripts"]:
        events.append(
            {
                "kind_label": SEARCH_KIND_META["transcript"]["label"],
                "symbol_label": transcript["linked_symbols_label"] or "未关联股票",
                "title": transcript["title"],
                "summary": transcript["summary"],
                "display_time": transcript["display_time"],
                "sort_value": float(transcript["sort_value"]),
            }
        )

    events.sort(key=lambda item: (float(item["sort_value"]), item["title"]), reverse=True)
    return events[:limit]


def style_label_to_prompt(style_value: str) -> str:
    mapping = {
        "简洁": "回答尽量简洁，直接给出结论、提醒和最关键证据。",
        "平衡": "回答保持清晰和实用，先给结论，再给必要依据和待跟进点。",
        "详细": "回答尽量完整，按结论、证据、风险、遗漏点、后续动作展开。",
    }
    return mapping.get(style_value, mapping["平衡"])


def build_ai_knowledge_bundle(session: dict[str, Any]) -> Path:
    reports = collect_reports()
    stock_store = load_stock_store()
    workspace_timeline = build_workspace_recent_timeline(stock_store, reports)
    AI_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = AI_CONTEXT_DIR / f"{session['id']}-knowledge.md"

    lines = [
        "# 网页资料知识包",
        "",
        "这份文件由网页后端自动生成，供只读 Codex 问答使用。",
        "",
        "## 站点概览",
        f"- 生成时间: {now_iso()}",
        f"- 报告数量: {len(reports)}",
        f"- 股票数量: {len(list_stock_symbols(stock_store))}",
        f"- 分组数量: {len(stock_store['groups'])}",
        f"- 自选数量: {len(stock_store['favorites'])}",
        f"- 转录任务数量: {len(stock_store.get('transcripts', []))}",
        "",
        "## 股票分组与自选",
    ]

    if stock_store["groups"]:
        for group in stock_store["groups"]:
            lines.append(f"- 分组 {group['name']}: {', '.join(group['stocks']) or '空'}")
    else:
        lines.append("- 当前没有分组")
    lines.append(f"- 自选: {', '.join(stock_store['favorites']) or '空'}")
    lines.append("")

    lines.extend(
        build_timeline_digest_lines(
            workspace_timeline,
            heading="## 全站最近变化",
            empty_message="当前还没有可供比较的近期变化。",
            limit=28,
        )
    )

    lines.append("## 报告索引")
    if reports:
        for report in reports[:18]:
            lines.extend(
                [
                    f"### {report['title']}",
                    f"- 日期: {report['report_date']}",
                    f"- 文件: {report['filename']}",
                    f"- 摘要: {report['summary']}",
                    "",
                ]
            )
            content = read_report_text(REPORTS_DIR / report["filename"]).strip()
            if content:
                lines.append(trim_note_content(content[:8000]))
                lines.append("")
    else:
        lines.append("- 当前没有报告")
        lines.append("")

    lines.append("## 股票研究资料")
    for symbol in sorted(list_stock_symbols(stock_store)):
        detail = build_stock_detail(stock_store, symbol)
        lines.extend(
            [
                f"### {symbol}",
                f"- 分组: {', '.join(group['name'] for group in detail['groups']) or '无'}",
                f"- 标签汇总: {', '.join(item['value'] for item in detail['tag_summary']) or '无'}",
                f"- 笔记数: {detail['note_count']}",
                f"- 文件数: {detail['file_count']}",
                f"- 转录数: {detail['transcript_count']}",
                "",
            ]
        )
        lines.extend(
            build_timeline_digest_lines(
                detail["timeline"],
                heading="#### 这只股票的时间线",
                empty_message="这只股票还没有沉淀出可比较的时间线内容。",
                limit=18,
            )
        )
        for note in detail["notes"][:12]:
            lines.extend(
                [
                    f"#### 笔记: {note['display_title']}",
                    f"- 时间: {note['display_created_at']}",
                    f"- 标签: {', '.join(note['tags']) or '无'}",
                    trim_note_content(note["content_text"][:8000]),
                    "",
                ]
            )
        for file_entry in detail["files"][:12]:
            lines.extend(
                [
                    f"#### 文件: {file_entry['original_name']}",
                    f"- 时间: {file_entry['display_uploaded_at']}",
                    f"- 标签: {', '.join(file_entry['tags']) or '无'}",
                    f"- 说明: {file_entry['description'] or '无'}",
                    "",
                ]
            )
        for transcript in detail["transcripts"][:10]:
            lines.extend(
                [
                    f"#### 转录: {transcript['display_title']}",
                    f"- 会议日期: {transcript['meeting_date_label']}",
                    f"- 状态: {transcript['status_label']}",
                    f"- 标签: {', '.join(transcript['tags']) or '无'}",
                    trim_note_content((transcript.get('transcript_text') or transcript['summary_excerpt'])[:12000]),
                    "",
                ]
            )
        related_titles = ", ".join(report["title"] for report in detail["related_reports"][:8]) or "无"
        lines.append(f"- 关联日报: {related_titles}")
        lines.append("")

    bundle_path.write_text("\n".join(lines), encoding="utf-8")
    return bundle_path


def build_ai_scoped_knowledge_bundle(session: dict[str, Any]) -> Path:
    reports = collect_reports()
    stock_store = load_stock_store()
    scope_settings = normalize_ai_scope_settings(session.get("scope_settings", {}))
    materials = collect_ai_scope_materials(stock_store, reports, scope_settings=scope_settings)
    workspace_timeline = build_ai_workspace_timeline(materials)
    scope_summary = build_ai_scope_summary(scope_settings, materials)
    range_start_timestamp, range_end_timestamp = build_ai_scope_time_bounds(scope_settings)
    AI_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = AI_CONTEXT_DIR / f"{session['id']}-knowledge.md"

    def in_scope_timeline(item: dict[str, Any]) -> bool:
        if not scope_settings.get("use_date_scope"):
            return True
        sort_value = float(item.get("sort_value") or 0)
        if range_start_timestamp is not None and sort_value < range_start_timestamp:
            return False
        if range_end_timestamp is not None and sort_value > range_end_timestamp:
            return False
        return True

    lines = [
        "# 网页资料知识包",
        "",
        "这份文件由网页后端自动生成，供只读模式的 Codex 问答使用。",
        "",
        "## 当前知识范围",
        f"- 生成时间: {now_iso()}",
        f"- {scope_summary['stock_label']}",
        f"- {scope_summary['time_label']}",
        f"- {scope_summary['content_label']}",
        f"- 范围内报告数: {materials['report_count']}",
        f"- 范围内笔记数: {materials['note_count']}",
        f"- 范围内文件数: {materials['file_count']}",
        f"- 范围内转录数: {materials['transcript_count']}",
        "",
        "## 站点概览",
        f"- 全站报告数量: {len(reports)}",
        f"- 全站股票数量: {len(list_stock_symbols(stock_store))}",
        f"- 分组数量: {len(stock_store['groups'])}",
        f"- 自选数量: {len(stock_store['favorites'])}",
        f"- 转录任务数量: {len(stock_store.get('transcripts', []))}",
        "",
    ]

    lines.extend(
        build_timeline_digest_lines(
            workspace_timeline,
            heading="## 当前范围内的时间线",
            empty_message="当前范围里还没有可比较的时间线内容。",
            limit=36,
        )
    )

    lines.append("## 报告索引")
    if materials["reports"]:
        for report in materials["reports"][:18]:
            lines.extend(
                [
                    f"### {report['title']}",
                    f"- 日期: {report['report_date']}",
                    f"- 文件: {report['filename']}",
                    f"- 摘要: {report['summary']}",
                    "",
                ]
            )
            content = read_report_text(REPORTS_DIR / report["filename"]).strip()
            if content:
                lines.append(trim_note_content(content[:8000]))
                lines.append("")
    else:
        lines.extend(["- 当前范围内没有日报", ""])

    lines.append("## 股票研究资料")
    grouped_notes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_files: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_transcripts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in materials["notes"]:
        grouped_notes[note["symbol"]].append(note)
    for file_entry in materials["files"]:
        grouped_files[file_entry["symbol"]].append(file_entry)
    for transcript in materials["transcripts"]:
        for symbol in transcript.get("linked_symbols") or []:
            if symbol:
                grouped_transcripts[symbol].append(transcript)

    scoped_symbols = materials["included_symbols"] or (
        sorted(list_stock_symbols(stock_store))
        if not scope_settings.get("use_stock_scope") and not scope_settings.get("use_date_scope")
        else []
    )
    for symbol in scoped_symbols:
        stock_card = build_stock_card(stock_store, symbol)
        timeline = [
            item
            for item in build_stock_timeline(
                stock_store,
                symbol,
                related_reports=[report for report in materials["reports"] if report_matches_symbol(report, symbol)],
            )
            if in_scope_timeline(item)
        ]
        tag_items = collect_tag_counts(
            grouped_notes.get(symbol, [])
            + grouped_files.get(symbol, [])
            + grouped_transcripts.get(symbol, [])
        )[:12]

        lines.extend(
            [
                f"### {symbol}",
                f"- 分组: {', '.join(group['name'] for group in stock_card['groups']) or '无'}",
                f"- 标签汇总: {', '.join(item['value'] for item in tag_items) or '无'}",
                f"- 笔记数: {len(grouped_notes.get(symbol, []))}",
                f"- 文件数: {len(grouped_files.get(symbol, []))}",
                f"- 转录数: {len(grouped_transcripts.get(symbol, []))}",
                "",
            ]
        )
        lines.extend(
            build_timeline_digest_lines(
                timeline,
                heading="#### 这只股票的时间线",
                empty_message="这只股票在当前范围里还没有可比较的时间线内容。",
                limit=18,
            )
        )
        for note in grouped_notes.get(symbol, [])[:12]:
            lines.extend(
                [
                    f"#### 笔记: {note['title']}",
                    f"- 时间: {note['display_time']}",
                    f"- 标签: {', '.join(note['tags']) or '无'}",
                    trim_note_content(note["content_text"][:8000]),
                    "",
                ]
            )
        for file_entry in grouped_files.get(symbol, [])[:12]:
            lines.extend(
                [
                    f"#### 文件: {file_entry['title']}",
                    f"- 时间: {file_entry['display_time']}",
                    f"- 标签: {', '.join(file_entry['tags']) or '无'}",
                    f"- 说明: {file_entry['description'] or '无'}",
                    "",
                ]
            )
        for transcript in grouped_transcripts.get(symbol, [])[:10]:
            lines.extend(
                [
                    f"#### 转录: {transcript['title']}",
                    f"- 会议日期: {transcript['meeting_date'] or transcript['display_time']}",
                    f"- 状态: {transcript['status_label']}",
                    f"- 标签: {', '.join(transcript['tags']) or '无'}",
                    trim_note_content((transcript.get("transcript_text") or transcript["summary"])[:12000]),
                    "",
                ]
            )
        related_titles = ", ".join(
            report["title"] for report in materials["reports"] if report_matches_symbol(report, symbol)
        ) or "无"
        lines.append(f"- 关联日报: {related_titles}")
        lines.append("")

    bundle_path.write_text("\n".join(lines), encoding="utf-8")
    return bundle_path


def build_ai_recent_history(session: dict[str, Any], limit: int = 8) -> str:
    messages = session["messages"][-limit:]
    history_lines: list[str] = []
    for message in messages:
        if message["status"] in {"pending", "running", "error", "cancelled"}:
            continue
        if message["role"] == "assistant" and "无法读取" in message["content"] and "知识包" in message["content"]:
            continue
        role_label = "用户" if message["role"] == "user" else "Codex"
        history_lines.append(f"{role_label}: {message['content']}")
    return "\n\n".join(history_lines)


def load_ai_knowledge_text(bundle_path: Path) -> str:
    try:
        knowledge_text = bundle_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""

    limit = max(AI_PROMPT_KNOWLEDGE_CHAR_LIMIT, 4000)
    if len(knowledge_text) <= limit:
        return knowledge_text

    return (
        knowledge_text[:limit].rstrip()
        + "\n\n[知识包内容过长，后续部分已截断；请只基于上方已提供内容回答。]"
    )


def build_ai_codex_prompt(
    *,
    session: dict[str, Any],
    user_question: str,
    response_style: str,
    bundle_path: Path,
) -> str:
    history_block = build_ai_recent_history(session)
    knowledge_text = load_ai_knowledge_text(bundle_path)
    return (
        "你现在是一个只读的网页研究问答助手。\n"
        "目标：基于当前网页资料回答用户问题，帮助提醒遗漏点、风险点、待跟进事项或相互印证关系。\n"
        "重要约束：\n"
        "1. 你运行在只读模式，严禁修改任何文件，也不要提出执行修改。\n"
        "2. 本次问答所需的网页知识包正文，已经直接放在这条 prompt 里；请优先只基于下方正文回答。\n"
        f"3. 知识包原始文件路径仅供标注参考，不要求你主动去读文件：{bundle_path}\n"
        "4. 如果资料中没有明确证据，请直接说明“目前资料里没有看到”。\n"
        "5. 不要再回答“无法读取本地文件”或“拿不到知识包”，因为正文已经直接提供给你了。\n"
        "6. 回答尽量基于网页已有资料，不要脱离资料泛泛而谈。\n"
        f"7. 回答风格要求: {style_label_to_prompt(response_style)}\n"
        "8. 如果问题涉及某段时间、变化趋势、前后对比，请优先参考知识包里的“最近变化”和“时间线”部分，按时间顺序作答。\n"
        "9. 回答时尽量分成：结论 / 依据 / 提醒或遗漏点 / 下一步建议。\n\n"
        f"网页知识包正文:\n{knowledge_text or '（当前知识包正文为空，请明确说明资料不足。）'}\n\n"
        f"最近对话历史:\n{history_block or '（这是新对话）'}\n\n"
        f"当前用户问题:\n{user_question.strip()}\n"
    )


def update_ai_message(
    session_id: str,
    message_id: str,
    *,
    status: str | None = None,
    content: str | None = None,
) -> None:
    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = get_ai_session(store, session_id)
        for message in session["messages"]:
            if message["id"] != message_id:
                continue
            if status is not None:
                message["status"] = status
            if content is not None:
                message["content"] = content
            touch_ai_session(session)
            save_ai_chat_store(store)
            return


def read_ai_message(session_id: str, message_id: str) -> dict[str, Any] | None:
    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = get_ai_session(store, session_id)
        for message in session["messages"]:
            if message["id"] == message_id:
                return deepcopy(message)
    return None


def register_ai_process(message_id: str, process: subprocess.Popen[str]) -> None:
    with AI_PROCESS_LOCK:
        AI_RUNNING_PROCESSES[message_id] = process


def release_ai_process(message_id: str) -> None:
    with AI_PROCESS_LOCK:
        AI_RUNNING_PROCESSES.pop(message_id, None)


def request_ai_stop(message_id: str) -> subprocess.Popen[str] | None:
    with AI_PROCESS_LOCK:
        AI_STOP_REQUESTS.add(message_id)
        return AI_RUNNING_PROCESSES.get(message_id)


def ai_stop_requested(message_id: str) -> bool:
    with AI_PROCESS_LOCK:
        return message_id in AI_STOP_REQUESTS


def clear_ai_stop_request(message_id: str) -> None:
    with AI_PROCESS_LOCK:
        AI_STOP_REQUESTS.discard(message_id)


def resolve_codex_cli_path() -> Path | None:
    candidates: list[Path] = []

    env_path = str(os.getenv("CODEX_CLI_PATH") or "").strip()
    if env_path:
        candidates.append(Path(env_path))

    detected = shutil.which("codex")
    if detected:
        candidates.append(Path(detected))

    extension_root = Path.home() / ".vscode" / "extensions"
    if extension_root.exists():
        patterns = [
            "openai.chatgpt-*-win32-x64/bin/windows-x86_64/codex.exe",
            "openai.chatgpt-*/bin/windows-x86_64/codex.exe",
            "openai.chatgpt-*-linux-x64/bin/linux-x86_64/codex",
            "openai.chatgpt-*/bin/linux-x86_64/codex",
            "openai.chatgpt-*-darwin-arm64/bin/darwin-aarch64/codex",
            "openai.chatgpt-*-darwin-x64/bin/darwin-x86_64/codex",
        ]
        for pattern in patterns:
            candidates.extend(sorted(extension_root.glob(pattern), reverse=True))

    for candidate in candidates:
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue

    return None


def run_ai_codex_reply(
    session_id: str,
    message_id: str,
    *,
    model: str,
    reasoning_effort: str,
    response_style: str,
) -> None:
    output_path = AI_CONTEXT_DIR / f"{message_id}-reply.txt"
    process: subprocess.Popen[str] | None = None
    try:
        codex_cli_path = resolve_codex_cli_path()
        if codex_cli_path is None:
            raise RuntimeError("当前电脑没有检测到可用的 Codex 可执行文件。")

        with AI_SESSION_LOCK:
            store = load_ai_chat_store()
            session = get_ai_session(store, session_id)
            last_user_message = next(
                (item for item in reversed(session["messages"]) if item["role"] == "user"),
                None,
            )
            if last_user_message is None:
                raise RuntimeError("找不到当前问题，无法发送给 Codex。")
            update_ai_message(session_id, message_id, status="running", content="回答中")
            with app.test_request_context("/"):
                bundle_path = build_ai_scoped_knowledge_bundle(session)
            prompt_text = build_ai_codex_prompt(
                session=session,
                user_question=last_user_message["content"],
                response_style=response_style,
                bundle_path=bundle_path,
            )
        if ai_stop_requested(message_id):
            return

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            output_path.unlink()

        command = [
            str(codex_cli_path),
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "-m",
            model,
            "-c",
            f"model_reasoning_effort={reasoning_effort}",
            "-o",
            str(output_path),
            "-",
        ]

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(BASE_DIR),
        )
        register_ai_process(message_id, process)
        stdout_text, stderr_text = process.communicate(prompt_text, timeout=AI_CODEX_TIMEOUT_SECONDS)

        if ai_stop_requested(message_id):
            return

        reply_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        if process.returncode != 0 and not reply_text:
            stderr_text = (stderr_text or "").strip()
            raise RuntimeError(stderr_text or "本地 Codex 没有返回可用答复。")

        if not reply_text:
            stdout_text = (stdout_text or "").strip()
            if stdout_text:
                reply_text = stdout_text
        reply_text = reply_text.strip()
        if not reply_text:
            raise RuntimeError("本地 Codex 运行结束，但没有产出最终答复。")

        current_message = read_ai_message(session_id, message_id)
        if current_message and current_message["status"] == "cancelled":
            return
        update_ai_message(session_id, message_id, status="completed", content=reply_text)
    except subprocess.TimeoutExpired:
        if process is not None:
            process.kill()
            try:
                process.communicate(timeout=5)
            except Exception:
                pass
        if ai_stop_requested(message_id):
            return
        update_ai_message(
            session_id,
            message_id,
            status="error",
            content="这次问答等待时间过长，Codex 暂时没有在设定时间内返回结果。",
        )
    except Exception as exc:
        if ai_stop_requested(message_id):
            return
        update_ai_message(
            session_id,
            message_id,
            status="error",
            content=f"本地 Codex 调用失败：{exc}",
        )
    finally:
        release_ai_process(message_id)
        clear_ai_stop_request(message_id)


def codex_cli_available() -> bool:
    return resolve_codex_cli_path() is not None


def build_ai_page_context(
    *,
    session_id: str | None,
    reports: list[dict[str, Any]] | None = None,
    stock_store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = load_ai_chat_store()
    sessions = build_ai_session_cards(store)
    reports = reports if reports is not None else collect_reports()
    stock_store = stock_store if stock_store is not None else load_stock_store()
    stock_options = build_stock_selector_options(stock_store)
    known_symbols = {item["symbol"] for item in stock_options}
    active_session = None
    if session_id:
        active_session = get_ai_session(store, session_id)
    elif store["sessions"]:
        active_session = store["sessions"][0]

    model_catalog = load_codex_model_catalog()
    default_model = (
        model_catalog[0]
        if model_catalog
        else {
            "slug": "gpt-5.4",
            "display_name": "gpt-5.4",
            "reasoning_levels": ["medium"],
            "default_reasoning": "medium",
        }
    )
    active_model_slug = default_model["slug"]
    active_reasoning = default_model["default_reasoning"]
    active_response_style = "平衡"
    if active_session:
        assistant_messages = [item for item in active_session["messages"] if item["role"] == "assistant"]
        if assistant_messages:
            latest_assistant = assistant_messages[-1]
            active_model_slug = latest_assistant.get("model") or active_model_slug
            active_reasoning = latest_assistant.get("reasoning_effort") or active_reasoning
            active_response_style = latest_assistant.get("response_style") or active_response_style

    selected_model_meta = next(
        (item for item in model_catalog if item["slug"] == active_model_slug),
        default_model,
    )
    selected_reasoning_levels = selected_model_meta.get("reasoning_levels") or ["medium"]
    if active_reasoning not in selected_reasoning_levels:
        active_reasoning = selected_model_meta.get("default_reasoning") or selected_reasoning_levels[0]

    pending_message = None
    if active_session:
        pending_message = next(
            (item for item in reversed(active_session["messages"]) if item["status"] in {"pending", "running"}),
            None,
        )

    try:
        active_scope_settings = normalize_ai_scope_settings(
            (active_session or {}).get("scope_settings", {}),
            known_symbols=known_symbols,
        )
    except ValueError:
        active_scope_settings = normalize_ai_scope_settings({})
    preview_month = active_scope_settings.get("preview_month") or active_scope_settings.get("end_date", "")[:7]
    scope_preview = build_ai_scope_preview_context(
        stock_store,
        reports,
        active_scope_settings,
        month_param=preview_month or None,
        date_param=active_scope_settings.get("selected_date") or None,
    )
    active_scope_settings["preview_month"] = scope_preview["month_key"]
    scope_summary = scope_preview["summary"]

    return {
        "chat_sessions": sessions,
        "active_session": active_session,
        "selected_session_id": active_session["id"] if active_session else "",
        "model_catalog": model_catalog,
        "selected_model_meta": selected_model_meta,
        "selected_model_slug": active_model_slug,
        "selected_model_reasoning_levels": selected_reasoning_levels,
        "selected_reasoning_effort": active_reasoning,
        "response_style_options": ["简洁", "平衡", "详细"],
        "selected_response_style": active_response_style,
        "pending_message": pending_message,
        "poll_interval_ms": AI_POLL_INTERVAL_SECONDS * 1000,
        "codex_ready": codex_cli_available(),
        "stock_options": stock_options,
        "ai_scope_settings": active_scope_settings,
        "ai_scope_summary": scope_summary,
        "ai_scope_preview": scope_preview,
        "default_export_symbol": stock_options[0]["symbol"] if stock_options else "",
        "current_ai_url": url_for("ai_workspace", session=active_session["id"]) if active_session else url_for("ai_workspace"),
    }


def build_export_center_context() -> dict[str, Any]:
    store = load_stock_store()
    stock_options = build_stock_selector_options(store)
    today = datetime.now().date()
    return {
        "stock_options": stock_options,
        "default_export_symbol": stock_options[0]["symbol"] if stock_options else "",
        "current_export_url": url_for("export_center_page"),
        "default_export_end_date": today.isoformat(),
        "default_export_start_date": (today - timedelta(days=6)).isoformat(),
    }


def export_safe_name(value: str, fallback: str = "item", max_length: int = 80) -> str:
    cleaned = re.sub(r"[<>:\"/\\|?*\n\r\t]+", " ", str(value or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-_")
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_length]


def build_export_file_stem(timestamp_value: str | None, item_id: str, title: str) -> str:
    raw_time = str(timestamp_value or "").replace(":", "").replace("-", "").replace("T", "_").replace(" ", "_")
    raw_time = re.sub(r"[^0-9_]", "", raw_time).strip("_")
    return export_safe_name(f"{raw_time or 'item'}-{item_id}-{title}", fallback=f"{item_id}-{title}")


def collect_ai_export_package(
    store: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    package_kind: str,
    symbol: str = "",
) -> dict[str, Any]:
    now = datetime.now()
    cutoff_timestamp = (now - timedelta(days=7)).timestamp()
    normalized_symbol = normalize_stock_symbol(symbol or "") or ""

    if package_kind == "weekly":
        package_title = "本周资料包"
        export_slug = f"gpt-weekly-{now.strftime('%Y%m%d')}"
        report_items = [item for item in reports if float(item.get("sort_key") or 0) >= cutoff_timestamp]
    elif package_kind == "stock_full":
        if not normalized_symbol:
            raise RuntimeError("请选择你要导出的股票。")
        package_title = f"{normalized_symbol} 全量研究包"
        export_slug = f"gpt-{normalized_symbol.lower()}-full-{now.strftime('%Y%m%d')}"
        report_items = find_related_reports(normalized_symbol, limit=24)
    elif package_kind == "stock_transcripts_week":
        if not normalized_symbol:
            raise RuntimeError("请选择你要导出的股票。")
        package_title = f"{normalized_symbol} 近 7 天会议转录包"
        export_slug = f"gpt-{normalized_symbol.lower()}-transcripts-week-{now.strftime('%Y%m%d')}"
        report_items = [item for item in find_related_reports(normalized_symbol, limit=12) if float(item.get("sort_key") or 0) >= cutoff_timestamp]
    else:
        raise RuntimeError("暂不支持这个导出类型。")

    notes: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []

    symbols = [normalized_symbol] if normalized_symbol else sorted(list_stock_symbols(store))
    for item_symbol in symbols:
        entry = ensure_stock_entry(store, item_symbol)

        for note in entry["notes"]:
            sort_value = coerce_sort_timestamp(note.get("created_at"))
            if package_kind == "weekly" and sort_value < cutoff_timestamp:
                continue
            notes.append(
                {
                    "symbol": item_symbol,
                    "id": note["id"],
                    "title": note.get("title") or "未命名笔记",
                    "content_text": note.get("content_text") or "",
                    "created_at": str(note.get("created_at") or ""),
                    "display_time": note_display_time(note),
                    "sort_value": sort_value,
                    "tags": normalize_tag_list(note.get("tags", [])),
                }
            )

        if package_kind != "stock_transcripts_week":
            for file_entry in entry["files"]:
                sort_value = coerce_sort_timestamp(file_entry.get("uploaded_at"))
                if package_kind == "weekly" and sort_value < cutoff_timestamp:
                    continue
                files.append(
                    {
                        "symbol": item_symbol,
                        "id": file_entry["id"],
                        "title": file_entry.get("original_name") or "未命名文件",
                        "description": file_entry.get("description") or "",
                        "uploaded_at": str(file_entry.get("uploaded_at") or ""),
                        "display_time": file_display_time(file_entry),
                        "sort_value": sort_value,
                        "tags": normalize_tag_list(file_entry.get("tags", [])),
                        "path": stock_upload_dir(item_symbol) / str(file_entry.get("stored_name") or ""),
                        "stored_name": str(file_entry.get("stored_name") or ""),
                    }
                )

    for transcript in store.get("transcripts", []):
        transcript_symbols = transcript_linked_symbols(transcript)
        if normalized_symbol and normalized_symbol not in transcript_symbols:
            continue
        sort_source = transcript.get("meeting_date") or transcript.get("created_at")
        sort_value = coerce_sort_timestamp(sort_source)
        if package_kind in {"weekly", "stock_transcripts_week"} and sort_value < cutoff_timestamp:
            continue
        storage_symbol = normalized_symbol or (transcript_symbols[0] if transcript_symbols else "")
        transcripts.append(
            {
                "symbol": storage_symbol,
                "symbols": transcript_symbols,
                "symbol_label": "；".join(transcript_symbols),
                "id": transcript["id"],
                "title": transcript.get("title") or transcript.get("original_name") or "会议转录",
                "meeting_date": str(transcript.get("meeting_date") or ""),
                "display_time": str(transcript.get("meeting_date") or "") or format_iso_timestamp(transcript.get("created_at")),
                "created_at": str(transcript.get("created_at") or ""),
                "sort_value": sort_value,
                "tags": normalize_tag_list(transcript.get("tags", [])),
                "status": str(transcript.get("status") or ""),
                "status_label": TRANSCRIPT_STATUS_META.get(str(transcript.get("status") or ""), TRANSCRIPT_STATUS_META["pending_api"])["label"],
                "transcript_text": transcript.get("transcript_text") or "",
                "summary": summarize_text_block(transcript.get("transcript_text") or TRANSCRIPT_PLACEHOLDER_COPY),
                "path": transcript_local_path(transcript),
                "original_name": str(transcript.get("original_name") or ""),
            }
        )

    if package_kind == "stock_transcripts_week":
        notes = []
        files = []

    notes.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    files.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    transcripts.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    report_items.sort(key=lambda item: (float(item.get("sort_key") or 0), item["title"]), reverse=True)

    included_symbols = ordered_unique(
        [item["symbol"] for item in notes if item["symbol"]]
        + [item["symbol"] for item in files if item["symbol"]]
        + [linked_symbol for item in transcripts for linked_symbol in item.get("symbols", [])]
    )
    tag_summary = collect_tag_counts(notes + files + transcripts)[:16]

    timeline: list[dict[str, Any]] = []
    for report in report_items:
        timeline.append(
            {
                "kind": "日报",
                "symbol": "",
                "title": report["title"],
                "summary": report["summary"],
                "display_time": report["report_date"],
                "sort_value": float(report["sort_key"]),
            }
        )
    for note in notes:
        timeline.append(
            {
                "kind": "笔记",
                "symbol": note["symbol"],
                "title": note["title"],
                "summary": summarize_text_block(note["content_text"]),
                "display_time": note["display_time"],
                "sort_value": note["sort_value"],
            }
        )
    for file_entry in files:
        timeline.append(
            {
                "kind": "文件",
                "symbol": file_entry["symbol"],
                "title": file_entry["title"],
                "summary": summarize_text_block(file_entry["description"] or detect_file_type_label(file_entry["title"])),
                "display_time": file_entry["display_time"],
                "sort_value": file_entry["sort_value"],
            }
        )
    for transcript in transcripts:
        timeline.append(
            {
                "kind": "转录",
                "symbol": transcript.get("symbol_label") or transcript["symbol"],
                "title": transcript["title"],
                "summary": transcript["summary"],
                "display_time": transcript["display_time"],
                "sort_value": transcript["sort_value"],
            }
        )
    timeline.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)

    return {
        "kind": package_kind,
        "title": package_title,
        "slug": export_slug,
        "generated_at": now_iso(),
        "symbol": normalized_symbol,
        "reports": report_items,
        "notes": notes,
        "files": files,
        "transcripts": transcripts,
        "included_symbols": included_symbols,
        "tag_summary": tag_summary,
        "timeline": timeline[:80],
        "counts": {
            "reports": len(report_items),
            "notes": len(notes),
            "files": len(files),
            "transcripts": len(transcripts),
            "symbols": len(included_symbols),
        },
    }


def build_ai_export_upload_guide(context: dict[str, Any]) -> str:
    lines = [
        f"# {context['title']} · 上传建议",
        "",
        f"- 生成时间: {context['generated_at']}",
        f"- 包含日报: {context['counts']['reports']} 篇",
        f"- 包含笔记: {context['counts']['notes']} 条",
        f"- 包含研究资料: {context['counts']['files']} 个",
        f"- 包含会议转录: {context['counts']['transcripts']} 条",
        "",
        "## 建议上传顺序",
        "1. 先上传 `01_PACKAGE_SUMMARY.md`，让外部 GPT 快速建立全局上下文。",
        "2. 如果需要原文对照，再追加 `reports/`、`notes/`、`transcripts/` 里的 markdown。",
        "3. 如果还要核对原始文档，再上传 `files/` 下的原文件；语音相关问题可再补 `media/`。",
        "",
        "## 推荐提问方式",
        "- 先让它基于 `01_PACKAGE_SUMMARY.md` 做总览判断。",
        "- 再追加一两份关键原文，让它做对比、找矛盾、找遗漏证据。",
        "- 如果是会议场景，优先上传 `transcripts/` 的整理稿，再按需补音频源文件。",
    ]
    return "\n".join(lines).strip()


def build_ai_export_summary(context: dict[str, Any]) -> str:
    lines = [
        f"# {context['title']}",
        "",
        f"- 生成时间: {context['generated_at']}",
        f"- 涵盖股票: {', '.join(context['included_symbols']) or '无'}",
        f"- 日报: {context['counts']['reports']} 篇",
        f"- 笔记: {context['counts']['notes']} 条",
        f"- 研究资料: {context['counts']['files']} 个",
        f"- 会议转录: {context['counts']['transcripts']} 条",
        "",
        "## 标签概览",
    ]
    if context["tag_summary"]:
        for item in context["tag_summary"]:
            lines.append(f"- {item['value']}: {item['count']}")
    else:
        lines.append("- 当前导出范围内没有标签。")

    lines.extend(["", "## 时间线总览"])
    if context["timeline"]:
        for item in context["timeline"]:
            symbol_prefix = f"[{item['symbol']}] " if item["symbol"] else ""
            lines.append(f"- {item['display_time']} | {item['kind']} | {symbol_prefix}{item['title']} | {item['summary']}")
    else:
        lines.append("- 当前导出范围内没有可汇总内容。")

    if context["reports"]:
        lines.extend(["", "## 关联日报"])
        for report in context["reports"]:
            lines.extend(
                [
                    f"### {report['title']}",
                    f"- 日期: {report['report_date']}",
                    f"- 摘要: {report['summary']}",
                    "",
                ]
            )

    if context["notes"]:
        lines.extend(["## 研究笔记摘要"])
        for note in context["notes"][:20]:
            lines.append(f"- [{note['symbol']}] {note['display_time']} | {note['title']} | {summarize_text_block(note['content_text'])}")

    if context["transcripts"]:
        lines.extend(["", "## 会议转录摘要"])
        for transcript in context["transcripts"][:20]:
            symbol_prefix = (
                f"[{transcript.get('symbol_label') or transcript['symbol']}] "
                if (transcript.get("symbol_label") or transcript["symbol"])
                else ""
            )
            lines.append(f"- {symbol_prefix}{transcript['display_time']} | {transcript['title']} | {transcript['summary']}")

    return "\n".join(lines).strip()


def build_ai_export_manifest(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": context["title"],
        "kind": context["kind"],
        "generated_at": context["generated_at"],
        "symbol": context["symbol"],
        "included_symbols": context["included_symbols"],
        "counts": context["counts"],
        "tags": context["tag_summary"],
    }


def build_ai_export_note_markdown(note: dict[str, Any]) -> str:
    lines = [
        f"# {note['title']}",
        "",
        f"- 股票: {note['symbol']}",
        f"- 时间: {note['display_time']}",
        f"- 标签: {', '.join(note['tags']) or '无'}",
        "",
        "## 正文",
        note["content_text"] or "当前笔记没有正文。",
    ]
    return "\n".join(lines).strip()


def build_ai_export_file_markdown(file_entry: dict[str, Any], extracted_text: str | None) -> str:
    lines = [
        f"# {file_entry['title']}",
        "",
        f"- 股票: {file_entry['symbol']}",
        f"- 时间: {file_entry['display_time']}",
        f"- 标签: {', '.join(file_entry['tags']) or '无'}",
        f"- 说明: {file_entry['description'] or '无'}",
        "",
    ]
    if extracted_text:
        lines.extend(["## 抽取文字", extracted_text.strip()])
    else:
        lines.extend(["## 抽取文字", "该文件未抽取到可直接对比的文字内容。"])
    return "\n".join(lines).strip()


def build_ai_export_transcript_markdown(transcript: dict[str, Any]) -> str:
    lines = [
        f"# {transcript['title']}",
        "",
        f"- 股票: {transcript.get('symbol_label') or transcript['symbol'] or '未关联'}",
        f"- 日期: {transcript['display_time']}",
        f"- 状态: {transcript['status_label']}",
        f"- 标签: {', '.join(transcript['tags']) or '无'}",
        "",
        "## 转录正文",
        transcript["transcript_text"] or "当前任务还没有可导出的转录正文。",
    ]
    return "\n".join(lines).strip()


def parse_ai_export_days(raw_value: Any, default: int = 7) -> int:
    try:
        value = int(str(raw_value or default).strip())
    except (TypeError, ValueError):
        value = default
    return min(max(value, 1), 90)


def coerce_export_range_dates(start_date: str, end_date: str) -> tuple[str, str]:
    normalized_start = normalize_date_field(start_date)
    normalized_end = normalize_date_field(end_date)
    if not normalized_start or not normalized_end:
        raise RuntimeError("请选择完整的起始日期和终止日期。")
    if normalized_start > normalized_end:
        raise RuntimeError("起始日期不能晚于终止日期。")
    return normalized_start, normalized_end


def collect_ai_export_package_custom(
    store: dict[str, Any],
    reports: list[dict[str, Any]],
    *,
    package_kind: str,
    symbol: str = "",
    days: int = 7,
    include_reports: bool | None = None,
    include_notes: bool | None = None,
    include_files: bool | None = None,
    include_transcripts: bool | None = None,
    start_date: str = "",
    end_date: str = "",
) -> dict[str, Any]:
    if package_kind != "custom":
        return collect_ai_export_package(store, reports, package_kind=package_kind, symbol=symbol)

    normalized_symbol = normalize_stock_symbol(symbol or "") or ""
    days = 0 if int(days or 0) <= 0 else min(max(int(days), 1), 90)
    cutoff_timestamp = None if days == 0 else (datetime.now() - timedelta(days=days)).timestamp()
    range_start = normalize_date_field(start_date)
    range_end = normalize_date_field(end_date)
    range_start_dt = parse_iso_date_value(range_start)
    range_end_dt = parse_iso_date_value(range_end)
    range_start_timestamp = range_start_dt.timestamp() if range_start_dt else None
    range_end_timestamp = (
        (range_end_dt + timedelta(days=1)).timestamp() - 1 if range_end_dt else None
    )

    include_reports = bool(include_reports)
    include_notes = bool(include_notes)
    include_files = bool(include_files)
    include_transcripts = bool(include_transcripts)
    if not any([include_reports, include_notes, include_files, include_transcripts]):
        raise RuntimeError("请至少勾选一种要导出的内容。")

    def in_selected_range(sort_value: float) -> bool:
        if cutoff_timestamp is not None and sort_value < cutoff_timestamp:
            return False
        if range_start_timestamp is not None and sort_value < range_start_timestamp:
            return False
        if range_end_timestamp is not None and sort_value > range_end_timestamp:
            return False
        return True

    report_items: list[dict[str, Any]] = []
    if include_reports:
        if normalized_symbol:
            report_limit = 240 if days == 0 else max(days * 8, 24)
            report_items = find_related_reports(normalized_symbol, limit=report_limit)
        else:
            report_items = list(reports)
        report_items = [item for item in report_items if in_selected_range(float(item.get("sort_key") or 0))]

    notes: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []
    symbols = [normalized_symbol] if normalized_symbol else sorted(list_stock_symbols(store))

    for item_symbol in symbols:
        entry = ensure_stock_entry(store, item_symbol)

        if include_notes:
            for note in entry["notes"]:
                sort_value = coerce_sort_timestamp(note.get("created_at"))
                if not in_selected_range(sort_value):
                    continue
                notes.append(
                    {
                        "symbol": item_symbol,
                        "id": note["id"],
                        "title": note.get("title") or "未命名笔记",
                        "content_text": note.get("content_text") or "",
                        "created_at": str(note.get("created_at") or ""),
                        "display_time": note_display_time(note),
                        "sort_value": sort_value,
                        "tags": normalize_tag_list(note.get("tags", [])),
                    }
                )

        if include_files:
            for file_entry in entry["files"]:
                sort_value = coerce_sort_timestamp(file_entry.get("uploaded_at"))
                if not in_selected_range(sort_value):
                    continue
                files.append(
                    {
                        "symbol": item_symbol,
                        "id": file_entry["id"],
                        "title": file_entry.get("original_name") or "未命名文件",
                        "description": file_entry.get("description") or "",
                        "uploaded_at": str(file_entry.get("uploaded_at") or ""),
                        "display_time": file_display_time(file_entry),
                        "sort_value": sort_value,
                        "tags": normalize_tag_list(file_entry.get("tags", [])),
                        "path": stock_upload_dir(item_symbol) / str(file_entry.get("stored_name") or ""),
                        "stored_name": str(file_entry.get("stored_name") or ""),
                    }
                )

    if include_transcripts:
        for transcript in store.get("transcripts", []):
            transcript_symbols = transcript_linked_symbols(transcript)
            if normalized_symbol and normalized_symbol not in transcript_symbols:
                continue
            sort_source = transcript.get("meeting_date") or transcript.get("created_at")
            sort_value = coerce_sort_timestamp(sort_source)
            if not in_selected_range(sort_value):
                continue
            storage_symbol = normalized_symbol or (transcript_symbols[0] if transcript_symbols else "")
            transcripts.append(
                {
                    "symbol": storage_symbol,
                    "symbols": transcript_symbols,
                    "symbol_label": "；".join(transcript_symbols),
                    "id": transcript["id"],
                    "title": transcript.get("title") or transcript.get("original_name") or "会议转录",
                    "meeting_date": str(transcript.get("meeting_date") or ""),
                    "display_time": str(transcript.get("meeting_date") or "") or format_iso_timestamp(transcript.get("created_at")),
                    "created_at": str(transcript.get("created_at") or ""),
                    "sort_value": sort_value,
                    "tags": normalize_tag_list(transcript.get("tags", [])),
                    "status": str(transcript.get("status") or ""),
                    "status_label": TRANSCRIPT_STATUS_META.get(str(transcript.get("status") or ""), TRANSCRIPT_STATUS_META["pending_api"])["label"],
                    "transcript_text": transcript.get("transcript_text") or "",
                    "summary": summarize_text_block(transcript.get("transcript_text") or TRANSCRIPT_PLACEHOLDER_COPY),
                    "path": transcript_local_path(transcript),
                    "original_name": str(transcript.get("original_name") or ""),
                }
            )

    report_items.sort(key=lambda item: (float(item.get("sort_key") or 0), item["title"]), reverse=True)
    notes.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    files.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    transcripts.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)

    included_symbols = ordered_unique(
        [item["symbol"] for item in notes if item["symbol"]]
        + [item["symbol"] for item in files if item["symbol"]]
        + [linked_symbol for item in transcripts for linked_symbol in item.get("symbols", [])]
    )
    tag_summary = collect_tag_counts(notes + files + transcripts)[:16]

    timeline: list[dict[str, Any]] = []
    for report in report_items:
        timeline.append(
            {
                "kind": "日报",
                "symbol": "",
                "title": report["title"],
                "summary": report["summary"],
                "display_time": report["report_date"],
                "sort_value": float(report["sort_key"]),
            }
        )
    for note in notes:
        timeline.append(
            {
                "kind": "笔记",
                "symbol": note["symbol"],
                "title": note["title"],
                "summary": summarize_text_block(note["content_text"]),
                "display_time": note["display_time"],
                "sort_value": note["sort_value"],
            }
        )
    for file_entry in files:
        timeline.append(
            {
                "kind": "文件",
                "symbol": file_entry["symbol"],
                "title": file_entry["title"],
                "summary": summarize_text_block(file_entry["description"] or detect_file_type_label(file_entry["title"])),
                "display_time": file_entry["display_time"],
                "sort_value": file_entry["sort_value"],
            }
        )
    for transcript in transcripts:
        timeline.append(
            {
                "kind": "转录",
                "symbol": transcript.get("symbol_label") or transcript["symbol"],
                "title": transcript["title"],
                "summary": transcript["summary"],
                "display_time": transcript["display_time"],
                "sort_value": transcript["sort_value"],
            }
        )
    timeline.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)

    content_labels = [
        label
        for label, enabled in (
            ("日报", include_reports),
            ("笔记", include_notes),
            ("资料", include_files),
            ("转录", include_transcripts),
        )
        if enabled
    ]
    scope_label = normalized_symbol or "全站"
    if range_start and range_end:
        range_label = f"{range_start} 至 {range_end}"
    else:
        range_label = "全部时间" if days == 0 else f"最近 {days} 天"
    type_slug = "-".join(
        slug
        for slug, enabled in (
            ("reports", include_reports),
            ("notes", include_notes),
            ("files", include_files),
            ("transcripts", include_transcripts),
        )
        if enabled
    )
    slug_scope = normalized_symbol.lower() if normalized_symbol else "all"
    range_slug = (
        f"{range_start.replace('-', '')}-{range_end.replace('-', '')}"
        if range_start and range_end
        else ("all" if days == 0 else f"{days}d")
    )

    return {
        "kind": "custom",
        "title": f"{scope_label} · {range_label} · {'/'.join(content_labels)}",
        "slug": f"gpt-custom-{slug_scope}-{range_slug}-{type_slug}-{datetime.now().strftime('%Y%m%d')}",
        "generated_at": now_iso(),
        "symbol": normalized_symbol,
        "reports": report_items,
        "notes": notes,
        "files": files,
        "transcripts": transcripts,
        "included_symbols": included_symbols,
        "tag_summary": tag_summary,
        "timeline": timeline[:80],
        "counts": {
            "reports": len(report_items),
            "notes": len(notes),
            "files": len(files),
            "transcripts": len(transcripts),
            "symbols": len(included_symbols),
        },
        "filters": {
            "scope_label": scope_label,
            "range_label": range_label,
            "days": days,
            "start_date": range_start,
            "end_date": range_end,
            "include_reports": include_reports,
            "include_notes": include_notes,
            "include_files": include_files,
            "include_transcripts": include_transcripts,
            "content_labels": content_labels,
        },
    }


def build_ai_export_upload_guide_custom(context: dict[str, Any]) -> str:
    if context.get("kind") != "custom":
        return build_ai_export_upload_guide(context)

    filters = context.get("filters") or {}
    lines = [
        f"# {context['title']} · 上传建议",
        "",
        f"- 生成时间: {context['generated_at']}",
        f"- 导出范围: {filters.get('scope_label', context.get('symbol') or '全站')}",
        f"- 时间范围: {filters.get('range_label', '最近 7 天')}",
        f"- 内容类型: {'、'.join(filters.get('content_labels') or ['日报', '笔记', '资料', '转录'])}",
        f"- 包含日报: {context['counts']['reports']} 篇",
        f"- 包含笔记: {context['counts']['notes']} 条",
        f"- 包含研究资料: {context['counts']['files']} 份",
        f"- 包含会议转录: {context['counts']['transcripts']} 条",
        "",
        "## 建议上传顺序",
        "1. 先上传 `01_PACKAGE_SUMMARY.md`，让外部 GPT 先建立整体上下文。",
        "2. 如果需要原文对照，再补 `reports/`、`notes/`、`transcripts/` 目录下的 markdown。",
        "3. 如果需要核对原始文档或音频，再补 `files/` 与 `media/` 目录。",
    ]
    return "\n".join(lines).strip()


def build_ai_export_summary_custom(context: dict[str, Any]) -> str:
    if context.get("kind") != "custom":
        return build_ai_export_summary(context)

    filters = context.get("filters") or {}
    lines = [
        f"# {context['title']}",
        "",
        f"- 生成时间: {context['generated_at']}",
        f"- 导出范围: {filters.get('scope_label', context.get('symbol') or '全站')}",
        f"- 时间范围: {filters.get('range_label', '最近 7 天')}",
        f"- 内容类型: {'、'.join(filters.get('content_labels') or ['日报', '笔记', '资料', '转录'])}",
        f"- 涵盖股票: {', '.join(context['included_symbols']) or '无'}",
        f"- 日报: {context['counts']['reports']} 篇",
        f"- 笔记: {context['counts']['notes']} 条",
        f"- 研究资料: {context['counts']['files']} 份",
        f"- 会议转录: {context['counts']['transcripts']} 条",
        "",
        "## 标签概览",
    ]
    if context["tag_summary"]:
        for item in context["tag_summary"]:
            lines.append(f"- {item['value']}: {item['count']}")
    else:
        lines.append("- 当前导出范围内没有标签。")

    lines.extend(["", "## 时间线总览"])
    if context["timeline"]:
        for item in context["timeline"]:
            symbol_prefix = f"[{item['symbol']}] " if item["symbol"] else ""
            lines.append(f"- {item['display_time']} | {item['kind']} | {symbol_prefix}{item['title']} | {item['summary']}")
    else:
        lines.append("- 当前导出范围内没有可汇总内容。")

    return "\n".join(lines).strip()


def build_ai_export_manifest_custom(context: dict[str, Any], *, summary_only: bool) -> dict[str, Any]:
    if context.get("kind") != "custom":
        manifest = build_ai_export_manifest(context)
    else:
        manifest = {
            "title": context["title"],
            "kind": context["kind"],
            "generated_at": context["generated_at"],
            "symbol": context["symbol"],
            "included_symbols": context["included_symbols"],
            "counts": context["counts"],
            "tags": context["tag_summary"],
            "filters": context.get("filters", {}),
        }
    manifest["summary_only"] = summary_only
    return manifest


def build_ai_export_archive(
    *,
    package_kind: str,
    symbol: str,
    days: int = 7,
    include_reports: bool | None = None,
    include_notes: bool | None = None,
    include_files: bool | None = None,
    include_transcripts: bool | None = None,
    include_original_files: bool,
    include_source_media: bool,
    summary_only: bool = False,
    start_date: str = "",
    end_date: str = "",
) -> tuple[io.BytesIO, str]:
    store = load_stock_store()
    reports = collect_reports()
    context = collect_ai_export_package_custom(
        store,
        reports,
        package_kind=package_kind,
        symbol=symbol,
        days=days,
        include_reports=include_reports,
        include_notes=include_notes,
        include_files=include_files,
        include_transcripts=include_transcripts,
        start_date=start_date,
        end_date=end_date,
    )

    if not any(context["counts"].values()):
        raise RuntimeError("当前范围内还没有可导出的资料。")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("00_UPLOAD_GUIDE.md", build_ai_export_upload_guide_custom(context))
        archive.writestr("01_PACKAGE_SUMMARY.md", build_ai_export_summary_custom(context))
        archive.writestr(
            "02_MANIFEST.json",
            json.dumps(build_ai_export_manifest_custom(context, summary_only=summary_only), ensure_ascii=False, indent=2),
        )

        if not summary_only:
            for report in context["reports"]:
                report_path = REPORTS_DIR / report["filename"]
                if report_path.exists():
                    archive.write(report_path, arcname=f"reports/{report['filename']}")

            for note in context["notes"]:
                stem = build_export_file_stem(note["created_at"], note["id"], note["title"])
                archive.writestr(f"notes/{note['symbol']}/{stem}.md", build_ai_export_note_markdown(note))

            for file_entry in context["files"]:
                stem = build_export_file_stem(file_entry["uploaded_at"], file_entry["id"], file_entry["title"])
                extracted_text, _ = try_extract_file_text(file_entry["path"], file_entry["title"]) if file_entry["path"].exists() else (None, False)
                archive.writestr(
                    f"files_text/{file_entry['symbol']}/{stem}.md",
                    build_ai_export_file_markdown(file_entry, extracted_text),
                )
                if include_original_files and file_entry["path"].exists():
                    archive.write(
                        file_entry["path"],
                        arcname=f"files/{file_entry['symbol']}/{stem}-{export_safe_name(file_entry['title'])}",
                    )

            for transcript in context["transcripts"]:
                stem = build_export_file_stem(transcript["meeting_date"] or transcript["created_at"], transcript["id"], transcript["title"])
                archive.writestr(
                    f"transcripts/{transcript['symbol'] or 'unlinked'}/{stem}.md",
                    build_ai_export_transcript_markdown(transcript),
                )
                if include_source_media and transcript["path"].exists():
                    archive.write(
                        transcript["path"],
                        arcname=f"media/{transcript['symbol'] or 'unlinked'}/{stem}-{export_safe_name(transcript['original_name'] or 'source')}",
                    )

    buffer.seek(0)
    return buffer, f"{context['slug']}.zip"


@app.get("/ai")
def ai_workspace() -> str:
    reports = collect_reports()
    stock_store = load_stock_store()
    session_id = request.args.get("session", "").strip() or None
    return render_template(
        "ai.html",
        **build_ai_page_context(session_id=session_id, reports=reports, stock_store=stock_store),
        **build_navigation_context(active_page="ai", reports=reports, stock_store=stock_store),
    )


@app.get("/ai/scope/preview")
def ai_scope_preview() -> str:
    stock_store = load_stock_store()
    reports = collect_reports()
    known_symbols = {item["symbol"] for item in build_stock_selector_options(stock_store)}
    scope_settings = normalize_ai_scope_settings(
        {
            "use_stock_scope": request.args.get("use_stock_scope"),
            "symbols": request.args.get("symbols", ""),
            "content_kinds": request.args.get("content_kinds", ""),
            "use_date_scope": request.args.get("use_date_scope"),
            "start_date": request.args.get("start_date"),
            "end_date": request.args.get("end_date"),
            "preview_month": request.args.get("month"),
            "selected_date": request.args.get("date"),
        },
        known_symbols=known_symbols,
    )
    preview_context = build_ai_scope_preview_context(
        stock_store,
        reports,
        scope_settings,
        month_param=request.args.get("month"),
        year_param=request.args.get("year"),
        month_number_param=request.args.get("month_number"),
        date_param=request.args.get("date"),
    )
    return render_template("_ai_scope_preview.html", scope_preview=preview_context)


@app.post("/ai/scope")
def save_ai_scope():
    stock_store = load_stock_store()
    reports = collect_reports()
    known_symbols = {item["symbol"] for item in build_stock_selector_options(stock_store)}

    try:
        scope_settings = normalize_ai_scope_settings(
            {
                "use_stock_scope": request.form.get("use_stock_scope"),
                "symbols": request.form.get("symbols", ""),
                "content_kinds": request.form.get("content_kinds", ""),
                "use_date_scope": request.form.get("use_date_scope"),
                "start_date": request.form.get("start_date"),
                "end_date": request.form.get("end_date"),
                "preview_month": request.form.get("preview_month"),
                "selected_date": request.form.get("selected_date"),
            },
            known_symbols=known_symbols,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400

    session_id = request.form.get("session_id", "").strip()
    if session_id:
        with AI_SESSION_LOCK:
            store = load_ai_chat_store()
            session = get_ai_session(store, session_id)
            session["scope_settings"] = scope_settings
            touch_ai_session(session)
            save_ai_chat_store(store)

    preview_context = build_ai_scope_preview_context(
        stock_store,
        reports,
        scope_settings,
        month_param=scope_settings.get("preview_month") or None,
        date_param=scope_settings.get("selected_date") or None,
    )

    return jsonify(
        {
            "ok": True,
            "scope": preview_context["scope_settings"],
            "summary": preview_context["summary"],
            "preview_month": preview_context["month_key"],
            "selected_date": preview_context["selected_date"] or "",
        }
    )


@app.get("/exports")
def export_center_page() -> str:
    reports = collect_reports()
    stock_store = load_stock_store()
    return render_template(
        "exports.html",
        **build_export_center_context(),
        **build_navigation_context(active_page="exports", reports=reports, stock_store=stock_store),
    )


@app.post("/ai/sessions/new")
def create_ai_session():
    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = normalize_ai_session(
            {
                "id": uuid.uuid4().hex[:12],
                "title": "新对话",
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "messages": [],
            }
        )
        if session is None:
            abort(500)
        store.setdefault("sessions", []).insert(0, session)
        save_ai_chat_store(store)
    return redirect(url_for("ai_workspace", session=session["id"]))


@app.post("/ai/sessions/<session_id>/rename")
def rename_ai_session(session_id: str):
    next_session_id = request.form.get("next_session_id", "").strip() or session_id
    title = re.sub(r"\s+", " ", request.form.get("title", "").strip())[:120]
    if not title:
        flash("请先输入新的对话名称。", "error")
        return redirect(url_for("ai_workspace", session=next_session_id))

    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = get_ai_session(store, session_id)
        session["title"] = title
        touch_ai_session(session)
        save_ai_chat_store(store)

    flash("对话名称已更新。", "success")
    return redirect(url_for("ai_workspace", session=next_session_id))


@app.post("/ai/sessions/<session_id>/delete")
def delete_ai_session(session_id: str):
    preferred_session_id = request.form.get("next_session_id", "").strip()
    redirect_session_id = ""
    running_message_ids: list[str] = []

    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = get_ai_session(store, session_id)
        running_message_ids = [
            str(item["id"])
            for item in session.get("messages", [])
            if item["role"] == "assistant" and item["status"] in {"pending", "running"}
        ]
        store["sessions"] = [item for item in store.get("sessions", []) if item["id"] != session_id]
        if preferred_session_id and any(item["id"] == preferred_session_id for item in store["sessions"]):
            redirect_session_id = preferred_session_id
        elif store["sessions"]:
            redirect_session_id = store["sessions"][0]["id"]
        save_ai_chat_store(store)

    for message_id in running_message_ids:
        process = request_ai_stop(message_id)
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    flash(f"对话“{session['title']}”已删除。", "success")
    if redirect_session_id:
        return redirect(url_for("ai_workspace", session=redirect_session_id))
    return redirect(url_for("ai_workspace"))


@app.post("/ai/export-package")
def export_ai_package():
    next_url = safe_next_url(request.form.get("next_url"), url_for("ai_workspace"))
    package_kind = str(request.form.get("package_kind") or "").strip()
    symbol = str(request.form.get("symbol") or "").strip()
    days = parse_ai_export_days(request.form.get("days"), default=7)
    start_date = str(request.form.get("start_date") or "").strip()
    end_date = str(request.form.get("end_date") or "").strip()
    export_scope = str(request.form.get("export_scope") or "single_stock").strip()
    date_scope = str(request.form.get("date_scope") or "recent").strip()
    content_mode = str(request.form.get("content_mode") or "summary_plus_raw").strip()
    include_original_files = request.form.get("include_original_files") == "1"
    include_source_media = request.form.get("include_source_media") == "1"
    include_reports_raw = request.form.get("include_reports")
    include_notes_raw = request.form.get("include_notes")
    include_files_raw = request.form.get("include_files")
    include_transcripts_raw = request.form.get("include_transcripts")

    include_reports = None if include_reports_raw is None else include_reports_raw == "1"
    include_notes = None if include_notes_raw is None else include_notes_raw == "1"
    include_files = None if include_files_raw is None else include_files_raw == "1"
    include_transcripts = None if include_transcripts_raw is None else include_transcripts_raw == "1"
    summary_only = content_mode == "summary_only"

    if package_kind == "custom":
        if export_scope != "single_stock":
            symbol = ""
        if date_scope == "all":
            days = 0
            start_date = ""
            end_date = ""
        elif date_scope == "range":
            start_date, end_date = coerce_export_range_dates(start_date, end_date)
            days = 0
        else:
            start_date = ""
            end_date = ""
        if include_files is False:
            include_original_files = False
        if include_transcripts is False:
            include_source_media = False

    if summary_only:
        include_original_files = False
        include_source_media = False

    try:
        archive_buffer, download_name = build_ai_export_archive(
            package_kind=package_kind,
            symbol=symbol,
            days=days,
            include_reports=include_reports,
            include_notes=include_notes,
            include_files=include_files,
            include_transcripts=include_transcripts,
            include_original_files=include_original_files,
            include_source_media=include_source_media,
            summary_only=summary_only,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception as exc:
        flash(str(exc), "error")
        return redirect(next_url)

    return send_file(
        archive_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=download_name,
        max_age=0,
    )


@app.get("/backup/download")
def download_workspace_backup():
    next_url = request.args.get("next") or request.referrer or url_for("index")

    try:
        backup_path = create_workspace_backup_archive()
    except Exception as exc:
        flash(f"备份创建失败：{exc}", "error")
        return redirect(next_url)

    return send_file(
        backup_path,
        mimetype="application/zip",
        as_attachment=True,
        download_name=backup_path.name,
        max_age=0,
    )


@app.post("/ai/messages")
def send_ai_message():
    prompt = request.form.get("prompt", "").strip()
    if not prompt:
        flash("请先输入你想问 Codex 的问题。", "error")
        return redirect(url_for("ai_workspace"))

    if not codex_cli_available():
        flash("当前电脑还没有可用的本地 Codex，暂时无法发起 AI 问答。", "error")
        return redirect(url_for("ai_workspace"))

    session_id = request.form.get("session_id", "").strip()
    stock_store = load_stock_store()
    known_symbols = {item["symbol"] for item in build_stock_selector_options(stock_store)}
    try:
        scope_settings = normalize_ai_scope_settings(
            {
                "use_stock_scope": request.form.get("use_stock_scope"),
                "symbols": request.form.get("scope_symbols", ""),
                "content_kinds": request.form.get("scope_content_kinds", ""),
                "use_date_scope": request.form.get("use_date_scope"),
                "start_date": request.form.get("scope_start_date"),
                "end_date": request.form.get("scope_end_date"),
                "preview_month": request.form.get("scope_preview_month"),
                "selected_date": request.form.get("scope_selected_date"),
            },
            known_symbols=known_symbols,
        )
    except ValueError as exc:
        flash(str(exc), "error")
        if session_id:
            return redirect(url_for("ai_workspace", session=session_id))
        return redirect(url_for("ai_workspace"))

    model_catalog = load_codex_model_catalog()
    selected_model = next(
        (
            item
            for item in model_catalog
            if item["slug"] == str(request.form.get("model_slug") or "").strip()
        ),
        model_catalog[0]
        if model_catalog
        else {
            "slug": "gpt-5.4",
            "reasoning_levels": ["medium"],
            "default_reasoning": "medium",
        },
    )
    model_slug = selected_model["slug"]
    reasoning_effort = str(request.form.get("reasoning_effort") or "").strip()
    if reasoning_effort not in (selected_model.get("reasoning_levels") or []):
        reasoning_effort = selected_model.get("default_reasoning") or "medium"
    response_style = str(request.form.get("response_style") or "平衡").strip()
    if response_style not in {"简洁", "平衡", "详细"}:
        response_style = "平衡"

    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = None
        if session_id:
            session = get_ai_session(store, session_id)
            has_pending = any(item["status"] in {"pending", "running"} for item in session["messages"])
            if has_pending:
                flash("当前会话还有一条回答正在生成，请先等待完成或点击停止。", "error")
                return redirect(url_for("ai_workspace", session=session["id"]))
        else:
            session = normalize_ai_session(
                {
                    "id": uuid.uuid4().hex[:12],
                    "title": shorten_ai_session_title(prompt),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "messages": [],
                    "scope_settings": scope_settings,
                }
            )
            if session is None:
                abort(500)
            store.setdefault("sessions", []).insert(0, session)

        if not session["messages"]:
            session["title"] = shorten_ai_session_title(prompt)
        session["scope_settings"] = scope_settings

        user_message = normalize_ai_message(
            {
                "id": uuid.uuid4().hex[:12],
                "role": "user",
                "content": prompt,
                "created_at": now_iso(),
                "status": "completed",
            }
        )
        assistant_message = normalize_ai_message(
            {
                "id": uuid.uuid4().hex[:12],
                "role": "assistant",
                "content": "回答中",
                "created_at": now_iso(),
                "status": "pending",
                "model": model_slug,
                "reasoning_effort": reasoning_effort,
                "response_style": response_style,
            }
        )
        if user_message is None or assistant_message is None:
            abort(500)

        session["messages"].extend([user_message, assistant_message])
        touch_ai_session(session)
        save_ai_chat_store(store)

    worker = threading.Thread(
        target=run_ai_codex_reply,
        args=(session["id"], assistant_message["id"]),
        kwargs={
            "model": model_slug,
            "reasoning_effort": reasoning_effort,
            "response_style": response_style,
        },
        daemon=True,
    )
    worker.start()

    return redirect(url_for("ai_workspace", session=session["id"]))


@app.post("/ai/messages/<message_id>/stop")
def stop_ai_message(message_id: str):
    session_id = request.form.get("session_id", "").strip()
    if not session_id:
        return redirect(url_for("ai_workspace"))

    with AI_SESSION_LOCK:
        store = load_ai_chat_store()
        session = get_ai_session(store, session_id)
        target_message = next((item for item in session["messages"] if item["id"] == message_id), None)
        if target_message is None:
            abort(404)
        if target_message["status"] not in {"pending", "running"}:
            return redirect(url_for("ai_workspace", session=session_id))
        target_message["status"] = "cancelled"
        target_message["content"] = "已停止生成。"
        touch_ai_session(session)
        save_ai_chat_store(store)

    process = request_ai_stop(message_id)
    if process is not None:
        try:
            process.terminate()
        except OSError:
            pass

    return redirect(url_for("ai_workspace", session=session_id))


@app.get("/ai/sessions/<session_id>/status")
def ai_session_status(session_id: str):
    store = load_ai_chat_store()
    session = get_ai_session(store, session_id)
    has_pending = any(item["status"] in {"pending", "running"} for item in session["messages"])
    return jsonify(
        {
            "session_id": session["id"],
            "has_pending": has_pending,
            "updated_at": session["updated_at"],
            "messages": [
                {
                    "id": item["id"],
                    "role": item["role"],
                    "status": item["status"],
                    "content": item["content"],
                }
                for item in session["messages"]
            ],
        }
    )


@app.route("/")
def index() -> str:
    reports = collect_reports()
    selected_name = request.args.get("report")

    active_report = None
    if reports:
        default_name = selected_name or reports[0]["filename"]
        active_report = load_report(default_name)

    return render_template(
        "index.html",
        reports=reports,
        active_report=active_report,
        reports_dir=str(REPORTS_DIR),
        local_url=current_local_url(),
        lan_url=guess_lan_url(current_port()),
        **build_navigation_context(active_page="archive", reports=reports),
    )


@app.get("/monitor")
def monitor_page() -> str:
    store = load_stock_store()
    reports = collect_reports()
    return render_template(
        "monitor.html",
        reports_dir=str(REPORTS_DIR),
        **build_monitor_page_context(store),
        **build_navigation_context(active_page="monitor", reports=reports, stock_store=store),
    )


@app.post("/monitor/config")
def save_monitor_defaults():
    stock_pool = parse_monitor_stock_pool(request.form.get("stock_pool", ""))
    if not stock_pool:
        flash("请先添加至少一只股票，再保存默认股票池。", "error")
        return redirect(url_for("monitor_page"))

    config = load_monitor_config()
    config["stock_pool"] = stock_pool
    config["updated_at"] = now_iso()
    save_monitor_config(config)
    flash("默认股票池已更新，下次打开会继续沿用这组股票。", "success")
    return redirect(url_for("monitor_page"))


@app.post("/monitor/run")
def run_monitor_job():
    stock_pool = parse_monitor_stock_pool(request.form.get("stock_pool", ""))
    if not stock_pool:
        flash("请先添加至少一只股票，再运行监测。", "error")
        return redirect(url_for("monitor_page"))

    runtime = sync_monitor_runtime()
    if runtime["status"] == "running":
        flash("程序已在运行，是否终止。", "error")
        return redirect(url_for("monitor_page"))

    today_reports = collect_today_monitor_reports()
    if today_reports and request.form.get("confirm_existing_today") != "1":
        flash("当天已经存在一份监测结果，请确认后继续运行。", "error")
        return redirect(url_for("monitor_page"))

    try:
        start_monitor_process(stock_pool)
    except Exception as exc:
        flash(f"启动监测失败：{exc}", "error")
        return redirect(url_for("monitor_page"))

    flash("监测任务已经在后台启动。跑完后会自动写入当前网页使用的报告目录。", "success")
    return redirect(url_for("monitor_page"))


@app.post("/monitor/terminate")
def terminate_monitor_job():
    current = sync_monitor_runtime()
    if current["status"] != "running":
        flash("当前没有正在运行的监测任务。", "error")
        return redirect(url_for("monitor_page"))

    terminate_monitor_process(current)
    flash("后台监测任务已终止。", "success")
    return redirect(url_for("monitor_page"))


@app.get("/monitor/status")
def monitor_status():
    store = load_stock_store()
    runtime = sync_monitor_runtime()
    reports = collect_monitor_reports()
    today_reports = collect_today_monitor_reports(reports)
    latest_report = reports[0] if reports else None
    return jsonify(
        {
            "ok": True,
            "runtime": {
                **runtime,
                "status_label": monitor_runtime_status_label(runtime["status"]),
                "status_tone": monitor_runtime_status_tone(runtime["status"]),
                "is_running": runtime["status"] == "running",
                "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未运行",
                "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未完成",
            },
            "today_report_count": len(today_reports),
            "latest_report": latest_report,
            "report_count": len(reports),
            "trash_count": len(store.get("trash", [])),
            "suggestions": build_monitor_suggestions(store, load_monitor_config()),
        }
    )


@app.post("/monitor/reports/<path:filename>/delete")
def delete_monitor_report(filename: str):
    store = load_stock_store()
    trash_entry = move_monitor_report_to_trash(store, filename)
    save_stock_store(store)
    message = "Monitor 报告已移入回收站。"
    if expects_json_response():
        report_cards = collect_monitor_reports()
        return jsonify(
            {
                "ok": True,
                "message": message,
                "deleted_id": trash_entry["id"],
                "deleted_filename": filename,
                "report_count": len(report_cards),
                "today_report_count": len(collect_today_monitor_reports(report_cards)),
                "trash_count": len(store.get("trash", [])),
            }
        )
    flash(message, "success")
    return redirect(url_for("monitor_page"))


@app.get("/signals")
def signal_monitor_page() -> str:
    store = load_stock_store()
    reports = collect_reports()
    signal_reports = collect_signal_reports()
    selected_name = request.args.get("report", "").strip()
    active_report = None
    if signal_reports:
        active_name = selected_name or signal_reports[0]["filename"]
        active_report = get_signal_report(active_name)

    return render_template(
        "signal_monitor.html",
        signal_reports_dir=str(SIGNAL_MONITOR_REPORTS_DIR),
        active_signal_report=active_report,
        **build_signal_monitor_page_context(),
        **build_navigation_context(active_page="signals", reports=reports, stock_store=store),
    )


@app.post("/signals/config")
def save_signal_monitor_defaults():
    raw_sources = request.form.get("sources_json", "").strip()
    try:
        parsed_sources = json.loads(raw_sources) if raw_sources else []
    except json.JSONDecodeError:
        parsed_sources = []

    config = load_signal_monitor_config()
    seen_ids: set[str] = set()
    sources = [
        source
        for raw_item in parsed_sources
        if (source := normalize_signal_source(raw_item, existing_ids=seen_ids)) is not None
    ]
    if not sources:
        flash("请先添加至少一个要监控的大 V 或来源。", "error")
        return redirect(url_for("signal_monitor_page"))
    if not any(source.get("enabled", True) for source in sources):
        flash("请至少保留一个启用中的来源。", "error")
        return redirect(url_for("signal_monitor_page"))

    try:
        default_window_days = min(max(int(request.form.get("default_window_days") or config.get("default_window_days") or SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS), 1), 30)
    except (TypeError, ValueError):
        default_window_days = SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS

    config["sources"] = sources
    config["default_window_days"] = default_window_days
    config["updated_at"] = now_iso()
    save_signal_monitor_config(config)
    flash("信息监控默认来源已更新。", "success")
    return redirect(url_for("signal_monitor_page"))


@app.post("/signals/run")
def run_signal_monitor_job():
    raw_sources = request.form.get("sources_json", "").strip()
    try:
        parsed_sources = json.loads(raw_sources) if raw_sources else []
    except json.JSONDecodeError:
        parsed_sources = []

    seen_ids: set[str] = set()
    sources = [
        source
        for raw_item in parsed_sources
        if (source := normalize_signal_source(raw_item, existing_ids=seen_ids)) is not None
    ]
    if not sources:
        flash("请先添加至少一个要监控的大 V 或来源。", "error")
        return redirect(url_for("signal_monitor_page"))
    if not any(source.get("enabled", True) for source in sources):
        flash("请至少保留一个启用中的来源。", "error")
        return redirect(url_for("signal_monitor_page"))

    runtime = sync_signal_monitor_runtime()
    if runtime["status"] == "running":
        flash("程序已在运行，是否终止。", "error")
        return redirect(url_for("signal_monitor_page"))

    today_reports = collect_today_signal_reports()
    if today_reports and request.form.get("confirm_existing_today") != "1":
        flash("当天已经存在一份监测结果，是否继续运行。", "error")
        return redirect(url_for("signal_monitor_page"))

    enabled_sources = [source for source in sources if source.get("enabled", True)]
    cooldown_hits = get_signal_monitor_cooldown_hits(enabled_sources)
    if cooldown_hits and len(cooldown_hits) == len(enabled_sources):
        earliest_label = "；".join(
            f"{item['display_name']} 最早可在 {item['cooldown_until']} 后重跑"
            for item in cooldown_hits[:3]
        )
        flash(f"这些来源刚跑过，不建议高频扫描。{earliest_label}", "error")
        return redirect(url_for("signal_monitor_page"))

    config = load_signal_monitor_config()
    try:
        default_window_days = min(max(int(request.form.get("default_window_days") or config.get("default_window_days") or SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS), 1), 30)
    except (TypeError, ValueError):
        default_window_days = SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS
    config["sources"] = sources
    config["default_window_days"] = default_window_days
    config["updated_at"] = now_iso()
    save_signal_monitor_config(config)

    try:
        start_signal_monitor_process(sources)
    except Exception as exc:
        flash(f"启动信息监控失败：{exc}", "error")
        return redirect(url_for("signal_monitor_page"))

    flash("信息监控任务已经在后台启动。跑完后会自动写入独立归档，不会混进正式研究报告。", "success")
    return redirect(url_for("signal_monitor_page"))


@app.post("/signals/terminate")
def terminate_signal_monitor_job():
    current = sync_signal_monitor_runtime()
    if current["status"] != "running":
        flash("当前没有正在运行的信息监控任务。", "error")
        return redirect(url_for("signal_monitor_page"))

    terminate_signal_monitor_process(current)
    flash("后台信息监控任务已终止。", "success")
    return redirect(url_for("signal_monitor_page"))


@app.get("/signals/status")
def signal_monitor_status():
    store = load_stock_store()
    reports = collect_reports()
    runtime = sync_signal_monitor_runtime()
    signal_reports = collect_signal_reports()
    today_reports = collect_today_signal_reports(signal_reports)
    latest_report = signal_reports[0] if signal_reports else None
    return jsonify(
        {
            "ok": True,
            "runtime": {
                **runtime,
                "status_label": monitor_runtime_status_label(runtime["status"]),
                "status_tone": monitor_runtime_status_tone(runtime["status"]),
                "is_running": runtime["status"] == "running",
                "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未运行",
                "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未完成",
            },
            "today_report_count": len(today_reports),
            "latest_report": latest_report,
            "report_count": len(signal_reports),
            "trash_count": len(store.get("trash", [])),
            "source_count": len(load_signal_monitor_config().get("sources", [])),
            "nav_reports_count": len(reports),
        }
    )


@app.post("/signals/reports/<path:filename>/delete")
def delete_signal_report(filename: str):
    store = load_stock_store()
    trash_entry = move_signal_report_to_trash(store, filename)
    save_stock_store(store)
    message = "信息监控报告已移入回收站。"
    if expects_json_response():
        report_cards = collect_signal_reports()
        return jsonify(
            {
                "ok": True,
                "message": message,
                "deleted_id": trash_entry["id"],
                "deleted_filename": filename,
                "report_count": len(report_cards),
                "today_report_count": len(collect_today_signal_reports(report_cards)),
                "trash_count": len(store.get("trash", [])),
            }
        )
    flash(message, "success")
    return redirect(url_for("signal_monitor_page"))


@app.route("/signals/files/<path:filename>")
def raw_signal_report(filename: str):
    report_path = validate_report_name_in_directory(filename, SIGNAL_MONITOR_REPORTS_DIR)
    return send_from_directory(SIGNAL_MONITOR_REPORTS_DIR, report_path.name, as_attachment=False)


@app.route("/stocks")
def stocks_workspace() -> str:
    store = load_stock_store()
    focus_group = request.args.get("focus_group", "").strip()
    groups = build_group_cards(store, focus_group=focus_group)
    favorites = [build_stock_card(store, symbol) for symbol in store["favorites"]]
    total_symbols = len(list_stock_symbols(store))

    return render_template(
        "stocks.html",
        groups=groups,
        favorites=favorites,
        focus_group=focus_group,
        total_symbols=total_symbols,
        local_url=current_local_url(),
        lan_url=guess_lan_url(current_port()),
        reports_dir=str(REPORTS_DIR),
        **build_navigation_context(active_page="stocks", stock_store=store),
    )


@app.get("/search")
def global_search() -> str:
    store = load_stock_store()
    reports = collect_reports()
    search_context = build_global_search_context(
        store,
        reports,
        query=request.args.get("q", ""),
        kind_filter=request.args.get("kind", "").strip(),
        symbol_filter=request.args.get("symbol", "").strip(),
        tag_filter=request.args.get("tag", "").strip(),
    )

    return render_template(
        "search.html",
        **search_context,
        **build_navigation_context(active_page="search", reports=reports, stock_store=store),
    )


@app.get("/trash")
def trash_page() -> str:
    store = load_stock_store()
    query = request.args.get("q", "").strip()
    item_type = request.args.get("item_type", "").strip()
    symbol_filter = normalize_stock_symbol(request.args.get("symbol", "")) or ""
    tag_filter = normalize_tag_value(request.args.get("tag")) or ""
    terms = split_search_terms(query)

    trash_items = build_trash_cards(store)
    trash_stats = build_trash_stats(trash_items)
    filtered_items: list[dict[str, Any]] = []
    for item in trash_items:
        if item_type and item["item_type"] != item_type:
            continue
        if symbol_filter and item.get("display_symbol") != symbol_filter:
            continue
        if tag_filter and not tag_match(item.get("tags", []), tag_filter):
            continue
        haystack = " ".join(
            [
                item.get("display_title", ""),
                item.get("display_symbol", ""),
                item.get("kind_label", ""),
                " ".join(item.get("tags", [])),
            ]
        )
        if terms and not text_contains_all_terms(haystack, terms):
            continue
        filtered_items.append(item)

    tag_counts = collect_tag_counts(store.get("trash", []))

    return render_template(
        "trash.html",
        trash_items=filtered_items,
        trash_stats={**trash_stats, "filtered_count": len(filtered_items)},
        trash_filters={
            "query": query,
            "item_type": item_type,
            "symbol": symbol_filter,
            "tag": tag_filter,
        },
        trash_kind_options=[{"value": "", "label": "全部"}]
        + [
            {"value": key, "label": meta["label"]}
            for key, meta in TRASH_KIND_META.items()
        ],
        stock_options=build_stock_selector_options(store),
        popular_tags=tag_counts[:14],
        **build_navigation_context(active_page="trash", stock_store=store),
    )


@app.post("/trash/<trash_id>/restore")
def restore_trash_item(trash_id: str):
    store = load_stock_store()
    trash_entry = get_trash_entry(store, trash_id)
    payload = deepcopy(trash_entry["payload"])
    item_type = trash_entry["item_type"]
    symbol = str(trash_entry.get("symbol") or "")
    next_url = safe_next_url(request.form.get("next_url"), url_for("trash_page"))

    if item_type == "note":
        if not symbol:
            abort(400)
        entry = ensure_stock_entry(store, symbol)
        payload["id"] = ensure_unique_id(payload.get("id", ""), {item["id"] for item in entry["notes"]})
        entry["notes"].append(payload)
        touch_stock(store, symbol)
    elif item_type == "file":
        if not symbol:
            abort(400)
        entry = ensure_stock_entry(store, symbol)
        payload["id"] = ensure_unique_id(payload.get("id", ""), {item["id"] for item in entry["files"]})
        entry["files"].append(payload)
        touch_stock(store, symbol)
    elif item_type == "transcript":
        payload["id"] = ensure_unique_id(payload.get("id", ""), {item["id"] for item in store.get("transcripts", [])})
        store.setdefault("transcripts", []).append(payload)
        touch_transcript_stocks(store, payload)
    elif item_type == "group":
        payload["id"] = ensure_unique_id(payload.get("id", ""), {group["id"] for group in store["groups"]}, length=8)
        store["groups"].append(payload)
    elif item_type == "monitor_report":
        trash_path = Path(str(payload.get("trash_path") or ""))
        if not trash_path.exists():
            abort(400)
        restore_name = Path(str(payload.get("filename") or "")).name
        if not restore_name:
            abort(400)
        target_path = REPORTS_DIR / restore_name
        if target_path.exists():
            target_path = REPORTS_DIR / f"{target_path.stem}-restored-{uuid.uuid4().hex[:6]}{target_path.suffix}"
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        trash_path.replace(target_path)
    elif item_type == "signal_report":
        trash_path = Path(str(payload.get("trash_path") or ""))
        if not trash_path.exists():
            abort(400)
        restore_name = Path(str(payload.get("filename") or "")).name
        if not restore_name:
            abort(400)
        target_path = SIGNAL_MONITOR_REPORTS_DIR / restore_name
        if target_path.exists():
            target_path = SIGNAL_MONITOR_REPORTS_DIR / f"{target_path.stem}-restored-{uuid.uuid4().hex[:6]}{target_path.suffix}"
        SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        trash_path.replace(target_path)
    else:
        abort(400)

    store["trash"] = [item for item in store.get("trash", []) if item["id"] != trash_id]
    save_stock_store(store)
    message = f"{TRASH_KIND_META[item_type]['label']}已从回收站恢复。"
    if expects_json_response():
        return jsonify(
            {
                "ok": True,
                "restored_id": trash_id,
                "message": message,
                "stats": build_trash_stats(store.get("trash", [])),
            }
        )
    flash(message, "success")
    return redirect(next_url)


@app.post("/trash/<trash_id>/delete")
def permanently_delete_trash_item(trash_id: str):
    store = load_stock_store()
    trash_entry = get_trash_entry(store, trash_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("trash_page"))

    try:
        permanently_delete_trash_entry(trash_entry)
    except Exception as exc:
        flash(f"永久删除时有一部分资源清理失败：{exc}", "error")

    store["trash"] = [item for item in store.get("trash", []) if item["id"] != trash_id]
    save_stock_store(store)
    message = "该条目已从回收站永久删除。"
    if expects_json_response():
        return jsonify(
            {
                "ok": True,
                "deleted_id": trash_id,
                "message": message,
                "stats": build_trash_stats(store.get("trash", [])),
            }
        )
    flash(message, "success")
    return redirect(next_url)


@app.get("/transcripts")
def transcripts_page() -> str:
    store = load_stock_store()
    requested_symbol = normalize_stock_symbol(request.args.get("symbol", ""))
    page_context = build_transcript_page_context(store, requested_symbol=requested_symbol or "")
    tingwu_status = build_tingwu_status()
    oss_status = probe_oss_bridge()

    return render_template(
        "transcripts.html",
        tingwu_status=tingwu_status,
        oss_status=oss_status,
        today_date=today_date_iso(),
        capability_cards=TRANSCRIPT_CAPABILITY_CARDS,
        transcript_requirement_notes=TRANSCRIPT_REQUIREMENT_NOTES,
        source_language_options=TRANSCRIPT_SOURCE_LANGUAGE_OPTIONS,
        output_level_options=TRANSCRIPT_OUTPUT_LEVEL_OPTIONS,
        speaker_count_options=TRANSCRIPT_SPEAKER_COUNT_OPTIONS,
        meeting_assistance_options=TRANSCRIPT_MEETING_ASSISTANCE_OPTIONS,
        summarization_options=TRANSCRIPT_SUMMARIZATION_OPTIONS,
        supported_format_hint=(
            "音频支持 mp3 / wav / m4a / aac / amr / flac，"
            "视频支持 mp4 / mov / mkv / webm / avi 等格式。保存后会自动尝试上传到 OSS。"
        ),
        **page_context,
        **build_navigation_context(active_page="transcripts", stock_store=store),
    )


@app.post("/transcripts")
def create_transcript_job():
    store = load_stock_store()
    uploaded = request.files.get("transcript_media")
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))

    if uploaded is None or not uploaded.filename:
        flash("请先选择要上传的音频或视频文件。", "error")
        return redirect(next_url)

    if not is_transcript_source_allowed(uploaded.filename):
        flash("当前只支持常见音频/视频文件，如 mp3、wav、mp4、mov、mkv。", "error")
        return redirect(next_url)

    link_to_stock = request.form.get("link_to_stock") == "on"
    link_to_multiple_stocks = request.form.get("link_to_multiple_stocks") == "on"
    linked_symbols: list[str] = []
    known_symbols = set(list_stock_symbols(store))
    if link_to_stock:
        if link_to_multiple_stocks:
            linked_symbols = parse_symbol_list(request.form.get("linked_symbols_text", ""))
            if not linked_symbols:
                flash("如果要关联到多个股票，请先填写股票代码，支持用分号分隔。", "error")
                return redirect(next_url)
        else:
            linked_symbol = normalize_stock_symbol(request.form.get("linked_symbol", ""))
            if not linked_symbol:
                flash("如果要关联到个股页，请先选择股票。", "error")
                return redirect(next_url)
            linked_symbols = [linked_symbol]

        missing_symbols = [symbol for symbol in linked_symbols if symbol not in known_symbols]
        if missing_symbols:
            flash(f"未找到对应股票：{'；'.join(missing_symbols)}", "error")
            return redirect(next_url)

        for linked_symbol in linked_symbols:
            ensure_stock_entry(store, linked_symbol)

    source_language = str(request.form.get("source_language") or "cn").strip()
    if source_language not in TRANSCRIPT_SOURCE_LANGUAGE_LABELS:
        source_language = "cn"

    output_level = str(request.form.get("output_level") or "2").strip()
    if output_level not in TRANSCRIPT_OUTPUT_LEVEL_LABELS:
        output_level = "2"

    try:
        speaker_count = int(request.form.get("speaker_count") or 2)
    except (TypeError, ValueError):
        speaker_count = 2
    speaker_count = min(max(speaker_count, 2), 8)

    diarization_enabled = request.form.get("diarization_enabled") == "on"
    meeting_assistance_enabled = request.form.get("meeting_assistance_enabled") == "on"
    summarization_enabled = request.form.get("summarization_enabled") == "on"
    custom_prompt_enabled = request.form.get("custom_prompt_enabled") == "on"

    meeting_assistance_types = normalize_choice_list(
        request.form.getlist("meeting_assistance_types"),
        set(TRANSCRIPT_MEETING_ASSISTANCE_LABELS),
    )
    if meeting_assistance_enabled and not meeting_assistance_types:
        meeting_assistance_types = [item["value"] for item in TRANSCRIPT_MEETING_ASSISTANCE_OPTIONS]

    summarization_types = normalize_choice_list(
        request.form.getlist("summarization_types"),
        set(TRANSCRIPT_SUMMARIZATION_LABELS),
    )
    if summarization_enabled and not summarization_types:
        summarization_types = ["Paragraph"]

    safe_name = secure_filename(uploaded.filename)
    original_suffix = Path(uploaded.filename).suffix.lower()
    if not safe_name:
        safe_name = f"meeting-recording{original_suffix or '.bin'}"
    elif original_suffix and not safe_name.lower().endswith(original_suffix):
        safe_name = f"{Path(safe_name).stem}{original_suffix}"

    timestamp = now_iso()
    stored_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{safe_name}"
    TRANSCRIPT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = TRANSCRIPT_UPLOADS_DIR / stored_name
    uploaded.save(target_path)

    transcript_entry = {
        "id": uuid.uuid4().hex[:10],
        "title": request.form.get("transcript_title", "").strip()[:160],
        "meeting_date": normalize_date_field(request.form.get("meeting_date")) or iso_to_date(timestamp) or today_date_iso(),
        "created_at": timestamp,
        "updated_at": timestamp,
        "stored_name": stored_name,
        "original_name": uploaded.filename[:240],
        "media_kind": detect_transcript_media_kind(uploaded.filename),
        "provider": "tingwu",
        "status": "pending_api",
        "provider_task_id": "",
        "provider_task_status": "not_submitted",
        "provider_request_id": "",
        "submitted_at": "",
        "last_synced_at": "",
        "last_error": "",
        "provider_result_urls": {},
        "file_url_hint": request.form.get("file_url_hint", "").strip()[:2000],
        "source_bucket_name": "",
        "source_object_key": "",
        "source_endpoint": "",
        "source_region_id": "",
        "source_url_expires_at": "",
        "linked_symbol": linked_symbols[0] if linked_symbols else "",
        "linked_symbols": linked_symbols,
        "source_language": source_language,
        "output_level": output_level,
        "diarization_enabled": diarization_enabled,
        "speaker_count": speaker_count,
        "phrase_id": request.form.get("phrase_id", "").strip()[:80],
        "auto_chapters_enabled": request.form.get("auto_chapters_enabled") == "on",
        "meeting_assistance_enabled": meeting_assistance_enabled,
        "meeting_assistance_types": meeting_assistance_types,
        "summarization_enabled": summarization_enabled,
        "summarization_types": summarization_types,
        "text_polish_enabled": request.form.get("text_polish_enabled") == "on",
        "ppt_extraction_enabled": request.form.get("ppt_extraction_enabled") == "on",
        "custom_prompt_enabled": custom_prompt_enabled,
        "custom_prompt_name": request.form.get("custom_prompt_name", "").strip()[:80],
        "custom_prompt_text": request.form.get("custom_prompt_text", "").strip()[:4000],
        "transcript_html": "",
        "transcript_text": "",
        "tags": normalize_tag_list(request.form.get("transcript_tags", "")),
    }

    normalized_transcript = normalize_transcript_entry(transcript_entry)
    if normalized_transcript is None:
        flash("转录任务写入失败，请重试。", "error")
        return redirect(next_url)

    tingwu_status = build_tingwu_status()
    oss_status = build_oss_status()
    auto_submitted = False
    auto_submit_error = ""
    auto_source_ready = False
    if tingwu_status["is_ready"] and not normalized_transcript["file_url_hint"] and oss_status["is_ready"]:
        try:
            ensure_transcript_source_url(normalized_transcript)
            auto_source_ready = True
        except Exception as exc:
            normalized_transcript["last_error"] = str(exc)[:2000]
            normalized_transcript["updated_at"] = now_iso()
            auto_submit_error = str(exc)

    if tingwu_status["is_ready"] and (normalized_transcript["file_url_hint"] or normalized_transcript["source_object_key"]):
        try:
            submit_transcript_job_to_tingwu(normalized_transcript)
            auto_submitted = True
        except Exception as exc:
            normalized_transcript["last_error"] = str(exc)[:2000]
            normalized_transcript["updated_at"] = now_iso()
            auto_submit_error = str(exc)

    store.setdefault("transcripts", []).append(normalized_transcript)
    touch_transcript_stocks(store, normalized_transcript)
    save_stock_store(store)

    if auto_submitted:
        flash("会议转录任务已保存，并已提交到听悟。后续请用“刷新状态”主动轮询结果。", "success")
    elif auto_submit_error:
        flash(f"任务已保存，但提交到听悟失败：{auto_submit_error}", "error")
    elif auto_source_ready:
        flash("会议转录任务已保存，源文件也已自动上传到 OSS。你可以稍后继续提交到听悟。", "success")
    elif transcript_entry["file_url_hint"]:
        flash("会议转录任务已保存。当前可以随时手动提交到听悟。", "success")
    else:
        flash("会议转录任务已保存。系统还没拿到可用的云端地址，稍后可以直接点“提交到听悟”再试。", "success")
    return redirect(next_url)


@app.post("/transcripts/<transcript_id>/submit")
def submit_transcript_job(transcript_id: str):
    store = load_stock_store()
    transcript = get_transcript_entry(store, transcript_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))

    try:
        submit_transcript_job_to_tingwu(transcript)
        touch_transcript_stocks(store, transcript)
        save_stock_store(store)
        flash("任务已提交到听悟。当前项目按主动轮询设计，请继续点击“刷新状态”获取结果。", "success")
    except Exception as exc:
        transcript["last_error"] = str(exc)[:2000]
        transcript["updated_at"] = now_iso()
        save_stock_store(store)
        flash(f"提交到听悟失败：{exc}", "error")

    return redirect(next_url)


@app.post("/transcripts/<transcript_id>/sync")
def sync_transcript_job(transcript_id: str):
    store = load_stock_store()
    transcript = get_transcript_entry(store, transcript_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))

    try:
        task_info = sync_transcript_job_from_tingwu(transcript)
        touch_transcript_stocks(store, transcript)
        save_stock_store(store)
        if transcript["status"] == "completed":
            flash("听悟结果已同步回来，转录内容已经写入页面。", "success")
        elif transcript["status"] == "failed":
            flash(
                transcript.get("last_error") or "听悟任务返回失败状态，请检查云端任务。",
                "error",
            )
        else:
            flash(f"任务状态已刷新：{task_info.get('task_status') or '处理中'}。", "success")
    except Exception as exc:
        transcript["last_error"] = str(exc)[:2000]
        transcript["updated_at"] = now_iso()
        save_stock_store(store)
        flash(f"刷新任务状态失败：{exc}", "error")

    return redirect(next_url)


@app.post("/transcripts/sync-active")
def sync_active_transcripts():
    store = load_stock_store()
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))
    refreshed = 0
    completed = 0
    failed = 0

    for transcript in store.get("transcripts", []):
        if transcript.get("status") not in {"queued", "processing"}:
            continue
        if not transcript.get("provider_task_id"):
            continue
        try:
            sync_transcript_job_from_tingwu(transcript)
            refreshed += 1
            if transcript["status"] == "completed":
                completed += 1
            elif transcript["status"] == "failed":
                failed += 1
            touch_transcript_stocks(store, transcript)
        except Exception as exc:
            transcript["last_error"] = str(exc)[:2000]
            transcript["updated_at"] = now_iso()
            failed += 1

    save_stock_store(store)

    if refreshed:
        flash(f"已轮询 {refreshed} 个进行中任务，其中完成 {completed} 个，失败 {failed} 个。", "success")
    else:
        flash("当前没有需要轮询的进行中任务。", "success")
    return redirect(next_url)


@app.get("/transcripts/<transcript_id>/source")
def download_transcript_source(transcript_id: str):
    store = load_stock_store()
    transcript = get_transcript_entry(store, transcript_id)
    return send_from_directory(
        TRANSCRIPT_UPLOADS_DIR,
        transcript["stored_name"],
        as_attachment=True,
        download_name=transcript["original_name"],
    )


@app.post("/transcripts/<transcript_id>/delete")
def delete_transcript_job(transcript_id: str):
    store = load_stock_store()
    transcript = get_transcript_entry(store, transcript_id)
    linked_symbols = transcript_linked_symbols(transcript)
    append_to_trash(
        store,
        create_trash_entry(
            "transcript",
            transcript,
            symbol=str(linked_symbols[0] if linked_symbols else ""),
            title=transcript.get("title") or transcript.get("original_name") or "会议转录",
        ),
    )
    store["transcripts"] = [
        item for item in store.get("transcripts", []) if item["id"] != transcript_id
    ]
    touch_transcript_stocks(store, transcript)
    save_stock_store(store)
    message = "会议转录任务已移入回收站。"

    if expects_json_response():
        transcript_cards = build_transcript_cards(store)
        return jsonify(
            {
                "ok": True,
                "message": message,
                "deleted_id": transcript_id,
                "trash_count": len(store.get("trash", [])),
                "counts": build_transcript_stats_payload(transcript_cards),
            }
        )

    flash(message, "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("transcripts_page")))


@app.get("/stocks/calendar")
def stocks_calendar() -> str:
    store = load_stock_store()
    activity = build_stock_activity(store)
    calendar_context = build_activity_calendar_context(
        activity,
        month_param=request.args.get("month"),
        year_param=request.args.get("year"),
        month_number_param=request.args.get("month_number"),
        date_param=request.args.get("date"),
    )

    return render_template(
        "stocks_calendar.html",
        **calendar_context,
        **build_navigation_context(active_page="calendar", stock_store=store),
    )


@app.get("/stocks/calendar/modal")
def stocks_calendar_modal() -> str:
    store = load_stock_store()
    activity = build_stock_activity(store)
    calendar_context = build_activity_calendar_context(
        activity,
        month_param=request.args.get("month"),
        year_param=request.args.get("year"),
        month_number_param=request.args.get("month_number"),
        date_param=request.args.get("date"),
    )

    return render_template("calendar_modal.html", **calendar_context)


@app.route("/stocks/<symbol>")
def stock_detail(symbol: str) -> str:
    symbol = require_stock_symbol(symbol)
    store = load_stock_store()
    detail = build_stock_detail(store, symbol)
    stock_calendar = build_activity_calendar_context(
        build_stock_activity(store, symbol_filter=symbol),
        month_param=request.args.get("stock_month"),
        year_param=request.args.get("stock_year"),
        month_number_param=request.args.get("stock_month_number"),
        date_param=request.args.get("stock_date"),
    )
    available_groups = [
        group for group in store["groups"] if symbol not in group["stocks"]
    ]

    return render_template(
        "stock_detail.html",
        stock=detail,
        related_reports=detail["related_reports"],
        available_groups=available_groups,
        stock_calendar=stock_calendar,
        today_date=today_date_iso(),
        return_to=request.full_path if request.query_string else request.path,
        **build_navigation_context(active_page="stocks", stock_store=store),
    )


@app.post("/stocks/groups")
def create_stock_group():
    store = load_stock_store()
    name = request.form.get("group_name", "").strip()
    description = request.form.get("group_description", "").strip()

    if not name:
        flash("请先填写分组名称。", "error")
        return redirect(url_for("stocks_workspace"))

    group_id = create_group_id(name, {group["id"] for group in store["groups"]})
    store["groups"].append(
        {
            "id": group_id,
            "name": name[:80],
            "description": description[:240],
            "stocks": [],
            "created_at": now_iso(),
        }
    )
    save_stock_store(store)
    flash(f'分组“{name}”已创建。', "success")
    return redirect(url_for("stocks_workspace", focus_group=group_id))


@app.post("/stocks/groups/<group_id>/update")
def update_stock_group(group_id: str):
    store = load_stock_store()
    group = get_group(store, group_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("stocks_workspace", focus_group=group_id))
    name = request.form.get("group_name", "").strip()
    description = request.form.get("group_description", "").strip()

    if not name:
        flash("请先填写分组名称。", "error")
        return redirect(next_url)

    group["name"] = name[:80]
    group["description"] = description[:240]
    group["updated_at"] = now_iso()
    save_stock_store(store)
    flash(f'分组“{group["name"]}”已更新。', "success")
    return redirect(next_url)


@app.post("/stocks/groups/<group_id>/delete")
def delete_stock_group(group_id: str):
    store = load_stock_store()
    group = get_group(store, group_id)
    append_to_trash(
        store,
        create_trash_entry(
            "group",
            group,
            title=group["name"],
        ),
    )
    store["groups"] = [item for item in store["groups"] if item["id"] != group_id]
    save_stock_store(store)
    flash(f'分组“{group["name"]}”已移入回收站。', "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stocks_workspace")))


@app.post("/stocks/groups/<group_id>/stocks")
def add_group_stocks(group_id: str):
    store = load_stock_store()
    group = get_group(store, group_id)
    symbols = parse_symbol_list(request.form.get("symbols", ""))
    add_to_favorites = request.form.get("add_to_favorites") == "on"

    if not symbols:
        flash("请填写有效股票代码，例如 AAPL、NVDA、FTAI。", "error")
        return redirect(safe_next_url(request.form.get("next_url"), url_for("stocks_workspace", focus_group=group_id)))

    added_symbols: list[str] = []
    existing_symbols: list[str] = []
    store_changed = False

    for symbol in symbols:
        if symbol in group["stocks"]:
            existing_symbols.append(symbol)
            continue

        ensure_stock_entry(store, symbol)
        group["stocks"].append(symbol)
        added_symbols.append(symbol)
        store_changed = True

        if add_to_favorites and symbol not in store["favorites"]:
            store["favorites"].append(symbol)

        touch_stock(store, symbol)

    if store_changed:
        save_stock_store(store)

    if added_symbols:
        flash(f'已将 {", ".join(added_symbols)} 加入“{group["name"]}”。', "success")
    if existing_symbols:
        flash(f'股票已经存在: {", ".join(existing_symbols)}', "error")

    return redirect(safe_next_url(request.form.get("next_url"), url_for("stocks_workspace", focus_group=group_id)))


@app.post("/stocks/groups/<group_id>/stocks/<symbol>/remove")
def remove_group_stock(group_id: str, symbol: str):
    store = load_stock_store()
    group = get_group(store, group_id)
    symbol = require_stock_symbol(symbol)
    group["stocks"] = [item for item in group["stocks"] if item != symbol]
    save_stock_store(store)
    flash(f"{symbol} 已从“{group['name']}”移除。", "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stocks_workspace", focus_group=group_id)))


@app.post("/stocks/<symbol>/favorite")
def toggle_favorite(symbol: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    ensure_stock_entry(store, symbol)

    if symbol in store["favorites"]:
        store["favorites"] = [item for item in store["favorites"] if item != symbol]
        flash(f"{symbol} 已取消自选。", "success")
    else:
        store["favorites"].append(symbol)
        flash(f"{symbol} 已加入自选。", "success")

    touch_stock(store, symbol)
    save_stock_store(store)
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stocks_workspace")))


@app.post("/stocks/<symbol>/groups")
def add_stock_to_group(symbol: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    group_id = request.form.get("group_id", "").strip()
    next_url = safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol))

    if not group_id:
        flash("请先选择目标分组。", "error")
        return redirect(next_url)

    group = get_group(store, group_id)
    ensure_stock_entry(store, symbol)
    if symbol not in group["stocks"]:
        group["stocks"].append(symbol)
        touch_stock(store, symbol)
        save_stock_store(store)
        flash(f"{symbol} 已加入“{group['name']}”。", "success")
    else:
        flash(f"股票已经存在: {symbol}", "error")

    return redirect(next_url)


@app.post("/stocks/<symbol>/notes")
def add_stock_note(symbol: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    entry = ensure_stock_entry(store, symbol)
    title = request.form.get("note_title", "").strip()
    created_at, record_date = build_recorded_timestamp(request.form.get("note_record_date"))
    content_html, content_text = prepare_note_payload(
        request.form.get("note_content_html", ""),
        request.form.get("note_content", ""),
    )

    if not content_text:
        flash("请先输入笔记内容。", "error")
        return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))

    entry["notes"].append(
        {
            "id": uuid.uuid4().hex[:10],
            "title": title[:120],
            "content_html": content_html,
            "content_text": content_text,
            "created_at": created_at,
            "record_date": record_date,
            "source_file_id": "",
            "source_file_name": "",
            "source_mode": "manual",
            "tags": normalize_tag_list(request.form.get("note_tags", "")),
        }
    )
    touch_stock(store, symbol)
    save_stock_store(store)
    flash(f"{symbol} 的笔记已保存。", "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))


@app.post("/stocks/<symbol>/notes/<note_id>/update")
def update_stock_note(symbol: str, note_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    entry = ensure_stock_entry(store, symbol)
    note = next((item for item in entry["notes"] if item["id"] == note_id), None)
    if note is None:
        abort(404)

    content_html, content_text = prepare_note_payload(
        request.form.get("note_content_html", ""),
        request.form.get("note_content", ""),
    )
    if not content_text:
        flash("请先输入笔记内容。", "error")
        return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))

    note["title"] = request.form.get("note_title", "").strip()[:120]
    note["content_html"] = content_html
    note["content_text"] = content_text
    note["tags"] = normalize_tag_list(request.form.get("note_tags", ""))
    note["updated_at"] = now_iso()

    touch_stock(store, symbol)
    save_stock_store(store)
    flash(f"{symbol} 的笔记已更新。", "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))


@app.post("/stocks/<symbol>/notes/<note_id>/delete")
def delete_stock_note(symbol: str, note_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    entry = ensure_stock_entry(store, symbol)
    note = next((item for item in entry["notes"] if item["id"] == note_id), None)
    if note is None:
        abort(404)
    append_to_trash(
        store,
        create_trash_entry(
            "note",
            note,
            symbol=symbol,
            title=note.get("title") or "未命名笔记",
        ),
    )
    entry["notes"] = [item for item in entry["notes"] if item["id"] != note_id]
    touch_stock(store, symbol)
    save_stock_store(store)
    flash(f"{symbol} 的笔记已移入回收站。", "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))


@app.post("/stocks/<symbol>/files")
def upload_stock_file(symbol: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    entry = ensure_stock_entry(store, symbol)
    uploaded = request.files.get("research_file")
    description = request.form.get("file_description", "").strip()
    note_title = request.form.get("file_note_title", "").strip()
    note_comment_html = request.form.get("file_note_content_html", "").strip()
    note_comment_text = request.form.get("file_note_content", "").strip()
    extract_text_to_note = request.form.get("extract_text_to_note") == "on"
    next_url = safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol))

    if uploaded is None or not uploaded.filename:
        flash("请先选择要上传的文件。", "error")
        return redirect(next_url)

    timestamp = now_iso()
    uploaded_at, record_date = build_recorded_timestamp(request.form.get("file_record_date"), fallback_timestamp=timestamp)
    safe_name = secure_filename(uploaded.filename) or f"{symbol.lower()}-research-file"
    stored_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{safe_name}"
    target_dir = stock_upload_dir(symbol)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / stored_name
    uploaded.save(target_path)

    file_id = uuid.uuid4().hex[:10]
    file_entry = {
        "id": file_id,
        "stored_name": stored_name,
        "original_name": uploaded.filename,
        "description": description[:200],
        "uploaded_at": uploaded_at,
        "record_date": record_date,
        "linked_note_id": "",
        "linked_note_title": "",
        "extract_text": extract_text_to_note,
        "tags": normalize_tag_list(request.form.get("file_tags", "")),
    }

    extracted_text: str | None = None
    extracted_success = False
    if extract_text_to_note:
        extracted_text, extracted_success = try_extract_file_text(target_path, uploaded.filename)
        if not extracted_success:
            flash("该文件类型无法读取文字", "error")

    note_content_html, note_content_text = build_file_note_payload(
        note_comment_html,
        note_comment_text,
        extracted_text if extracted_success else None,
        uploaded.filename,
    )
    if note_content_text:
        resolved_title = (note_title[:120] or fallback_title(Path(uploaded.filename))[:120])
        note_id = uuid.uuid4().hex[:10]
        entry["notes"].append(
            {
                "id": note_id,
                "title": resolved_title,
                "content_html": note_content_html,
                "content_text": note_content_text,
                "created_at": uploaded_at,
                "record_date": record_date,
                "source_file_id": file_id,
                "source_file_name": uploaded.filename[:240],
                "source_mode": "extracted" if extracted_success else "attachment",
                "tags": normalize_tag_list(request.form.get("file_tags", "")),
            }
        )
        file_entry["linked_note_id"] = note_id
        file_entry["linked_note_title"] = resolved_title

    entry["files"].append(file_entry)
    touch_stock(store, symbol)
    save_stock_store(store)
    if file_entry["linked_note_id"] and extracted_success:
        flash(f"{symbol} 文件已上传，文字已抽取进笔记。", "success")
    elif file_entry["linked_note_id"]:
        flash(f"{symbol} 文件已上传，评论已保存为笔记。", "success")
    else:
        flash(f"{symbol} 的研究文件已上传。", "success")
    return redirect(next_url)


def get_stock_file_entry(store: dict[str, Any], symbol: str, file_id: str) -> dict[str, Any]:
    entry = ensure_stock_entry(store, symbol)
    for file_entry in entry["files"]:
        if file_entry["id"] == file_id:
            return file_entry

    abort(404)


def build_stock_file_preview_context(
    store: dict[str, Any],
    symbol: str,
    file_entry: dict[str, Any],
) -> dict[str, Any]:
    entry = ensure_stock_entry(store, symbol)
    linked_note_id = str(file_entry.get("linked_note_id") or "").strip()
    linked_note = next((item for item in entry["notes"] if item["id"] == linked_note_id), None)
    original_name = str(file_entry.get("original_name") or "")
    file_path = stock_upload_dir(symbol) / str(file_entry.get("stored_name") or "")
    preview_text = ""
    is_truncated = False

    if is_text_previewable(original_name):
        preview_text, is_truncated = load_text_preview(file_path)

    preview_note_html = ""
    if is_image_previewable(original_name):
        if linked_note and linked_note.get("content_html"):
            preview_note_html = linked_note["content_html"]
        elif file_entry.get("description"):
            preview_note_html = plain_text_to_html(str(file_entry.get("description") or "").strip())

    return {
        "file_entry": {
            **file_entry,
            "display_uploaded_at": file_display_time(file_entry),
            "is_text_previewable": is_text_previewable(original_name),
            "is_image_previewable": is_image_previewable(original_name),
            "is_previewable": is_file_previewable(original_name),
        },
        "preview_text": preview_text,
        "is_truncated": is_truncated,
        "preview_note_html": preview_note_html,
        "image_url": url_for("inline_stock_file", symbol=symbol, file_id=file_entry["id"])
        if is_image_previewable(original_name)
        else "",
    }


@app.get("/stocks/<symbol>/files/<file_id>")
def download_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_entry = get_stock_file_entry(store, symbol, file_id)
    return send_from_directory(
        stock_upload_dir(symbol),
        file_entry["stored_name"],
        as_attachment=True,
        download_name=file_entry["original_name"],
    )


@app.get("/stocks/<symbol>/files/<file_id>/inline")
def inline_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_entry = get_stock_file_entry(store, symbol, file_id)
    return send_from_directory(
        stock_upload_dir(symbol),
        file_entry["stored_name"],
        as_attachment=False,
        download_name=file_entry["original_name"],
    )


@app.get("/stocks/<symbol>/files/<file_id>/preview")
def preview_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_entry = get_stock_file_entry(store, symbol, file_id)

    if not is_file_previewable(file_entry["original_name"]):
        flash("该文件类型暂不支持在线预览。", "error")
        return redirect(url_for("stock_detail", symbol=symbol))

    return render_template(
        "stock_file_preview.html",
        stock=build_stock_detail(store, symbol),
        **build_stock_file_preview_context(store, symbol, file_entry),
        **build_navigation_context(active_page="stocks", stock_store=store),
    )


@app.get("/stocks/<symbol>/files/<file_id>/preview-fragment")
def preview_stock_file_fragment(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_entry = get_stock_file_entry(store, symbol, file_id)

    if not is_file_previewable(file_entry["original_name"]):
        abort(404)

    return render_template(
        "stock_file_modal.html",
        stock_symbol=symbol,
        **build_stock_file_preview_context(store, symbol, file_entry),
    )


@app.post("/stocks/<symbol>/files/<file_id>/delete")
def delete_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    entry = ensure_stock_entry(store, symbol)
    file_entry = get_stock_file_entry(store, symbol, file_id)
    append_to_trash(
        store,
        create_trash_entry(
            "file",
            file_entry,
            symbol=symbol,
            title=file_entry.get("original_name") or "未命名文件",
        ),
    )
    entry["files"] = [item for item in entry["files"] if item["id"] != file_id]
    touch_stock(store, symbol)
    save_stock_store(store)
    flash(f"{symbol} 的文件已移入回收站。", "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))


@app.route("/files/<path:filename>")
def raw_report(filename: str):
    report_path = validate_report_name(filename)
    return send_from_directory(REPORTS_DIR, report_path.name, as_attachment=False)


if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STOCK_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    host = os.getenv("HOST", "0.0.0.0")
    port = current_port()
    app.run(host=host, port=port, debug=False)
