from __future__ import annotations

import calendar
import hmac
import hashlib
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
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
import requests
from bleach.css_sanitizer import CSSSanitizer
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env.local", override=False)
load_dotenv(BASE_DIR / ".env", override=False)

from monitor_runner import check_codex_login as check_monitor_codex_login
from monitor_runner import discover_codex_path as discover_monitor_codex_path
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
    "earnings_call": {"label": "电话会议", "tone": "transcript"},
    "note": {"label": "研究笔记", "tone": "note"},
    "file": {"label": "研究资料", "tone": "file"},
    "transcript": {"label": "会议转录", "tone": "transcript"},
    "schedule": {"label": "日程", "tone": "schedule"},
    "report": {"label": "关联日报", "tone": "report"},
    "group": {"label": "股票分组", "tone": "group"},
}
AI_SCOPE_CONTENT_KIND_META = {
    "report": "日报",
    "note": "笔记",
    "file": "文件",
    "earnings_call": "电话会议",
    "transcript": "转录",
}
AI_SCOPE_DEFAULT_CONTENT_KINDS = tuple(AI_SCOPE_CONTENT_KIND_META.keys())
MINDMAP_STATUS_META = {
    "pending": {"label": "排队中", "tone": "pending"},
    "running": {"label": "生成中", "tone": "info"},
    "completed": {"label": "已完成", "tone": "success"},
    "error": {"label": "失败", "tone": "danger"},
    "cancelled": {"label": "已停止", "tone": "pending"},
}
MINDMAP_STRUCTURE_KIND_META = {
    "single_stock": "单股拆解",
    "peer_group": "同行对比",
    "value_chain": "产业链传导",
    "theme_bundle": "主题资料包",
}
MINDMAP_STUDIO_THEME_META = {
    "graphite": {
        "label": "石墨蓝图",
        "description": "适合长时间梳理研究结构的冷静深色主题。",
    },
    "paper": {
        "label": "纸面研究",
        "description": "偏文稿与会议复盘的浅色纸面视图。",
    },
    "ocean": {
        "label": "海港晨光",
        "description": "更适合产业链与主题图谱的蓝绿层次。",
    },
}
MINDMAP_STUDIO_SURFACE_META = {
    "desktop": {
        "label": "桌面工作台",
        "description": "适合独立使用的大画布布局。",
        "frame_width": 1480,
    },
    "embedded": {
        "label": "网页嵌入",
        "description": "为未来嵌入现有网页预留更紧凑的安全边距。",
        "frame_width": 1180,
    },
    "mobile": {
        "label": "移动预览",
        "description": "提前检查窄屏下节点密度与检查器行为。",
        "frame_width": 430,
    },
}
MINDMAP_STUDIO_DENSITY_META = {
    "roomy": {"label": "宽松", "description": "更强调阅读与汇报展示。"},
    "compact": {"label": "紧凑", "description": "更适合高密度研究梳理。"},
}
MINDMAP_STUDIO_LAYOUT_META = {
    "mindmap": {
        "label": "分叉导图",
        "description": "根节点居中，主分支向左右延展，适合大多数研究梳理。",
    },
    "logic": {
        "label": "逻辑链",
        "description": "从左到右单向展开，适合判断链和会议复盘。",
    },
    "lanes": {
        "label": "分栏链路",
        "description": "按栏位并列展示，适合产业链、对比和资料分组。",
    },
}
MINDMAP_STUDIO_NODE_KIND_META = {
    "topic": "主题",
    "thesis": "判断",
    "evidence": "证据",
    "question": "待验证",
    "risk": "风险",
    "catalyst": "催化",
    "timeline": "时间锚点",
}
MINDMAP_STUDIO_RELATION_TONE_META = {
    "support": "支撑",
    "conflict": "冲突",
    "compare": "对照",
    "flow": "传导",
}
MINDMAP_STUDIO_ORIGIN_META = {
    "seed": "模板",
    "generated": "生成",
    "manual": "手动",
}
MINDMAP_STUDIO_VERIFY_META = {
    "stable": "已确认",
    "needs_verify": "待验证",
    "draft": "草稿",
}
MINDMAP_STUDIO_TEMPLATE_META = {
    "blank": {
        "label": "空白导图",
        "description": "从一张空白结构开始。",
    },
    "thesis": {
        "label": "投资判断",
        "description": "适合单股或主题判断拆解。",
    },
    "value_chain": {
        "label": "产业链传导",
        "description": "适合上下游与供需链路追踪。",
    },
    "debrief": {
        "label": "访谈复盘",
        "description": "适合专家会和内部会议复盘。",
    },
}
TRASH_KIND_META = {
    "note": {"label": "研究笔记", "description": "可恢复到原股票页"},
    "file": {"label": "研究资料", "description": "会保留原来的文件与说明"},
    "transcript": {"label": "会议转录", "description": "恢复后仍可继续查看与同步"},
    "group": {"label": "股票分组", "description": "恢复后会带回原有股票列表"},
    "schedule_item": {"label": "日程条目", "description": "恢复后会回到日程区，保留日期、备忘和关联公司"},
    "monitor_report": {"label": "Monitor 报告", "description": "恢复后会重新回到 Monitor 报告区"},
}
SCHEDULE_KIND_META = {
    "meeting": {"label": "专家会", "tone": "meeting"},
    "earnings": {"label": "业绩期", "tone": "earnings"},
    "task": {"label": "待办", "tone": "task"},
    "reminder": {"label": "提醒", "tone": "reminder"},
}
SCHEDULE_STATUS_META = {
    "planned": {"label": "待处理", "tone": "pending"},
    "done": {"label": "已完成", "tone": "success"},
    "cancelled": {"label": "已取消", "tone": "danger"},
}
SCHEDULE_PRIORITY_META = {
    "high": {"label": "高优先", "tone": "danger"},
    "normal": {"label": "常规", "tone": "info"},
    "low": {"label": "低优先", "tone": "pending"},
}
EXPERT_CATEGORY_META = {
    "management": {"label": "公司/管理层", "tone": "info", "order": 1},
    "industry": {"label": "产业专家", "tone": "note", "order": 2},
    "channel": {"label": "渠道/客户", "tone": "success", "order": 3},
    "supply_chain": {"label": "供应链/制造", "tone": "pending", "order": 4},
    "former_employee": {"label": "前员工/前高管", "tone": "danger", "order": 5},
    "capital": {"label": "投资/顾问", "tone": "group", "order": 6},
}
EXPERT_STAGE_META = {
    "priority": {"label": "重点跟进", "tone": "danger", "order": 1},
    "active": {"label": "稳定覆盖", "tone": "success", "order": 2},
    "watch": {"label": "观察名单", "tone": "pending", "order": 3},
    "archived": {"label": "已归档", "tone": "info", "order": 4},
}
EXPERT_INTERVIEW_KIND_META = {
    "expert_call": {"label": "专家会", "order": 1},
    "follow_up": {"label": "跟进访谈", "order": 2},
    "channel_check": {"label": "渠道验证", "order": 3},
    "debrief": {"label": "会后复盘", "order": 4},
}
EXPERT_INTERVIEW_STATUS_META = {
    "planned": {"label": "待访谈", "tone": "pending", "order": 1},
    "completed": {"label": "已完成", "tone": "success", "order": 2},
    "cancelled": {"label": "已取消", "tone": "danger", "order": 3},
}
EXPERT_RESOURCE_KIND_META = {
    "note": {"label": "研究笔记", "tone": "note", "order": 1},
    "file": {"label": "研究资料", "tone": "file", "order": 2},
    "transcript": {"label": "会议转录", "tone": "transcript", "order": 3},
    "schedule": {"label": "日程安排", "tone": "schedule", "order": 4},
}
EXPERT_VIEW_OPTIONS = {"manage", "create"}
SCHEDULE_VIEW_OPTIONS = {"board", "form"}
TIME_VALUE_PATTERN = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")
EARNINGS_SYNC_TAG = "自动同步业绩"
EARNINGS_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}
EARNINGS_SOURCE_CATALOG = (
    {
        "label": "Barchart",
        "url_template": "https://www.barchart.com/stocks/quotes/{symbol}/earnings-estimates",
        "date_pattern": re.compile(
            r"Next Earnings Release Date\s*-\s*<span class=\"next-earning \">\s*(\d{2}/\d{2}/\d{2})\s*</span>",
            re.IGNORECASE,
        ),
        "date_format": "%m/%d/%y",
    },
    {
        "label": "Stock Analysis",
        "url_template": "https://stockanalysis.com/stocks/{symbol}/",
        "date_pattern": re.compile(
            r"Earnings Date\s*</td>\s*<td[^>]*>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})\s*</td>",
            re.IGNORECASE,
        ),
        "date_format": "%b %d, %Y",
    },
)
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
TRANSCRIPT_CATEGORY_META = {
    "work": {
        "label": "工作",
        "description": "直接的工作内容",
        "summary": "电话会、专家访谈、内部会议等直接面向工作的录音。",
        "order": 1,
    },
    "reading": {
        "label": "阅读",
        "description": "工作补充阅读",
        "summary": "博客、文章、播客等作为工作补充的阅读或收听材料。",
        "order": 2,
    },
}
TRANSCRIPT_CATEGORY_OPTIONS = [
    {"value": key, "label": meta["label"], "description": meta["description"]}
    for key, meta in sorted(TRANSCRIPT_CATEGORY_META.items(), key=lambda item: item[1]["order"])
]
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
STOCK_SETUPS_DIR = resolve_app_path("STOCK_SETUPS_DIR", BASE_DIR / "data" / "stock_setups")
STOCK_UPLOADS_DIR = resolve_app_path("STOCKS_UPLOADS_DIR", BASE_DIR / "uploads" / "stocks")
TRANSCRIPT_UPLOADS_DIR = resolve_app_path("TRANSCRIPT_UPLOADS_DIR", BASE_DIR / "uploads" / "transcripts")
AI_CHAT_STORE_PATH = resolve_app_path("AI_CHAT_DATA_PATH", BASE_DIR / "data" / "ai_chats.json")
AI_CONTEXT_DIR = resolve_app_path("AI_CONTEXT_DIR", BASE_DIR / "data" / "ai_context")
MINDMAP_STORE_PATH = resolve_app_path("MINDMAP_DATA_PATH", BASE_DIR / "data" / "mindmaps.json")
MINDMAP_CONTEXT_DIR = resolve_app_path("MINDMAP_CONTEXT_DIR", BASE_DIR / "data" / "mindmap_context")
MINDMAP_STUDIO_STORE_PATH = resolve_app_path("MINDMAP_STUDIO_DATA_PATH", BASE_DIR / "data" / "mindmap_studio.json")
CODEX_CONFIG_DIR = Path.home() / ".codex"
CODEX_MODELS_CACHE_PATH = CODEX_CONFIG_DIR / "models_cache.json"
AI_CODEX_TIMEOUT_SECONDS = int(os.getenv("AI_CODEX_TIMEOUT_SECONDS", "900"))
AI_POLL_INTERVAL_SECONDS = int(os.getenv("AI_POLL_INTERVAL_SECONDS", "5"))
MINDMAP_POLL_INTERVAL_SECONDS = int(os.getenv("MINDMAP_POLL_INTERVAL_SECONDS", "5"))
MINDMAP_STALE_JOB_SECONDS = int(os.getenv("MINDMAP_STALE_JOB_SECONDS", "120"))
TRANSCRIPT_STATUS_POLL_INTERVAL_SECONDS = int(os.getenv("TRANSCRIPT_STATUS_POLL_INTERVAL_SECONDS", "12"))
AI_PROMPT_KNOWLEDGE_CHAR_LIMIT = int(os.getenv("AI_PROMPT_KNOWLEDGE_CHAR_LIMIT", "40000"))
MINDMAP_PLAN_KNOWLEDGE_CHAR_LIMIT = int(os.getenv("MINDMAP_PLAN_KNOWLEDGE_CHAR_LIMIT", "22000"))
MINDMAP_FINAL_KNOWLEDGE_CHAR_LIMIT = int(os.getenv("MINDMAP_FINAL_KNOWLEDGE_CHAR_LIMIT", "32000"))
MINDMAP_REPAIR_KNOWLEDGE_CHAR_LIMIT = int(os.getenv("MINDMAP_REPAIR_KNOWLEDGE_CHAR_LIMIT", "22000"))
MINDMAP_MAX_STEP_TIMEOUT_SECONDS = int(os.getenv("MINDMAP_MAX_STEP_TIMEOUT_SECONDS", "2400"))
MINDMAP_PIPELINE_VERSION = "20260331-research-v4"
MINDMAP_PROMPT_VERSION = "20260331-compare-verify-v3"
MINDMAP_SCHEMA_VERSION = "20260331-schema-v3"
MINDMAP_SCOPE_DRAFT_SESSION_KEY = "mindmap_scope_draft"
MINDMAP_MAX_CURATED_SOURCES = 28
MINDMAP_RECENT_WINDOW_DAYS = 45
AI_SESSION_LOCK = threading.RLock()
AI_PROCESS_LOCK = threading.RLock()
AI_RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
AI_STOP_REQUESTS: set[str] = set()
MINDMAP_LOCK = threading.RLock()
MINDMAP_PROCESS_LOCK = threading.RLock()
MINDMAP_RUNNING_PROCESSES: dict[str, subprocess.Popen[str]] = {}
MINDMAP_ACTIVE_TASKS: set[str] = set()
MINDMAP_STOP_REQUESTS: set[str] = set()
MINDMAP_STUDIO_LOCK = threading.RLock()
STOCK_STORE_LOCK = threading.RLock()
STOCK_STORE_CACHE_LOCK = threading.RLock()
STOCK_STORE_CACHE: dict[str, Any] = {"signature": None, "data": None}
STABLECOIN_MONITOR_ACTIVE_THREAD: threading.Thread | None = None
STABLECOIN_MONITOR_SCHEDULER_THREAD: threading.Thread | None = None
STABLECOIN_MONITOR_SCHEDULER_STARTED = False
COINGECKO_REQUEST_LOCK = threading.Lock()
COINGECKO_LAST_REQUEST_AT = 0.0
MINDMAP_KIND_PRIORITY = {
    "report": 1.1,
    "earnings_call": 1.05,
    "transcript": 1.0,
    "note": 0.92,
    "file": 0.84,
}
MINDMAP_CONFLICT_HINTS = (
    "但",
    "但是",
    "不过",
    "然而",
    "相反",
    "冲突",
    "分歧",
    "不一致",
    "修正",
    "推翻",
    "对冲",
    "验证后发现",
    "however",
    "but",
    "conflict",
    "disagree",
    "revised",
)
MINDMAP_EVIDENCE_HINT_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d+(?:\.\d+)?%|\$\d+(?:\.\d+)?|\b(?:Q[1-4]|FY\d{2,4}|bps|mt|tons|aircraft|engines?)\b",
    re.IGNORECASE,
)
REPORT_CACHE_LOCK = threading.RLock()
REPORT_INDEX_CACHE: dict[str, Any] = {
    "signature": None,
    "items": [],
    "by_filename": {},
}
REPORT_HTML_CACHE: dict[tuple[str, int, int], str] = {}
REPORT_HTML_RENDER_VERSION = 3
PDF_READER_CLASS: Any | None = None
DOCX_DOCUMENT_CLASS: Any | None = None
OSS_CLIENT_API: dict[str, Any] | None = None
TINGWU_CLIENT_API: dict[str, Any] | None = None
DEFAULT_MONITOR_SOURCE_DIR = Path(r"D:\工作\FTAI")
ORIGINAL_MONITOR_CONFIG_PATH = DEFAULT_MONITOR_SOURCE_DIR / "stock_monitor_config.json"
MONITOR_DATA_DIR = BASE_DIR / "data" / "monitor"
MONITOR_CONFIG_PATH = MONITOR_DATA_DIR / "config.json"
MONITOR_RUNTIME_PATH = MONITOR_DATA_DIR / "runtime.json"
MONITOR_RUNNER_PATH = BASE_DIR / "monitor_runner.py"


def get_pdf_reader_class() -> Any:
    global PDF_READER_CLASS
    if PDF_READER_CLASS is None:
        from pypdf import PdfReader as pdf_reader_class

        PDF_READER_CLASS = pdf_reader_class
    return PDF_READER_CLASS


def get_docx_document_class() -> Any:
    global DOCX_DOCUMENT_CLASS
    if DOCX_DOCUMENT_CLASS is None:
        from docx import Document as docx_document_class

        DOCX_DOCUMENT_CLASS = docx_document_class
    return DOCX_DOCUMENT_CLASS


def get_oss_client_api() -> dict[str, Any]:
    global OSS_CLIENT_API
    if OSS_CLIENT_API is None:
        from oss_client import (
            build_oss_status as build_oss_status_impl,
            build_signed_url as build_signed_url_impl,
            delete_uploaded_object as delete_uploaded_object_impl,
            probe_oss_bridge as probe_oss_bridge_impl,
            upload_file_for_tingwu as upload_file_for_tingwu_impl,
        )

        OSS_CLIENT_API = {
            "build_oss_status": build_oss_status_impl,
            "build_signed_url": build_signed_url_impl,
            "delete_uploaded_object": delete_uploaded_object_impl,
            "probe_oss_bridge": probe_oss_bridge_impl,
            "upload_file_for_tingwu": upload_file_for_tingwu_impl,
        }
    return OSS_CLIENT_API


def build_oss_status() -> dict[str, Any]:
    return get_oss_client_api()["build_oss_status"]()


def build_signed_url(*, bucket_name: str, object_key: str) -> dict[str, Any]:
    return get_oss_client_api()["build_signed_url"](bucket_name=bucket_name, object_key=object_key)


def delete_uploaded_object(*, bucket_name: str, object_key: str) -> None:
    get_oss_client_api()["delete_uploaded_object"](bucket_name=bucket_name, object_key=object_key)


def probe_oss_bridge() -> dict[str, Any]:
    return get_oss_client_api()["probe_oss_bridge"]()


def upload_file_for_tingwu(path: Path, *, original_name: str, transcript_id: str) -> dict[str, Any]:
    return get_oss_client_api()["upload_file_for_tingwu"](
        path,
        original_name=original_name,
        transcript_id=transcript_id,
    )


def get_tingwu_client_api() -> dict[str, Any]:
    global TINGWU_CLIENT_API
    if TINGWU_CLIENT_API is None:
        from tingwu_client import (
            build_tingwu_status as build_tingwu_status_impl,
            fetch_result_documents as fetch_result_documents_impl,
            get_task_info as get_task_info_impl,
            submit_offline_task as submit_offline_task_impl,
        )

        TINGWU_CLIENT_API = {
            "build_tingwu_status": build_tingwu_status_impl,
            "fetch_result_documents": fetch_result_documents_impl,
            "get_task_info": get_task_info_impl,
            "submit_offline_task": submit_offline_task_impl,
        }
    return TINGWU_CLIENT_API


def build_tingwu_status() -> dict[str, Any]:
    return get_tingwu_client_api()["build_tingwu_status"]()


def fetch_result_documents(result_urls: dict[str, Any]) -> dict[str, Any]:
    return get_tingwu_client_api()["fetch_result_documents"](result_urls)


def get_task_info(task_id: str) -> dict[str, Any]:
    return get_tingwu_client_api()["get_task_info"](task_id)


def submit_offline_task(transcript: dict[str, Any], *, file_url: str) -> dict[str, Any]:
    return get_tingwu_client_api()["submit_offline_task"](transcript, file_url=file_url)
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
SIGNAL_MONITOR_DEFAULT_CATEGORY = "通用监控"
SIGNAL_MONITOR_DEFAULT_SOURCES = [
    {
        "id": "semianalysis-x",
        "display_name": "SemiAnalysis",
        "source_type": "x",
        "handle": "SemiAnalysis_",
        "profile_url": "https://x.com/SemiAnalysis_",
        "notes": "先作为大 V 言论监控的默认示例。",
        "category": SIGNAL_MONITOR_DEFAULT_CATEGORY,
        "enabled": True,
    }
]
DATA_MONITOR_DATA_DIR = BASE_DIR / "data" / "data_monitor"
STABLECOIN_MONITOR_CACHE_PATH = DATA_MONITOR_DATA_DIR / "stablecoins.json"
STABLECOIN_MONITOR_RUNTIME_PATH = DATA_MONITOR_DATA_DIR / "stablecoins_runtime.json"
STABLECOIN_MONITOR_LOCK = threading.RLock()
STABLECOIN_MONITOR_STATUS_POLL_INTERVAL_SECONDS = 5
STABLECOIN_MONITOR_REFRESH_INTERVAL_HOURS = int(os.getenv("STABLECOIN_MONITOR_REFRESH_INTERVAL_HOURS", "12"))
STABLECOIN_MONITOR_SCHEDULER_SLEEP_SECONDS = int(os.getenv("STABLECOIN_MONITOR_SCHEDULER_SLEEP_SECONDS", "900"))
STABLECOIN_MONITOR_DAY_RANGE = 365
STABLECOIN_MONITOR_START_MONTH = str(os.getenv("STABLECOIN_MONITOR_START_MONTH", "2024-01")).strip() or "2024-01"
COINGECKO_MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("COINGECKO_MIN_REQUEST_INTERVAL_SECONDS", "8"))
COINGECKO_API_BASE_URL = "https://api.coingecko.com/api/v3"
DEFILLAMA_STABLECOINS_API_BASE_URL = "https://stablecoins.llama.fi"
COINGECKO_REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
}
STABLECOIN_MONITOR_ASSETS = [
    {"id": "tether", "llama_id": "1", "symbol": "USDT", "label": "Tether", "color": "var(--stablecoin-series-1)"},
    {"id": "usd-coin", "llama_id": "2", "symbol": "USDC", "label": "USD Coin", "color": "var(--stablecoin-series-2)"},
    {"id": "dai", "llama_id": "5", "symbol": "DAI", "label": "DAI", "color": "var(--stablecoin-series-3)"},
    {"id": "ethena-usde", "llama_id": "146", "symbol": "USDe", "label": "Ethena USDe", "color": "var(--stablecoin-series-4)"},
    {"id": "first-digital-usd", "llama_id": "119", "symbol": "FDUSD", "label": "First Digital USD", "color": "var(--stablecoin-series-5)"},
    {"id": "paypal-usd", "llama_id": "120", "symbol": "PYUSD", "label": "PayPal USD", "color": "var(--stablecoin-series-6)"},
]
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_KEEP_COUNT = int(os.getenv("BACKUP_KEEP_COUNT", "20"))
BACKUP_EXCLUDED_DIR_NAMES = {".git", ".venv", "__pycache__", "backups"}
BACKUP_EXCLUDED_FILE_NAMES = {".env", ".env.local"}
BACKUP_EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
WEB_ACCESS_PASSWORD = str(os.getenv("WEB_ACCESS_PASSWORD", "4242wei")).strip()
WEB_ACCESS_SESSION_KEY = "web_access_signature"
WEB_ACCESS_REMEMBER_DAYS = 30
WEB_ACCESS_PASSWORD_SIGNATURE = (
    hashlib.sha256(WEB_ACCESS_PASSWORD.encode("utf-8")).hexdigest() if WEB_ACCESS_PASSWORD else ""
)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "stock-daily-analysis-local-secret")
app.permanent_session_lifetime = timedelta(days=WEB_ACCESS_REMEMBER_DAYS)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True


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


def compact_report_summary_text(text: str, *, limit: int = 180) -> str:
    compact = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    compact = re.sub(r"`([^`]*)`", r"\1", compact)
    compact = re.sub(r"\s+", " ", compact).strip(" -:;")
    if len(compact) > limit:
        return compact[:limit].rstrip() + "..."
    return compact


def collect_report_section_bullets(content: str, heading: str) -> list[str]:
    bullets: list[str] = []
    heading_marker = f"## {heading}"
    in_section = False

    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("## "):
            if stripped == heading_marker:
                in_section = True
                continue
            if in_section:
                break
        if in_section and stripped.startswith("- "):
            bullets.append(stripped[2:].strip())

    return bullets


def extract_monitor_report_summary(content: str) -> str:
    head = content[:320]
    if "# Stock Monitor Report" not in head and "Stock Monitor Report" not in head:
        return ""

    summary_parts: list[str] = []
    run_summary_bullets = collect_report_section_bullets(content, "Run Summary")
    high_signal_line = next(
        (
            compact_report_summary_text(item.split(":", 1)[1])
            for item in run_summary_bullets
            if item.lower().startswith("high-signal changes:") and ":" in item
        ),
        "",
    )
    if high_signal_line:
        summary_parts.append(f"高信号：{high_signal_line}")

    signal_board = collect_report_section_bullets(content, "Signal Board")
    meaningful_signal_board = [
        compact_report_summary_text(item)
        for item in signal_board
        if not re.search(r":\s*(?:none|无|无实质|没有)\s*$", item, re.IGNORECASE)
    ]
    if meaningful_signal_board:
        summary_parts.append("；".join(meaningful_signal_board[:2]))

    if not summary_parts:
        top_changes = collect_report_section_bullets(content, "Top Changes")
        meaningful_top_changes = [
            compact_report_summary_text(item)
            for item in top_changes
            if "no stock had a material company-level change" not in item.lower()
        ]
        if meaningful_top_changes:
            summary_parts.append("；".join(meaningful_top_changes[:2]))

    if summary_parts:
        return compact_report_summary_text("；".join(summary_parts), limit=210)
    return ""


def extract_summary(content: str) -> str:
    monitor_summary = extract_monitor_report_summary(content)
    if monitor_summary:
        return monitor_summary

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


def format_compact_currency(value: Any, *, decimals: int = 1) -> str:
    try:
        numeric_value = float(value or 0.0)
    except (TypeError, ValueError):
        numeric_value = 0.0

    sign = "-" if numeric_value < 0 else ""
    amount = abs(numeric_value)
    units = (
        (1_000_000_000_000, "T", 2),
        (1_000_000_000, "B", decimals),
        (1_000_000, "M", decimals),
        (1_000, "K", decimals),
    )
    for threshold, suffix, digits in units:
        if amount >= threshold:
            return f"{sign}${amount / threshold:.{digits}f}{suffix}"

    return f"{sign}${amount:,.0f}"


def format_signed_percent(value: Any, *, decimals: int = 1) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{numeric_value:+.{decimals}f}%"


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


def format_month_day_label(date_value: str | None) -> str:
    parsed = parse_iso_date_value(date_value)
    if not parsed:
        return "待同步"
    return f"{parsed.month}月{parsed.day}日"


def normalize_stock_earnings_info(raw_info: Any) -> dict[str, Any]:
    source = raw_info if isinstance(raw_info, dict) else {}
    return {
        "next_date": normalize_date_field(source.get("next_date")),
        "source_label": str(source.get("source_label") or "").strip()[:80],
        "source_url": str(source.get("source_url") or "").strip()[:600],
        "last_synced_at": str(source.get("last_synced_at") or "").strip()[:40],
        "is_estimated": bool(source.get("is_estimated")),
    }


def build_stock_earnings_view(entry: dict[str, Any]) -> dict[str, Any]:
    info = normalize_stock_earnings_info(entry.get("earnings"))
    next_date = info["next_date"]
    return {
        **info,
        "has_date": bool(next_date),
        "short_label": format_month_day_label(next_date),
        "full_label": next_date or "待同步",
        "headline": f"下一次业绩：{format_month_day_label(next_date)}",
        "display_last_synced_at": (
            format_iso_timestamp(info["last_synced_at"]) if info["last_synced_at"] else "未同步"
        ),
    }


def normalize_stock_earnings_call_sync_info(raw_info: Any) -> dict[str, Any]:
    source = raw_info if isinstance(raw_info, dict) else {}
    try:
        lookback_days = max(0, int(source.get("lookback_days") or 730))
    except (TypeError, ValueError):
        lookback_days = 730

    return {
        "source_label": str(source.get("source_label") or "").strip()[:80],
        "source_url": str(source.get("source_url") or "").strip()[:600],
        "last_synced_at": str(source.get("last_synced_at") or "").strip()[:40],
        "last_error": str(source.get("last_error") or "").strip()[:2000],
        "lookback_days": lookback_days,
    }


def build_stock_earnings_call_sync_view(entry: dict[str, Any]) -> dict[str, Any]:
    info = normalize_stock_earnings_call_sync_info(entry.get("earnings_call_sync"))
    return {
        **info,
        "has_synced": bool(info["last_synced_at"]),
        "display_last_synced_at": (
            format_iso_timestamp(info["last_synced_at"]) if info["last_synced_at"] else "未同步"
        ),
    }


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


def stock_setup_path(symbol: str) -> Path:
    normalized_symbol = str(symbol or "").strip().upper()
    return STOCK_SETUPS_DIR / f"{normalized_symbol}.md"


def build_stock_setup_view(symbol: str) -> dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    title_fallback = f"{normalized_symbol} Set up"
    placeholder_copy = "这只股票的公开信息 set up 还没放进来。后面可以把 thesis、预期差、验证点和 kill criteria 都沉淀在这里。"
    template_id = f"stock-setup-reader-{normalized_symbol.lower() or 'default'}"
    path = stock_setup_path(normalized_symbol)

    if not path.exists():
        return {
            "has_setup": False,
            "title": title_fallback,
            "summary": placeholder_copy,
            "html": plain_text_to_html(placeholder_copy),
            "updated_at": "",
            "template_id": template_id,
        }

    content = read_text_file(path).strip()
    if not content:
        return {
            "has_setup": False,
            "title": title_fallback,
            "summary": placeholder_copy,
            "html": plain_text_to_html(placeholder_copy),
            "updated_at": "",
            "template_id": template_id,
        }

    try:
        stat_result = path.stat()
    except OSError:
        stat_result = None

    html = markdown.markdown(
        content,
        extensions=MARKDOWN_EXTENSIONS,
        output_format="html5",
    )
    summary = extract_summary(content)
    if not summary or summary == "在报告前几段补一小段摘要，这里就会自动显示预览。":
        summary = "先看 thesis、预期差、验证点，再决定要不要继续往下深挖。"

    return {
        "has_setup": True,
        "title": extract_title(content, title_fallback),
        "summary": summary,
        "html": html,
        "updated_at": format_timestamp(stat_result.st_mtime) if stat_result else "",
        "template_id": template_id,
    }


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
    reader = get_pdf_reader_class()(str(path))
    chunks = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if text:
            chunks.append(text)

    return "\n\n".join(chunks).strip()


def extract_docx_text(path: Path) -> str:
    document = get_docx_document_class()(str(path))
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


def build_recent_month_windows(
    month_count: int,
    *,
    end_date: datetime | None = None,
) -> list[dict[str, str]]:
    base = end_date or datetime.now()
    windows: list[dict[str, str]] = []
    for offset in range(month_count - 1, -1, -1):
        year, month = shift_month(base.year, base.month, -offset)
        month_key = f"{year:04d}-{month:02d}"
        windows.append(
            {
                "month": month_key,
                "label": month_key,
                "short_label": f"{str(year)[2:]}-{month:02d}",
                "month_name": f"{calendar.month_abbr[month]} {str(year)[2:]}",
            }
        )
    return windows


def build_month_windows_between(
    start_month: str,
    end_month: str | None = None,
) -> list[dict[str, str]]:
    start_date = parse_month_value(start_month)
    end_date = parse_month_value(end_month, fallback=start_date) if end_month else datetime.now().replace(day=1)
    start_date = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if end_date < start_date:
        end_date = start_date

    windows: list[dict[str, str]] = []
    cursor = start_date
    while cursor <= end_date:
        month_key = f"{cursor.year:04d}-{cursor.month:02d}"
        windows.append(
            {
                "month": month_key,
                "label": month_key,
                "short_label": f"{str(cursor.year)[2:]}-{cursor.month:02d}",
                "month_name": f"{calendar.month_abbr[cursor.month]} {str(cursor.year)[2:]}",
            }
        )
        next_year, next_month = shift_month(cursor.year, cursor.month, 1)
        cursor = datetime(next_year, next_month, 1)

    return windows


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


def infer_date_from_filename(filename: str | None) -> str:
    stem = Path(str(filename or "")).stem
    if not stem:
        return ""

    separator_match = re.search(
        r"(?<!\d)(?P<year>20\d{2})[-_.\s](?P<month>\d{1,2})[-_.\s](?P<day>\d{1,2})(?!\d)",
        stem,
    )
    if separator_match:
        try:
            return datetime(
                int(separator_match.group("year")),
                int(separator_match.group("month")),
                int(separator_match.group("day")),
            ).date().isoformat()
        except ValueError:
            pass

    compact_match = re.search(r"(?<!\d)(?P<date>20\d{6})(?!\d)", stem)
    if compact_match:
        try:
            return datetime.strptime(compact_match.group("date"), "%Y%m%d").date().isoformat()
        except ValueError:
            pass

    return ""


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
        values = re.findall(r"earnings_call|report|note|file|transcript", raw_values.lower())
    elif isinstance(raw_values, (list, tuple, set)):
        values: list[Any] = []
        for raw_value in raw_values:
            if isinstance(raw_value, str):
                values.extend(re.findall(r"earnings_call|report|note|file|transcript", raw_value.lower()))
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


def normalize_identifier_list(
    raw_values: Any,
    *,
    max_items: int = 200,
    max_length: int = 80,
) -> list[str]:
    if isinstance(raw_values, str):
        values = re.split(r"[\s,;，；]+", raw_values)
    elif isinstance(raw_values, (list, tuple, set)):
        values = raw_values
    else:
        values = []

    ordered: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = re.sub(r"[^A-Za-z0-9._:-]", "", str(raw_value or "").strip())[:max_length]
        if not value:
            continue
        normalized_key = value.casefold()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        ordered.append(value)

    return ordered[:max_items]


def normalize_expert_resource_ref(raw_ref: Any) -> dict[str, str] | None:
    if not isinstance(raw_ref, dict):
        return None

    kind = str(raw_ref.get("kind") or "").strip().lower()
    if kind not in EXPERT_RESOURCE_KIND_META:
        return None

    resource_id = re.sub(r"[^A-Za-z0-9._-]", "", str(raw_ref.get("resource_id") or "").strip())[:80]
    if not resource_id:
        return None

    symbol = normalize_stock_symbol(str(raw_ref.get("symbol") or "")) or ""
    if kind in {"note", "file"} and not symbol:
        return None

    return {
        "kind": kind,
        "symbol": symbol if kind in {"note", "file"} else "",
        "resource_id": resource_id,
    }


def build_expert_resource_token(resource_ref: dict[str, Any]) -> str:
    kind = str(resource_ref.get("kind") or "").strip().lower()
    symbol = str(resource_ref.get("symbol") or "").strip().upper()
    resource_id = str(resource_ref.get("resource_id") or "").strip()
    return "|".join([kind, symbol, resource_id])


def build_expert_resource_preview_url(resource_ref: dict[str, Any]) -> str:
    return url_for("expert_resource_preview", token=build_expert_resource_token(resource_ref))


def parse_expert_resource_token(raw_value: str | None) -> dict[str, str] | None:
    parts = str(raw_value or "").split("|", 2)
    if len(parts) != 3:
        return None

    return normalize_expert_resource_ref(
        {
            "kind": parts[0],
            "symbol": parts[1],
            "resource_id": parts[2],
        }
    )


def normalize_expert_resource_refs(raw_values: Any) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    values = raw_values if isinstance(raw_values, (list, tuple, set)) else []
    for raw_value in values:
        if isinstance(raw_value, str):
            resource_ref = parse_expert_resource_token(raw_value)
        else:
            resource_ref = normalize_expert_resource_ref(raw_value)
        if resource_ref is None:
            continue

        token = build_expert_resource_token(resource_ref)
        if token in seen:
            continue
        seen.add(token)
        refs.append(resource_ref)

    return refs


def normalize_time_field(value: str | None) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    match = TIME_VALUE_PATTERN.fullmatch(raw_value)
    if not match:
        return ""

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return ""

    return f"{hour:02d}:{minute:02d}"


def normalize_schedule_view(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in SCHEDULE_VIEW_OPTIONS:
        return candidate
    return "board"


def normalize_expert_view(value: str | None, *, has_experts: bool) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in EXPERT_VIEW_OPTIONS:
        return candidate
    return "manage" if has_experts else "create"


def normalize_schedule_item(raw_item: Any) -> dict[str, Any] | None:
    if not isinstance(raw_item, dict):
        return None

    title = str(raw_item.get("title") or "").strip()
    scheduled_date = normalize_date_field(raw_item.get("scheduled_date"))
    if not title or not scheduled_date:
        return None

    kind = str(raw_item.get("kind") or "meeting").strip()
    if kind not in SCHEDULE_KIND_META:
        kind = "meeting"

    status = str(raw_item.get("status") or "planned").strip()
    if status not in SCHEDULE_STATUS_META:
        status = "planned"

    priority = str(raw_item.get("priority") or "normal").strip()
    if priority not in SCHEDULE_PRIORITY_META:
        priority = "normal"

    start_time = normalize_time_field(raw_item.get("start_time"))
    end_time = normalize_time_field(raw_item.get("end_time"))
    all_day = bool(raw_item.get("all_day"))
    has_time_range = bool(raw_item.get("has_time_range")) or bool(start_time or end_time)
    if all_day:
        has_time_range = False
        start_time = ""
        end_time = ""
    elif not has_time_range:
        start_time = ""
        end_time = ""
    elif start_time and end_time and end_time <= start_time:
        end_time = ""

    return {
        "id": str(raw_item.get("id") or uuid.uuid4().hex[:10]),
        "title": title[:160],
        "kind": kind,
        "status": status,
        "priority": priority,
        "symbol": normalize_stock_symbol(str(raw_item.get("symbol") or "")) or "",
        "company": str(raw_item.get("company") or "").strip()[:120],
        "scheduled_date": scheduled_date,
        "has_time_range": has_time_range,
        "start_time": start_time,
        "end_time": end_time,
        "all_day": all_day,
        "location": str(raw_item.get("location") or "").strip()[:180],
        "note": trim_note_content(str(raw_item.get("note") or "").strip(), limit=1800),
        "tags": normalize_tag_list(raw_item.get("tags", [])),
        "created_at": str(raw_item.get("created_at") or now_iso()),
        "updated_at": str(raw_item.get("updated_at") or now_iso()),
    }


def normalize_expert_interview(raw_interview: Any) -> dict[str, Any] | None:
    if not isinstance(raw_interview, dict):
        return None

    title = str(raw_interview.get("title") or "").strip()
    interview_date = normalize_date_field(raw_interview.get("interview_date"))
    if not title or not interview_date:
        return None

    kind = str(raw_interview.get("kind") or "expert_call").strip()
    if kind not in EXPERT_INTERVIEW_KIND_META:
        kind = "expert_call"

    status = str(raw_interview.get("status") or "completed").strip()
    if status not in EXPERT_INTERVIEW_STATUS_META:
        status = "completed"

    return {
        "id": str(raw_interview.get("id") or uuid.uuid4().hex[:10]),
        "title": title[:160],
        "kind": kind,
        "status": status,
        "interview_date": interview_date,
        "summary": trim_note_content(str(raw_interview.get("summary") or "").strip(), limit=2200),
        "follow_up": trim_note_content(str(raw_interview.get("follow_up") or "").strip(), limit=1400),
        "tags": normalize_tag_list(raw_interview.get("tags", [])),
        "created_at": str(raw_interview.get("created_at") or now_iso()),
        "updated_at": str(raw_interview.get("updated_at") or now_iso()),
    }


def normalize_expert_entry(raw_expert: Any) -> dict[str, Any] | None:
    if not isinstance(raw_expert, dict):
        return None

    name = str(raw_expert.get("name") or "").strip()
    if not name:
        return None

    category = str(raw_expert.get("category") or "industry").strip()
    if category not in EXPERT_CATEGORY_META:
        category = "industry"

    stage = str(raw_expert.get("stage") or "watch").strip()
    if stage not in EXPERT_STAGE_META:
        stage = "watch"

    interviews = [
        interview
        for raw_interview in raw_expert.get("interviews", [])
        if (interview := normalize_expert_interview(raw_interview)) is not None
    ]

    return {
        "id": str(raw_expert.get("id") or uuid.uuid4().hex[:10]),
        "name": name[:120],
        "organization": str(raw_expert.get("organization") or "").strip()[:120],
        "title": str(raw_expert.get("title") or "").strip()[:120],
        "category": category,
        "stage": stage,
        "region": str(raw_expert.get("region") or "").strip()[:80],
        "source": str(raw_expert.get("source") or "").strip()[:120],
        "related_symbols": normalize_stock_symbol_list(raw_expert.get("related_symbols", [])),
        "tags": normalize_tag_list(raw_expert.get("tags", [])),
        "expertise": trim_note_content(str(raw_expert.get("expertise") or "").strip(), limit=1800),
        "contact_notes": trim_note_content(str(raw_expert.get("contact_notes") or "").strip(), limit=2000),
        "resource_refs": normalize_expert_resource_refs(raw_expert.get("resource_refs", [])),
        "interviews": interviews,
        "created_at": str(raw_expert.get("created_at") or now_iso()),
        "updated_at": str(raw_expert.get("updated_at") or now_iso()),
    }


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


def normalize_transcript_category(value: str | None) -> str:
    candidate = str(value or "").strip()
    if candidate in TRANSCRIPT_CATEGORY_META:
        return candidate
    return "work"


def build_transcript_category_payload(value: str | None) -> dict[str, str]:
    category = normalize_transcript_category(value)
    meta = TRANSCRIPT_CATEGORY_META[category]
    return {
        "key": category,
        "label": meta["label"],
        "description": meta["description"],
        "summary": meta["summary"],
    }


def build_transcript_card(entry: dict[str, Any]) -> dict[str, Any]:
    status_meta = TRANSCRIPT_STATUS_META.get(entry["status"], TRANSCRIPT_STATUS_META["pending_api"])
    transcript_html = entry.get("transcript_html", "")
    transcript_text = entry.get("transcript_text", "")
    has_transcript_content = bool(transcript_html and transcript_text)
    has_remote_task = bool(entry.get("provider_task_id"))
    has_file_url = bool(str(entry.get("file_url_hint") or "").strip())
    source_meta = build_transcript_source_meta(entry)
    category_meta = build_transcript_category_payload(entry.get("category"))
    linked_symbols = transcript_linked_symbols(entry)
    linked_symbol = linked_symbols[0] if linked_symbols else ""
    linked_search_symbol = linked_symbol if len(linked_symbols) == 1 else ""

    return {
        **entry,
        "linked_symbol": linked_symbol,
        "linked_symbols": linked_symbols,
        "linked_symbols_label": "；".join(linked_symbols),
        "linked_symbols_form_value": "; ".join(linked_symbols),
        "linked_symbol_count": len(linked_symbols),
        "linked_search_symbol": linked_search_symbol,
        "display_title": entry["title"] or fallback_title(Path(entry["original_name"])),
        "display_created_at": format_iso_timestamp(entry["created_at"]),
        "display_updated_at": format_iso_timestamp(entry["updated_at"]),
        "meeting_date_label": entry["meeting_date"] or "未设置会议日期",
        "category_label": category_meta["label"],
        "category_description": category_meta["description"],
        "category_summary": category_meta["summary"],
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


def build_transcript_category_cards(transcript_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for key, meta in sorted(TRANSCRIPT_CATEGORY_META.items(), key=lambda item: item[1]["order"]):
        matched = [item for item in transcript_cards if item.get("category") == key]
        cards.append(
            {
                "key": key,
                "label": meta["label"],
                "description": meta["description"],
                "summary": meta["summary"],
                "total_count": len(matched),
                "completed_count": sum(1 for item in matched if item["status"] == "completed"),
                "queue_count": sum(1 for item in matched if item["status"] != "completed"),
            }
        )

    return cards


def build_transcript_page_context(
    store: dict[str, Any],
    *,
    requested_symbol: str = "",
) -> dict[str, Any]:
    stock_options = build_stock_selector_options(store)
    available_symbols = {item["symbol"] for item in stock_options}
    preferred_symbol = requested_symbol if requested_symbol in available_symbols else ""
    transcript_cards = build_transcript_cards(store, symbol_filter=preferred_symbol or None)
    transcript_stats = build_transcript_stats_payload(transcript_cards)

    return {
        "stock_options": stock_options,
        "preferred_symbol": preferred_symbol,
        "transcripts": transcript_cards,
        "transcript_category_cards": build_transcript_category_cards(transcript_cards),
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


def stock_file_storage_symbol(file_entry: dict[str, Any], fallback_symbol: str | None = None) -> str:
    return normalize_stock_symbol(str(file_entry.get("storage_symbol") or "")) or (
        normalize_stock_symbol(fallback_symbol or "") or ""
    )


def stock_file_linked_symbols(file_entry: dict[str, Any], fallback_symbol: str | None = None) -> list[str]:
    storage_symbol = stock_file_storage_symbol(file_entry, fallback_symbol)
    return ordered_unique(
        ([storage_symbol] if storage_symbol else []) + normalize_stock_symbol_list(file_entry.get("linked_symbols", []))
    )


def build_stock_file_record(owner_symbol: str, file_entry: dict[str, Any]) -> dict[str, Any]:
    storage_symbol = stock_file_storage_symbol(file_entry, owner_symbol) or owner_symbol
    linked_symbols = stock_file_linked_symbols(file_entry, storage_symbol)
    return {
        "owner_symbol": owner_symbol,
        "storage_symbol": storage_symbol,
        "linked_symbols": linked_symbols,
        "linked_symbols_label": "；".join(linked_symbols),
        "file_entry": file_entry,
    }


def iter_stock_file_records(
    store: dict[str, Any],
    *,
    symbol_filter: str | None = None,
):
    normalized_symbol = normalize_stock_symbol(symbol_filter)
    seen_keys: set[str] = set()
    raw_stocks = store.get("stocks", {})
    stock_symbols = sorted(raw_stocks.keys()) if isinstance(raw_stocks, dict) else []

    for owner_symbol in stock_symbols:
        entry = ensure_stock_entry(store, owner_symbol)
        for file_entry in entry["files"]:
            record = build_stock_file_record(owner_symbol, file_entry)
            if normalized_symbol and normalized_symbol not in record["linked_symbols"]:
                continue

            dedupe_key = str(file_entry.get("id") or "").strip() or (
                f"{record['storage_symbol']}::{file_entry.get('stored_name') or ''}"
            )
            if dedupe_key in seen_keys:
                continue

            seen_keys.add(dedupe_key)
            yield record


def get_stock_file_record(store: dict[str, Any], symbol: str, file_id: str) -> dict[str, Any]:
    target_id = str(file_id or "").strip()
    normalized_symbol = normalize_stock_symbol(symbol)
    for record in iter_stock_file_records(store, symbol_filter=normalized_symbol or None):
        if str(record["file_entry"].get("id") or "").strip() == target_id:
            return record
    abort(404)


def get_stock_file_linked_note(store: dict[str, Any], record: dict[str, Any]) -> dict[str, Any] | None:
    linked_note_id = str(record["file_entry"].get("linked_note_id") or "").strip()
    if not linked_note_id:
        return None

    storage_entry = ensure_stock_entry(store, record["storage_symbol"])
    return next((item for item in storage_entry["notes"] if item["id"] == linked_note_id), None)


def build_stock_file_card(
    store: dict[str, Any],
    record: dict[str, Any],
    *,
    access_symbol: str,
) -> dict[str, Any]:
    file_entry = record["file_entry"]
    original_name = str(file_entry.get("original_name") or "")
    resolved_symbol = normalize_stock_symbol(access_symbol) or record["storage_symbol"]
    linked_symbols = record["linked_symbols"]

    return {
        **file_entry,
        "storage_symbol": record["storage_symbol"],
        "linked_symbols": linked_symbols,
        "linked_symbols_label": record["linked_symbols_label"],
        "linked_symbol_count": len(linked_symbols),
        "linked_symbols_form_value": "; ".join(linked_symbols),
        "display_uploaded_at": file_display_time(file_entry),
        "is_text_previewable": is_text_previewable(original_name),
        "is_image_previewable": is_image_previewable(original_name),
        "is_previewable": is_file_previewable(original_name),
        "preview_label": "查看图片" if is_image_previewable(original_name) else "在线预览",
        "has_linked_note": bool(file_entry.get("linked_note_id")),
        "summary_excerpt": summarize_text_block(file_entry.get("description") or original_name),
        "tags": normalize_tag_list(file_entry.get("tags", [])),
        "context_symbol": resolved_symbol,
        "is_owner_context": resolved_symbol == record["storage_symbol"],
        "origin_symbol": record["storage_symbol"],
        "download_url": url_for("download_stock_file", symbol=resolved_symbol, file_id=file_entry["id"]),
        "preview_url": url_for("preview_stock_file_fragment", symbol=resolved_symbol, file_id=file_entry["id"]),
        "update_links_url": url_for("update_stock_file_links", symbol=resolved_symbol, file_id=file_entry["id"]),
        "delete_url": url_for("delete_stock_file", symbol=resolved_symbol, file_id=file_entry["id"]),
    }


def stock_file_count_for_symbol(store: dict[str, Any], symbol: str) -> int:
    return sum(1 for _ in iter_stock_file_records(store, symbol_filter=symbol))


def touch_stock_symbols(store: dict[str, Any], symbols: list[str]) -> None:
    for symbol in normalize_stock_symbol_list(symbols):
        touch_stock(store, symbol)


def touch_transcript_stocks(store: dict[str, Any], transcript: dict[str, Any]) -> None:
    touch_stock_symbols(store, transcript_linked_symbols(transcript))


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


def read_runtime_error_excerpt(log_path_value: str, limit: int = 600) -> str:
    log_path = Path(str(log_path_value or "").strip()) if str(log_path_value or "").strip() else None
    if not log_path or not log_path.exists():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    excerpt = text[-limit:].strip()
    return excerpt


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
            current["error"] = (
                current["error"]
                or read_runtime_error_excerpt(current.get("stderr_path", ""))
                or "进程提前退出，未找到完整的结果文件。"
            )

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


def build_monitor_report_cards(
    reports: list[dict[str, Any]],
    *,
    active_filename: str | None = None,
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    today_compact = datetime.now().strftime("%Y%m%d")
    for report in reports:
        filename = str(report.get("filename") or "")
        cards.append(
            {
                **report,
                "is_today": filename.startswith(today_compact),
                "is_active": bool(active_filename and filename == active_filename),
            }
        )
    return cards


def build_monitor_page_context(
    stock_store: dict[str, Any],
    *,
    all_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_monitor_config()
    runtime = sync_monitor_runtime()
    all_reports = all_reports if all_reports is not None else collect_reports()
    monitor_reports = [report for report in all_reports if is_monitor_report_entry(report)]
    selected_name = str(request.args.get("report") or "").strip()
    available_names = {str(report.get("filename") or "") for report in all_reports}
    default_name = ""
    if selected_name and selected_name in available_names:
        default_name = selected_name
    elif monitor_reports:
        default_name = str(monitor_reports[0].get("filename") or "")
    elif all_reports:
        default_name = str(all_reports[0].get("filename") or "")

    active_report = load_report(default_name) if default_name else None
    today_reports = collect_today_monitor_reports(monitor_reports)
    latest_report = monitor_reports[0] if monitor_reports else None
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
        "monitor_reports": build_monitor_report_cards(monitor_reports, active_filename=default_name),
        "monitor_today_reports": today_reports,
        "monitor_latest_report": latest_report,
        "monitor_active_report": active_report,
        "monitor_active_report_is_monitor": bool(active_report and is_monitor_report_entry(active_report)),
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


def normalize_signal_source_category(raw_value: Any) -> str:
    category = re.sub(r"\s+", " ", str(raw_value or "").strip())[:40]
    return category or SIGNAL_MONITOR_DEFAULT_CATEGORY


def infer_signal_source_category(raw_source: Any) -> str:
    if not isinstance(raw_source, dict):
        return SIGNAL_MONITOR_DEFAULT_CATEGORY

    haystack_parts = [
        str(raw_source.get("notes") or "").strip(),
        str(raw_source.get("display_name") or raw_source.get("name") or "").strip(),
        str(raw_source.get("query") or raw_source.get("profile_url") or "").strip(),
        str(raw_source.get("handle") or "").strip(),
    ]
    raw_text = " ".join(part for part in haystack_parts if part)
    lowered = raw_text.lower()

    category_keywords = (
        (
            "硬件监控",
            (
                "硬件",
                "半导体",
                "芯片",
                "晶圆",
                "供应链",
                "数据中心",
                "hardware",
                "semiconductor",
                "chip",
                "wafer",
                "fab",
                "gpu",
                "cpu",
                "ai 供应链",
                "ai供应链",
            ),
        ),
        (
            "苹果链监控",
            (
                "苹果链",
                "iphone",
                "ipad",
                "ios",
                "apple",
                "mac",
            ),
        ),
        (
            "汽车监控",
            (
                "汽车",
                "智能车",
                "整车",
                "tesla",
                "mobility",
                "autonomous",
                "ev",
            ),
        ),
    )

    for category_name, keywords in category_keywords:
        for keyword in keywords:
            if keyword in lowered or keyword in raw_text:
                return category_name

    return SIGNAL_MONITOR_DEFAULT_CATEGORY


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
        "category": normalize_signal_source_category(
            raw_source.get("category") or infer_signal_source_category(raw_source)
        ),
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
            current["error"] = (
                current["error"]
                or read_runtime_error_excerpt(current.get("stderr_path", ""))
                or "进程提前退出，未找到完整的信息监控结果文件。"
            )

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


def build_signal_report_cards(
    reports: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    active_filename: str | None = None,
) -> list[dict[str, Any]]:
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
                "is_active": bool(active_filename and report["filename"] == active_filename),
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


def build_signal_source_groups(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for card in cards:
        category_name = normalize_signal_source_category(card.get("category"))
        if category_name not in grouped:
            grouped[category_name] = {
                "name": category_name,
                "count": 0,
                "enabled_count": 0,
                "is_scrollable": False,
                "items": [],
            }
        group = grouped[category_name]
        group["items"].append(card)
        group["count"] += 1
        if card.get("enabled", True):
            group["enabled_count"] += 1

    groups = list(grouped.values())
    for group in groups:
        group["is_scrollable"] = len(group["items"]) >= 4
    return groups


def build_signal_monitor_page_context(
    *,
    selected_name: str | None = None,
    reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_signal_monitor_config()
    state = load_signal_monitor_state()
    runtime = sync_signal_monitor_runtime()
    reports = reports if reports is not None else collect_signal_reports()
    today_reports = collect_today_signal_reports(reports)
    latest_report = reports[0] if reports else None
    available_names = {str(report.get("filename") or "") for report in reports}
    active_name = ""
    if selected_name and selected_name in available_names:
        active_name = selected_name
    elif latest_report:
        active_name = str(latest_report.get("filename") or "")
    active_report = get_signal_report(active_name) if active_name else None
    source_cards = build_signal_source_cards(config, state)
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
        "signal_reports": build_signal_report_cards(reports, state, active_filename=active_name),
        "signal_today_reports": today_reports,
        "signal_latest_report": latest_report,
        "active_signal_report": active_report,
        "signal_sources": source_cards,
        "signal_source_groups": build_signal_source_groups(source_cards),
        "signal_status_poll_seconds": SIGNAL_MONITOR_STATUS_POLL_INTERVAL_SECONDS,
    }


def build_stablecoin_month_windows(*, end_month: str | None = None) -> list[dict[str, str]]:
    return build_month_windows_between(STABLECOIN_MONITOR_START_MONTH, end_month)


def resolve_stablecoin_cache_end_month(source: dict[str, Any]) -> str | None:
    candidates: list[str] = []
    coverage_end = str(source.get("coverage_end") or "").strip()
    if coverage_end:
        candidates.append(coverage_end)

    latest_month_snapshot = source.get("latest_month_snapshot") if isinstance(source.get("latest_month_snapshot"), dict) else {}
    latest_snapshot = source.get("latest_snapshot") if isinstance(source.get("latest_snapshot"), dict) else {}
    candidates.extend(
        [
            str(latest_month_snapshot.get("month") or "").strip(),
            str(latest_snapshot.get("month") or "").strip(),
        ]
    )

    for candidate in candidates:
        if re.fullmatch(r"\d{4}-\d{2}", candidate):
            return candidate
    return None


def format_stablecoin_point_label(value: Any, *, fallback: str = "n/a") -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return fallback

    parsed = parse_signal_monitor_datetime(raw_value)
    if parsed is not None:
        return parsed.strftime("%Y-%m-%d %H:%M")
    return raw_value


def normalize_coingecko_snapshot_timestamp(value: Any) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""

    parsed = parse_signal_monitor_datetime(raw_value)
    if parsed is not None:
        return parsed.replace(microsecond=0).isoformat()
    return raw_value


def default_stablecoin_market_cache(*, end_month: str | None = None) -> dict[str, Any]:
    month_windows = build_stablecoin_month_windows(end_month=end_month)
    coins = [
        {
            **asset,
            "latest_market_cap": 0.0,
            "latest_volume": 0.0,
            "latest_point_at": "",
            "history_latest_point_at": "",
        }
        for asset in STABLECOIN_MONITOR_ASSETS
    ]
    monthly_series = []
    for window in month_windows:
        monthly_series.append(
            {
                **window,
                "market_cap_total": 0.0,
                "volume_total": 0.0,
                "volume_available": False,
                "coins": [
                    {
                        "symbol": asset["symbol"],
                        "label": asset["label"],
                        "color": asset["color"],
                        "market_cap": 0.0,
                        "volume": 0.0,
                    }
                    for asset in STABLECOIN_MONITOR_ASSETS
                ],
            }
        )
    return {
        "updated_at": "",
        "coverage_start": month_windows[0]["label"] if month_windows else "",
        "coverage_end": month_windows[-1]["label"] if month_windows else "",
        "granularity": "monthly",
        "period_months": len(month_windows),
        "source": {
            "name": "DeFiLlama + CoinGecko",
            "url": "https://stablecoins.llama.fi/stablecoins",
            "endpoint": (
                "DeFiLlama /stablecoins + /stablecoin/{id}"
                " + CoinGecko /api/v3/coins/markets?vs_currency=usd&ids={ids}"
                " + /api/v3/coins/{id}/market_chart?vs_currency=usd&days=365&interval=daily"
            ),
        },
        "coins": coins,
        "monthly_series": monthly_series,
        "latest_snapshot": {
            "month": month_windows[-1]["label"] if month_windows else "",
            "total_market_cap": 0.0,
            "total_volume": 0.0,
            "latest_point_at": "",
            "market_cap_change_24h": 0.0,
            "market_cap_change_24h_pct": 0.0,
            "is_realtime": False,
        },
        "latest_month_snapshot": {
            "month": month_windows[-1]["label"] if month_windows else "",
            "total_market_cap": 0.0,
            "total_volume": 0.0,
            "latest_point_at": "",
        },
        "notes": (
            f"市值自 {STABLECOIN_MONITOR_START_MONTH} 起按月聚合，成交量保留近 365 天月累计；"
            "右侧独立展示当日总市值与最新 24h 成交量。当前覆盖 USDT、USDC、DAI、USDe、FDUSD、PYUSD。"
        ),
    }


def normalize_stablecoin_market_cache(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}
    baseline = default_stablecoin_market_cache(end_month=resolve_stablecoin_cache_end_month(source))

    raw_coins = source.get("coins") if isinstance(source.get("coins"), list) else []
    raw_coin_map: dict[str, dict[str, Any]] = {}
    for item in raw_coins:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if symbol:
            raw_coin_map[symbol] = item

    normalized_coins: list[dict[str, Any]] = []
    for asset in STABLECOIN_MONITOR_ASSETS:
        raw_item = raw_coin_map.get(asset["symbol"], {})
        normalized_coins.append(
            {
                **asset,
                "latest_market_cap": float(raw_item.get("latest_market_cap") or 0.0),
                "latest_volume": float(raw_item.get("latest_volume") or 0.0),
                "latest_point_at": str(raw_item.get("latest_point_at") or "").strip(),
                "history_latest_point_at": str(
                    raw_item.get("history_latest_point_at") or raw_item.get("latest_point_at") or ""
                ).strip(),
            }
        )

    raw_monthly = source.get("monthly_series") if isinstance(source.get("monthly_series"), list) else []
    raw_month_map: dict[str, dict[str, Any]] = {}
    for item in raw_monthly:
        if not isinstance(item, dict):
            continue
        month_key = str(item.get("month") or "").strip()
        if month_key:
            raw_month_map[month_key] = item

    normalized_months: list[dict[str, Any]] = []
    for window in baseline["monthly_series"]:
        raw_month = raw_month_map.get(window["month"], {})
        raw_month_coins = raw_month.get("coins") if isinstance(raw_month.get("coins"), list) else []
        raw_month_coin_map: dict[str, dict[str, Any]] = {}
        for coin_item in raw_month_coins:
            if not isinstance(coin_item, dict):
                continue
            symbol = str(coin_item.get("symbol") or "").strip().upper()
            if symbol:
                raw_month_coin_map[symbol] = coin_item

        coin_entries: list[dict[str, Any]] = []
        market_cap_total = 0.0
        volume_total = 0.0
        for asset in STABLECOIN_MONITOR_ASSETS:
            raw_coin_entry = raw_month_coin_map.get(asset["symbol"], {})
            market_cap_value = float(raw_coin_entry.get("market_cap") or 0.0)
            volume_value = float(raw_coin_entry.get("volume") or 0.0)
            market_cap_total += market_cap_value
            volume_total += volume_value
            coin_entries.append(
                {
                    "symbol": asset["symbol"],
                    "label": asset["label"],
                    "color": asset["color"],
                    "market_cap": market_cap_value,
                    "volume": volume_value,
                }
            )

        normalized_months.append(
            {
                **window,
                "market_cap_total": market_cap_total,
                "volume_total": volume_total,
                "volume_available": bool(raw_month.get("volume_available")) or volume_total > 0.0,
                "coins": coin_entries,
            }
        )

    raw_snapshot = source.get("latest_snapshot") if isinstance(source.get("latest_snapshot"), dict) else {}
    raw_month_snapshot = (
        source.get("latest_month_snapshot") if isinstance(source.get("latest_month_snapshot"), dict) else {}
    )
    latest_market_cap_total = sum(float(item.get("latest_market_cap") or 0.0) for item in normalized_coins)
    latest_volume_total = sum(float(item.get("latest_volume") or 0.0) for item in normalized_coins)
    latest_point_at = max((str(item.get("latest_point_at") or "").strip() for item in normalized_coins), default="")
    latest_history_point_at = max(
        (str(item.get("history_latest_point_at") or "").strip() for item in normalized_coins),
        default="",
    )
    latest_month = normalized_months[-1] if normalized_months else {}

    return {
        "updated_at": str(source.get("updated_at") or "").strip(),
        "coverage_start": str(source.get("coverage_start") or baseline["coverage_start"]).strip(),
        "coverage_end": str(source.get("coverage_end") or baseline["coverage_end"]).strip(),
        "granularity": "monthly",
        "period_months": int(source.get("period_months") or baseline["period_months"]),
        "source": {
            "name": str(source.get("source", {}).get("name") or baseline["source"]["name"]).strip(),
            "url": str(source.get("source", {}).get("url") or baseline["source"]["url"]).strip(),
            "endpoint": str(source.get("source", {}).get("endpoint") or baseline["source"]["endpoint"]).strip(),
        },
        "coins": normalized_coins,
        "monthly_series": normalized_months,
        "latest_snapshot": {
            "month": str(raw_snapshot.get("month") or latest_month.get("label") or "").strip(),
            "total_market_cap": float(raw_snapshot.get("total_market_cap") or latest_market_cap_total),
            "total_volume": float(raw_snapshot.get("total_volume") or latest_volume_total),
            "latest_point_at": str(raw_snapshot.get("latest_point_at") or latest_point_at).strip(),
            "market_cap_change_24h": float(raw_snapshot.get("market_cap_change_24h") or 0.0),
            "market_cap_change_24h_pct": float(raw_snapshot.get("market_cap_change_24h_pct") or 0.0),
            "is_realtime": bool(raw_snapshot.get("is_realtime")),
        },
        "latest_month_snapshot": {
            "month": str(raw_month_snapshot.get("month") or latest_month.get("label") or "").strip(),
            "total_market_cap": float(raw_month_snapshot.get("total_market_cap") or latest_month.get("market_cap_total") or 0.0),
            "total_volume": float(raw_month_snapshot.get("total_volume") or latest_month.get("volume_total") or 0.0),
            "latest_point_at": str(raw_month_snapshot.get("latest_point_at") or latest_history_point_at).strip(),
        },
        "notes": str(source.get("notes") or baseline["notes"]).strip(),
    }


def load_stablecoin_market_cache() -> dict[str, Any]:
    STABLECOIN_MONITOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STABLECOIN_MONITOR_CACHE_PATH.exists():
        cache = default_stablecoin_market_cache()
        save_stablecoin_market_cache(cache)
        return cache
    return normalize_stablecoin_market_cache(load_json(STABLECOIN_MONITOR_CACHE_PATH))


def save_stablecoin_market_cache(cache: dict[str, Any]) -> None:
    normalized = normalize_stablecoin_market_cache(cache)
    STABLECOIN_MONITOR_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STABLECOIN_MONITOR_CACHE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(STABLECOIN_MONITOR_CACHE_PATH)


def normalize_stablecoin_monitor_runtime(raw: Any) -> dict[str, Any]:
    source = raw if isinstance(raw, dict) else {}

    def normalize_runtime_text(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if re.fullmatch(r"[?？\uFFFD\s]+", text):
            return ""
        return text

    return {
        "status": str(source.get("status") or "idle").strip() or "idle",
        "started_at": str(source.get("started_at") or "").strip(),
        "finished_at": str(source.get("finished_at") or "").strip(),
        "reason": str(source.get("reason") or "").strip(),
        "message": normalize_runtime_text(source.get("message")),
        "error": normalize_runtime_text(source.get("error")),
    }


def load_stablecoin_monitor_runtime() -> dict[str, Any]:
    STABLECOIN_MONITOR_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not STABLECOIN_MONITOR_RUNTIME_PATH.exists():
        runtime = normalize_stablecoin_monitor_runtime({})
        save_stablecoin_monitor_runtime(runtime)
        return runtime
    return normalize_stablecoin_monitor_runtime(load_json(STABLECOIN_MONITOR_RUNTIME_PATH))


def save_stablecoin_monitor_runtime(runtime: dict[str, Any]) -> None:
    normalized = normalize_stablecoin_monitor_runtime(runtime)
    STABLECOIN_MONITOR_RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STABLECOIN_MONITOR_RUNTIME_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(STABLECOIN_MONITOR_RUNTIME_PATH)


def stablecoin_market_cache_is_stale(cache: dict[str, Any]) -> bool:
    updated_at = parse_signal_monitor_datetime(cache.get("updated_at"))
    if updated_at is None:
        return True
    return datetime.now() - updated_at >= timedelta(hours=STABLECOIN_MONITOR_REFRESH_INTERVAL_HOURS)


def throttle_coingecko_requests() -> None:
    global COINGECKO_LAST_REQUEST_AT

    with COINGECKO_REQUEST_LOCK:
        now_value = time.monotonic()
        wait_seconds = COINGECKO_MIN_REQUEST_INTERVAL_SECONDS - (now_value - COINGECKO_LAST_REQUEST_AT)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
            now_value = time.monotonic()
        COINGECKO_LAST_REQUEST_AT = now_value


def fetch_coingecko_market_chart(coin_id: str) -> dict[str, Any]:
    url = f"{COINGECKO_API_BASE_URL}/coins/{coin_id}/market_chart"
    params = {
        "vs_currency": "usd",
        "days": str(STABLECOIN_MONITOR_DAY_RANGE),
        "interval": "daily",
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            throttle_coingecko_requests()
            response = requests.get(
                url,
                params=params,
                headers=COINGECKO_REQUEST_HEADERS,
                timeout=40,
            )
            if response.status_code == 429:
                retry_after = 12 + (attempt * 8)
                time.sleep(retry_after)
                raise RuntimeError("CoinGecko 当前限流，请稍后再试。")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("CoinGecko 返回了无法识别的数据结构。")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
    raise RuntimeError(f"抓取 {coin_id} 历史行情失败：{last_error}")


def fetch_coingecko_market_snapshot(coin_ids: list[str]) -> list[dict[str, Any]]:
    url = f"{COINGECKO_API_BASE_URL}/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": ",".join(coin_ids),
        "per_page": str(max(len(coin_ids), 10)),
        "page": "1",
        "sparkline": "false",
    }
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            throttle_coingecko_requests()
            response = requests.get(
                url,
                params=params,
                headers=COINGECKO_REQUEST_HEADERS,
                timeout=40,
            )
            if response.status_code == 429:
                retry_after = 12 + (attempt * 8)
                time.sleep(retry_after)
                raise RuntimeError("CoinGecko 当前限流，请稍后再试。")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("CoinGecko 返回了无法识别的实时快照结构。")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
    raise RuntimeError(f"抓取稳定币实时快照失败：{last_error}")


def fetch_defillama_stablecoins_index() -> list[dict[str, Any]]:
    url = f"{DEFILLAMA_STABLECOINS_API_BASE_URL}/stablecoins"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(url, params={"includePrices": "true"}, timeout=40)
            response.raise_for_status()
            payload = response.json()
            pegged_assets = payload.get("peggedAssets") if isinstance(payload, dict) else None
            if not isinstance(pegged_assets, list):
                raise RuntimeError("DeFiLlama 返回了无法识别的稳定币列表结构。")
            return pegged_assets
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
    raise RuntimeError(f"抓取 DeFiLlama 稳定币列表失败：{last_error}")


def fetch_defillama_stablecoin_detail(stablecoin_id: str) -> dict[str, Any]:
    url = f"{DEFILLAMA_STABLECOINS_API_BASE_URL}/stablecoin/{stablecoin_id}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(url, timeout=40)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("DeFiLlama 返回了无法识别的稳定币详情结构。")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt * 2)
                continue
    raise RuntimeError(f"抓取 DeFiLlama 稳定币详情失败：{last_error}")


def summarize_stablecoin_market_chart(
    payload: dict[str, Any],
    *,
    month_windows: list[dict[str, str]],
) -> dict[str, Any]:
    month_keys = [item["month"] for item in month_windows]
    month_key_set = set(month_keys)
    market_caps_by_month: dict[str, list[float]] = defaultdict(list)
    volumes_by_month: dict[str, list[float]] = defaultdict(list)
    latest_market_cap = 0.0
    latest_volume = 0.0
    latest_point_at = ""

    for raw_point in payload.get("market_caps", []) if isinstance(payload.get("market_caps"), list) else []:
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
            continue
        try:
            point_at = datetime.utcfromtimestamp(float(raw_point[0]) / 1000.0)
            value = max(float(raw_point[1]), 0.0)
        except (TypeError, ValueError, OSError):
            continue
        month_key = f"{point_at.year:04d}-{point_at.month:02d}"
        if month_key in month_key_set:
            market_caps_by_month[month_key].append(value)
        if point_at.isoformat() >= latest_point_at:
            latest_point_at = point_at.date().isoformat()
            latest_market_cap = value

    for raw_point in payload.get("total_volumes", []) if isinstance(payload.get("total_volumes"), list) else []:
        if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
            continue
        try:
            point_at = datetime.utcfromtimestamp(float(raw_point[0]) / 1000.0)
            value = max(float(raw_point[1]), 0.0)
        except (TypeError, ValueError, OSError):
            continue
        month_key = f"{point_at.year:04d}-{point_at.month:02d}"
        if month_key in month_key_set:
            volumes_by_month[month_key].append(value)
        if point_at.date().isoformat() >= latest_point_at:
            latest_point_at = point_at.date().isoformat()
            latest_volume = value

    monthly_rollup: dict[str, dict[str, float]] = {}
    for month_key in month_keys:
        month_market_caps = market_caps_by_month.get(month_key, [])
        month_volumes = volumes_by_month.get(month_key, [])
        monthly_rollup[month_key] = {
            "market_cap": (sum(month_market_caps) / len(month_market_caps)) if month_market_caps else 0.0,
            "market_cap_available": bool(month_market_caps),
            "volume": sum(month_volumes) if month_volumes else 0.0,
            "volume_available": bool(month_volumes),
        }

    return {
        "monthly": monthly_rollup,
        "latest_market_cap": latest_market_cap,
        "latest_volume": latest_volume,
        "latest_point_at": latest_point_at,
    }


def summarize_defillama_stablecoin_history(
    payload: dict[str, Any],
    *,
    month_windows: list[dict[str, str]],
) -> dict[str, Any]:
    month_keys = [item["month"] for item in month_windows]
    month_key_set = set(month_keys)
    market_caps_by_month: dict[str, list[float]] = defaultdict(list)
    latest_market_cap = 0.0
    latest_point_at = ""

    for raw_point in payload.get("tokens", []) if isinstance(payload.get("tokens"), list) else []:
        if not isinstance(raw_point, dict):
            continue
        try:
            point_at = datetime.utcfromtimestamp(int(raw_point.get("date") or 0))
            value = max(float((raw_point.get("circulating") or {}).get("peggedUSD") or 0.0), 0.0)
        except (TypeError, ValueError, OSError):
            continue
        month_key = f"{point_at.year:04d}-{point_at.month:02d}"
        if month_key in month_key_set:
            market_caps_by_month[month_key].append(value)
        point_label = point_at.date().isoformat()
        if point_label >= latest_point_at:
            latest_point_at = point_label
            latest_market_cap = value

    monthly_rollup: dict[str, dict[str, float | bool]] = {}
    for month_key in month_keys:
        month_market_caps = market_caps_by_month.get(month_key, [])
        monthly_rollup[month_key] = {
            "market_cap": (sum(month_market_caps) / len(month_market_caps)) if month_market_caps else 0.0,
            "market_cap_available": bool(month_market_caps),
        }

    return {
        "monthly": monthly_rollup,
        "latest_market_cap": latest_market_cap,
        "latest_point_at": latest_point_at,
    }


def summarize_cached_stablecoin_volume_history(
    cache: dict[str, Any],
    *,
    coin_symbol: str,
    month_windows: list[dict[str, str]],
) -> dict[str, Any]:
    month_keys = [item["month"] for item in month_windows]
    monthly_rollup: dict[str, dict[str, float | bool]] = {
        month_key: {
            "market_cap": 0.0,
            "market_cap_available": False,
            "volume": 0.0,
            "volume_available": False,
        }
        for month_key in month_keys
    }
    latest_volume = 0.0
    latest_point_at = ""
    target_symbol = str(coin_symbol or "").strip().upper()

    monthly_series = cache.get("monthly_series") if isinstance(cache.get("monthly_series"), list) else []
    for month in monthly_series:
        if not isinstance(month, dict):
            continue
        month_key = str(month.get("month") or month.get("label") or "").strip()
        if month_key not in monthly_rollup:
            continue

        coin_entries = month.get("coins") if isinstance(month.get("coins"), list) else []
        for coin_entry in coin_entries:
            if not isinstance(coin_entry, dict):
                continue
            symbol = str(coin_entry.get("symbol") or "").strip().upper()
            if symbol != target_symbol:
                continue

            volume_value = float(coin_entry.get("volume") or 0.0)
            monthly_rollup[month_key] = {
                "market_cap": 0.0,
                "market_cap_available": False,
                "volume": volume_value,
                "volume_available": bool(month.get("volume_available")) or volume_value > 0.0,
            }
            if month_key >= latest_point_at:
                latest_point_at = month_key
                latest_volume = volume_value
            break

    return {
        "monthly": monthly_rollup,
        "latest_market_cap": 0.0,
        "latest_volume": latest_volume,
        "latest_point_at": latest_point_at,
    }


def build_stablecoin_market_dataset() -> dict[str, Any]:
    market_cap_payload_map: dict[str, dict[str, Any]] = {}
    latest_history_point_dt: datetime | None = None
    previous_cache = load_stablecoin_market_cache()

    for asset in STABLECOIN_MONITOR_ASSETS:
        payload = fetch_defillama_stablecoin_detail(str(asset["llama_id"]))
        market_cap_payload_map[asset["id"]] = payload
        summary = summarize_defillama_stablecoin_history(payload, month_windows=[])
        latest_point_dt = parse_iso_date_value(summary.get("latest_point_at"))
        if latest_point_dt is not None and (latest_history_point_dt is None or latest_point_dt > latest_history_point_dt):
            latest_history_point_dt = latest_point_dt

    latest_history_month = latest_history_point_dt.strftime("%Y-%m") if latest_history_point_dt is not None else None
    month_windows = build_stablecoin_month_windows(end_month=latest_history_month)
    monthly_series_map = {
        window["month"]: {
            **window,
            "market_cap_total": 0.0,
            "volume_total": 0.0,
            "volume_available": False,
            "coins": [],
        }
        for window in month_windows
    }
    coins: list[dict[str, Any]] = []
    defillama_snapshot_map: dict[str, dict[str, Any]] = {}
    try:
        defillama_records = fetch_defillama_stablecoins_index()
        for item in defillama_records:
            if not isinstance(item, dict):
                continue
            coin_id = str(item.get("gecko_id") or "").strip()
            if coin_id:
                defillama_snapshot_map[coin_id] = item
    except Exception:
        defillama_snapshot_map = {}
    snapshot_map: dict[str, dict[str, Any]] = {}
    try:
        snapshot_records = fetch_coingecko_market_snapshot([asset["id"] for asset in STABLECOIN_MONITOR_ASSETS])
        for item in snapshot_records:
            if not isinstance(item, dict):
                continue
            coin_id = str(item.get("id") or "").strip()
            if coin_id:
                snapshot_map[coin_id] = item
    except Exception:
        snapshot_map = {}

    latest_snapshot_point_at = ""
    latest_snapshot_point_dt: datetime | None = None
    latest_market_cap_total = 0.0
    latest_volume_total = 0.0
    latest_market_cap_change_24h = 0.0

    for asset in STABLECOIN_MONITOR_ASSETS:
        market_cap_payload = market_cap_payload_map[asset["id"]]
        market_cap_summary = summarize_defillama_stablecoin_history(market_cap_payload, month_windows=month_windows)
        try:
            volume_payload = fetch_coingecko_market_chart(asset["id"])
            volume_summary = summarize_stablecoin_market_chart(volume_payload, month_windows=month_windows)
        except Exception:
            volume_summary = summarize_cached_stablecoin_volume_history(
                previous_cache,
                coin_symbol=str(asset["symbol"]),
                month_windows=month_windows,
            )
        market_cap_snapshot = defillama_snapshot_map.get(asset["id"], {})
        volume_snapshot = snapshot_map.get(asset["id"], {})

        latest_market_cap = float(
            (market_cap_snapshot.get("circulating") or {}).get("peggedUSD")
            or market_cap_summary["latest_market_cap"]
            or 0.0
        )
        previous_market_cap = float((market_cap_snapshot.get("circulatingPrevDay") or {}).get("peggedUSD") or 0.0)
        latest_volume = float(volume_snapshot.get("total_volume") or volume_summary["latest_volume"] or 0.0)
        latest_point_at = normalize_coingecko_snapshot_timestamp(volume_snapshot.get("last_updated")) or str(
            market_cap_summary["latest_point_at"] or volume_summary["latest_point_at"] or ""
        )
        latest_point_dt = parse_signal_monitor_datetime(latest_point_at) or parse_iso_date_value(latest_point_at)
        if latest_point_dt is not None and (latest_snapshot_point_dt is None or latest_point_dt > latest_snapshot_point_dt):
            latest_snapshot_point_dt = latest_point_dt
            latest_snapshot_point_at = latest_point_at

        latest_market_cap_total += latest_market_cap
        latest_volume_total += latest_volume
        if previous_market_cap > 0:
            latest_market_cap_change_24h += latest_market_cap - previous_market_cap
        coins.append(
            {
                **asset,
                "latest_market_cap": latest_market_cap,
                "latest_volume": latest_volume,
                "latest_point_at": latest_point_at,
                "history_latest_point_at": str(market_cap_summary["latest_point_at"] or "").strip(),
            }
        )
        for window in month_windows:
            market_cap_month_values = market_cap_summary["monthly"].get(window["month"], {})
            volume_month_values = volume_summary["monthly"].get(window["month"], {})
            market_cap_value = float(market_cap_month_values.get("market_cap") or 0.0)
            volume_value = float(volume_month_values.get("volume") or 0.0)
            volume_available = bool(volume_month_values.get("volume_available"))
            bucket = monthly_series_map[window["month"]]
            bucket["market_cap_total"] += market_cap_value
            bucket["volume_total"] += volume_value
            bucket["volume_available"] = bool(bucket.get("volume_available")) or volume_available
            bucket["coins"].append(
                {
                    "symbol": asset["symbol"],
                    "label": asset["label"],
                    "color": asset["color"],
                    "market_cap": market_cap_value,
                    "volume": volume_value,
                }
            )

    monthly_series = [monthly_series_map[window["month"]] for window in month_windows]
    latest_month_snapshot = monthly_series[-1] if monthly_series else {"label": "", "market_cap_total": 0.0, "volume_total": 0.0}
    previous_market_cap_total = latest_market_cap_total - latest_market_cap_change_24h
    return {
        "updated_at": now_iso(),
        "coverage_start": month_windows[0]["label"] if month_windows else "",
        "coverage_end": month_windows[-1]["label"] if month_windows else "",
        "granularity": "monthly",
        "period_months": len(month_windows),
        "source": {
            "name": "DeFiLlama + CoinGecko",
            "url": "https://stablecoins.llama.fi/stablecoins",
            "endpoint": (
                "DeFiLlama /stablecoins + /stablecoin/{id}"
                " + CoinGecko /api/v3/coins/markets?vs_currency=usd&ids={ids}"
                " + /api/v3/coins/{id}/market_chart?vs_currency=usd&days=365&interval=daily"
            ),
        },
        "coins": coins,
        "monthly_series": monthly_series,
        "latest_snapshot": {
            "month": str(latest_month_snapshot.get("label") or ""),
            "total_market_cap": latest_market_cap_total,
            "total_volume": latest_volume_total,
            "latest_point_at": latest_snapshot_point_at,
            "market_cap_change_24h": latest_market_cap_change_24h,
            "market_cap_change_24h_pct": calculate_percent_change(latest_market_cap_total, previous_market_cap_total) or 0.0,
            "is_realtime": bool(snapshot_map),
        },
        "latest_month_snapshot": {
            "month": str(latest_month_snapshot.get("label") or ""),
            "total_market_cap": float(latest_month_snapshot.get("market_cap_total") or 0.0),
            "total_volume": float(latest_month_snapshot.get("volume_total") or 0.0),
            "latest_point_at": latest_history_point_dt.date().isoformat() if latest_history_point_dt is not None else "",
        },
        "notes": (
            f"市值自 {STABLECOIN_MONITOR_START_MONTH} 起按月聚合，成交量保留近 365 天月累计；"
            "右侧独立展示当日总市值与最新 24h 成交量。当前覆盖 USDT、USDC、DAI、USDe、FDUSD、PYUSD。"
        ),
    }


def run_stablecoin_market_refresh(reason: str, started_at: str | None = None) -> None:
    global STABLECOIN_MONITOR_ACTIVE_THREAD

    runtime = {
        "status": "running",
        "started_at": started_at or now_iso(),
        "finished_at": "",
        "reason": reason,
        "message": f"正在抓取自 {STABLECOIN_MONITOR_START_MONTH} 以来的稳定币历史数据。",
        "error": "",
    }
    save_stablecoin_monitor_runtime(runtime)

    try:
        dataset = build_stablecoin_market_dataset()
        save_stablecoin_market_cache(dataset)
        runtime = {
            "status": "completed",
            "started_at": runtime["started_at"],
            "finished_at": now_iso(),
            "reason": reason,
            "message": "稳定币数据已刷新，图表和摘要已同步更新。",
            "error": "",
        }
    except Exception as exc:
        runtime = {
            "status": "failed",
            "started_at": runtime["started_at"],
            "finished_at": now_iso(),
            "reason": reason,
            "message": "",
            "error": str(exc),
        }
    finally:
        save_stablecoin_monitor_runtime(runtime)
        with STABLECOIN_MONITOR_LOCK:
            STABLECOIN_MONITOR_ACTIVE_THREAD = None


def sync_stablecoin_monitor_runtime() -> dict[str, Any]:
    runtime = load_stablecoin_monitor_runtime()
    if runtime["status"] != "running":
        return runtime

    active_thread = STABLECOIN_MONITOR_ACTIVE_THREAD
    if active_thread is not None and active_thread.is_alive():
        return runtime

    runtime["status"] = "failed"
    runtime["finished_at"] = runtime["finished_at"] or now_iso()
    runtime["error"] = runtime["error"] or "稳定币刷新线程已经结束，但没有留下完整结果。"
    save_stablecoin_monitor_runtime(runtime)
    return runtime


def start_stablecoin_market_refresh(reason: str) -> dict[str, Any]:
    global STABLECOIN_MONITOR_ACTIVE_THREAD

    with STABLECOIN_MONITOR_LOCK:
        runtime = sync_stablecoin_monitor_runtime()
        if runtime["status"] == "running":
            return runtime

        started_at = now_iso()
        runtime = {
            "status": "running",
            "started_at": started_at,
            "finished_at": "",
            "reason": reason,
            "message": f"正在抓取自 {STABLECOIN_MONITOR_START_MONTH} 以来的稳定币历史数据。",
            "error": "",
        }
        save_stablecoin_monitor_runtime(runtime)

        worker = threading.Thread(
            target=run_stablecoin_market_refresh,
            args=(reason, started_at),
            daemon=True,
            name="stablecoin-monitor-refresh",
        )
        STABLECOIN_MONITOR_ACTIVE_THREAD = worker
        worker.start()
        return runtime


def maybe_start_stablecoin_monitor_scheduler() -> None:
    global STABLECOIN_MONITOR_SCHEDULER_STARTED, STABLECOIN_MONITOR_SCHEDULER_THREAD

    with STABLECOIN_MONITOR_LOCK:
        if STABLECOIN_MONITOR_SCHEDULER_STARTED:
            return

        def scheduler_loop() -> None:
            while True:
                try:
                    cache = load_stablecoin_market_cache()
                    runtime = sync_stablecoin_monitor_runtime()
                    if runtime["status"] != "running" and stablecoin_market_cache_is_stale(cache):
                        start_stablecoin_market_refresh("scheduler")
                except Exception:
                    pass
                time.sleep(max(120, STABLECOIN_MONITOR_SCHEDULER_SLEEP_SECONDS))

        worker = threading.Thread(
            target=scheduler_loop,
            daemon=True,
            name="stablecoin-monitor-scheduler",
        )
        STABLECOIN_MONITOR_SCHEDULER_THREAD = worker
        STABLECOIN_MONITOR_SCHEDULER_STARTED = True
        worker.start()


def ensure_stablecoin_market_cache_ready() -> tuple[dict[str, Any], dict[str, Any]]:
    maybe_start_stablecoin_monitor_scheduler()
    cache = load_stablecoin_market_cache()
    runtime = sync_stablecoin_monitor_runtime()
    if not cache.get("updated_at") and runtime["status"] != "running":
        run_stablecoin_market_refresh("bootstrap")
        cache = load_stablecoin_market_cache()
        runtime = sync_stablecoin_monitor_runtime()
    elif stablecoin_market_cache_is_stale(cache) and runtime["status"] != "running":
        runtime = start_stablecoin_market_refresh("stale_auto")
    return cache, runtime


def calculate_percent_change(current_value: float, previous_value: float) -> float | None:
    if previous_value <= 0:
        return None
    return ((current_value - previous_value) / previous_value) * 100.0


def build_stablecoin_chart_payload(
    monthly_series: list[dict[str, Any]],
    *,
    metric_key: str,
    metric_total_key: str,
    title: str,
    subtitle: str,
    chart_key: str,
) -> dict[str, Any]:
    bars: list[dict[str, Any]] = []
    max_total = 0.0
    for month in monthly_series:
        total_value = float(month.get(metric_total_key) or 0.0)
        max_total = max(max_total, total_value)
        series = []
        for coin in month.get("coins", []):
            value = float(coin.get(metric_key) or 0.0)
            series.append(
                {
                    "symbol": str(coin.get("symbol") or ""),
                    "label": str(coin.get("label") or ""),
                    "color": str(coin.get("color") or "#6b86b8"),
                    "value": value,
                    "value_label": format_compact_currency(value),
                }
            )
        bars.append(
            {
                "label": str(month.get("short_label") or month.get("label") or ""),
                "month": str(month.get("label") or ""),
                "total_value": total_value,
                "total_label": format_compact_currency(total_value),
                "series": series,
            }
        )

    return {
        "title": title,
        "subtitle": subtitle,
        "bars": bars,
        "max_total": max_total,
        "chart_key": chart_key,
    }


def build_stablecoin_data_monitor_context() -> dict[str, Any]:
    cache, runtime = ensure_stablecoin_market_cache_ready()
    monthly_series = cache.get("monthly_series", []) if isinstance(cache.get("monthly_series"), list) else []
    coins = cache.get("coins", []) if isinstance(cache.get("coins"), list) else []
    latest_snapshot = cache.get("latest_snapshot", {}) if isinstance(cache.get("latest_snapshot"), dict) else {}
    latest_month_snapshot = (
        cache.get("latest_month_snapshot") if isinstance(cache.get("latest_month_snapshot"), dict) else {}
    )
    latest_market_cap_total = float(latest_snapshot.get("total_market_cap") or 0.0)
    latest_volume_total = float(latest_snapshot.get("total_volume") or 0.0)
    earliest_month = monthly_series[0] if monthly_series else {}
    latest_month = monthly_series[-1] if monthly_series else {}
    volume_months = [month for month in monthly_series if bool(month.get("volume_available"))]
    earliest_volume_month = volume_months[0] if volume_months else {}
    latest_volume_month = volume_months[-1] if volume_months else {}
    latest_month_label = str(latest_month_snapshot.get("month") or latest_month.get("label") or "").strip()
    latest_month_point_at = str(latest_month_snapshot.get("latest_point_at") or "").strip()
    market_cap_change_pct = calculate_percent_change(
        float(latest_month.get("market_cap_total") or 0.0),
        float(earliest_month.get("market_cap_total") or 0.0),
    )
    volume_change_pct = calculate_percent_change(
        float(latest_volume_month.get("volume_total") or 0.0),
        float(earliest_volume_month.get("volume_total") or 0.0),
    )

    monthly_coin_history: dict[str, list[dict[str, float]]] = {asset["symbol"]: [] for asset in STABLECOIN_MONITOR_ASSETS}
    for month in monthly_series:
        for coin in month.get("coins", []):
            symbol = str(coin.get("symbol") or "").strip().upper()
            if symbol in monthly_coin_history:
                monthly_coin_history[symbol].append(
                    {
                        "market_cap": float(coin.get("market_cap") or 0.0),
                        "volume": float(coin.get("volume") or 0.0),
                    }
                )

    sorted_coins = sorted(coins, key=lambda item: float(item.get("latest_market_cap") or 0.0), reverse=True)
    coin_cards: list[dict[str, Any]] = []
    for coin in sorted_coins:
        symbol = str(coin.get("symbol") or "")
        history = monthly_coin_history.get(symbol, [])
        first_market_cap = float(history[0]["market_cap"]) if history else 0.0
        last_market_cap = float(history[-1]["market_cap"]) if history else 0.0
        share = ((float(coin.get("latest_market_cap") or 0.0) / latest_market_cap_total) * 100.0) if latest_market_cap_total > 0 else 0.0
        coin_cards.append(
            {
                **coin,
                "latest_market_cap_label": format_compact_currency(coin.get("latest_market_cap") or 0.0),
                "latest_volume_label": format_compact_currency(coin.get("latest_volume") or 0.0),
                "share_label": f"{share:.1f}%",
                "market_cap_change_label": format_signed_percent(
                    calculate_percent_change(last_market_cap, first_market_cap)
                ),
                "latest_point_label": format_stablecoin_point_label(coin.get("latest_point_at")),
            }
        )

    monthly_rows: list[dict[str, Any]] = []
    for month in reversed(monthly_series):
        total_market_cap = float(month.get("market_cap_total") or 0.0)
        leaders = sorted(
            month.get("coins", []),
            key=lambda item: float(item.get("market_cap") or 0.0),
            reverse=True,
        )[:3]
        monthly_rows.append(
            {
                **month,
                "market_cap_total_label": format_compact_currency(total_market_cap),
                "volume_total_label": (
                    format_compact_currency(month.get("volume_total") or 0.0)
                    if month.get("volume_available")
                    else "n/a"
                ),
                "leaders": [
                    {
                        **coin,
                        "market_cap_label": format_compact_currency(coin.get("market_cap") or 0.0),
                        "share_label": (
                            f"{((float(coin.get('market_cap') or 0.0) / total_market_cap) * 100.0):.1f}%"
                            if total_market_cap > 0
                            else "0.0%"
                        ),
                    }
                    for coin in leaders
                ],
            }
        )

    latest_month_point_dt = parse_iso_date_value(latest_month_point_at)
    latest_month_days_included = 0
    if latest_month_point_dt is not None and latest_month_label == latest_month_point_dt.strftime("%Y-%m"):
        latest_month_days_included = latest_month_point_dt.day

    if latest_month_label:
        stablecoin_monthly_latest_label = f"{latest_month_label} 平均"
    else:
        stablecoin_monthly_latest_label = "n/a"

    if latest_month_label and latest_month_days_included > 0:
        stablecoin_monthly_latest_caption = (
            f"左侧连续月份当前滚动到 {latest_month_label}，已纳入本月前 {latest_month_days_included} 天的日度数据。"
        )
    elif latest_month_label and latest_month_point_at:
        stablecoin_monthly_latest_caption = f"左侧连续月份当前滚动到 {latest_month_label}，截至 {latest_month_point_at}。"
    else:
        stablecoin_monthly_latest_caption = "左侧连续月份会沿最新有数据的月份继续向前滚动。"

    realtime_vs_month_pct = calculate_percent_change(
        latest_market_cap_total,
        float(latest_month_snapshot.get("total_market_cap") or latest_month.get("market_cap_total") or 0.0),
    )
    realtime_is_live = bool(latest_snapshot.get("is_realtime"))
    realtime_mode_label = "当日快照" if realtime_is_live else "最近日度快照"
    realtime_point_label = format_stablecoin_point_label(latest_snapshot.get("latest_point_at"))
    realtime_caption = "和左侧月均序列分开看，方便月初直接对照当下状态。"
    if latest_month_label and realtime_vs_month_pct is not None:
        realtime_caption = (
            f"相对 {latest_month_label} 月均 {format_signed_percent(realtime_vs_month_pct)}，和左侧月均序列分开看更直观。"
        )

    market_cap_coverage_label = f"{cache.get('coverage_start') or STABLECOIN_MONITOR_START_MONTH} 至 {cache.get('coverage_end') or '-'}"
    volume_coverage_label = (
        f"{earliest_volume_month.get('label') or '-'} 至 {latest_volume_month.get('label') or '-'}"
        if volume_months
        else "近 365 天数据暂不可用"
    )
    combined_coverage_label = f"市值 {market_cap_coverage_label}；成交量 {volume_coverage_label}"

    return {
        "stablecoin_cache": cache,
        "stablecoin_runtime": {
            **runtime,
            "status_label": monitor_runtime_status_label(runtime["status"]),
            "status_tone": monitor_runtime_status_tone(runtime["status"]),
            "is_running": runtime["status"] == "running",
            "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未刷新",
            "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未刷新",
        },
        "stablecoin_status_poll_seconds": STABLECOIN_MONITOR_STATUS_POLL_INTERVAL_SECONDS,
        "stablecoin_is_stale": stablecoin_market_cache_is_stale(cache),
        "stablecoin_tracked_count": len(coins),
        "stablecoin_last_updated_label": format_iso_timestamp(cache.get("updated_at")) if cache.get("updated_at") else "尚未抓取",
        "stablecoin_latest_market_cap_label": format_compact_currency(latest_market_cap_total),
        "stablecoin_latest_volume_label": format_compact_currency(latest_volume_total),
        "stablecoin_market_cap_change_label": format_signed_percent(market_cap_change_pct),
        "stablecoin_volume_change_label": format_signed_percent(volume_change_pct),
        "stablecoin_market_cap_window_label": f"自 {STABLECOIN_MONITOR_START_MONTH}",
        "stablecoin_volume_window_label": "近 365 天",
        "stablecoin_market_cap_coverage_label": market_cap_coverage_label,
        "stablecoin_volume_coverage_label": volume_coverage_label,
        "stablecoin_coverage_label": combined_coverage_label,
        "stablecoin_latest_point_label": realtime_point_label,
        "stablecoin_monthly_latest_label": stablecoin_monthly_latest_label,
        "stablecoin_monthly_latest_point_label": latest_month_point_at or "n/a",
        "stablecoin_monthly_latest_caption": stablecoin_monthly_latest_caption,
        "stablecoin_realtime_mode_label": realtime_mode_label,
        "stablecoin_realtime_market_cap_label": format_compact_currency(latest_market_cap_total),
        "stablecoin_realtime_volume_label": format_compact_currency(latest_volume_total),
        "stablecoin_realtime_point_label": realtime_point_label,
        "stablecoin_realtime_change_label": format_signed_percent(latest_snapshot.get("market_cap_change_24h_pct")),
        "stablecoin_realtime_vs_month_label": format_signed_percent(realtime_vs_month_pct),
        "stablecoin_realtime_caption": realtime_caption,
        "stablecoin_realtime_is_live": realtime_is_live,
        "stablecoin_coins": coin_cards,
        "stablecoin_source_name": str(cache.get("source", {}).get("name") or "CoinGecko"),
        "stablecoin_source_url": str(cache.get("source", {}).get("url") or "https://www.coingecko.com/"),
        "stablecoin_source_endpoint": str(cache.get("source", {}).get("endpoint") or ""),
        "stablecoin_notes": str(cache.get("notes") or ""),
        "stablecoin_market_cap_chart": build_stablecoin_chart_payload(
            monthly_series,
            metric_key="market_cap",
            metric_total_key="market_cap_total",
            title="月均市值",
            subtitle=f"按月汇总 6 种主流稳定币自 {STABLECOIN_MONITOR_START_MONTH} 以来的平均市值，观察份额与绝对规模的变化。",
            chart_key="market-cap",
        ),
        "stablecoin_volume_chart": build_stablecoin_chart_payload(
            volume_months,
            metric_key="volume",
            metric_total_key="volume_total",
            title="月累计成交量",
            subtitle="按月累计日度成交量，追踪链上与场内稳定币交易活跃度；当前受公开接口限制，覆盖近 365 天。",
            chart_key="volume",
        ),
        "stablecoin_monthly_rows": monthly_rows,
        "stablecoin_auto_refresh_label": f"应用运行时每 {STABLECOIN_MONITOR_REFRESH_INTERVAL_HOURS} 小时自动刷新一次",
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
        "earnings": normalize_stock_earnings_info({}),
        "earnings_calls": [],
        "earnings_call_sync": normalize_stock_earnings_call_sync_info({}),
        "notes": [],
        "files": [],
    }


def normalize_stock_earnings_call_entry(raw_call: Any, *, trust_saved_html: bool = False) -> dict[str, Any] | None:
    if not isinstance(raw_call, dict):
        return None

    raw_html = str(raw_call.get("transcript_html") or "").strip()
    transcript_text = trim_note_content(str(raw_call.get("transcript_text") or "").strip())
    transcript_html = raw_html if trust_saved_html and raw_html else (sanitize_note_html(raw_html) if raw_html else "")
    if transcript_html and not transcript_text:
        transcript_text = trim_note_content(note_html_to_text(transcript_html))
    if transcript_text and not transcript_html:
        transcript_html = plain_text_to_html(transcript_text)
    if not transcript_text and not transcript_html:
        return None

    title = str(raw_call.get("title") or raw_call.get("original_title") or "").strip()[:200]
    if not title:
        return None

    summary_text = trim_note_content(str(raw_call.get("summary_text") or "").strip())
    saved_summary_excerpt = str(raw_call.get("summary_excerpt") or "").strip()
    summary_excerpt = (
        saved_summary_excerpt[:240]
        if trust_saved_html and saved_summary_excerpt
        else summarize_text_block(summary_text or transcript_text)
    )
    try:
        word_count = max(0, int(raw_call.get("word_count") or 0))
    except (TypeError, ValueError):
        word_count = 0
    try:
        speaker_turn_count = max(0, int(raw_call.get("speaker_turn_count") or 0))
    except (TypeError, ValueError):
        speaker_turn_count = 0
    try:
        fiscal_year = int(raw_call.get("fiscal_year") or 0)
    except (TypeError, ValueError):
        fiscal_year = 0
    try:
        fiscal_quarter = int(raw_call.get("fiscal_quarter") or 0)
    except (TypeError, ValueError):
        fiscal_quarter = 0

    return {
        "id": str(raw_call.get("id") or uuid.uuid4().hex[:12]).strip()[:40],
        "title": title,
        "original_title": str(raw_call.get("original_title") or title).strip()[:220],
        "source_label": str(raw_call.get("source_label") or "").strip()[:80],
        "source_short_label": str(raw_call.get("source_short_label") or "").strip()[:40],
        "source_url": str(raw_call.get("source_url") or "").strip()[:600],
        "source_query_label": str(raw_call.get("source_query_label") or "").strip()[:120],
        "published_at": str(raw_call.get("published_at") or "").strip()[:40],
        "published_date": normalize_date_field(raw_call.get("published_date")),
        "call_date": normalize_date_field(raw_call.get("call_date")),
        "call_date_label": str(raw_call.get("call_date_label") or "").strip()[:80],
        "summary_text": summary_text,
        "summary_excerpt": summary_excerpt,
        "transcript_html": transcript_html,
        "transcript_text": transcript_text,
        "word_count": word_count,
        "speaker_turn_count": speaker_turn_count,
        "has_question_section": bool(raw_call.get("has_question_section")),
        "is_complete": bool(raw_call.get("is_complete", True)),
        "quality_notes": [
            str(item).strip()[:120]
            for item in raw_call.get("quality_notes", [])
            if str(item).strip()
        ],
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
    }


def normalize_note(raw_note: Any, *, trust_saved_html: bool = False) -> dict[str, Any] | None:
    if not isinstance(raw_note, dict):
        return None

    raw_html = str(raw_note.get("content_html") or "").strip()
    legacy_content = str(raw_note.get("content") or "").strip()
    content_html = (
        raw_html
        if trust_saved_html and raw_html
        else (sanitize_note_html(raw_html) if raw_html else plain_text_to_html(trim_note_content(legacy_content)))
    )
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


def normalize_file_entry(raw_file: Any, *, fallback_symbol: str = "") -> dict[str, Any] | None:
    if not isinstance(raw_file, dict):
        return None

    stored_name = str(raw_file.get("stored_name") or "").strip()
    original_name = str(raw_file.get("original_name") or "").strip()
    if not stored_name or not original_name:
        return None

    storage_symbol = normalize_stock_symbol(str(raw_file.get("storage_symbol") or "")) or (
        normalize_stock_symbol(fallback_symbol) or ""
    )
    linked_symbols = ordered_unique(
        ([storage_symbol] if storage_symbol else []) + normalize_stock_symbol_list(raw_file.get("linked_symbols", []))
    )

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
        "storage_symbol": storage_symbol,
        "linked_symbols": linked_symbols,
    }


def normalize_transcript_entry(raw_transcript: Any, *, trust_saved_html: bool = False) -> dict[str, Any] | None:
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

    category = normalize_transcript_category(raw_transcript.get("category"))

    try:
        speaker_count = int(raw_transcript.get("speaker_count") or 2)
    except (TypeError, ValueError):
        speaker_count = 2
    speaker_count = min(max(speaker_count, 2), 8)

    raw_transcript_html = str(raw_transcript.get("transcript_html") or "").strip()
    transcript_text = trim_note_content(str(raw_transcript.get("transcript_text") or "").strip())
    transcript_html = (
        raw_transcript_html
        if trust_saved_html and raw_transcript_html
        else (sanitize_note_html(raw_transcript_html) if raw_transcript_html else "")
    )
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
        "category": category,
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


def normalize_trash_entry(raw_entry: Any, *, trust_saved_html: bool = False) -> dict[str, Any] | None:
    if not isinstance(raw_entry, dict):
        return None

    item_type = str(raw_entry.get("item_type") or "").strip()
    payload = raw_entry.get("payload")
    normalized_payload: dict[str, Any] | None = None

    if item_type == "note":
        normalized_payload = normalize_note(payload, trust_saved_html=trust_saved_html)
    elif item_type == "file":
        normalized_payload = normalize_file_entry(
            payload,
            fallback_symbol=normalize_stock_symbol(str(raw_entry.get("symbol") or "")) or "",
        )
    elif item_type == "transcript":
        normalized_payload = normalize_transcript_entry(payload, trust_saved_html=trust_saved_html)
    elif item_type == "group":
        normalized_payload = normalize_group_entry(payload)
    elif item_type == "schedule_item":
        normalized_payload = normalize_schedule_item(payload)
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


def normalize_stock_store(data: Any, *, trust_saved_html: bool = False) -> dict[str, Any]:
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
        if (transcript := normalize_transcript_entry(raw_transcript, trust_saved_html=trust_saved_html)) is not None
    ]
    experts = [
        expert
        for raw_expert in source.get("experts", [])
        if (expert := normalize_expert_entry(raw_expert)) is not None
    ]
    schedule_items = [
        item
        for raw_item in source.get("schedule_items", [])
        if (item := normalize_schedule_item(raw_item)) is not None
    ]
    trash = [
        trash_entry
        for raw_entry in source.get("trash", [])
        if (trash_entry := normalize_trash_entry(raw_entry, trust_saved_html=trust_saved_html)) is not None
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
                entry["earnings"] = normalize_stock_earnings_info(raw_entry.get("earnings"))
                entry["earnings_calls"] = [
                    call
                    for raw_call in raw_entry.get("earnings_calls", [])
                    if (
                        call := normalize_stock_earnings_call_entry(
                            raw_call,
                            trust_saved_html=trust_saved_html,
                        )
                    )
                    is not None
                ]
                entry["earnings_call_sync"] = normalize_stock_earnings_call_sync_info(
                    raw_entry.get("earnings_call_sync")
                )
                entry["notes"] = [
                    note
                    for raw_note in raw_entry.get("notes", [])
                    if (note := normalize_note(raw_note, trust_saved_html=trust_saved_html)) is not None
                ]
                entry["files"] = [
                    file_entry
                    for raw_file in raw_entry.get("files", [])
                    if (file_entry := normalize_file_entry(raw_file, fallback_symbol=symbol)) is not None
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
        "experts": experts,
        "schedule_items": schedule_items,
        "trash": trash,
    }


def get_stock_store_signature() -> tuple[str, int, int]:
    try:
        stat_result = STOCK_STORE_PATH.stat()
    except OSError:
        return ("missing", 0, 0)
    return ("file", int(stat_result.st_mtime_ns), int(stat_result.st_size))


def load_stock_store() -> dict[str, Any]:
    STOCK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    signature = get_stock_store_signature()

    with STOCK_STORE_CACHE_LOCK:
        cached_signature = STOCK_STORE_CACHE.get("signature")
        cached_data = STOCK_STORE_CACHE.get("data")
        if cached_signature == signature and isinstance(cached_data, dict):
            return deepcopy(cached_data)

    if signature[0] == "missing":
        normalized = normalize_stock_store({}, trust_saved_html=True)
    else:
        try:
            raw_data = json.loads(STOCK_STORE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            normalized = normalize_stock_store({}, trust_saved_html=True)
        else:
            normalized = normalize_stock_store(raw_data, trust_saved_html=True)

    refreshed_signature = get_stock_store_signature()
    with STOCK_STORE_CACHE_LOCK:
        STOCK_STORE_CACHE["signature"] = refreshed_signature
        STOCK_STORE_CACHE["data"] = normalized

    return deepcopy(normalized)


def save_stock_store(store: dict[str, Any]) -> None:
    normalized = normalize_stock_store(store)
    STOCK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STOCK_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(STOCK_STORE_PATH)
    with STOCK_STORE_CACHE_LOCK:
        STOCK_STORE_CACHE["signature"] = get_stock_store_signature()
        STOCK_STORE_CACHE["data"] = normalized


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


def fetch_next_stock_earnings(symbol: str) -> dict[str, Any]:
    normalized_symbol = normalize_stock_symbol(symbol)
    if not normalized_symbol:
        raise ValueError("无效股票代码")

    errors: list[str] = []
    for source in EARNINGS_SOURCE_CATALOG:
        source_label = str(source["label"])
        source_url = str(source["url_template"]).format(symbol=normalized_symbol.lower())
        try:
            response = requests.get(
                source_url,
                headers=EARNINGS_REQUEST_HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            match = source["date_pattern"].search(response.text)
            if not match:
                raise ValueError("页面里没有找到下一次业绩日期")

            next_date = datetime.strptime(match.group(1).strip(), str(source["date_format"])).date().isoformat()
            if next_date < today_date_iso():
                raise ValueError(f"返回了历史日期 {next_date}")

            return normalize_stock_earnings_info(
                {
                    "next_date": next_date,
                    "source_label": source_label,
                    "source_url": source_url,
                    "last_synced_at": now_iso(),
                    "is_estimated": source_label == "Barchart",
                }
            )
        except Exception as exc:
            errors.append(f"{source_label}: {exc}")

    raise RuntimeError("；".join(errors) or "未找到可用的业绩日期来源")


def fetch_recent_stock_earnings_calls(
    symbol: str,
    *,
    existing_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    from earnings_calls import fetch_recent_earnings_calls

    return fetch_recent_earnings_calls(symbol, existing_calls=existing_calls)


def build_managed_earnings_schedule_title(symbol: str) -> str:
    return f"{symbol} 下一次业绩"


def build_stock_earnings_priority(next_date: str) -> str:
    parsed = parse_iso_date_value(next_date)
    if not parsed:
        return "normal"

    days_until = (parsed.date() - datetime.now().date()).days
    if days_until <= 14:
        return "high"
    if days_until >= 60:
        return "low"
    return "normal"


def build_auto_earnings_schedule_note(earnings_info: dict[str, Any]) -> str:
    synced_label = (
        format_iso_timestamp(earnings_info.get("last_synced_at"))
        if earnings_info.get("last_synced_at")
        else "刚刚"
    )
    source_label = str(earnings_info.get("source_label") or "外部行情页")
    note = f"自动同步来源：{source_label}；同步时间：{synced_label}。"
    if earnings_info.get("is_estimated"):
        note += " 如果公司后续正式公告不同，请以公司公告为准。"
    return note


def is_managed_earnings_schedule_item(item: dict[str, Any], symbol: str) -> bool:
    if str(item.get("kind") or "") != "earnings":
        return False
    if normalize_stock_symbol(str(item.get("symbol") or "")) != symbol:
        return False

    tags = normalize_tag_list(item.get("tags", []))
    title = str(item.get("title") or "").strip()
    return EARNINGS_SYNC_TAG in tags or title == build_managed_earnings_schedule_title(symbol)


def upsert_stock_earnings_schedule_item(
    store: dict[str, Any],
    symbol: str,
    earnings_info: dict[str, Any],
) -> None:
    next_date = str(earnings_info.get("next_date") or "")
    if not next_date:
        return

    entry = ensure_stock_entry(store, symbol)
    schedule_items = store.setdefault("schedule_items", [])
    matched_indexes = [
        index for index, item in enumerate(schedule_items) if is_managed_earnings_schedule_item(item, symbol)
    ]
    existing = schedule_items[matched_indexes[0]] if matched_indexes else {}
    payload = normalize_schedule_item(
        {
            "id": existing.get("id"),
            "title": build_managed_earnings_schedule_title(symbol),
            "kind": "earnings",
            "status": "planned",
            "priority": build_stock_earnings_priority(next_date),
            "symbol": symbol,
            "company": str(entry.get("display_name") or symbol).strip(),
            "scheduled_date": next_date,
            "has_time_range": False,
            "all_day": True,
            "location": "",
            "note": build_auto_earnings_schedule_note(earnings_info),
            "tags": ["业绩期", EARNINGS_SYNC_TAG],
            "created_at": existing.get("created_at") or now_iso(),
            "updated_at": now_iso(),
        }
    )
    if not payload:
        return

    if matched_indexes:
        schedule_items[matched_indexes[0]] = payload
        for index in reversed(matched_indexes[1:]):
            del schedule_items[index]
    else:
        schedule_items.append(payload)


def apply_stock_earnings_snapshot(
    store: dict[str, Any],
    symbol: str,
    earnings_info: dict[str, Any],
) -> None:
    entry = ensure_stock_entry(store, symbol)
    normalized = normalize_stock_earnings_info(earnings_info)
    if not normalized["next_date"]:
        raise ValueError("缺少可写入的业绩日期")

    entry["earnings"] = normalized
    upsert_stock_earnings_schedule_item(store, symbol, normalized)


def apply_stock_earnings_call_snapshot(
    store: dict[str, Any],
    symbol: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    entry = ensure_stock_entry(store, symbol)
    raw_calls = payload.get("calls", []) if isinstance(payload, dict) else []
    calls = [
        call
        for raw_call in raw_calls
        if (call := normalize_stock_earnings_call_entry(raw_call)) is not None
    ]
    entry["earnings_calls"] = calls
    entry["earnings_call_sync"] = normalize_stock_earnings_call_sync_info(
        {
            "source_label": payload.get("source_label") if isinstance(payload, dict) else "",
            "source_url": payload.get("source_url") if isinstance(payload, dict) else "",
            "lookback_days": payload.get("lookback_days") if isinstance(payload, dict) else 730,
            "last_synced_at": now_iso(),
            "last_error": "",
        }
    )
    touch_stock(store, symbol)
    return entry


def note_stock_earnings_call_sync_failure(
    store: dict[str, Any],
    symbol: str,
    error_message: str,
    *,
    source_label: str = "",
    source_url: str = "",
    lookback_days: int = 730,
) -> None:
    entry = ensure_stock_entry(store, symbol)
    current = normalize_stock_earnings_call_sync_info(entry.get("earnings_call_sync"))
    entry["earnings_call_sync"] = normalize_stock_earnings_call_sync_info(
        {
            "source_label": source_label or current.get("source_label") or "",
            "source_url": source_url or current.get("source_url") or "",
            "lookback_days": lookback_days or current.get("lookback_days") or 730,
            "last_synced_at": now_iso(),
            "last_error": error_message,
        }
    )


def collect_stock_earnings_snapshots(symbols: list[str]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    snapshots: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for raw_symbol in ordered_unique(symbols):
        symbol = normalize_stock_symbol(raw_symbol)
        if not symbol:
            continue
        try:
            snapshots[symbol] = fetch_next_stock_earnings(symbol)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")

    return snapshots, errors


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


def get_schedule_item(store: dict[str, Any], item_id: str) -> dict[str, Any]:
    for item in store.get("schedule_items", []):
        if item["id"] == item_id:
            return item

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


def normalize_monitor_workspace_tab(raw_value: str | None, *, fallback: str = "info") -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"signals", "signal", "bigv", "big-v", "big_v", "v"}:
        return "signals"
    if value in {"info", "monitor", "stock", "stocks"}:
        return "info"
    return fallback


def redirect_to_monitor_workspace(
    *,
    tab: str = "info",
    report: str | None = None,
    signal_report: str | None = None,
):
    params: dict[str, Any] = {}
    normalized_tab = normalize_monitor_workspace_tab(tab)
    if normalized_tab != "info":
        params["tab"] = normalized_tab
    if report:
        params["report"] = report
    if signal_report:
        params["signal_report"] = signal_report
    return redirect(url_for("monitor_page", **params))


def normalize_data_monitor_tab(raw_value: str | None, *, fallback: str = "stablecoins") -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"stablecoins", "stablecoin", "stable", "stables", "usdt"}:
        return "stablecoins"
    return fallback


def is_web_access_authenticated() -> bool:
    if not WEB_ACCESS_PASSWORD_SIGNATURE:
        return True
    return hmac.compare_digest(
        str(session.get(WEB_ACCESS_SESSION_KEY) or ""),
        WEB_ACCESS_PASSWORD_SIGNATURE,
    )


@app.before_request
def enforce_web_access_password():
    if not WEB_ACCESS_PASSWORD_SIGNATURE:
        return None

    allowed_endpoints = {"static", "favicon", "access_password_gate", "access_password_submit"}
    if request.endpoint in allowed_endpoints:
        return None

    if is_web_access_authenticated():
        return None

    next_url = request.full_path if request.query_string else request.path
    return redirect(url_for("access_password_gate", next=next_url))


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
        "file_count": stock_file_count_for_symbol(store, symbol),
        "transcript_count": transcript_count_for_symbol(store, symbol),
        "earnings_call_count": len(entry.get("earnings_calls", [])),
        "updated_label": format_iso_timestamp(entry.get("updated_at")),
        "next_earnings": build_stock_earnings_view(entry),
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


def schedule_item_sort_datetime(item: dict[str, Any]) -> datetime:
    date_value = parse_iso_date_value(str(item.get("scheduled_date") or ""))
    if date_value is None:
        return datetime.now().replace(microsecond=0)

    if item.get("all_day"):
        return datetime.combine(date_value.date(), datetime.min.time())

    start_time = normalize_time_field(str(item.get("start_time") or ""))
    if not start_time:
        return datetime.combine(date_value.date(), datetime.strptime("12:00", "%H:%M").time())

    return datetime.combine(date_value.date(), datetime.strptime(start_time, "%H:%M").time())


def schedule_item_has_time_range(item: dict[str, Any]) -> bool:
    if item.get("all_day"):
        return False

    if bool(item.get("has_time_range")):
        return True

    start_time = normalize_time_field(str(item.get("start_time") or ""))
    end_time = normalize_time_field(str(item.get("end_time") or ""))
    return bool(start_time or end_time)


def schedule_item_time_rank(item: dict[str, Any]) -> int:
    if schedule_item_has_time_range(item):
        return 0
    if item.get("all_day"):
        return 1
    return 2


def schedule_card_sort_key(item: dict[str, Any]) -> tuple[str, int, float, str]:
    return (
        str(item.get("scheduled_date") or ""),
        schedule_item_time_rank(item),
        float(item.get("sort_value") or 0),
        str(item.get("title") or "").lower(),
    )


def build_schedule_time_label(item: dict[str, Any]) -> str:
    if item.get("all_day"):
        return "全天"

    start_time = normalize_time_field(str(item.get("start_time") or ""))
    end_time = normalize_time_field(str(item.get("end_time") or ""))
    if start_time and end_time:
        return f"{start_time} - {end_time}"
    if start_time:
        return start_time
    return "时间待定"


def build_schedule_day_heading(date_value: str) -> dict[str, str]:
    parsed = parse_iso_date_value(date_value)
    if parsed is None:
        return {"label": date_value, "relative_label": "日程"}

    today = datetime.now().date()
    delta_days = (parsed.date() - today).days
    weekday_label = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][parsed.weekday()]

    if delta_days == 0:
        relative_label = "今天"
    elif delta_days == 1:
        relative_label = "明天"
    elif delta_days == -1:
        relative_label = "昨天"
    elif delta_days < 0:
        relative_label = f"已过 {abs(delta_days)} 天"
    else:
        relative_label = f"{delta_days} 天后"

    return {
        "label": f"{parsed.strftime('%Y-%m-%d')} · {weekday_label}",
        "relative_label": relative_label,
    }


def build_schedule_company_label(store: dict[str, Any], item: dict[str, Any]) -> str:
    company = str(item.get("company") or "").strip()
    symbol = str(item.get("symbol") or "").strip()
    if not symbol:
        return company

    stock_label = symbol
    if symbol in store.get("stocks", {}):
        stock_label = str(store["stocks"][symbol].get("display_name") or symbol).strip() or symbol

    if company and company.casefold() != stock_label.casefold() and company.casefold() != symbol.casefold():
        return f"{company} · {symbol}"
    if company:
        return company
    if stock_label.casefold() != symbol.casefold():
        return f"{stock_label} · {symbol}"
    return symbol


def build_schedule_card(
    store: dict[str, Any],
    item: dict[str, Any],
    *,
    focus_item_id: str = "",
) -> dict[str, Any]:
    status = str(item.get("status") or "planned")
    status_meta = SCHEDULE_STATUS_META.get(status, SCHEDULE_STATUS_META["planned"])
    priority = str(item.get("priority") or "normal")
    priority_meta = SCHEDULE_PRIORITY_META.get(priority, SCHEDULE_PRIORITY_META["normal"])
    sort_value = schedule_item_sort_datetime(item)
    scheduled_date = str(item.get("scheduled_date") or "")
    today = today_date_iso()
    is_overdue = status == "planned" and scheduled_date < today

    note = str(item.get("note") or "").strip()
    location = str(item.get("location") or "").strip()
    fallback_summary = location or build_schedule_time_label(item)

    return {
        **item,
        "kind_label": SCHEDULE_KIND_META.get(str(item.get("kind") or ""), SCHEDULE_KIND_META["meeting"])["label"],
        "kind_tone": SCHEDULE_KIND_META.get(str(item.get("kind") or ""), SCHEDULE_KIND_META["meeting"])["tone"],
        "status_label": status_meta["label"],
        "status_tone": status_meta["tone"],
        "priority_label": priority_meta["label"],
        "priority_tone": priority_meta["tone"],
        "company_label": build_schedule_company_label(store, item),
        "display_time": build_schedule_time_label(item),
        "has_time_range": schedule_item_has_time_range(item),
        "time_sort_rank": schedule_item_time_rank(item),
        "summary": summarize_text_block(note or fallback_summary, limit=180),
        "sort_value": sort_value.timestamp(),
        "display_updated_at": format_iso_timestamp(str(item.get("updated_at") or "")),
        "is_overdue": is_overdue,
        "is_today": scheduled_date == today,
        "is_focus": bool(focus_item_id and str(item.get("id") or "") == focus_item_id),
        "stock_url": url_for("stock_detail", symbol=item["symbol"]) if item.get("symbol") else "",
    }


def build_schedule_date_groups(cards: list[dict[str, Any]], *, reverse: bool = False) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        grouped[str(card.get("scheduled_date") or "")].append(card)

    ordered_dates = sorted(grouped.keys(), reverse=reverse)
    groups: list[dict[str, Any]] = []
    for date_value in ordered_dates:
        items = sorted(grouped[date_value], key=schedule_card_sort_key)
        heading = build_schedule_day_heading(date_value)
        groups.append(
            {
                "date": date_value,
                "label": heading["label"],
                "relative_label": heading["relative_label"],
                "items": items,
            }
        )
    return groups


def build_schedule_period_stats(cards: list[dict[str, Any]], prefix: str) -> dict[str, int]:
    matched = [item for item in cards if str(item.get("scheduled_date") or "").startswith(prefix)]
    return {
        "total_count": len(matched),
        "open_count": sum(1 for item in matched if item.get("status") == "planned"),
        "earnings_count": sum(1 for item in matched if item.get("kind") == "earnings"),
    }


def build_schedule_activity(
    store: dict[str, Any],
    *,
    focus_item_id: str = "",
) -> dict[str, Any]:
    cards = [build_schedule_card(store, item, focus_item_id=focus_item_id) for item in store.get("schedule_items", [])]
    cards.sort(key=schedule_card_sort_key)

    summaries: dict[str, dict[str, Any]] = {}
    entries: list[dict[str, Any]] = []
    for card in cards:
        schedule_date = str(card.get("scheduled_date") or "")
        entries.append(
            {
                "date": schedule_date,
                "kind": str(card.get("kind") or ""),
                "status": str(card.get("status") or ""),
            }
        )
        summary = summaries.setdefault(
            schedule_date,
            {
                "total_count": 0,
                "open_count": 0,
                "earnings_count": 0,
                "items": [],
            },
        )
        summary["total_count"] += 1
        if card.get("status") == "planned":
            summary["open_count"] += 1
        if card.get("kind") == "earnings":
            summary["earnings_count"] += 1
        summary["items"].append(card)

    for summary in summaries.values():
        summary["items"].sort(key=schedule_card_sort_key)

    return {
        "cards": cards,
        "entries": entries,
        "summaries": summaries,
    }


def build_schedule_sections(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = today_date_iso()
    week_end = (datetime.now().date() + timedelta(days=7)).isoformat()

    planned_cards = [item for item in cards if item.get("status") == "planned"]
    overdue_cards = [item for item in planned_cards if str(item.get("scheduled_date") or "") < today]
    today_cards = [item for item in planned_cards if str(item.get("scheduled_date") or "") == today]
    next_week_cards = [
        item
        for item in planned_cards
        if today < str(item.get("scheduled_date") or "") <= week_end
    ]
    later_cards = [item for item in planned_cards if str(item.get("scheduled_date") or "") > week_end]
    archived_cards = [item for item in cards if item.get("status") in {"done", "cancelled"}]

    return [
        {
            "key": "overdue",
            "title": "逾期未完成",
            "caption": "优先把已经过期但还没处理的会议、提醒和业绩节点拉出来。",
            "empty_copy": "当前没有逾期项目，节奏还算稳。",
            "groups": build_schedule_date_groups(overdue_cards),
            "count": len(overdue_cards),
        },
        {
            "key": "today",
            "title": "今天",
            "caption": "今天要发生的事集中放在这里，适合临开会前快速看一眼。",
            "empty_copy": "今天还没有安排，后面新增后会立刻出现在这里。",
            "groups": build_schedule_date_groups(today_cards),
            "count": len(today_cards),
        },
        {
            "key": "next_week",
            "title": "未来 7 天",
            "caption": "把最近一周的节奏提前排好，避免专家会和业绩期撞在一起。",
            "empty_copy": "未来 7 天暂时是空的，可以先把最近要约的会补进来。",
            "groups": build_schedule_date_groups(next_week_cards),
            "count": len(next_week_cards),
        },
        {
            "key": "later",
            "title": "之后",
            "caption": "更远的安排放在后面，先占住坑位，之后再补细节。",
            "empty_copy": "更远时间段还没有安排。",
            "groups": build_schedule_date_groups(later_cards),
            "count": len(later_cards),
        },
        {
            "key": "archived",
            "title": "已完成 / 已取消",
            "caption": "保留最近处理过的事项，方便回看自己排期是否合理。",
            "empty_copy": "最近还没有归档项。",
            "groups": build_schedule_date_groups(archived_cards, reverse=True),
            "count": len(archived_cards),
        },
    ]


def build_schedule_page_context(
    store: dict[str, Any],
    *,
    month_param: str | None,
    year_param: str | None = None,
    month_number_param: str | None = None,
    date_param: str | None,
    focus_item_id: str = "",
) -> dict[str, Any]:
    activity = build_schedule_activity(store, focus_item_id=focus_item_id)
    cards = activity["cards"]
    selected_date_value = parse_iso_date_value(date_param)
    fallback_month = selected_date_value or (
        parse_iso_date_value(cards[0]["scheduled_date"]) if cards else datetime.now()
    )
    month_value = resolve_month_value(
        month_param=month_param,
        year_param=year_param,
        month_number_param=month_number_param,
        fallback=fallback_month,
    )
    selected_date = selected_date_value.date().isoformat() if selected_date_value else None
    month_key = month_value.strftime("%Y-%m")

    if not selected_date or not selected_date.startswith(month_key):
        if today_date_iso().startswith(month_key):
            selected_date = today_date_iso()
        else:
            selected_date = find_month_default_date(activity["summaries"], month_value)

    previous_year, previous_month = shift_month(month_value.year, month_value.month, -1)
    next_year, next_month = shift_month(month_value.year, month_value.month, 1)
    selected_summary = activity["summaries"].get(selected_date or "")

    today = today_date_iso()
    week_end = (datetime.now().date() + timedelta(days=7)).isoformat()
    upcoming_cards = [
        item
        for item in cards
        if item.get("status") == "planned" and str(item.get("scheduled_date") or "") >= today
    ]
    upcoming_cards.sort(key=schedule_card_sort_key)
    upcoming_earnings = [
        item
        for item in cards
        if item.get("kind") == "earnings"
        and item.get("status") == "planned"
        and str(item.get("scheduled_date") or "") >= today
    ]
    upcoming_earnings.sort(key=schedule_card_sort_key)

    return {
        "schedule_cards": cards,
        "schedule_sections": build_schedule_sections(cards),
        "schedule_open_count": sum(1 for item in cards if item.get("status") == "planned"),
        "schedule_today_count": sum(
            1 for item in cards if item.get("status") == "planned" and item.get("scheduled_date") == today
        ),
        "schedule_week_count": sum(
            1
            for item in cards
            if item.get("status") == "planned" and today < str(item.get("scheduled_date") or "") <= week_end
        ),
        "schedule_earnings_count": len(upcoming_earnings),
        "schedule_overdue_count": sum(
            1 for item in cards if item.get("status") == "planned" and str(item.get("scheduled_date") or "") < today
        ),
        "schedule_month_stats": build_schedule_period_stats(cards, month_key),
        "schedule_year_stats": build_schedule_period_stats(cards, f"{month_value.year:04d}"),
        "schedule_upcoming_cards": upcoming_cards[:10],
        "upcoming_earnings": upcoming_earnings[:8],
        "selected_schedule_items": selected_summary.get("items", []) if selected_summary else [],
        "selected_schedule_date": selected_date,
        "selected_schedule_heading": build_schedule_day_heading(selected_date)["label"] if selected_date else "选择一天",
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
        "calendar_weeks": build_calendar_weeks(month_value, activity["summaries"], selected_date),
        "weekday_labels": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        "focus_schedule_item_id": focus_item_id,
    }


def build_expert_identity_line(expert: dict[str, Any]) -> str:
    bits = [str(expert.get("organization") or "").strip(), str(expert.get("title") or "").strip()]
    return " · ".join(bit for bit in bits if bit)


def expert_stage_order(value: str | None) -> int:
    return int(EXPERT_STAGE_META.get(str(value or "").strip(), {}).get("order") or 999)


def expert_category_order(value: str | None) -> int:
    return int(EXPERT_CATEGORY_META.get(str(value or "").strip(), {}).get("order") or 999)


def expert_interview_status_order(value: str | None) -> int:
    return int(EXPERT_INTERVIEW_STATUS_META.get(str(value or "").strip(), {}).get("order") or 999)


def expert_interview_sort_key(interview: dict[str, Any]) -> tuple[str, int, float, str]:
    return (
        str(interview.get("interview_date") or ""),
        expert_interview_status_order(str(interview.get("status") or "")),
        coerce_sort_timestamp(interview.get("updated_at") or interview.get("created_at")),
        str(interview.get("title") or "").casefold(),
    )


def get_expert_entry(store: dict[str, Any], expert_id: str) -> dict[str, Any]:
    for expert in store.get("experts", []):
        if expert["id"] == expert_id:
            return expert

    abort(404)


def get_expert_interview_entry(expert: dict[str, Any], interview_id: str) -> dict[str, Any]:
    for interview in expert.get("interviews", []):
        if interview["id"] == interview_id:
            return interview

    abort(404)


def resolve_expert_resource_ref(store: dict[str, Any], resource_ref: dict[str, Any]) -> dict[str, Any] | None:
    kind = str(resource_ref.get("kind") or "").strip()
    resource_id = str(resource_ref.get("resource_id") or "").strip()
    symbol = str(resource_ref.get("symbol") or "").strip()
    kind_meta = EXPERT_RESOURCE_KIND_META.get(kind)
    if not kind_meta or not resource_id:
        return None
    normalized_ref = {
        "kind": kind,
        "symbol": symbol if kind in {"note", "file"} else "",
        "resource_id": resource_id,
    }
    preview_url = build_expert_resource_preview_url(normalized_ref)
    token = build_expert_resource_token(normalized_ref)

    if kind == "note" and symbol:
        entry = ensure_stock_entry(store, symbol)
        for note in entry.get("notes", []):
            if str(note.get("id") or "") != resource_id:
                continue
            return {
                "kind": kind,
                "kind_label": kind_meta["label"],
                "kind_tone": kind_meta["tone"],
                "resource_id": resource_id,
                "symbol": symbol,
                "title": note.get("title") or "未命名笔记",
                "summary": summarize_text_block(note.get("content_text") or ""),
                "display_time": note_display_time(note),
                "sort_value": coerce_sort_timestamp(note.get("created_at")),
                "token": token,
                "preview_url": preview_url,
                "url": build_stock_detail_deep_link(
                    symbol=symbol,
                    panel="notes",
                    item_kind="note",
                    item_id=resource_id,
                    anchor=f"note-{resource_id}",
                ),
            }

    if kind == "file" and symbol:
        entry = ensure_stock_entry(store, symbol)
        for file_entry in entry.get("files", []):
            if str(file_entry.get("id") or "") != resource_id:
                continue
            return {
                "kind": kind,
                "kind_label": kind_meta["label"],
                "kind_tone": kind_meta["tone"],
                "resource_id": resource_id,
                "symbol": symbol,
                "title": file_entry.get("original_name") or "已上传资料",
                "summary": summarize_text_block(
                    file_entry.get("description")
                    or f"{detect_file_type_label(str(file_entry.get('original_name') or ''))} 文件"
                ),
                "display_time": file_display_time(file_entry),
                "sort_value": coerce_sort_timestamp(file_entry.get("uploaded_at")),
                "token": token,
                "preview_url": preview_url,
                "url": build_stock_detail_deep_link(
                    symbol=symbol,
                    panel="files",
                    item_kind="file",
                    item_id=resource_id,
                    anchor=f"file-{resource_id}",
                ),
                "secondary_url": url_for("download_stock_file", symbol=symbol, file_id=resource_id),
                "secondary_label": "下载文件",
            }

    if kind == "transcript":
        for transcript in store.get("transcripts", []):
            if str(transcript.get("id") or "") != resource_id:
                continue
            card = build_transcript_card(transcript)
            primary_symbol = card["linked_symbols"][0] if card.get("linked_symbols") else ""
            return {
                "kind": kind,
                "kind_label": kind_meta["label"],
                "kind_tone": kind_meta["tone"],
                "resource_id": resource_id,
                "symbol": primary_symbol,
                "symbols": card.get("linked_symbols", []),
                "title": card.get("display_title") or "会议转录",
                "summary": card.get("summary_excerpt") or TRANSCRIPT_PLACEHOLDER_COPY,
                "display_time": card.get("meeting_date_label") or card.get("display_created_at"),
                "sort_value": coerce_sort_timestamp(card.get("meeting_date") or card.get("created_at")),
                "token": token,
                "preview_url": preview_url,
                "url": (
                    build_stock_detail_deep_link(
                        symbol=primary_symbol,
                        panel="transcripts",
                        item_kind="transcript",
                        item_id=resource_id,
                        anchor=f"transcript-{resource_id}",
                    )
                    if primary_symbol
                    else url_for("transcripts_page")
                ),
            }

    if kind == "schedule":
        for item in store.get("schedule_items", []):
            if str(item.get("id") or "") != resource_id:
                continue
            card = build_schedule_card(store, item)
            schedule_date = str(card.get("scheduled_date") or "")
            return {
                "kind": kind,
                "kind_label": kind_meta["label"],
                "kind_tone": kind_meta["tone"],
                "resource_id": resource_id,
                "symbol": str(card.get("symbol") or ""),
                "title": card.get("title") or "未命名日程",
                "summary": card.get("summary") or "",
                "display_time": f"{schedule_date} · {card.get('display_time') or '时间待定'}",
                "sort_value": schedule_item_sort_datetime(item).timestamp(),
                "status_label": card.get("status_label") or "",
                "status_tone": card.get("status_tone") or "pending",
                "token": token,
                "preview_url": preview_url,
                "url": url_for("schedule_page", month=schedule_date[:7], date=schedule_date, focus=resource_id),
            }

    return None


def build_expert_resource_groups(store: dict[str, Any], expert: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for resource_ref in expert.get("resource_refs", []):
        resolved = resolve_expert_resource_ref(store, resource_ref)
        if resolved is None:
            continue
        grouped[resolved["kind"]].append(resolved)

    groups: list[dict[str, Any]] = []
    for kind, meta in sorted(EXPERT_RESOURCE_KIND_META.items(), key=lambda item: item[1]["order"]):
        items = grouped.get(kind, [])
        items.sort(key=lambda item: (float(item.get("sort_value") or 0), item.get("title") or ""), reverse=True)
        groups.append(
            {
                "kind": kind,
                "label": meta["label"],
                "tone": meta["tone"],
                "count": len(items),
                "items": items,
            }
        )

    return groups


def build_expert_resource_catalog(
    store: dict[str, Any],
    expert: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    selected_tokens = {
        build_expert_resource_token(resource_ref)
        for resource_ref in (expert.get("resource_refs", []) if expert else [])
    }
    preferred_symbols = set(expert.get("related_symbols", []) if expert else [])
    scope_symbols = sorted(preferred_symbols) if preferred_symbols else sorted(list_stock_symbols(store))
    sections: list[dict[str, Any]] = []

    note_items: list[dict[str, Any]] = []
    file_items: list[dict[str, Any]] = []
    for symbol in scope_symbols:
        entry = ensure_stock_entry(store, symbol)
        for note in entry.get("notes", []):
            resource_ref = {"kind": "note", "symbol": symbol, "resource_id": str(note.get("id") or "")}
            token = build_expert_resource_token(resource_ref)
            note_items.append(
                {
                    "token": token,
                    "title": note.get("title") or "未命名笔记",
                    "summary": summarize_text_block(note.get("content_text") or ""),
                    "display_time": note_display_time(note),
                    "symbol": symbol,
                    "is_selected": token in selected_tokens,
                    "sort_value": coerce_sort_timestamp(note.get("created_at")),
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="notes",
                        item_kind="note",
                        item_id=str(note.get("id") or ""),
                        anchor=f"note-{note.get('id')}",
                    ),
                }
            )

        for file_entry in entry.get("files", []):
            resource_ref = {"kind": "file", "symbol": symbol, "resource_id": str(file_entry.get("id") or "")}
            token = build_expert_resource_token(resource_ref)
            file_items.append(
                {
                    "token": token,
                    "title": file_entry.get("original_name") or "已上传资料",
                    "summary": summarize_text_block(
                        file_entry.get("description")
                        or f"{detect_file_type_label(str(file_entry.get('original_name') or ''))} 文件"
                    ),
                    "display_time": file_display_time(file_entry),
                    "symbol": symbol,
                    "is_selected": token in selected_tokens,
                    "sort_value": coerce_sort_timestamp(file_entry.get("uploaded_at")),
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="files",
                        item_kind="file",
                        item_id=str(file_entry.get("id") or ""),
                        anchor=f"file-{file_entry.get('id')}",
                    ),
                }
            )

    note_items.sort(key=lambda item: (float(item["sort_value"]), item["title"]), reverse=True)
    file_items.sort(key=lambda item: (float(item["sort_value"]), item["title"]), reverse=True)
    sections.append(
        {
            "kind": "note",
            "label": EXPERT_RESOURCE_KIND_META["note"]["label"],
            "tone": EXPERT_RESOURCE_KIND_META["note"]["tone"],
            "items": note_items,
            "count": len(note_items),
        }
    )
    sections.append(
        {
            "kind": "file",
            "label": EXPERT_RESOURCE_KIND_META["file"]["label"],
            "tone": EXPERT_RESOURCE_KIND_META["file"]["tone"],
            "items": file_items,
            "count": len(file_items),
        }
    )

    transcript_items: list[dict[str, Any]] = []
    for call in []:
            if selected_kind and selected_kind != "earnings_call":
                continue
            if normalized_symbol and symbol != normalized_symbol:
                continue
            if normalized_tag:
                continue

            search_text = " ".join(
                [
                    symbol,
                    str(call.get("display_title") or ""),
                    str(call.get("original_title") or ""),
                    str(call.get("transcript_text") or ""),
                    str(call.get("source_query_label") or ""),
                ]
            )
            if terms and not text_contains_all_terms(search_text, terms):
                continue

            results.append(
                {
                    "kind": "earnings_call",
                    "kind_label": SEARCH_KIND_META["earnings_call"]["label"],
                    "kind_tone": SEARCH_KIND_META["earnings_call"]["tone"],
                    "title": call["display_title"],
                    "summary": build_match_excerpt(
                        call.get("transcript_text") or "",
                        terms,
                        call["summary_excerpt"],
                    ),
                    "symbol": symbol,
                    "display_time": call.get("display_call_date") or call.get("display_published_at"),
                    "sort_value": coerce_sort_timestamp(call.get("call_date") or call.get("published_at")),
                    "tags": [],
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="earnings-calls",
                        item_kind="earnings_call",
                        item_id=str(call.get("id") or ""),
                        anchor=f"earnings-call-{call.get('id')}",
                    ),
                    "secondary_url": call.get("source_url") or "",
                    "secondary_label": "原始来源",
                }
            )

    for transcript in build_transcript_cards(store):
        linked_symbols = transcript.get("linked_symbols", [])
        symbol_match_rank = 0 if not preferred_symbols or preferred_symbols.intersection(linked_symbols) else 1
        resource_ref = {"kind": "transcript", "symbol": "", "resource_id": transcript["id"]}
        token = build_expert_resource_token(resource_ref)
        transcript_items.append(
            {
                "token": token,
                "title": transcript.get("display_title") or "会议转录",
                "summary": transcript.get("summary_excerpt") or TRANSCRIPT_PLACEHOLDER_COPY,
                "display_time": transcript.get("meeting_date_label") or transcript.get("display_created_at"),
                "symbol": linked_symbols[0] if linked_symbols else "",
                "symbols": linked_symbols,
                "is_selected": token in selected_tokens,
                "match_rank": symbol_match_rank,
                "sort_value": coerce_sort_timestamp(transcript.get("meeting_date") or transcript.get("created_at")),
                "url": (
                    build_stock_detail_deep_link(
                        symbol=linked_symbols[0],
                        panel="transcripts",
                        item_kind="transcript",
                        item_id=transcript["id"],
                        anchor=f"transcript-{transcript['id']}",
                    )
                    if linked_symbols
                    else url_for("transcripts_page")
                ),
            }
        )

    transcript_items.sort(
        key=lambda item: (int(item["match_rank"]), -float(item["sort_value"]), item["title"]),
    )
    sections.append(
        {
            "kind": "transcript",
            "label": EXPERT_RESOURCE_KIND_META["transcript"]["label"],
            "tone": EXPERT_RESOURCE_KIND_META["transcript"]["tone"],
            "items": transcript_items,
            "count": len(transcript_items),
        }
    )

    schedule_items: list[dict[str, Any]] = []
    for item in [build_schedule_card(store, raw_item) for raw_item in store.get("schedule_items", [])]:
        item_symbol = str(item.get("symbol") or "")
        symbol_match_rank = 0 if not preferred_symbols or item_symbol in preferred_symbols or not item_symbol else 1
        resource_ref = {"kind": "schedule", "symbol": "", "resource_id": item["id"]}
        token = build_expert_resource_token(resource_ref)
        schedule_items.append(
            {
                "token": token,
                "title": item.get("title") or "未命名日程",
                "summary": item.get("summary") or "",
                "display_time": f"{item.get('scheduled_date') or ''} · {item.get('display_time') or '时间待定'}",
                "symbol": item_symbol,
                "is_selected": token in selected_tokens,
                "match_rank": symbol_match_rank,
                "sort_value": schedule_item_sort_datetime(item).timestamp(),
                "status_label": item.get("status_label") or "",
                "status_tone": item.get("status_tone") or "pending",
                "url": url_for(
                    "schedule_page",
                    month=str(item.get("scheduled_date") or "")[:7],
                    date=item.get("scheduled_date"),
                    focus=item["id"],
                ),
            }
        )

    schedule_items.sort(
        key=lambda item: (int(item["match_rank"]), -float(item["sort_value"]), item["title"]),
    )
    sections.append(
        {
            "kind": "schedule",
            "label": EXPERT_RESOURCE_KIND_META["schedule"]["label"],
            "tone": EXPERT_RESOURCE_KIND_META["schedule"]["tone"],
            "items": schedule_items,
            "count": len(schedule_items),
        }
    )

    return sections


def build_expert_resource_preview_context(
    store: dict[str, Any],
    resource_ref: dict[str, Any],
) -> dict[str, Any]:
    resolved = resolve_expert_resource_ref(store, resource_ref)
    if resolved is None:
        abort(404)

    preview_kind = str(resolved.get("kind") or "")
    context: dict[str, Any] = {
        "preview_kind": preview_kind,
        "resource": resolved,
    }

    if preview_kind == "note":
        symbol = str(resolved.get("symbol") or "")
        entry = ensure_stock_entry(store, symbol)
        note = next(
            (item for item in entry.get("notes", []) if str(item.get("id") or "") == str(resolved.get("resource_id") or "")),
            None,
        )
        if note is None:
            abort(404)
        file_lookup = {item["id"]: item for item in entry.get("files", [])}
        source_file = file_lookup.get(str(note.get("source_file_id") or ""))
        context["note"] = {
            **note,
            "symbol": symbol,
            "display_title": note.get("title") or "未命名笔记",
            "display_created_at": note_display_time(note),
            "source_file": source_file,
            "source_file_name_display": note.get("source_file_name")
            or (str(source_file.get("original_name") or "") if source_file else ""),
            "tags": normalize_tag_list(note.get("tags", [])),
        }
        return context

    if preview_kind == "file":
        symbol = str(resolved.get("symbol") or "")
        file_entry = get_stock_file_entry(store, symbol, str(resolved.get("resource_id") or ""))
        return {
            **context,
            "stock_symbol": symbol,
            **build_stock_file_preview_context(store, symbol, file_entry),
        }

    if preview_kind == "transcript":
        transcript = get_transcript_entry(store, str(resolved.get("resource_id") or ""))
        context["transcript"] = build_transcript_card(transcript)
        return context

    if preview_kind == "schedule":
        schedule_item = get_schedule_item(store, str(resolved.get("resource_id") or ""))
        context["schedule_item"] = build_schedule_card(store, schedule_item)
        return context

    abort(404)


def build_expert_interview_card(interview: dict[str, Any]) -> dict[str, Any]:
    kind_meta = EXPERT_INTERVIEW_KIND_META.get(str(interview.get("kind") or ""), EXPERT_INTERVIEW_KIND_META["expert_call"])
    status_meta = EXPERT_INTERVIEW_STATUS_META.get(
        str(interview.get("status") or ""),
        EXPERT_INTERVIEW_STATUS_META["completed"],
    )
    summary = str(interview.get("summary") or "").strip()
    follow_up = str(interview.get("follow_up") or "").strip()

    return {
        **interview,
        "kind_label": kind_meta["label"],
        "status_label": status_meta["label"],
        "status_tone": status_meta["tone"],
        "display_date": str(interview.get("interview_date") or ""),
        "summary_preview": summarize_text_block(summary, limit=220) if summary else "",
        "follow_up_preview": summarize_text_block(follow_up, limit=220) if follow_up else "",
        "sort_value": coerce_sort_timestamp(interview.get("interview_date") or interview.get("updated_at")),
        "display_updated_at": format_iso_timestamp(str(interview.get("updated_at") or "")),
    }


def build_expert_card(expert: dict[str, Any], *, selected_expert_id: str = "") -> dict[str, Any]:
    category_meta = EXPERT_CATEGORY_META.get(str(expert.get("category") or ""), EXPERT_CATEGORY_META["industry"])
    stage_meta = EXPERT_STAGE_META.get(str(expert.get("stage") or ""), EXPERT_STAGE_META["watch"])
    identity_line = build_expert_identity_line(expert)
    interviews = [build_expert_interview_card(item) for item in expert.get("interviews", [])]
    interviews.sort(key=expert_interview_sort_key, reverse=True)
    latest_interview = interviews[0] if interviews else None
    related_symbols = expert.get("related_symbols", [])
    resource_count = len(expert.get("resource_refs", []))
    brief = summarize_text_block(
        str(expert.get("expertise") or "").strip()
        or str(expert.get("contact_notes") or "").strip()
        or identity_line
        or f"{category_meta['label']} · {stage_meta['label']}",
        limit=120,
    )

    return {
        **expert,
        "category_label": category_meta["label"],
        "category_tone": category_meta["tone"],
        "category_order": category_meta["order"],
        "stage_label": stage_meta["label"],
        "stage_tone": stage_meta["tone"],
        "stage_order": stage_meta["order"],
        "identity_line": identity_line,
        "brief": brief,
        "brief_full": (
            str(expert.get("expertise") or "").strip()
            or str(expert.get("contact_notes") or "").strip()
            or identity_line
            or f"{category_meta['label']} 路 {stage_meta['label']}"
        ),
        "related_symbols": related_symbols,
        "related_symbols_label": " · ".join(related_symbols),
        "interview_count": len(interviews),
        "resource_count": resource_count,
        "latest_interview_label": latest_interview["display_date"] if latest_interview else "暂无访谈",
        "display_updated_at": format_iso_timestamp(str(expert.get("updated_at") or "")),
        "is_selected": bool(selected_expert_id and expert["id"] == selected_expert_id),
        "url": url_for("experts_page", view="manage", expert=expert["id"]),
    }


def build_expert_overview_groups(experts: list[dict[str, Any]], *, selected_expert_id: str = "") -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in EXPERT_CATEGORY_META}
    for expert in experts:
        card = build_expert_card(expert, selected_expert_id=selected_expert_id)
        grouped.setdefault(card["category"], []).append(card)

    groups: list[dict[str, Any]] = []
    for category, meta in sorted(EXPERT_CATEGORY_META.items(), key=lambda item: item[1]["order"]):
        items = grouped.get(category, [])
        items.sort(
            key=lambda item: (
                int(item["stage_order"]),
                -(coerce_sort_timestamp(item.get("latest_interview_label")) or 0),
                -(coerce_sort_timestamp(item.get("updated_at")) or 0),
                item["name"].casefold(),
            )
        )
        groups.append(
            {
                "category": category,
                "label": meta["label"],
                "tone": meta["tone"],
                "count": len(items),
                "experts": items,
            }
        )

    return groups


def build_expert_stock_groups(experts: list[dict[str, Any]], *, selected_expert_id: str = "") -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    uncategorized: list[dict[str, Any]] = []

    for expert in experts:
        card = build_expert_card(expert, selected_expert_id=selected_expert_id)
        symbols = sorted(
            {
                str(symbol).strip().upper()
                for symbol in card.get("related_symbols", [])
                if str(symbol).strip()
            },
            key=str.casefold,
        )
        if symbols:
            for symbol in symbols:
                grouped[symbol].append(card)
        else:
            uncategorized.append(card)

    groups: list[dict[str, Any]] = []
    for symbol in sorted(grouped.keys(), key=str.casefold):
        items = grouped[symbol]
        items.sort(
            key=lambda item: (
                int(item["stage_order"]),
                -(coerce_sort_timestamp(item.get("latest_interview_label")) or 0),
                -(coerce_sort_timestamp(item.get("updated_at")) or 0),
                item["name"].casefold(),
            )
        )
        groups.append(
            {
                "symbol": symbol,
                "label": symbol,
                "tone": "info",
                "count": len(items),
                "experts": items,
            }
        )

    if uncategorized:
        uncategorized.sort(
            key=lambda item: (
                int(item["stage_order"]),
                -(coerce_sort_timestamp(item.get("latest_interview_label")) or 0),
                -(coerce_sort_timestamp(item.get("updated_at")) or 0),
                item["name"].casefold(),
            )
        )
        groups.append(
            {
                "symbol": "",
                "label": "未关联股票",
                "tone": "pending",
                "count": len(uncategorized),
                "experts": uncategorized,
            }
        )

    return groups


def build_expert_stats(experts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_count": len(experts),
        "active_count": sum(1 for item in experts if item.get("stage") in {"priority", "active"}),
        "priority_count": sum(1 for item in experts if item.get("stage") == "priority"),
        "interview_count": sum(len(item.get("interviews", [])) for item in experts),
        "planned_interview_count": sum(
            1
            for item in experts
            for interview in item.get("interviews", [])
            if interview.get("status") == "planned"
        ),
        "resource_count": sum(len(item.get("resource_refs", [])) for item in experts),
    }


def build_experts_page_context(store: dict[str, Any], *, selected_expert_id: str = "") -> dict[str, Any]:
    experts = list(store.get("experts", []))
    experts.sort(
        key=lambda item: (
            expert_stage_order(item.get("stage")),
            expert_category_order(item.get("category")),
            -(coerce_sort_timestamp(item.get("updated_at")) or 0),
            str(item.get("name") or "").casefold(),
        )
    )

    selected_expert = next((item for item in experts if item["id"] == selected_expert_id), None)
    if selected_expert is None and experts:
        selected_expert = next((item for item in experts if item.get("stage") != "archived"), experts[0])

    selected_card = build_expert_card(selected_expert, selected_expert_id=selected_expert["id"]) if selected_expert else None
    selected_interviews = (
        sorted(
            [build_expert_interview_card(item) for item in selected_expert.get("interviews", [])],
            key=expert_interview_sort_key,
            reverse=True,
        )
        if selected_expert
        else []
    )

    return {
        "expert_stats": build_expert_stats(experts),
        "expert_overview_groups": build_expert_overview_groups(
            experts,
            selected_expert_id=selected_expert["id"] if selected_expert else "",
        ),
        "expert_stock_groups": build_expert_stock_groups(
            experts,
            selected_expert_id=selected_expert["id"] if selected_expert else "",
        ),
        "selected_expert": selected_card,
        "selected_expert_raw": selected_expert,
        "selected_expert_interviews": selected_interviews,
        "selected_expert_resource_groups": build_expert_resource_groups(store, selected_expert) if selected_expert else [],
        "selected_expert_resource_catalog": build_expert_resource_catalog(store, selected_expert),
        "expert_category_options": [
            {"value": key, "label": meta["label"]}
            for key, meta in sorted(EXPERT_CATEGORY_META.items(), key=lambda item: item[1]["order"])
        ],
        "expert_stage_options": [
            {"value": key, "label": meta["label"]}
            for key, meta in sorted(EXPERT_STAGE_META.items(), key=lambda item: item[1]["order"])
        ],
        "expert_interview_kind_options": [
            {"value": key, "label": meta["label"]}
            for key, meta in sorted(EXPERT_INTERVIEW_KIND_META.items(), key=lambda item: item[1]["order"])
        ],
        "expert_interview_status_options": [
            {"value": key, "label": meta["label"]}
            for key, meta in sorted(EXPERT_INTERVIEW_STATUS_META.items(), key=lambda item: item[1]["order"])
        ],
    }


def build_stock_tag_summary(store: dict[str, Any], symbol: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    symbols = [symbol] if symbol else sorted(list_stock_symbols(store))
    for item_symbol in symbols:
        entry = ensure_stock_entry(store, item_symbol)
        items.extend(entry["notes"])
    if symbol:
        items.extend(record["file_entry"] for record in iter_stock_file_records(store, symbol_filter=symbol))
    else:
        items.extend(record["file_entry"] for record in iter_stock_file_records(store))

    transcripts = [
        transcript
        for transcript in store.get("transcripts", [])
        if not symbol or transcript_matches_symbol(transcript, symbol)
    ]
    items.extend(transcripts)

    return collect_tag_counts(items)


def build_stock_earnings_call_cards(entry: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = entry.get("earnings_calls", [])
    if not isinstance(raw_calls, list):
        raw_calls = []

    calls = [raw_call for raw_call in raw_calls if isinstance(raw_call, dict)]
    calls.sort(
        key=lambda item: (
            str(item.get("call_date") or item.get("published_at") or ""),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )

    cards: list[dict[str, Any]] = []
    for call in calls:
        quality_chips = build_stock_earnings_call_quality_chips(call)

        display_call_date = call.get("call_date") or ""
        if not display_call_date and call.get("published_at"):
            display_call_date = format_iso_timestamp(call.get("published_at"))

        cards.append(
            {
                **call,
                "display_title": call.get("title") or call.get("original_title") or "电话会议",
                "display_call_date": display_call_date or "待补充",
                "display_published_at": (
                    format_iso_timestamp(call.get("published_at")) if call.get("published_at") else "待补充"
                ),
                "reader_content_html": call.get("transcript_html")
                or plain_text_to_html(call.get("transcript_text") or ""),
                "summary_excerpt": call.get("summary_excerpt")
                or summarize_text_block(call.get("summary_text") or call.get("transcript_text") or ""),
                "quality_chips": quality_chips,
            }
        )

    return cards


def build_stock_earnings_call_quality_chips(call: dict[str, Any]) -> list[str]:
    chips: list[str] = []
    if call.get("is_complete"):
        chips.append("已校验正文")
    if call.get("has_question_section"):
        chips.append("含问答")
    if call.get("speaker_turn_count"):
        chips.append(f"{call['speaker_turn_count']} 轮发言")
    if call.get("word_count"):
        chips.append(f"{call['word_count']} 词")
    return chips


def build_stock_earnings_call_material_item(symbol: str, call: dict[str, Any]) -> dict[str, Any]:
    call_id = str(call.get("id") or "").strip()
    call_date = normalize_date_field(call.get("call_date")) or ""
    published_at = str(call.get("published_at") or "").strip()
    published_date = normalize_date_field(call.get("published_date")) or iso_to_date(published_at) or ""
    try:
        detail_url = url_for("stock_detail", symbol=symbol)
    except RuntimeError:
        detail_url = f"/stocks/{symbol}"
    if call_id:
        detail_url = f"{detail_url}#earnings-call-{call_id}"

    fiscal_year = max(0, int(call.get("fiscal_year") or 0))
    fiscal_quarter = max(0, int(call.get("fiscal_quarter") or 0))
    fiscal_label = ""
    if fiscal_year and fiscal_quarter:
        fiscal_label = f"FY{fiscal_year} Q{fiscal_quarter}"
    elif fiscal_year:
        fiscal_label = f"FY{fiscal_year}"
    elif fiscal_quarter:
        fiscal_label = f"Q{fiscal_quarter}"

    display_time = call_date
    if not display_time:
        display_time = format_iso_timestamp(published_at) if published_at else (published_date or "待补充")

    return {
        "symbol": symbol,
        "id": call_id,
        "title": str(call.get("title") or call.get("original_title") or "电话会议").strip()[:200],
        "original_title": str(call.get("original_title") or call.get("title") or "").strip()[:220],
        "call_date": call_date,
        "published_at": published_at,
        "published_date": published_date,
        "display_time": display_time,
        "sort_value": coerce_sort_timestamp(call_date or published_at or published_date),
        "summary": str(call.get("summary_excerpt") or "").strip()
        or summarize_text_block(call.get("summary_text") or call.get("transcript_text") or ""),
        "summary_text": trim_note_content(str(call.get("summary_text") or "").strip()),
        "transcript_text": trim_note_content(str(call.get("transcript_text") or "").strip()),
        "source_label": str(call.get("source_label") or "").strip()[:80],
        "source_url": str(call.get("source_url") or "").strip()[:600],
        "source_query_label": str(call.get("source_query_label") or "").strip()[:120],
        "quality_notes": [
            str(item).strip()[:120]
            for item in call.get("quality_notes", [])
            if str(item).strip()
        ],
        "quality_chips": build_stock_earnings_call_quality_chips(call),
        "is_complete": bool(call.get("is_complete")),
        "has_question_section": bool(call.get("has_question_section")),
        "speaker_turn_count": max(0, int(call.get("speaker_turn_count") or 0)),
        "word_count": max(0, int(call.get("word_count") or 0)),
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "fiscal_label": fiscal_label,
        "detail_url": detail_url,
        "detail_label": "打开电话会议",
        "activity_date": call_date or published_date or iso_to_date(published_at) or "",
    }


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


def fold_search_terms(terms: list[str]) -> list[str]:
    return [term.casefold() for term in terms if term]


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


def text_contains_all_terms(
    text: str,
    terms: list[str],
    *,
    text_casefolded: str | None = None,
    folded_terms: list[str] | None = None,
) -> bool:
    normalized_terms = folded_terms if folded_terms is not None else fold_search_terms(terms)
    if not normalized_terms:
        return True

    haystack = text_casefolded if text_casefolded is not None else text.casefold()
    return all(term in haystack for term in normalized_terms)


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
    folded_terms = fold_search_terms(terms)
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
            if terms and not text_contains_all_terms(
                search_text,
                terms,
                text_casefolded=search_text.casefold(),
                folded_terms=folded_terms,
            ):
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
            if terms and not text_contains_all_terms(
                search_text,
                terms,
                text_casefolded=search_text.casefold(),
                folded_terms=folded_terms,
            ):
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

        for call in build_stock_earnings_call_cards(entry):
            if selected_kind and selected_kind != "earnings_call":
                continue
            if normalized_symbol and symbol != normalized_symbol:
                continue
            if normalized_tag:
                continue

            search_text = " ".join(
                [
                    symbol,
                    str(call.get("display_title") or ""),
                    str(call.get("original_title") or ""),
                    str(call.get("transcript_text") or ""),
                    str(call.get("source_query_label") or ""),
                ]
            )
            if terms and not text_contains_all_terms(
                search_text,
                terms,
                text_casefolded=search_text.casefold(),
                folded_terms=folded_terms,
            ):
                continue

            results.append(
                {
                    "kind": "earnings_call",
                    "kind_label": SEARCH_KIND_META["earnings_call"]["label"],
                    "kind_tone": SEARCH_KIND_META["earnings_call"]["tone"],
                    "title": call["display_title"],
                    "summary": build_match_excerpt(
                        call.get("transcript_text") or "",
                        terms,
                        call["summary_excerpt"],
                    ),
                    "symbol": symbol,
                    "display_time": call.get("display_call_date") or call.get("display_published_at"),
                    "sort_value": coerce_sort_timestamp(call.get("call_date") or call.get("published_at")),
                    "tags": [],
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="earnings-calls",
                        item_kind="earnings_call",
                        item_id=str(call.get("id") or ""),
                        anchor=f"earnings-call-{call.get('id')}",
                    ),
                    "secondary_url": call.get("source_url") or "",
                    "secondary_label": "鍘熷鏉ユ簮",
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
        if terms and not text_contains_all_terms(
            search_text,
            terms,
            text_casefolded=search_text.casefold(),
            folded_terms=folded_terms,
        ):
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

    for schedule_item in store.get("schedule_items", []):
        if selected_kind and selected_kind != "schedule":
            continue
        tags = normalize_tag_list(schedule_item.get("tags", []))
        symbol = str(schedule_item.get("symbol") or "")
        search_text = " ".join(
            [
                symbol,
                str(schedule_item.get("company") or ""),
                str(schedule_item.get("title") or ""),
                str(schedule_item.get("note") or ""),
                str(schedule_item.get("location") or ""),
                " ".join(tags),
            ]
        )
        if normalized_symbol and symbol != normalized_symbol:
            continue
        if normalized_tag and not tag_match(tags, normalized_tag):
            continue
        if terms and not text_contains_all_terms(
            search_text,
            terms,
            text_casefolded=search_text.casefold(),
            folded_terms=folded_terms,
        ):
            continue

        schedule_date = str(schedule_item.get("scheduled_date") or "")
        results.append(
            {
                "kind": "schedule",
                "kind_label": SEARCH_KIND_META["schedule"]["label"],
                "kind_tone": SEARCH_KIND_META["schedule"]["tone"],
                "title": str(schedule_item.get("title") or "未命名日程"),
                "summary": build_match_excerpt(
                    " ".join(
                        [
                            str(schedule_item.get("note") or ""),
                            str(schedule_item.get("location") or ""),
                            str(schedule_item.get("company") or ""),
                        ]
                    ),
                    terms,
                    summarize_text_block(
                        str(schedule_item.get("note") or "")
                        or str(schedule_item.get("location") or "")
                        or build_schedule_time_label(schedule_item)
                    ),
                ),
                "symbol": symbol,
                "display_time": f"{schedule_date} · {build_schedule_time_label(schedule_item)}",
                "sort_value": schedule_item_sort_datetime(schedule_item).timestamp(),
                "tags": tags,
                "url": (
                    url_for("schedule_page", month=schedule_date[:7], date=schedule_date, focus=schedule_item["id"])
                    + f"#schedule-item-{schedule_item['id']}"
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
        content = str(report.get("content") or "") or read_report_text(REPORTS_DIR / report["filename"])
        combined_text = " ".join([report["title"], report["summary"], report["filename"], content])
        if normalized_symbol and report_symbol_pattern and not report_symbol_pattern.search(combined_text):
            continue
        if terms and not text_contains_all_terms(
            combined_text,
            terms,
            text_casefolded=combined_text.casefold(),
            folded_terms=folded_terms,
        ):
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
        "schedule_item_count": sum(1 for item in entries if item["item_type"] == "schedule_item"),
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
    earnings_calls = build_stock_earnings_call_cards(entry)
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
        "earnings_calls": earnings_calls,
        "earnings_call_sync": build_stock_earnings_call_sync_view(entry),
        "related_reports": related_reports,
        "timeline": build_stock_timeline(store, symbol, related_reports=related_reports),
        "tag_summary": build_stock_tag_summary(store, symbol)[:12],
        "created_label": format_iso_timestamp(entry.get("created_at")),
        "setup": build_stock_setup_view(symbol),
    }


def stock_upload_dir(symbol: str) -> Path:
    return STOCK_UPLOADS_DIR / symbol


def permanently_delete_trash_entry(trash_entry: dict[str, Any]) -> None:
    payload = trash_entry["payload"]
    if trash_entry["item_type"] == "file":
        symbol = stock_file_storage_symbol(payload, str(trash_entry.get("symbol") or ""))
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

    for record in iter_stock_file_records(store, symbol_filter=symbol_filter):
        file_entry = record["file_entry"]
        activity_date = iso_to_date(file_entry.get("uploaded_at"))
        if not activity_date:
            continue

        access_symbol = symbol_filter or record["storage_symbol"]
        file_id = str(file_entry.get("id") or "").strip()
        detail_url = url_for("stock_detail", symbol=access_symbol)
        download_url = ""
        if file_id:
            detail_url = f"{detail_url}#file-{file_id}"
            download_url = url_for("download_stock_file", symbol=access_symbol, file_id=file_id)

        entries.append(
            {
                "date": activity_date,
                "timestamp": str(file_entry.get("uploaded_at") or ""),
                "kind": "file",
                "kind_label": "文件",
                "symbol": access_symbol,
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

    for record in iter_stock_file_records(store, symbol_filter=symbol):
        file_entry = record["file_entry"]
        file_card = build_stock_file_card(store, record, access_symbol=symbol)
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
                "download_url": file_card["download_url"],
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


def build_stock_detail(store: dict[str, Any], symbol: str) -> dict[str, Any]:
    if symbol not in list_stock_symbols(store):
        abort(404)

    entry = ensure_stock_entry(store, symbol)
    notes = sorted(entry["notes"], key=lambda item: item["created_at"], reverse=True)
    files = sorted(
        [build_stock_file_card(store, record, access_symbol=symbol) for record in iter_stock_file_records(store, symbol_filter=symbol)],
        key=lambda item: str(item.get("uploaded_at") or ""),
        reverse=True,
    )
    transcripts = build_transcript_cards(store, symbol_filter=symbol)
    earnings_calls = build_stock_earnings_call_cards(entry)
    file_lookup = {str(file_entry.get("id") or ""): file_entry for file_entry in files}
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
        "files": files,
        "transcripts": transcripts,
        "earnings_calls": earnings_calls,
        "earnings_call_sync": build_stock_earnings_call_sync_view(entry),
        "related_reports": related_reports,
        "timeline": build_stock_timeline(store, symbol, related_reports=related_reports),
        "tag_summary": build_stock_tag_summary(store, symbol)[:12],
        "created_label": format_iso_timestamp(entry.get("created_at")),
        "setup": build_stock_setup_view(symbol),
    }


def get_stock_file_entry(store: dict[str, Any], symbol: str, file_id: str) -> dict[str, Any]:
    return get_stock_file_record(store, symbol, file_id)["file_entry"]


def build_stock_file_preview_context(
    store: dict[str, Any],
    symbol: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    file_entry = record["file_entry"]
    linked_note = get_stock_file_linked_note(store, record)
    original_name = str(file_entry.get("original_name") or "")
    file_path = stock_upload_dir(record["storage_symbol"]) / str(file_entry.get("stored_name") or "")
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
        "file_entry": build_stock_file_card(store, record, access_symbol=symbol),
        "preview_text": preview_text,
        "is_truncated": is_truncated,
        "preview_note_html": preview_note_html,
        "image_url": url_for("inline_stock_file", symbol=symbol, file_id=file_entry["id"])
        if is_image_previewable(original_name)
        else "",
    }


def get_transcript_entry(store: dict[str, Any], transcript_id: str) -> dict[str, Any]:
    for transcript in store.get("transcripts", []):
        if transcript["id"] == transcript_id:
            return transcript

    abort(404)


TRANSCRIPT_PDF_FONT_CACHE: str | None = None
TRANSCRIPT_PDF_FONT_CANDIDATES = [
    ("TranscriptPDFHei", Path(r"C:\Windows\Fonts\simhei.ttf")),
    ("TranscriptPDFKai", Path(r"C:\Windows\Fonts\simkai.ttf")),
    ("TranscriptPDFFang", Path(r"C:\Windows\Fonts\STFANGSO.TTF")),
    ("TranscriptPDFSong", Path(r"C:\Windows\Fonts\simsunb.ttf")),
]


def normalize_pdf_text(value: str) -> str:
    text = str(value or "")
    for source in ("\u2011", "\u2012", "\u2013", "\u2014", "\u2212", "\u00a0"):
        text = text.replace(source, "-" if source != "\u00a0" else " ")
    return text


def transcript_export_text(entry: dict[str, Any]) -> str:
    transcript_text = str(entry.get("transcript_text") or "").strip()
    if transcript_text:
        return normalize_pdf_text(transcript_text)

    transcript_html = str(entry.get("transcript_html") or "").strip()
    if transcript_html:
        return normalize_pdf_text(note_html_to_text(transcript_html))

    return normalize_pdf_text(TRANSCRIPT_PLACEHOLDER_COPY)


def ensure_transcript_pdf_font() -> str:
    global TRANSCRIPT_PDF_FONT_CACHE

    if TRANSCRIPT_PDF_FONT_CACHE:
        return TRANSCRIPT_PDF_FONT_CACHE

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ModuleNotFoundError as exc:
        raise RuntimeError("当前环境缺少 reportlab，暂时无法导出 PDF。") from exc

    for font_name, font_path in TRANSCRIPT_PDF_FONT_CANDIDATES:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            TRANSCRIPT_PDF_FONT_CACHE = font_name
            return font_name

    raise RuntimeError("当前电脑没有可用的中文字体文件，暂时无法导出 PDF。")


def build_transcript_pdf_buffer(entry: dict[str, Any]) -> tuple[io.BytesIO, str]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer
    except ModuleNotFoundError as exc:
        raise RuntimeError("当前环境缺少 reportlab，暂时无法导出 PDF。") from exc

    font_name = ensure_transcript_pdf_font()
    card = build_transcript_card(entry)
    transcript_text = transcript_export_text(entry)
    filename_stem = export_safe_name(card["display_title"], fallback=f"transcript-{entry['id']}")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=normalize_pdf_text(card["display_title"]),
        author="股票每日分析工作台",
    )

    palette = {
        "ink": colors.HexColor("#1f2f49"),
        "muted": colors.HexColor("#6b7a96"),
        "line": colors.HexColor("#dce4f4"),
        "accent": colors.HexColor("#3563d6"),
    }
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TranscriptPdfTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=20,
        leading=28,
        textColor=palette["ink"],
        alignment=TA_LEFT,
        spaceAfter=8,
    )
    meta_style = ParagraphStyle(
        "TranscriptPdfMeta",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.6,
        leading=14,
        textColor=palette["muted"],
        spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "TranscriptPdfBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=11.4,
        leading=19,
        textColor=palette["ink"],
        wordWrap="CJK",
        spaceAfter=8,
    )
    section_style = ParagraphStyle(
        "TranscriptPdfSection",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=10,
        leading=14,
        textColor=palette["accent"],
        spaceAfter=6,
    )

    support_lines = [
        f"会议日期：{normalize_pdf_text(card['meeting_date_label'])}",
        f"上传时间：{normalize_pdf_text(card['display_created_at'])}",
        f"状态：{normalize_pdf_text(card['status_label'])}",
    ]
    if card.get("linked_symbols"):
        support_lines.append(f"关联股票：{normalize_pdf_text(card['linked_symbols_label'])}")
    if card.get("original_name"):
        support_lines.append(f"源文件：{normalize_pdf_text(card['original_name'])}")

    story: list[Any] = [
        Paragraph(escape(normalize_pdf_text(card["display_title"])), title_style),
        Paragraph("<br/>".join(escape(line) for line in support_lines), meta_style),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=0.8, color=palette["line"], spaceBefore=2, spaceAfter=10),
        Paragraph("转录全文", section_style),
    ]

    for block in re.split(r"\n{2,}", transcript_text):
        compact = normalize_pdf_text(block).strip()
        if not compact:
            continue
        story.append(Paragraph("<br/>".join(escape(line) for line in compact.splitlines()), body_style))

    if len(story) <= 5:
        story.append(Paragraph(escape(normalize_pdf_text(TRANSCRIPT_PLACEHOLDER_COPY)), body_style))

    doc.build(story)
    buffer.seek(0)
    return buffer, f"{filename_stem}.pdf"


def build_navigation_context(
    *,
    active_page: str,
    reports: list[dict[str, Any]] | None = None,
    stock_store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    reports = reports if reports is not None else collect_reports()
    stock_store = stock_store if stock_store is not None else load_stock_store()
    nav_stock_search_options = []
    favorite_symbols = set(stock_store.get("favorites", []))
    for option in build_stock_selector_options(stock_store):
        symbol = option["symbol"]
        nav_stock_search_options.append(
            {
                **option,
                "detail_url": url_for("stock_detail", symbol=symbol),
                "is_favorite": symbol in favorite_symbols,
            }
        )

    return {
        "active_page": active_page,
        "nav_reports_count": len(reports),
        "nav_stock_count": len(list_stock_symbols(stock_store)),
        "nav_group_count": len(stock_store["groups"]),
        "nav_favorites_count": len(stock_store["favorites"]),
        "nav_transcript_count": len(stock_store.get("transcripts", [])),
        "nav_expert_count": len(stock_store.get("experts", [])),
        "nav_schedule_count": sum(
            1 for item in stock_store.get("schedule_items", []) if item.get("status") == "planned"
        ),
        "nav_trash_count": len(stock_store.get("trash", [])),
        "nav_stock_search_options": nav_stock_search_options,
    }


@app.get("/access")
def access_password_gate() -> str:
    if is_web_access_authenticated():
        return redirect(safe_next_url(request.args.get("next"), url_for("index")))

    next_url = safe_next_url(request.args.get("next"), url_for("index"))
    return render_template("access_gate.html", next_url=next_url)


@app.post("/access")
def access_password_submit():
    next_url = safe_next_url(request.form.get("next_url"), url_for("index"))
    if not WEB_ACCESS_PASSWORD_SIGNATURE:
        return redirect(next_url)

    submitted_password = str(request.form.get("password") or "")
    if not hmac.compare_digest(submitted_password, WEB_ACCESS_PASSWORD):
        flash("访问密码不对，请再试一次。", "error")
        return redirect(url_for("access_password_gate", next=next_url))

    session.permanent = True
    session[WEB_ACCESS_SESSION_KEY] = WEB_ACCESS_PASSWORD_SIGNATURE
    flash(f"访问验证已通过，当前浏览器 {WEB_ACCESS_REMEMBER_DAYS} 天内不用重复输入。", "success")
    return redirect(next_url)


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


def extract_mindmap_scope_request_payload(source: Any) -> dict[str, Any]:
    if not hasattr(source, "get"):
        return {}

    return {
        "use_stock_scope": source.get("use_stock_scope"),
        "scope_symbols": source.get("scope_symbols", ""),
        "scope_content_kinds": source.get("scope_content_kinds", ""),
        "use_date_scope": source.get("use_date_scope"),
        "scope_start_date": source.get("scope_start_date"),
        "scope_end_date": source.get("scope_end_date"),
        "scope_preview_month": source.get("scope_preview_month"),
        "scope_selected_date": source.get("scope_selected_date"),
    }


def save_mindmap_scope_draft(scope_settings: dict[str, Any] | None) -> None:
    if not scope_settings:
        session.pop(MINDMAP_SCOPE_DRAFT_SESSION_KEY, None)
        return

    session[MINDMAP_SCOPE_DRAFT_SESSION_KEY] = normalize_ai_scope_settings(scope_settings)
    session.modified = True


def load_mindmap_scope_draft(*, known_symbols: set[str] | None = None) -> dict[str, Any] | None:
    raw_scope = session.get(MINDMAP_SCOPE_DRAFT_SESSION_KEY)
    if not isinstance(raw_scope, dict):
        return None

    try:
        return normalize_ai_scope_settings(raw_scope, known_symbols=known_symbols)
    except ValueError:
        return None


def should_use_mindmap_scope_draft_fallback(
    submitted_scope: dict[str, Any],
    draft_scope: dict[str, Any] | None,
) -> bool:
    if not draft_scope:
        return False

    use_stock_scope = is_truthy_flag(submitted_scope.get("use_stock_scope"))
    submitted_symbols = normalize_stock_symbol_list(submitted_scope.get("scope_symbols", ""))
    if use_stock_scope and not submitted_symbols and draft_scope.get("use_stock_scope") and draft_scope.get("symbols"):
        return True

    submitted_content_kinds = normalize_ai_scope_content_kinds(submitted_scope.get("scope_content_kinds", ""))
    if not submitted_content_kinds and draft_scope.get("content_kinds"):
        return True

    use_date_scope = is_truthy_flag(submitted_scope.get("use_date_scope"))
    submitted_start_date = normalize_date_field(submitted_scope.get("scope_start_date"))
    submitted_end_date = normalize_date_field(submitted_scope.get("scope_end_date"))
    if use_date_scope and (
        not submitted_start_date
        or not submitted_end_date
        or submitted_start_date > submitted_end_date
    ):
        return True

    return False


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
    earnings_calls: list[dict[str, Any]] = []
    transcripts: list[dict[str, Any]] = []

    symbols = selected_symbols if selected_symbols else sorted(list_stock_symbols(store))
    for item_symbol in symbols:
        entry = ensure_stock_entry(store, item_symbol)
        note_lookup = {
            str(note.get("id") or "").strip(): note
            for note in entry["notes"]
            if str(note.get("id") or "").strip()
        }

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
                linked_note_id = str(file_entry.get("linked_note_id") or "").strip()
                linked_note = note_lookup.get(linked_note_id)

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
                        "content_text": str(linked_note.get("content_text") or "").strip() if linked_note else "",
                        "linked_note_id": linked_note_id,
                        "linked_note_title": str(file_entry.get("linked_note_title") or "").strip(),
                        "summary": summarize_text_block(file_entry.get("description") or file_entry.get("original_name") or ""),
                        "detail_url": detail_url,
                        "detail_label": "打开资料",
                        "download_url": download_url,
                        "file_type": detect_file_type_label(str(file_entry.get("original_name") or "")),
                        "activity_date": iso_to_date(file_entry.get("uploaded_at")) or "",
                    }
                )

        if "earnings_call" in selected_kind_set:
            for call in entry["earnings_calls"]:
                call_item = build_stock_earnings_call_material_item(item_symbol, call)
                if not in_scope_range(float(call_item.get("sort_value") or 0)):
                    continue
                earnings_calls.append(call_item)

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
    earnings_calls.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    transcripts.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)

    included_symbols = ordered_unique(
        selected_symbols
        + [item["symbol"] for item in notes if item.get("symbol")]
        + [item["symbol"] for item in files if item.get("symbol")]
        + [item["symbol"] for item in earnings_calls if item.get("symbol")]
        + [linked_symbol for item in transcripts for linked_symbol in item.get("linked_symbols", [])]
    )

    return {
        "selected_symbols": selected_symbols,
        "reports": report_items,
        "notes": notes,
        "files": files,
        "earnings_calls": earnings_calls,
        "transcripts": transcripts,
        "included_symbols": included_symbols,
        "report_count": len(report_items),
        "note_count": len(notes),
        "file_count": len(files),
        "earnings_call_count": len(earnings_calls),
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

    for call in materials["earnings_calls"]:
        activity_date = str(call.get("activity_date") or "")
        if not activity_date:
            continue
        entries.append(
            {
                "date": activity_date,
                "timestamp": call["call_date"] or call["published_at"],
                "kind": "earnings_call",
                "kind_label": "电话会议",
                "symbol": call["symbol"],
                "title": call["title"],
                "summary": call["summary"],
                "display_time": call["display_time"],
                "detail_url": call["detail_url"],
                "detail_label": call["detail_label"],
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
        day["earnings_call_count"] = day["kind_counter"].get("earnings_call", 0)
        day["transcript_count"] = day["kind_counter"].get("transcript", 0)
        day["report_count"] = day["kind_counter"].get("report", 0)
        day["kind_summary"] = [
            {"label": "笔记", "count": day["note_count"]},
            {"label": "文件", "count": day["file_count"]},
            {"label": "电话会议", "count": day["earnings_call_count"]},
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
        "earnings_call_count": sum(1 for item in matched_entries if item["kind"] == "earnings_call"),
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
        {"key": "earnings_call", "label": "电话会议", "count": kind_counter.get("earnings_call", 0)},
        {"key": "transcript", "label": "转录", "count": kind_counter.get("transcript", 0)},
    ]

    structure_parts = [f"{item['label']} {item['count']}" for item in kind_summary if item["count"]]
    return {
        "total_count": len(entries),
        "stock_count": len(symbol_values),
        "days_count": len(active_days),
        "note_count": kind_counter.get("note", 0),
        "file_count": kind_counter.get("file", 0),
        "earnings_call_count": kind_counter.get("earnings_call", 0),
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
        "earnings_call": [],
        "transcript": [],
    }
    for entry in entries:
        kind = str(entry.get("kind") or "")
        if kind in grouped:
            grouped[kind].append(entry)

    preferred_open_key = ""
    if detail_mode == "day":
        for key in ["note", "earnings_call", "file", "transcript", "report"]:
            if grouped[key]:
                preferred_open_key = key
                break

    groups: list[dict[str, Any]] = []
    for key, label in [
        ("note", "笔记"),
        ("file", "文件"),
        ("earnings_call", "电话会议"),
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
        "description": "提问时只会把这里定义范围内的报告、笔记、文件、管理层电话会议和转录交给 Codex。",
        "stock_label": stock_label,
        "time_label": time_label,
        "content_label": content_label,
        "has_filters": has_filters,
        "metrics": [
            {"label": "报告", "value": materials["report_count"]},
            {"label": "笔记", "value": materials["note_count"]},
            {"label": "文件", "value": materials["file_count"]},
            {"label": "电话会议", "value": materials["earnings_call_count"]},
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

    for call in materials["earnings_calls"]:
        events.append(
            {
                "kind_label": SEARCH_KIND_META["earnings_call"]["label"],
                "symbol_label": call["symbol"],
                "title": call["title"],
                "summary": call["summary"],
                "display_time": call["display_time"],
                "sort_value": float(call["sort_value"]),
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
        f"- 范围内电话会议数: {materials['earnings_call_count']}",
        f"- 范围内转录数: {materials['transcript_count']}",
        "",
        "## 站点概览",
        f"- 全站报告数量: {len(reports)}",
        f"- 全站股票数量: {len(list_stock_symbols(stock_store))}",
        f"- 分组数量: {len(stock_store['groups'])}",
        f"- 自选数量: {len(stock_store['favorites'])}",
        f"- 电话会议归档数量: {sum(len(item.get('earnings_calls', [])) for item in stock_store.get('stocks', {}).values() if isinstance(item, dict))}",
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
    grouped_earnings_calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_transcripts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in materials["notes"]:
        grouped_notes[note["symbol"]].append(note)
    for file_entry in materials["files"]:
        grouped_files[file_entry["symbol"]].append(file_entry)
    for call in materials["earnings_calls"]:
        grouped_earnings_calls[call["symbol"]].append(call)
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
        for call in grouped_earnings_calls.get(symbol, []):
            timeline.append(
                {
                    "kind": "earnings_call",
                    "kind_label": SEARCH_KIND_META["earnings_call"]["label"],
                    "kind_tone": SEARCH_KIND_META["earnings_call"]["tone"],
                    "title": call["title"],
                    "summary": call["summary"],
                    "timestamp": call["call_date"] or call["published_at"],
                    "sort_value": float(call["sort_value"]),
                    "display_time": call["display_time"],
                    "symbol_label": symbol,
                }
            )
        timeline.sort(key=lambda item: (float(item.get("sort_value") or 0), item.get("title") or ""), reverse=True)
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
                f"- 电话会议数: {len(grouped_earnings_calls.get(symbol, []))}",
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
        for call in grouped_earnings_calls.get(symbol, [])[:8]:
            lines.extend(
                [
                    f"#### 电话会议: {call['title']}",
                    f"- 日期: {call['display_time']}",
                    f"- 财季: {call['fiscal_label'] or '待补充'}",
                    f"- 来源: {call['source_label'] or '未标注'}",
                    f"- 质量: {'；'.join(call['quality_chips']) or '常规正文'}",
                    trim_note_content((call.get('transcript_text') or call['summary'])[:12000]),
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


def trim_text_for_prompt(text: str, *, limit: int, note: str) -> str:
    normalized = str(text or "").strip()
    capped_limit = max(int(limit or 0), 2000)
    if len(normalized) <= capped_limit:
        return normalized
    return normalized[:capped_limit].rstrip() + note


def mindmap_knowledge_text_for_step(knowledge_text: str, *, step_slug: str) -> str:
    step_limit = {
        "plan": min(MINDMAP_PLAN_KNOWLEDGE_CHAR_LIMIT, AI_PROMPT_KNOWLEDGE_CHAR_LIMIT),
        "mindmap": min(MINDMAP_FINAL_KNOWLEDGE_CHAR_LIMIT, AI_PROMPT_KNOWLEDGE_CHAR_LIMIT),
        "repair": min(MINDMAP_REPAIR_KNOWLEDGE_CHAR_LIMIT, AI_PROMPT_KNOWLEDGE_CHAR_LIMIT),
    }.get(step_slug, AI_PROMPT_KNOWLEDGE_CHAR_LIMIT)
    step_label = {
        "plan": "计划阶段正文已截短，优先依据上方时间线、比较轴和冲突线索搭骨架。",
        "mindmap": "正式成图阶段正文已截短，优先依据已给出的骨架、时间线和高权重证据补全结果。",
        "repair": "修复阶段正文已截短，请优先修正当前校验失败点。",
    }.get(step_slug, "当前阶段正文已截短，请优先依据上方内容作答。")
    return trim_text_for_prompt(
        knowledge_text,
        limit=step_limit,
        note=f"\n\n[知识包正文过长，{step_label}]",
    )


def compute_mindmap_step_timeout_seconds(
    *,
    step_slug: str,
    reasoning_effort: str,
    prompt_text: str,
) -> int:
    base_timeout = max(int(AI_CODEX_TIMEOUT_SECONDS or 0), 60)
    max_timeout = max(base_timeout, int(MINDMAP_MAX_STEP_TIMEOUT_SECONDS or base_timeout))
    reasoning_multiplier = {
        "low": 1.0,
        "medium": 1.0,
        "high": 1.2,
        "xhigh": 1.55,
    }.get(str(reasoning_effort or "").strip().lower(), 1.0)
    step_multiplier = {
        "plan": 1.15,
        "mindmap": 1.25,
        "repair": 1.0,
    }.get(step_slug, 1.0)
    prompt_length = len(str(prompt_text or ""))
    prompt_multiplier = 1.0
    if prompt_length >= 32000:
        prompt_multiplier = 1.18
    elif prompt_length >= 24000:
        prompt_multiplier = 1.1
    timeout_seconds = int(round(base_timeout * reasoning_multiplier * step_multiplier * prompt_multiplier))
    return max(base_timeout, min(timeout_seconds, max_timeout))


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def serialize_stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_mindmap_material_body(value: str, *, limit: int = 12_000) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + " ..."


def compact_mindmap_similarity_text(value: str, *, limit: int = 1_600) -> str:
    compact = re.sub(r"\s+", "", normalize_mindmap_material_body(value, limit=limit)).lower()
    return compact[:limit]


def build_mindmap_similarity_tokens(value: str) -> set[str]:
    compact = compact_mindmap_similarity_text(value)
    if not compact:
        return set()
    if len(compact) <= 3:
        return {compact}
    return {
        compact[index : index + 3]
        for index in range(min(len(compact) - 2, 360))
        if compact[index : index + 3]
    }


def detect_mindmap_material_density(value: str) -> float:
    text = normalize_mindmap_material_body(value, limit=4_000)
    if not text:
        return 0.0
    meaningful_chunks = [
        chunk
        for chunk in re.split(r"[。！？!?\n；;]+", text)
        if len(re.sub(r"\s+", "", chunk)) >= 12
    ]
    unique_chars = len(set(re.sub(r"\s+", "", text[:800])))
    chunk_score = min(len(meaningful_chunks), 8) / 8
    unique_score = min(unique_chars, 220) / 220
    return round((chunk_score * 0.55) + (unique_score * 0.45), 4)


def build_mindmap_material_items(materials: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    for report in materials.get("reports", []):
        filename = str(report.get("filename") or "").strip()
        if not filename:
            continue
        report_path = REPORTS_DIR / filename
        try:
            report_text = read_report_text(report_path)
        except OSError:
            report_text = ""
        body_text = normalize_mindmap_material_body(report_text, limit=9_000)
        summary = re.sub(r"\s+", " ", str(report.get("summary") or "").strip())[:320]
        items.append(
            {
                "source_key": f"report:{filename}",
                "kind": "report",
                "kind_label": "日报",
                "title": str(report.get("title") or filename).strip()[:160],
                "summary": summary,
                "body_text": body_text,
                "activity_date": normalize_date_field(report.get("activity_date")) or "",
                "display_time": str(report.get("report_date") or "").strip(),
                "sort_value": float(report.get("sort_value") or 0),
                "symbols": normalize_stock_symbol_list(report.get("matched_symbols", []))[:10],
                "detail_url": str(report.get("detail_url") or "").strip(),
            }
        )

    for note in materials.get("notes", []):
        note_id = str(note.get("id") or "").strip()
        symbol = str(note.get("symbol") or "").strip().upper()
        body_text = normalize_mindmap_material_body(note.get("content_text") or "", limit=7_000)
        items.append(
            {
                "source_key": f"note:{symbol}:{note_id or sha256_text(str(note.get('created_at') or ''))[:8]}",
                "kind": "note",
                "kind_label": "笔记",
                "title": str(note.get("title") or "未命名笔记").strip()[:160],
                "summary": re.sub(r"\s+", " ", str(note.get("summary") or "").strip())[:320],
                "body_text": body_text,
                "activity_date": normalize_date_field(note.get("activity_date")) or "",
                "display_time": str(note.get("display_time") or "").strip(),
                "sort_value": float(note.get("sort_value") or 0),
                "symbols": normalize_stock_symbol_list([symbol])[:10],
                "detail_url": str(note.get("detail_url") or "").strip(),
            }
        )

    for file_entry in materials.get("files", []):
        file_id = str(file_entry.get("id") or "").strip()
        symbol = str(file_entry.get("symbol") or "").strip().upper()
        linked_note_text = str(file_entry.get("content_text") or "").strip()
        description = str(file_entry.get("description") or "").strip()
        body_text = linked_note_text or description or str(file_entry.get("title") or "")
        items.append(
            {
                "source_key": f"file:{symbol}:{file_id or sha256_text(str(file_entry.get('uploaded_at') or ''))[:8]}",
                "kind": "file",
                "kind_label": "文件",
                "title": str(file_entry.get("title") or "已上传文件").strip()[:160],
                "summary": re.sub(r"\s+", " ", str(file_entry.get("summary") or description).strip())[:320],
                "body_text": normalize_mindmap_material_body(body_text, limit=6_000),
                "activity_date": normalize_date_field(file_entry.get("activity_date")) or "",
                "display_time": str(file_entry.get("display_time") or "").strip(),
                "sort_value": float(file_entry.get("sort_value") or 0),
                "symbols": normalize_stock_symbol_list([symbol])[:10],
                "detail_url": str(file_entry.get("detail_url") or "").strip(),
            }
        )

    for call in materials.get("earnings_calls", []):
        call_id = str(call.get("id") or "").strip()
        symbol = str(call.get("symbol") or "").strip().upper()
        items.append(
            {
                "source_key": f"earnings_call:{symbol}:{call_id or sha256_text(str(call.get('call_date') or call.get('published_at') or ''))[:8]}",
                "kind": "earnings_call",
                "kind_label": SEARCH_KIND_META["earnings_call"]["label"],
                "title": str(call.get("title") or "电话会议").strip()[:160],
                "summary": re.sub(r"\s+", " ", str(call.get("summary") or "").strip())[:320],
                "body_text": normalize_mindmap_material_body(call.get("transcript_text") or "", limit=10_500),
                "activity_date": normalize_date_field(call.get("activity_date")) or "",
                "display_time": str(call.get("display_time") or "").strip(),
                "sort_value": float(call.get("sort_value") or 0),
                "symbols": normalize_stock_symbol_list([symbol])[:10],
                "detail_url": str(call.get("detail_url") or "").strip(),
            }
        )

    for transcript in materials.get("transcripts", []):
        transcript_id = str(transcript.get("id") or "").strip()
        symbols = normalize_stock_symbol_list(transcript.get("linked_symbols", []))[:10]
        items.append(
            {
                "source_key": f"transcript:{transcript_id or sha256_text(str(transcript.get('created_at') or ''))[:8]}",
                "kind": "transcript",
                "kind_label": "转录",
                "title": str(transcript.get("title") or "会议转录").strip()[:160],
                "summary": re.sub(r"\s+", " ", str(transcript.get("summary") or "").strip())[:320],
                "body_text": normalize_mindmap_material_body(transcript.get("transcript_text") or "", limit=10_000),
                "activity_date": normalize_date_field(transcript.get("activity_date")) or "",
                "display_time": str(transcript.get("display_time") or "").strip(),
                "sort_value": float(transcript.get("sort_value") or 0),
                "symbols": symbols,
                "detail_url": str(transcript.get("detail_url") or "").strip(),
            }
        )

    return items


def score_mindmap_material(item: dict[str, Any], *, latest_sort_value: float) -> dict[str, Any]:
    combined_text = " ".join(
        value
        for value in [
            item.get("title"),
            item.get("summary"),
            item.get("body_text"),
        ]
        if str(value or "").strip()
    )
    normalized_text = normalize_mindmap_material_body(combined_text, limit=10_000)
    evidence_hits = len({match.lower() for match in MINDMAP_EVIDENCE_HINT_PATTERN.findall(normalized_text[:3_600])})
    lowered = normalized_text.casefold()
    conflict_hits = sum(1 for token in MINDMAP_CONFLICT_HINTS if token in lowered)
    density_score = detect_mindmap_material_density(normalized_text)
    recency_boost = 0.0
    if latest_sort_value > 0 and float(item.get("sort_value") or 0) > 0:
        age_days = max(0.0, (latest_sort_value - float(item.get("sort_value") or 0)) / 86_400)
        recency_boost = max(0.0, 1 - (age_days / max(MINDMAP_RECENT_WINDOW_DAYS, 1))) * 0.42
    evidence_boost = min(evidence_hits, 4) * 0.18
    conflict_boost = min(conflict_hits, 3) * 0.22
    base_priority = float(MINDMAP_KIND_PRIORITY.get(str(item.get("kind") or ""), 0.8))
    low_signal_penalty = 0.38 if density_score < 0.16 and evidence_hits == 0 and conflict_hits == 0 else 0.0
    priority_score = round(
        base_priority + density_score + recency_boost + evidence_boost + conflict_boost - low_signal_penalty,
        4,
    )
    return {
        **item,
        "normalized_text": normalized_text,
        "similarity_tokens": build_mindmap_similarity_tokens(normalized_text),
        "content_digest": sha256_text(normalized_text[:6_000]),
        "density_score": density_score,
        "evidence_hits": evidence_hits,
        "conflict_hits": conflict_hits,
        "recency_boost": round(recency_boost, 4),
        "evidence_boost": round(evidence_boost, 4),
        "conflict_boost": round(conflict_boost, 4),
        "priority_score": priority_score,
    }


def mindmap_material_is_low_signal(item: dict[str, Any]) -> bool:
    body_length = len(str(item.get("normalized_text") or ""))
    summary_length = len(str(item.get("summary") or ""))
    if body_length >= 90 or summary_length >= 60:
        return False
    if int(item.get("evidence_hits") or 0) > 0 or int(item.get("conflict_hits") or 0) > 0:
        return False
    return float(item.get("density_score") or 0) < 0.18


def compute_mindmap_material_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    if left.get("content_digest") == right.get("content_digest"):
        return 1.0
    left_tokens = left.get("similarity_tokens") or set()
    right_tokens = right.get("similarity_tokens") or set()
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    if union <= 0:
        return 0.0
    return intersection / union


def mindmap_material_duplicate_reason(candidate: dict[str, Any], keeper: dict[str, Any]) -> str | None:
    if candidate.get("content_digest") == keeper.get("content_digest"):
        return "exact"
    similarity = compute_mindmap_material_similarity(candidate, keeper)
    same_kind = str(candidate.get("kind") or "") == str(keeper.get("kind") or "")
    symbol_overlap = set(candidate.get("symbols") or []) & set(keeper.get("symbols") or [])
    if similarity >= 0.92 and (same_kind or symbol_overlap):
        return "near_duplicate"
    candidate_summary = re.sub(r"\s+", " ", str(candidate.get("summary") or "").strip())
    keeper_summary = re.sub(r"\s+", " ", str(keeper.get("summary") or "").strip())
    if candidate_summary and candidate_summary == keeper_summary and (same_kind or symbol_overlap):
        return "same_view"
    return None


def curate_mindmap_materials(materials: dict[str, Any]) -> dict[str, Any]:
    raw_items = build_mindmap_material_items(materials)
    latest_sort_value = max((float(item.get("sort_value") or 0) for item in raw_items), default=0.0)
    scored_items = [
        score_mindmap_material(item, latest_sort_value=latest_sort_value)
        for item in raw_items
    ]
    scored_items.sort(
        key=lambda item: (
            float(item.get("priority_score") or 0),
            float(item.get("sort_value") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    compressed_pairs: list[dict[str, str]] = []
    dropped_low_signal: list[dict[str, Any]] = []
    unselected_overflow: list[dict[str, Any]] = []

    for item in scored_items:
        if mindmap_material_is_low_signal(item):
            dropped_low_signal.append(item)
            continue
        duplicate_reason = next(
            (
                reason
                for keeper in selected
                if (reason := mindmap_material_duplicate_reason(item, keeper)) is not None
            ),
            None,
        )
        if duplicate_reason is not None:
            keeper = next(
                keeper for keeper in selected if mindmap_material_duplicate_reason(item, keeper) is not None
            )
            keeper.setdefault("compressed_duplicates", []).append(
                {
                    "source_key": str(item.get("source_key") or ""),
                    "title": str(item.get("title") or ""),
                    "kind_label": str(item.get("kind_label") or ""),
                    "activity_date": str(item.get("activity_date") or ""),
                    "reason": duplicate_reason,
                }
            )
            compressed_pairs.append(
                {
                    "source_key": str(item.get("source_key") or ""),
                    "keeper_source_key": str(keeper.get("source_key") or ""),
                    "reason": duplicate_reason,
                }
            )
            continue
        if len(selected) >= MINDMAP_MAX_CURATED_SOURCES:
            unselected_overflow.append(item)
            continue
        selected.append(item)

    for index, item in enumerate(selected, start=1):
        item["source_ref"] = f"M{index:02d}"
        flags: list[str] = []
        if float(item.get("recency_boost") or 0) >= 0.12:
            flags.append("recent")
        if float(item.get("evidence_boost") or 0) >= 0.18:
            flags.append("strong_evidence")
        if float(item.get("conflict_boost") or 0) >= 0.22:
            flags.append("conflict")
        if float(item.get("density_score") or 0) >= 0.55:
            flags.append("dense")
        item["weight_flags"] = flags

    selected_manifest = [
        {
            "source_ref": item.get("source_ref"),
            "source_key": item.get("source_key"),
            "kind": item.get("kind"),
            "title": item.get("title"),
            "activity_date": item.get("activity_date"),
            "symbols": item.get("symbols", []),
            "weight_flags": item.get("weight_flags", []),
            "priority_score": item.get("priority_score"),
        }
        for item in selected
    ]
    raw_manifest = [
        {
            "source_key": item.get("source_key"),
            "kind": item.get("kind"),
            "title": item.get("title"),
            "activity_date": item.get("activity_date"),
            "content_digest": item.get("content_digest"),
        }
        for item in scored_items
    ]
    return {
        "items": selected,
        "all_items": scored_items,
        "compressed_pairs": compressed_pairs,
        "dropped_low_signal": dropped_low_signal,
        "overflow_items": unselected_overflow,
        "raw_manifest": raw_manifest,
        "selected_manifest": selected_manifest,
        "selected_ref_set": {str(item.get("source_ref") or "") for item in selected if item.get("source_ref")},
        "stats": {
            "raw_material_count": len(raw_items),
            "selected_material_count": len(selected),
            "duplicate_compressed_count": len(compressed_pairs),
            "low_signal_dropped_count": len(dropped_low_signal),
            "overflow_count": len(unselected_overflow),
            "recent_boosted_count": sum(1 for item in selected if "recent" in item.get("weight_flags", [])),
            "strong_evidence_boosted_count": sum(1 for item in selected if "strong_evidence" in item.get("weight_flags", [])),
            "conflict_boosted_count": sum(1 for item in selected if "conflict" in item.get("weight_flags", [])),
        },
    }


def build_mindmap_weight_flag_labels(flags: list[str]) -> list[str]:
    mapping = {
        "recent": "近期资料",
        "strong_evidence": "强证据",
        "conflict": "存在冲突/对冲",
        "dense": "信息密度高",
    }
    return [mapping[item] for item in flags if item in mapping]


def build_mindmap_research_bundle(
    record_id: str,
    *,
    scope_summary: dict[str, Any],
    materials: dict[str, Any],
    curated: dict[str, Any],
) -> Path:
    bundle_path = MINDMAP_CONTEXT_DIR / f"{record_id}-research-bundle.md"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    stats = curated.get("stats", {})
    selected_items = curated.get("items", [])
    timeline_items = sorted(
        selected_items,
        key=lambda item: (str(item.get("activity_date") or ""), float(item.get("sort_value") or 0)),
    )

    lines = [
        "# 研究导图知识包",
        "",
        "这份文件由网页后端自动生成，供研究导图的两步式结构化整理使用。",
        "",
        "## 当前范围",
        f"- 生成时间: {now_iso()}",
        f"- {scope_summary.get('stock_label') or '股票范围：全站'}",
        f"- {scope_summary.get('time_label') or '时间窗口：不限'}",
        f"- {scope_summary.get('content_label') or '资料类型：日报；笔记；文件；电话会议；转录'}",
        f"- 原始资料数: {stats.get('raw_material_count', 0)}",
        f"- 入选资料数: {stats.get('selected_material_count', 0)}",
        f"- 压缩重复资料: {stats.get('duplicate_compressed_count', 0)}",
        f"- 丢弃低信息资料: {stats.get('low_signal_dropped_count', 0)}",
        "",
        "## 生成侧重点",
        "- 导图必须同时表达主题结构、资料互补/冲突关系和时间演化。",
        "- 如果范围里包含电话会议，要把它视作管理层原话/最新口径，与日报、笔记和其他转录交叉验证。",
        "- 已对重复观点、重复电话会议/转录和低信息密度资料做过压缩；模型应优先参考入选资料，不要把重复内容当成额外证据。",
        "- 已提高近期资料、强证据资料、存在冲突/对冲资料的权重；最终结论仍需按证据强弱决定。",
        "",
    ]

    if timeline_items:
        lines.append("## 按时间排序的入选资料")
        for item in timeline_items:
            symbol_label = " / ".join(item.get("symbols", [])) or "未限定股票"
            lines.extend(
                [
                    f"- {item.get('activity_date') or '无日期'} | {item['source_ref']} | {item.get('kind_label') or '资料'} | {item.get('title') or '未命名'}",
                    f"  股票: {symbol_label}",
                ]
            )
        lines.append("")

    if selected_items:
        lines.append("## 入选资料正文")
        for item in selected_items:
            flag_labels = build_mindmap_weight_flag_labels(item.get("weight_flags", []))
            excerpt = trim_note_content(str(item.get("normalized_text") or ""), limit=1_300)
            lines.extend(
                [
                    f"### {item['source_ref']} | {item.get('kind_label') or '资料'} | {item.get('title') or '未命名'}",
                    f"- source_key: {item.get('source_key') or ''}",
                    f"- 日期: {item.get('activity_date') or item.get('display_time') or '无'}",
                    f"- 股票: {' / '.join(item.get('symbols', [])) or '未限定'}",
                    f"- 权重标签: {'；'.join(flag_labels) or '常规'}",
                    f"- 摘要: {item.get('summary') or '无'}",
                    "",
                    excerpt or "（正文为空）",
                    "",
                ]
            )
            duplicates = item.get("compressed_duplicates", [])
            if duplicates:
                lines.append("合并的近似资料：")
                for duplicate in duplicates[:6]:
                    lines.append(
                        f"- {duplicate.get('kind_label') or '资料'} | {duplicate.get('title') or '未命名'} | "
                        f"{duplicate.get('activity_date') or '无日期'} | 原因: {duplicate.get('reason') or '近似重复'}"
                    )
                lines.append("")
    else:
        lines.extend(["## 入选资料正文", "- 当前没有足够资料进入导图生成。", ""])

    if curated.get("dropped_low_signal"):
        lines.append("## 已压缩的低信息资料")
        for item in curated.get("dropped_low_signal", [])[:12]:
            lines.append(
                f"- {item.get('kind_label') or '资料'} | {item.get('title') or '未命名'} | "
                f"{item.get('activity_date') or '无日期'}"
            )
        lines.append("")

    bundle_path.write_text("\n".join(lines), encoding="utf-8")
    return bundle_path


def build_mindmap_reproducibility_fingerprint(
    *,
    scope_settings: dict[str, Any],
    scope_summary: dict[str, Any],
    materials: dict[str, Any],
    curated: dict[str, Any],
    knowledge_text: str,
    bundle_path: Path,
) -> dict[str, Any]:
    stats = curated.get("stats", {})
    selected_sources = curated.get("selected_manifest", [])[:36]
    return {
        "generated_at": now_iso(),
        "pipeline_version": MINDMAP_PIPELINE_VERSION,
        "prompt_version": MINDMAP_PROMPT_VERSION,
        "schema_version": MINDMAP_SCHEMA_VERSION,
        "bundle_name": bundle_path.name,
        "scope_digest": sha256_text(serialize_stable_json(scope_settings)),
        "scope_summary_digest": sha256_text(serialize_stable_json(scope_summary)),
        "material_digest": sha256_text(serialize_stable_json(curated.get("raw_manifest", []))),
        "knowledge_digest": sha256_text(knowledge_text),
        "raw_material_count": int(stats.get("raw_material_count") or 0),
        "selected_material_count": int(stats.get("selected_material_count") or 0),
        "duplicate_compressed_count": int(stats.get("duplicate_compressed_count") or 0),
        "low_signal_dropped_count": int(stats.get("low_signal_dropped_count") or 0),
        "recent_boosted_count": int(stats.get("recent_boosted_count") or 0),
        "strong_evidence_boosted_count": int(stats.get("strong_evidence_boosted_count") or 0),
        "conflict_boosted_count": int(stats.get("conflict_boosted_count") or 0),
        "selected_sources": selected_sources,
        "validation": {
            "warnings": [],
            "errors": [],
            "repair_attempted": False,
        },
        "plan_digest": "",
        "final_digest": "",
        "material_selection_digest": sha256_text(serialize_stable_json(selected_sources)),
        "material_mix": {
            "report_count": int(materials.get("report_count") or 0),
            "note_count": int(materials.get("note_count") or 0),
            "file_count": int(materials.get("file_count") or 0),
            "earnings_call_count": int(materials.get("earnings_call_count") or 0),
            "transcript_count": int(materials.get("transcript_count") or 0),
        },
    }


def build_mindmap_selected_source_roster_lines(selected_sources: list[dict[str, Any]]) -> str:
    if not selected_sources:
        return "- 当前没有入选来源引用。"
    return "\n".join(
        (
            f"- {str(source.get('source_ref') or '').strip()}: "
            f"{str(source.get('kind') or '').strip() or 'source'} | "
            f"{str(source.get('activity_date') or '').strip() or '无日期'} | "
            f"{str(source.get('title') or '').strip() or '未命名'} | "
            f"标签: {'/'.join(source.get('weight_flags', [])) or '常规'}"
        )
        for source in selected_sources
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
        "9. 如果知识包里包含管理层电话会议，优先把它视作管理层原话/最新口径，并和日报、笔记、会议转录交叉验证。\n"
        "10. 回答时尽量分成：结论 / 依据 / 提醒或遗漏点 / 下一步建议。\n\n"
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


def normalize_mindmap_scope_summary(raw_summary: Any) -> dict[str, Any]:
    source = raw_summary if isinstance(raw_summary, dict) else {}
    metrics: list[dict[str, Any]] = []
    for raw_metric in source.get("metrics", []) if isinstance(source.get("metrics"), list) else []:
        if not isinstance(raw_metric, dict):
            continue
        label = str(raw_metric.get("label") or "").strip()[:20]
        if not label:
            continue
        try:
            value = max(0, int(raw_metric.get("value") or 0))
        except (TypeError, ValueError):
            value = 0
        metrics.append({"label": label, "value": value})

    return {
        "headline": str(source.get("headline") or "").strip()[:120],
        "description": str(source.get("description") or "").strip()[:240],
        "stock_label": str(source.get("stock_label") or "").strip()[:240],
        "time_label": str(source.get("time_label") or "").strip()[:120],
        "content_label": str(source.get("content_label") or "").strip()[:120],
        "has_filters": bool(source.get("has_filters")),
        "metrics": metrics,
    }


def build_mindmap_seed_title(scope_settings: dict[str, Any]) -> str:
    symbols = normalize_stock_symbol_list(scope_settings.get("symbols"))
    if symbols:
        label = " / ".join(symbols[:3])
        if len(symbols) > 3:
            label += " 等"
    else:
        label = "全站资料"

    if scope_settings.get("use_date_scope") and scope_settings.get("start_date") and scope_settings.get("end_date"):
        if scope_settings["start_date"] == scope_settings["end_date"]:
            return f"{label} {scope_settings['start_date']} 导图"
        return f"{label} {scope_settings['start_date']} 至 {scope_settings['end_date']} 导图"

    return f"{label} 研究导图"


def normalize_mindmap_source_refs(raw_items: Any, *, limit: int = 6, valid_source_refs: set[str] | None = None) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        ref = re.sub(r"[^A-Za-z0-9:-]+", "", str(raw_item or "").strip()).upper()[:24]
        if not ref or ref in seen:
            continue
        if valid_source_refs is not None and ref not in valid_source_refs:
            continue
        seen.add(ref)
        refs.append(ref)
    return refs[:limit]


def normalize_mindmap_confidence(raw_value: Any) -> str:
    value = str(raw_value or "").strip().lower()
    if value in {"low", "medium", "high"}:
        return value
    return "medium"


def normalize_mindmap_node(
    raw_node: Any,
    *,
    existing_ids: set[str],
    depth: int = 0,
    valid_source_refs: set[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw_node, dict) or depth > 4:
        return None

    label = re.sub(r"\s+", " ", str(raw_node.get("label") or "").strip())[:80]
    if not label:
        return None

    node_id = ensure_unique_id(str(raw_node.get("id") or "").strip(), existing_ids, length=8)
    existing_ids.add(node_id)
    summary = re.sub(r"\s+", " ", str(raw_node.get("summary") or "").strip())[:280]
    raw_evidence = raw_node.get("evidence", [])
    evidence = []
    for raw_item in raw_evidence if isinstance(raw_evidence, list) else []:
        item = re.sub(r"\s+", " ", str(raw_item or "").strip())[:180]
        if item:
            evidence.append(item)
    raw_time_signals = raw_node.get("time_signals", [])
    time_signals = []
    for raw_item in raw_time_signals if isinstance(raw_time_signals, list) else []:
        item = re.sub(r"\s+", " ", str(raw_item or "").strip())[:180]
        if item:
            time_signals.append(item)
    raw_source_notes = raw_node.get("source_notes", [])
    source_notes = []
    for raw_item in raw_source_notes if isinstance(raw_source_notes, list) else []:
        item = re.sub(r"\s+", " ", str(raw_item or "").strip())[:180]
        if item:
            source_notes.append(item)
    raw_children = raw_node.get("children", [])
    children = [
        child
        for raw_child in raw_children[:8] if isinstance(raw_children, list)
        if (
            child := normalize_mindmap_node(
                raw_child,
                existing_ids=existing_ids,
                depth=depth + 1,
                valid_source_refs=valid_source_refs,
            )
        ) is not None
    ]

    return {
        "id": node_id,
        "label": label,
        "kind": str(raw_node.get("kind") or "topic").strip().lower()[:30] or "topic",
        "summary": summary,
        "evidence": evidence[:3],
        "time_signals": time_signals[:3],
        "source_notes": source_notes[:3],
        "confidence": normalize_mindmap_confidence(raw_node.get("confidence")),
        "source_refs": normalize_mindmap_source_refs(
            raw_node.get("source_refs"),
            valid_source_refs=valid_source_refs,
        ),
        "symbols": normalize_stock_symbol_list(raw_node.get("symbols", []))[:8],
        "children": children,
    }


def count_mindmap_nodes(node: dict[str, Any]) -> int:
    return 1 + sum(count_mindmap_nodes(child) for child in node.get("children", []))


def compute_mindmap_depth(node: dict[str, Any]) -> int:
    children = node.get("children", [])
    if not children:
        return 1
    return 1 + max(compute_mindmap_depth(child) for child in children)


def collect_mindmap_node_ids(node: dict[str, Any]) -> set[str]:
    ids = {str(node.get("id") or "")}
    for child in node.get("children", []):
        ids.update(collect_mindmap_node_ids(child))
    ids.discard("")
    return ids


def build_mindmap_outline_lines(node: dict[str, Any], *, depth: int = 0) -> list[str]:
    indent = "  " * depth
    summary = str(node.get("summary") or "").strip()
    line = f"{indent}- {node['label']}"
    if summary:
        line += f": {summary}"
    lines = [line]
    for child in node.get("children", []):
        lines.extend(build_mindmap_outline_lines(child, depth=depth + 1))
    return lines


def build_mindmap_outline_markdown(root: dict[str, Any]) -> str:
    return "\n".join(build_mindmap_outline_lines(root))


def normalize_mindmap_cross_links(raw_links: Any, *, node_ids: set[str]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    raw_items = raw_links if isinstance(raw_links, list) else []
    for raw_link in raw_items[:8]:
        if not isinstance(raw_link, dict):
            continue
        from_id = str(raw_link.get("from") or "").strip()
        to_id = str(raw_link.get("to") or "").strip()
        label = re.sub(r"\s+", " ", str(raw_link.get("label") or "").strip())[:40]
        if not from_id or not to_id or from_id == to_id:
            continue
        if from_id not in node_ids or to_id not in node_ids:
            continue
        links.append(
            {
                "from": from_id,
                "to": to_id,
                "label": label or "关联",
            }
        )
    return links


def normalize_mindmap_timeline(
    raw_items: Any,
    *,
    valid_source_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        date_value = str(raw_item.get("date") or "").strip()[:40]
        label = re.sub(r"\s+", " ", str(raw_item.get("label") or "").strip())[:80]
        summary = re.sub(r"\s+", " ", str(raw_item.get("summary") or "").strip())[:220]
        if not label:
            continue
        date_type = str(raw_item.get("date_type") or "").strip().lower()
        if date_type not in {"event", "published", "meeting", "inferred"}:
            date_type = "event"
        phase = str(raw_item.get("phase") or "").strip().lower()
        if phase not in {"earliest", "mid", "latest"}:
            phase = ""
        timeline.append(
            {
                "date": date_value,
                "label": label,
                "summary": summary,
                "date_type": date_type,
                "phase": phase,
                "source_refs": normalize_mindmap_source_refs(
                    raw_item.get("source_refs"),
                    valid_source_refs=valid_source_refs,
                ),
            }
        )
    return timeline[:6]


def normalize_mindmap_source_relations(
    raw_items: Any,
    *,
    valid_source_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    relations: list[dict[str, Any]] = []
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        label = re.sub(r"\s+", " ", str(raw_item.get("label") or "").strip())[:40]
        source_from = re.sub(r"\s+", " ", str(raw_item.get("from") or "").strip())[:40]
        source_to = re.sub(r"\s+", " ", str(raw_item.get("to") or "").strip())[:40]
        summary = re.sub(r"\s+", " ", str(raw_item.get("summary") or "").strip())[:220]
        if not label or not source_from or not source_to:
            continue
        relations.append(
            {
                "label": label,
                "from": source_from,
                "to": source_to,
                "summary": summary,
                "source_refs": normalize_mindmap_source_refs(
                    raw_item.get("source_refs"),
                    valid_source_refs=valid_source_refs,
                ),
            }
        )
    return relations[:8]


def normalize_mindmap_comparison_axes(
    raw_items: Any,
    *,
    valid_source_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    axes: list[dict[str, Any]] = []
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        axis = re.sub(r"\s+", " ", str(raw_item.get("axis") or "").strip())[:60]
        takeaway = re.sub(r"\s+", " ", str(raw_item.get("takeaway") or "").strip())[:240]
        if not axis:
            continue

        views: list[dict[str, Any]] = []
        raw_views = raw_item.get("views", [])
        for raw_view in raw_views if isinstance(raw_views, list) else []:
            if not isinstance(raw_view, dict):
                continue
            symbol = normalize_stock_symbol(str(raw_view.get("symbol") or "")) or ""
            stance = re.sub(r"\s+", " ", str(raw_view.get("stance") or "").strip())[:24]
            summary = re.sub(r"\s+", " ", str(raw_view.get("summary") or "").strip())[:180]
            if not symbol or (not stance and not summary):
                continue
            views.append(
                {
                    "symbol": symbol,
                    "stance": stance,
                    "summary": summary,
                    "source_refs": normalize_mindmap_source_refs(
                        raw_view.get("source_refs"),
                        valid_source_refs=valid_source_refs,
                    ),
                }
            )
        if not views:
            continue

        axes.append(
            {
                "axis": axis,
                "takeaway": takeaway,
                "views": views[:8],
                "source_refs": normalize_mindmap_source_refs(
                    raw_item.get("source_refs"),
                    valid_source_refs=valid_source_refs,
                ),
            }
        )
    return axes[:6]


def normalize_mindmap_verification_targets(
    raw_items: Any,
    *,
    valid_source_refs: set[str] | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        question = re.sub(r"\s+", " ", str(raw_item.get("question") or "").strip())[:120]
        why_it_matters = re.sub(r"\s+", " ", str(raw_item.get("why_it_matters") or "").strip())[:220]
        evidence_gap = re.sub(r"\s+", " ", str(raw_item.get("evidence_gap") or "").strip())[:220]
        next_check = re.sub(r"\s+", " ", str(raw_item.get("next_check") or "").strip())[:220]
        if not question:
            continue
        priority = str(raw_item.get("priority") or "").strip().lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        targets.append(
            {
                "question": question,
                "why_it_matters": why_it_matters,
                "evidence_gap": evidence_gap,
                "next_check": next_check,
                "priority": priority,
                "symbols": normalize_stock_symbol_list(raw_item.get("symbols", []))[:8],
                "source_refs": normalize_mindmap_source_refs(
                    raw_item.get("source_refs"),
                    valid_source_refs=valid_source_refs,
                ),
            }
        )
    return targets[:6]


def normalize_mindmap_payload(
    raw_payload: Any,
    *,
    valid_source_refs: set[str] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw_payload, dict):
        return None

    existing_ids: set[str] = set()
    root = normalize_mindmap_node(
        raw_payload.get("root"),
        existing_ids=existing_ids,
        valid_source_refs=valid_source_refs,
    )
    if root is None:
        return None

    node_ids = collect_mindmap_node_ids(root)
    structure_kind = str(raw_payload.get("structure_kind") or "").strip().lower()
    if structure_kind not in MINDMAP_STRUCTURE_KIND_META:
        structure_kind = "theme_bundle"

    title = re.sub(r"\s+", " ", str(raw_payload.get("title") or "").strip())[:120] or root["label"]
    summary = re.sub(r"\s+", " ", str(raw_payload.get("summary") or "").strip())[:600]
    raw_insights = raw_payload.get("insights", [])
    insights = [
        item
        for raw_item in raw_insights if isinstance(raw_insights, list)
        if (item := re.sub(r"\s+", " ", str(raw_item or "").strip())[:180])
    ][:6]
    timeline = normalize_mindmap_timeline(
        raw_payload.get("timeline_highlights"),
        valid_source_refs=valid_source_refs,
    )
    source_relations = normalize_mindmap_source_relations(
        raw_payload.get("source_relations"),
        valid_source_refs=valid_source_refs,
    )
    comparison_axes = normalize_mindmap_comparison_axes(
        raw_payload.get("comparison_axes"),
        valid_source_refs=valid_source_refs,
    )
    verification_targets = normalize_mindmap_verification_targets(
        raw_payload.get("verification_targets"),
        valid_source_refs=valid_source_refs,
    )
    cross_links = normalize_mindmap_cross_links(raw_payload.get("cross_links"), node_ids=node_ids)

    return {
        "title": title,
        "summary": summary,
        "structure_kind": structure_kind,
        "root": root,
        "cross_links": cross_links,
        "insights": insights,
        "comparison_axes": comparison_axes,
        "verification_targets": verification_targets,
        "timeline_highlights": timeline,
        "source_relations": source_relations,
        "node_count": count_mindmap_nodes(root),
        "max_depth": compute_mindmap_depth(root),
        "outline_markdown": build_mindmap_outline_markdown(root),
    }


def normalize_mindmap_fingerprint(raw_fingerprint: Any) -> dict[str, Any]:
    source = raw_fingerprint if isinstance(raw_fingerprint, dict) else {}
    selected_sources: list[dict[str, Any]] = []
    raw_sources = source.get("selected_sources", [])
    for raw_source in raw_sources if isinstance(raw_sources, list) else []:
        if not isinstance(raw_source, dict):
            continue
        source_ref = re.sub(r"[^A-Za-z0-9:-]+", "", str(raw_source.get("source_ref") or "").strip()).upper()[:24]
        if not source_ref:
            continue
        raw_weight_flags = raw_source.get("weight_flags", [])
        raw_weight_flags_list = raw_weight_flags if isinstance(raw_weight_flags, list) else []
        selected_sources.append(
            {
                "source_ref": source_ref,
                "source_key": str(raw_source.get("source_key") or "").strip()[:160],
                "kind": str(raw_source.get("kind") or "").strip()[:20],
                "title": re.sub(r"\s+", " ", str(raw_source.get("title") or "").strip())[:180],
                "activity_date": str(raw_source.get("activity_date") or "").strip()[:40],
                "symbols": normalize_stock_symbol_list(raw_source.get("symbols", []))[:12],
                "weight_flags": [
                    str(item).strip()[:24]
                    for item in raw_weight_flags_list
                    if str(item).strip()[:24]
                ][:6],
                "priority_score": float(raw_source.get("priority_score") or 0),
            }
        )

    validation_source = source.get("validation") if isinstance(source.get("validation"), dict) else {}
    raw_warnings = validation_source.get("warnings", [])
    raw_errors = validation_source.get("errors", [])
    raw_warnings_list = raw_warnings if isinstance(raw_warnings, list) else []
    raw_errors_list = raw_errors if isinstance(raw_errors, list) else []
    validation = {
        "warnings": [
            re.sub(r"\s+", " ", str(item or "").strip())[:240]
            for item in raw_warnings_list
            if re.sub(r"\s+", " ", str(item or "").strip())[:240]
        ][:16],
        "errors": [
            re.sub(r"\s+", " ", str(item or "").strip())[:240]
            for item in raw_errors_list
            if re.sub(r"\s+", " ", str(item or "").strip())[:240]
        ][:16],
        "repair_attempted": bool(validation_source.get("repair_attempted")),
    }
    material_mix_source = source.get("material_mix") if isinstance(source.get("material_mix"), dict) else {}
    return {
        "generated_at": str(source.get("generated_at") or "").strip()[:40],
        "pipeline_version": str(source.get("pipeline_version") or "").strip()[:80],
        "prompt_version": str(source.get("prompt_version") or "").strip()[:80],
        "schema_version": str(source.get("schema_version") or "").strip()[:80],
        "bundle_name": str(source.get("bundle_name") or "").strip()[:160],
        "scope_digest": str(source.get("scope_digest") or "").strip()[:80],
        "scope_summary_digest": str(source.get("scope_summary_digest") or "").strip()[:80],
        "material_digest": str(source.get("material_digest") or "").strip()[:80],
        "knowledge_digest": str(source.get("knowledge_digest") or "").strip()[:80],
        "material_selection_digest": str(source.get("material_selection_digest") or "").strip()[:80],
        "plan_digest": str(source.get("plan_digest") or "").strip()[:80],
        "final_digest": str(source.get("final_digest") or "").strip()[:80],
        "raw_material_count": max(0, int(source.get("raw_material_count") or 0)),
        "selected_material_count": max(0, int(source.get("selected_material_count") or 0)),
        "duplicate_compressed_count": max(0, int(source.get("duplicate_compressed_count") or 0)),
        "low_signal_dropped_count": max(0, int(source.get("low_signal_dropped_count") or 0)),
        "recent_boosted_count": max(0, int(source.get("recent_boosted_count") or 0)),
        "strong_evidence_boosted_count": max(0, int(source.get("strong_evidence_boosted_count") or 0)),
        "conflict_boosted_count": max(0, int(source.get("conflict_boosted_count") or 0)),
        "selected_sources": selected_sources,
        "validation": validation,
        "material_mix": {
            "report_count": max(0, int(material_mix_source.get("report_count") or 0)),
            "note_count": max(0, int(material_mix_source.get("note_count") or 0)),
            "file_count": max(0, int(material_mix_source.get("file_count") or 0)),
            "earnings_call_count": max(0, int(material_mix_source.get("earnings_call_count") or 0)),
            "transcript_count": max(0, int(material_mix_source.get("transcript_count") or 0)),
        },
    }


def normalize_mindmap_record(raw_record: Any) -> dict[str, Any] | None:
    if not isinstance(raw_record, dict):
        return None

    record_id = str(raw_record.get("id") or uuid.uuid4().hex[:12]).strip()
    if not record_id:
        return None

    try:
        scope_settings = normalize_ai_scope_settings(raw_record.get("scope_settings", {}))
    except ValueError:
        scope_settings = normalize_ai_scope_settings({})

    map_payload = normalize_mindmap_payload(raw_record.get("map_payload"))
    status = str(raw_record.get("status") or "completed").strip().lower()
    if status not in MINDMAP_STATUS_META:
        status = "completed" if map_payload else "pending"

    title = re.sub(r"\s+", " ", str(raw_record.get("title") or "").strip())[:120]
    if not title:
        title = map_payload["title"] if map_payload else build_mindmap_seed_title(scope_settings)

    scope_summary = normalize_mindmap_scope_summary(raw_record.get("scope_summary"))
    fingerprint = normalize_mindmap_fingerprint(raw_record.get("fingerprint"))
    summary = re.sub(r"\s+", " ", str(raw_record.get("summary") or "").strip())[:600]
    if not summary and map_payload:
        summary = map_payload["summary"]

    return {
        "id": record_id,
        "title": title,
        "created_at": str(raw_record.get("created_at") or now_iso()),
        "updated_at": str(raw_record.get("updated_at") or now_iso()),
        "status": status,
        "error": str(raw_record.get("error") or "").strip()[:600],
        "model": str(raw_record.get("model") or "").strip()[:80],
        "reasoning_effort": str(raw_record.get("reasoning_effort") or "").strip()[:20],
        "scope_settings": scope_settings,
        "scope_summary": scope_summary,
        "fingerprint": fingerprint,
        "summary": summary,
        "map_payload": map_payload,
        "structure_kind": map_payload["structure_kind"] if map_payload else "",
        "outline_markdown": str(raw_record.get("outline_markdown") or (map_payload["outline_markdown"] if map_payload else "")).strip(),
        "node_count": int(map_payload["node_count"]) if map_payload else 0,
        "max_depth": int(map_payload["max_depth"]) if map_payload else 0,
    }


def normalize_mindmap_store(data: Any) -> dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    records = [
        record
        for raw_record in source.get("records", [])
        if (record := normalize_mindmap_record(raw_record)) is not None
    ]
    records.sort(key=lambda item: (item["updated_at"], item["id"]), reverse=True)
    return {"records": records}


def load_mindmap_store() -> dict[str, Any]:
    MINDMAP_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MINDMAP_STORE_PATH.exists():
        return normalize_mindmap_store({})

    try:
        raw_data = json.loads(MINDMAP_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return normalize_mindmap_store({})
    return normalize_mindmap_store(raw_data)


def save_mindmap_store(store: dict[str, Any]) -> None:
    normalized = normalize_mindmap_store(store)
    MINDMAP_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MINDMAP_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(MINDMAP_STORE_PATH)


def get_mindmap_record(store: dict[str, Any], record_id: str) -> dict[str, Any]:
    for record in store.get("records", []):
        if record["id"] == record_id:
            return record
    abort(404)


def touch_mindmap_record(record: dict[str, Any]) -> None:
    record["updated_at"] = now_iso()


def build_mindmap_record_cards(store: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for record in store.get("records", []):
        cards.append(
            {
                "id": record["id"],
                "title": record["title"],
                "updated_label": format_iso_timestamp(record["updated_at"]),
                "status": record["status"],
                "status_label": MINDMAP_STATUS_META.get(record["status"], MINDMAP_STATUS_META["pending"])["label"],
                "status_tone": MINDMAP_STATUS_META.get(record["status"], MINDMAP_STATUS_META["pending"])["tone"],
                "structure_label": MINDMAP_STRUCTURE_KIND_META.get(record.get("structure_kind") or "", "资料导图"),
                "node_count": record.get("node_count") or 0,
                "summary": record.get("summary") or "",
            }
        )
    return cards


def update_mindmap_record(record_id: str, **changes: Any) -> None:
    with MINDMAP_LOCK:
        store = load_mindmap_store()
        record = get_mindmap_record(store, record_id)
        for key, value in changes.items():
            record[key] = value
        touch_mindmap_record(record)
        save_mindmap_store(store)


def read_mindmap_record(record_id: str) -> dict[str, Any] | None:
    with MINDMAP_LOCK:
        store = load_mindmap_store()
        record = next((item for item in store.get("records", []) if item["id"] == record_id), None)
        return deepcopy(record) if record else None


def register_mindmap_process(record_id: str, process: subprocess.Popen[str]) -> None:
    with MINDMAP_PROCESS_LOCK:
        MINDMAP_RUNNING_PROCESSES[record_id] = process


def register_mindmap_task(record_id: str) -> None:
    with MINDMAP_PROCESS_LOCK:
        MINDMAP_ACTIVE_TASKS.add(record_id)


def release_mindmap_process(record_id: str) -> None:
    with MINDMAP_PROCESS_LOCK:
        MINDMAP_RUNNING_PROCESSES.pop(record_id, None)


def release_mindmap_task(record_id: str) -> None:
    with MINDMAP_PROCESS_LOCK:
        MINDMAP_ACTIVE_TASKS.discard(record_id)


def request_mindmap_stop(record_id: str) -> subprocess.Popen[str] | None:
    with MINDMAP_PROCESS_LOCK:
        MINDMAP_STOP_REQUESTS.add(record_id)
        return MINDMAP_RUNNING_PROCESSES.get(record_id)


def mindmap_stop_requested(record_id: str) -> bool:
    with MINDMAP_PROCESS_LOCK:
        return record_id in MINDMAP_STOP_REQUESTS


def clear_mindmap_stop_request(record_id: str) -> None:
    with MINDMAP_PROCESS_LOCK:
        MINDMAP_STOP_REQUESTS.discard(record_id)


def mindmap_runtime_active(record_id: str) -> bool:
    with MINDMAP_PROCESS_LOCK:
        if record_id in MINDMAP_ACTIVE_TASKS:
            return True
        process = MINDMAP_RUNNING_PROCESSES.get(record_id)
        if process is None:
            return False
        if process.poll() is None:
            return True
        MINDMAP_RUNNING_PROCESSES.pop(record_id, None)
        return False


def reconcile_stale_mindmap_store(store: dict[str, Any]) -> bool:
    changed = False
    stale_cutoff = time.time() - max(MINDMAP_STALE_JOB_SECONDS, 30)
    for record in store.get("records", []):
        if record.get("status") not in {"pending", "running"}:
            continue
        if mindmap_runtime_active(record["id"]):
            continue
        updated_at = coerce_sort_timestamp(record.get("updated_at"))
        if updated_at and updated_at > stale_cutoff:
            continue
        record["status"] = "error"
        record["error"] = "这次导图任务已经中断，通常是网页后端重启或本地 Codex 进程退出导致。请重新生成一次。"
        touch_mindmap_record(record)
        changed = True
    return changed


def extract_first_json_object(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("Codex 没有返回可用内容。")

    if text.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if match:
            text = match.group(1).strip()

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            payload, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload

    raise ValueError("Codex 返回了文本，但里面没有找到合法的 JSON 对象。")


def build_mindmap_json_schema_prompt() -> str:
    return (
        "{\n"
        '  "title": "导图标题",\n'
        '  "summary": "这张导图的总括摘要",\n'
        '  "structure_kind": "single_stock|peer_group|value_chain|theme_bundle",\n'
        '  "insights": ["核心判断 1", "核心判断 2"],\n'
        '  "comparison_axes": [\n'
        '    {"axis": "比较维度", "takeaway": "该维度的一句话判断", "source_refs": ["M01"], "views": [{"symbol": "NET", "stance": "领先|修复|承压|待定", "summary": "该标的在此维度下的判断", "source_refs": ["M01", "M02"]}]}\n'
        "  ],\n"
        '  "verification_targets": [\n'
        '    {"question": "关键待验证点", "why_it_matters": "为什么重要", "evidence_gap": "当前证据缺口或冲突", "next_check": "下一步去哪里验证", "priority": "high|medium|low", "symbols": ["NET"], "source_refs": ["M02", "M05"]}\n'
        "  ],\n"
        '  "timeline_highlights": [\n'
        '    {"date": "2026-03-11", "date_type": "event|published|meeting|inferred", "phase": "earliest|mid|latest", "label": "时间节点标题", "summary": "这一时点的信息变化", "source_refs": ["M01"]}\n'
        "  ],\n"
        '  "source_relations": [\n'
        '    {"label": "补充|验证|冲突|迭代", "from": "资料 A", "to": "资料 B", "summary": "关系说明", "source_refs": ["M01", "M04"]}\n'
        "  ],\n"
        '  "root": {\n'
        '    "id": "root",\n'
        '    "label": "根节点标题",\n'
        '    "kind": "root",\n'
        '    "summary": "根节点摘要",\n'
        '    "evidence": ["证据 1", "证据 2"],\n'
        '    "time_signals": ["时间信号 1", "时间信号 2"],\n'
        '    "source_notes": ["资料互补/冲突备注 1"],\n'
        '    "confidence": "low|medium|high",\n'
        '    "source_refs": ["M01", "M02"],\n'
        '    "symbols": ["AMD", "NVDA"],\n'
        '    "children": [\n'
        '      {"id": "branch-1", "label": "分支标题", "kind": "theme|question|risk|catalyst|evidence|timeline", "summary": "分支摘要", "evidence": ["..."], "time_signals": ["..."], "source_notes": ["..."], "confidence": "medium", "source_refs": ["M03"], "symbols": ["..."], "children": []}\n'
        "    ]\n"
        "  },\n"
        '  "cross_links": [\n'
        '    {"from": "branch-1", "to": "branch-2", "label": "同驱动|上游传导|结论冲突"}\n'
        "  ]\n"
        "}"
    )


def flatten_mindmap_nodes(root: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [root]
    for child in root.get("children", []):
        nodes.extend(flatten_mindmap_nodes(child))
    return nodes


def mindmap_timeline_sort_key(date_value: str) -> tuple[int, str]:
    normalized = normalize_date_field(date_value)
    if normalized:
        return (0, normalized)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(date_value or ""))
    if match:
        return (0, match.group(1))
    return (1, str(date_value or "").strip())


def validate_mindmap_research_payload(
    payload: dict[str, Any],
    *,
    curated: dict[str, Any],
) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    root = payload.get("root") or {}
    root_label = str(root.get("label") or "").strip()
    normalized_root_label = root_label.casefold()
    if normalized_root_label in {"资料整理", "研究导图", "导图", "思维导图", "资料导图"}:
        errors.append("根节点标题过于泛化，没有直接指向研究主题。")

    top_level_children = root.get("children", []) if isinstance(root.get("children"), list) else []
    if len(top_level_children) < 2:
        errors.append("顶层分支少于 2 个，主题拆解不够完整。")
    elif len(top_level_children) > 6:
        warnings.append("顶层分支超过 6 个，后续可继续收敛。")

    nodes = flatten_mindmap_nodes(root) if isinstance(root, dict) else []
    if payload.get("node_count", 0) < 10:
        warnings.append("节点数量偏少，可能没有充分展开研究主线。")
    if payload.get("node_count", 0) > 30:
        warnings.append("节点数量偏多，后续可继续压缩重复表达。")

    timeline = payload.get("timeline_highlights", []) if isinstance(payload.get("timeline_highlights"), list) else []
    comparison_axes = payload.get("comparison_axes", []) if isinstance(payload.get("comparison_axes"), list) else []
    verification_targets = payload.get("verification_targets", []) if isinstance(payload.get("verification_targets"), list) else []
    selected_manifest = curated.get("selected_manifest", []) if isinstance(curated.get("selected_manifest"), list) else []
    selected_count = int((curated.get("stats") or {}).get("selected_material_count") or 0)
    if selected_count >= 4 and not timeline:
        errors.append("已有较多入选资料，但导图没有给出时间轴主线。")
    elif selected_count >= 4 and len(timeline) < 3:
        warnings.append("时间轴节点少于 3 个，可能不够完整。")

    sortable_timeline = [item for item in timeline if mindmap_timeline_sort_key(item.get("date") or "")[0] == 0]
    sort_keys = [mindmap_timeline_sort_key(item.get("date") or "") for item in sortable_timeline]
    if len(sort_keys) >= 2 and sort_keys != sorted(sort_keys):
        errors.append("时间轴没有按从早到晚排序。")

    phases = {str(item.get("phase") or "") for item in timeline if str(item.get("phase") or "").strip()}
    if timeline and "latest" not in phases:
        warnings.append("时间轴缺少 latest 阶段，最新状态不够明确。")
    if timeline and "earliest" not in phases:
        warnings.append("时间轴缺少 earliest 阶段，最早信号不够明确。")

    selected_symbols = ordered_unique(
        symbol
        for item in selected_manifest
        for symbol in normalize_stock_symbol_list(item.get("symbols", []))
    )
    multi_symbol_scope = payload.get("structure_kind") == "peer_group" or len(selected_symbols) >= 2
    if multi_symbol_scope and len(comparison_axes) < 2:
        errors.append("多标的/同行导图缺少统一比较轴，容易退化成按公司或资料平铺。")
    elif selected_count >= 6 and not comparison_axes:
        warnings.append("资料已经较多，但还没有显式比较轴，后续对位比较会偏弱。")

    multi_symbol_axis_count = 0
    covered_axis_count = 0
    for axis in comparison_axes:
        axis_views = axis.get("views", []) if isinstance(axis.get("views"), list) else []
        axis_symbols = {
            str(item.get("symbol") or "").strip().upper()
            for item in axis_views
            if isinstance(item, dict) and str(item.get("symbol") or "").strip()
        }
        if len(axis_symbols) >= 2:
            multi_symbol_axis_count += 1
        if axis.get("source_refs") or any(item.get("source_refs") for item in axis_views if isinstance(item, dict)):
            covered_axis_count += 1

    if multi_symbol_scope and comparison_axes and multi_symbol_axis_count <= 0:
        errors.append("比较轴没有把至少两个标的放进同一维度下对位比较。")
    elif multi_symbol_scope and len(comparison_axes) >= 2 and multi_symbol_axis_count < 2:
        warnings.append("只有少数比较轴真正形成了跨标的对位比较，分析维度还可以继续收紧。")
    if comparison_axes and covered_axis_count / max(len(comparison_axes), 1) < 0.6:
        warnings.append("部分比较轴仍缺少明确来源引用，后续追溯会比较困难。")

    conflict_selected_count = sum(
        1
        for source in selected_manifest
        if "conflict" in (source.get("weight_flags") or [])
    )
    has_risk_or_question = any(str(node.get("kind") or "") in {"question", "risk"} for node in nodes)
    if conflict_selected_count >= 2 and not has_risk_or_question:
        errors.append("入选资料里存在明显冲突，但导图里没有保留待验证或风险分支。")

    if (conflict_selected_count >= 2 or selected_count >= 8) and len(verification_targets) < 2:
        errors.append("资料冲突或信息密度已经较高，但还没有沉淀出足够明确的关键验证点。")
    elif selected_count >= 5 and not verification_targets:
        warnings.append("当前导图还没有显式验证账本，后续追踪主判断会偏散。")

    actionable_target_count = sum(
        1
        for target in verification_targets
        if str(target.get("evidence_gap") or "").strip() and str(target.get("next_check") or "").strip()
    )
    high_priority_target_count = sum(
        1
        for target in verification_targets
        if str(target.get("priority") or "").strip().lower() == "high"
    )
    if verification_targets and actionable_target_count / max(len(verification_targets), 1) < 0.6:
        warnings.append("部分验证点还不够可执行，最好同时写明证据缺口和下一步验证动作。")
    if (conflict_selected_count >= 2 or multi_symbol_scope) and verification_targets and high_priority_target_count <= 0:
        warnings.append("当前导图缺少高优先级验证点，主分歧的跟踪顺序还不够清晰。")

    research_nodes = [
        node
        for node in nodes
        if str(node.get("kind") or "") not in {"root", "question", "risk"}
    ]
    if research_nodes:
        evidence_covered = sum(
            1 for node in research_nodes if node.get("evidence") or node.get("source_refs")
        )
        coverage_ratio = evidence_covered / len(research_nodes)
        if coverage_ratio < 0.55:
            errors.append("可验证节点的证据或来源引用覆盖率过低。")
        elif coverage_ratio < 0.75:
            warnings.append("部分节点仍缺少明确证据或来源引用。")

    if not any(node.get("source_refs") for node in nodes):
        warnings.append("整张导图没有显式来源引用，后续回溯会比较困难。")

    selected_kinds = {str(item.get("kind") or "").strip() for item in selected_manifest}
    if "earnings_call" in selected_kinds and multi_symbol_scope and not any(
        str(item.get("date_type") or "").strip() in {"meeting", "published"} and str(item.get("phase") or "").strip() == "latest"
        for item in timeline
    ):
        warnings.append("当前范围里已有较新的官方材料，但时间轴没有明确落下最新官方口径节点。")

    return {"errors": errors[:12], "warnings": warnings[:12]}


def build_mindmap_plan_prompt(
    *,
    scope_summary: dict[str, Any],
    knowledge_text: str,
    fingerprint: dict[str, Any],
) -> str:
    source_roster = build_mindmap_selected_source_roster_lines(fingerprint.get("selected_sources", []))
    return (
        "你现在在做研究导图的第一步：先梳理结构，再决定成图骨架。\n"
        "目标：基于资料先抽出主题主线、比较维度、时间主线、冲突点和待验证问题，形成一张可复用的骨架图。\n"
        "重要约束：\n"
        "1. 只能基于下方资料正文，不得补外部事实。\n"
        "2. 这是第一步，重点是结构判断，不需要把证据写满，但必须先把分叉逻辑、比较维度、时间轴和冲突关系梳理清楚。\n"
        "3. 结构模式只能四选一：single_stock / peer_group / value_chain / theme_bundle。\n"
        "4. 时间轴必须区分最早信号、中段验证/修正、最新状态；date_type 要区分 event / published / meeting / inferred。\n"
        "5. 资料若存在冲突、修正、对冲，必须明确留下 risk 或 question 分支，不能强行消解成单边结论。\n"
        "6. 只允许使用给定的来源引用 source_refs（例如 M01、M02）。\n"
        "7. 顶层分支控制在 4 到 6 个，总节点控制在 12 到 28 个，层级最多 4 层。\n"
        "8. 根节点不能写成“资料整理”“研究导图”之类的泛称，要直接写研究主题。\n"
        "9. 如果资料里包含电话会议，要优先识别管理层最新口径、指引、问答争议点，并和日报/笔记/专家材料互相验证。\n"
        "10. 在内部先把资料拆成“判断卡片”：比较维度、时间位置、来源角色、立场方向；不要输出中间稿，只把它体现在 comparison_axes、source_relations 和 root/children 结构里。\n"
        "11. 如果是 peer_group 或多标的主题，必须先抽 3 到 5 个统一比较轴，再决定分支结构；不能先按公司平铺，再事后硬补比较。\n"
        "12. verification_targets 不是泛泛提问，而是高杠杆验证清单：要写清 why_it_matters、evidence_gap、next_check、priority。\n"
        "13. 如果官方最新口径与渠道/笔记不同，要明确写成修正、冲突或待验证，不能揉成平均结论。\n"
        "14. 最终只输出一个 JSON 对象，不要 Markdown，不要代码块，不要解释。\n\n"
        "这一步的输出要求：\n"
        "- 使用最终 schema，但 evidence / time_signals / source_notes 可以先写最必要的 0 到 2 条。\n"
        "- comparison_axes 要尽量先搭出 2 到 5 个；如果是同行/多标的导图，至少给出 3 个统一比较轴。\n"
        "- timeline_highlights 至少给出 3 个节点（如果资料不足，再明确说明不足原因）。\n"
        "- 如果资料冲突明显或资料密度较高，verification_targets 至少给出 2 个高价值验证点。\n"
        "- 每个关键节点、比较轴和验证点都尽量带 source_refs 和 confidence/priority。\n\n"
        "当前资料范围：\n"
        f"- {scope_summary.get('stock_label') or '股票范围：全站'}\n"
        f"- {scope_summary.get('time_label') or '时间窗口：不限'}\n"
        f"- {scope_summary.get('content_label') or '资料类型：日报；笔记；文件；电话会议；转录'}\n"
        f"- pipeline_version: {fingerprint.get('pipeline_version') or MINDMAP_PIPELINE_VERSION}\n"
        f"- prompt_version: {fingerprint.get('prompt_version') or MINDMAP_PROMPT_VERSION}\n\n"
        f"允许引用的来源列表：\n{source_roster}\n\n"
        f"JSON schema：\n{build_mindmap_json_schema_prompt()}\n\n"
        f"资料正文：\n{knowledge_text or '（当前资料正文为空，请把导图收敛到资料不足与待验证问题。）'}\n"
    )


def build_mindmap_finalize_prompt(
    *,
    scope_summary: dict[str, Any],
    knowledge_text: str,
    plan_payload: dict[str, Any],
    fingerprint: dict[str, Any],
) -> str:
    source_roster = build_mindmap_selected_source_roster_lines(fingerprint.get("selected_sources", []))
    plan_text = json.dumps(plan_payload, ensure_ascii=False, indent=2)
    return (
        "你现在在做研究导图的第二步：在既有骨架上补齐研究合法的成图结果。\n"
        "目标：把骨架图补成一张可用于研究回看、横向比较和后续验证的正式导图。\n"
        "重要约束：\n"
        "1. 只能基于下方资料正文和骨架 JSON，不得补外部事实。\n"
        "2. 尽量保留骨架里的 structure_kind、节点 id、主要分支和时间主线；可以小幅修正，但不要推翻结构。\n"
        "3. 除 question / risk 外，关键节点尽量都要有 evidence 或 source_refs 支撑。\n"
        "4. timeline_highlights 必须按从早到晚排序，并保留 earliest / mid / latest 三种 phase 的主线意识。\n"
        "5. 必须区分 event（事件发生）、published（资料发布时间）、meeting（会议/访谈时间）、inferred（推断时间）。\n"
        "6. 对于仍未解开的冲突，要留在 risk / question / source_notes 里，不要硬写成确定结论。\n"
        "7. 只允许使用给定的来源引用 source_refs（例如 M01、M02）。\n"
        "8. summary、evidence、time_signals、source_notes 都要短、可扫读。\n"
        "9. comparison_axes 必须是统一比较维度，不是公司摘要列表；每个轴都要尽量把相关标的放到同一个维度下对位比较。\n"
        "10. verification_targets 必须是可执行的验证账本：写清 why_it_matters、evidence_gap、next_check、priority，优先保留真正能改变主判断的验证点。\n"
        "11. 如果资料里包含电话会议，要优先保留管理层最新口径、指引变化和问答争议，不要把它埋进泛泛摘要里。\n"
        "12. 如果官方口径和渠道反馈都存在，要明确指出谁在验证谁、谁在修正谁，不能只做表面折中。\n"
        "13. 最终只输出一个 JSON 对象，不要 Markdown，不要代码块，不要解释。\n\n"
        "当前资料范围：\n"
        f"- {scope_summary.get('stock_label') or '股票范围：全站'}\n"
        f"- {scope_summary.get('time_label') or '时间窗口：不限'}\n"
        f"- {scope_summary.get('content_label') or '资料类型：日报；笔记；文件；电话会议；转录'}\n\n"
        f"允许引用的来源列表：\n{source_roster}\n\n"
        f"必须遵守的 JSON schema：\n{build_mindmap_json_schema_prompt()}\n\n"
        f"第一步骨架 JSON：\n{plan_text}\n\n"
        f"资料正文：\n{knowledge_text or '（当前资料正文为空，请把导图收敛到资料不足与待验证问题。）'}\n"
    )


def build_mindmap_repair_prompt(
    *,
    knowledge_text: str,
    current_payload: dict[str, Any],
    validation: dict[str, list[str]],
    fingerprint: dict[str, Any],
) -> str:
    source_roster = build_mindmap_selected_source_roster_lines(fingerprint.get("selected_sources", []))
    payload_text = json.dumps(current_payload, ensure_ascii=False, indent=2)
    error_lines = "\n".join(f"- {item}" for item in validation.get("errors", [])) or "- 没有明确错误说明"
    warning_lines = "\n".join(f"- {item}" for item in validation.get("warnings", [])) or "- 无"
    return (
        "你现在是研究导图结果修复器。\n"
        "目标：在尽量少改动的前提下，修正当前 JSON，使其通过研究导图校验。\n"
        "要求：\n"
        "1. 只能输出一个修复后的 JSON 对象，不要解释。\n"
        "2. 优先修复 errors；warnings 能顺手优化就优化。\n"
        "3. 保留已有 structure_kind、节点 id、主分支和时间轴主线，不要大改主题。\n"
        "4. 如果缺少 comparison_axes 或 verification_targets，要优先补齐能通过校验的最小可用版本。\n"
        "5. 只允许使用给定的来源引用 source_refs（例如 M01、M02）。\n\n"
        f"允许引用的来源列表：\n{source_roster}\n\n"
        f"必须修复的问题：\n{error_lines}\n\n"
        f"可顺手优化的问题：\n{warning_lines}\n\n"
        f"当前 JSON：\n{payload_text}\n\n"
        f"资料正文：\n{knowledge_text or '（当前资料正文为空。）'}\n"
    )


def run_mindmap_codex_step(
    record_id: str,
    *,
    step_slug: str,
    step_label: str,
    prompt_text: str,
    model: str,
    reasoning_effort: str,
) -> str:
    codex_cli_path = resolve_codex_cli_path()
    if codex_cli_path is None:
        raise RuntimeError("当前电脑没有检测到可用的 Codex 可执行文件。")
    timeout_seconds = compute_mindmap_step_timeout_seconds(
        step_slug=step_slug,
        reasoning_effort=reasoning_effort,
        prompt_text=prompt_text,
    )

    output_path = MINDMAP_CONTEXT_DIR / f"{record_id}-{step_slug}.json"
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

    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            cwd=str(BASE_DIR),
        )
        register_mindmap_process(record_id, process)
        stdout_text, stderr_text = process.communicate(prompt_text, timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if process is not None:
            process.kill()
            try:
                process.communicate(timeout=5)
            except Exception:
                pass
        raise RuntimeError(
            f"{step_label}等待时间过长，Codex 在 {timeout_seconds} 秒内没有返回结果。"
            " 可以稍后重试，或缩小资料范围/降低思考深度。"
        )
    finally:
        release_mindmap_process(record_id)

    if mindmap_stop_requested(record_id):
        return ""

    reply_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
    if process is not None and process.returncode != 0 and not reply_text:
        stderr_text = (stderr_text or "").strip()
        raise RuntimeError(stderr_text or f"{step_label}没有返回可用结果。")
    if not reply_text:
        reply_text = (stdout_text or "").strip()
    if not reply_text:
        raise RuntimeError(f"{step_label}运行结束，但没有产出可用 JSON。")
    return reply_text


def run_mindmap_generation(
    record_id: str,
    *,
    model: str,
    reasoning_effort: str,
) -> None:
    fingerprint: dict[str, Any] = {}
    register_mindmap_task(record_id)
    try:
        reports = collect_reports()
        stock_store = load_stock_store()
        with MINDMAP_LOCK:
            store = load_mindmap_store()
            record = get_mindmap_record(store, record_id)
            record["status"] = "running"
            record["error"] = ""
            touch_mindmap_record(record)
            save_mindmap_store(store)
            scope_settings = deepcopy(record["scope_settings"])
            scope_summary = deepcopy(record["scope_summary"])

        with app.test_request_context("/"):
            materials = collect_ai_scope_materials(stock_store, reports, scope_settings=scope_settings)
        if not scope_summary.get("headline"):
            scope_summary = build_ai_scope_summary(scope_settings, materials)

        curated = curate_mindmap_materials(materials)
        if not curated.get("items"):
            raise RuntimeError("当前范围里的资料经过压缩后仍然不足以生成研究导图，请放宽范围或补充更有信息密度的资料。")

        bundle_path = build_mindmap_research_bundle(
            record_id,
            scope_summary=scope_summary,
            materials=materials,
            curated=curated,
        )
        knowledge_text = load_ai_knowledge_text(bundle_path)
        fingerprint = build_mindmap_reproducibility_fingerprint(
            scope_settings=scope_settings,
            scope_summary=scope_summary,
            materials=materials,
            curated=curated,
            knowledge_text=knowledge_text,
            bundle_path=bundle_path,
        )
        update_mindmap_record(record_id, fingerprint=fingerprint)

        if mindmap_stop_requested(record_id):
            return

        valid_source_refs = curated.get("selected_ref_set") or None
        plan_knowledge_text = mindmap_knowledge_text_for_step(knowledge_text, step_slug="plan")
        plan_prompt = build_mindmap_plan_prompt(
            scope_summary=scope_summary,
            knowledge_text=plan_knowledge_text,
            fingerprint=fingerprint,
        )
        plan_reply = run_mindmap_codex_step(
            record_id,
            step_slug="plan",
            step_label="导图骨架梳理",
            prompt_text=plan_prompt,
            model=model,
            reasoning_effort=reasoning_effort,
        )
        if mindmap_stop_requested(record_id):
            return

        plan_raw_payload = extract_first_json_object(plan_reply)
        plan_payload = normalize_mindmap_payload(plan_raw_payload, valid_source_refs=valid_source_refs)
        if plan_payload is None:
            raise RuntimeError("Codex 已返回导图骨架，但结构不符合要求。")
        fingerprint["plan_digest"] = sha256_text(serialize_stable_json(plan_payload))
        update_mindmap_record(record_id, fingerprint=fingerprint)

        final_knowledge_text = mindmap_knowledge_text_for_step(knowledge_text, step_slug="mindmap")
        final_prompt = build_mindmap_finalize_prompt(
            scope_summary=scope_summary,
            knowledge_text=final_knowledge_text,
            plan_payload=plan_payload,
            fingerprint=fingerprint,
        )
        final_reply = run_mindmap_codex_step(
            record_id,
            step_slug="mindmap",
            step_label="导图正式成图",
            prompt_text=final_prompt,
            model=model,
            reasoning_effort=reasoning_effort,
        )
        if mindmap_stop_requested(record_id):
            return

        final_raw_payload = extract_first_json_object(final_reply)
        payload = normalize_mindmap_payload(final_raw_payload, valid_source_refs=valid_source_refs)
        if payload is None:
            raise RuntimeError("Codex 返回了成图结果，但结构不符合导图要求。")

        validation = validate_mindmap_research_payload(payload, curated=curated)
        repair_attempted = False
        if validation["errors"]:
            repair_attempted = True
            repair_knowledge_text = mindmap_knowledge_text_for_step(knowledge_text, step_slug="repair")
            repair_prompt = build_mindmap_repair_prompt(
                knowledge_text=repair_knowledge_text,
                current_payload=payload,
                validation=validation,
                fingerprint=fingerprint,
            )
            repair_reply = run_mindmap_codex_step(
                record_id,
                step_slug="repair",
                step_label="导图结果修复",
                prompt_text=repair_prompt,
                model=model,
                reasoning_effort=reasoning_effort,
            )
            if mindmap_stop_requested(record_id):
                return
            repaired_raw_payload = extract_first_json_object(repair_reply)
            repaired_payload = normalize_mindmap_payload(repaired_raw_payload, valid_source_refs=valid_source_refs)
            if repaired_payload is None:
                raise RuntimeError("导图修复步骤返回了内容，但结构仍然不合法。")
            payload = repaired_payload
            validation = validate_mindmap_research_payload(payload, curated=curated)

        if validation["errors"]:
            raise RuntimeError(f"导图结构已生成，但研究校验仍未通过：{validation['errors'][0]}")

        fingerprint["final_digest"] = sha256_text(serialize_stable_json(payload))
        fingerprint["validation"] = {
            "warnings": validation["warnings"],
            "errors": validation["errors"],
            "repair_attempted": repair_attempted,
        }

        current_record = read_mindmap_record(record_id)
        if current_record and current_record["status"] == "cancelled":
            return

        update_mindmap_record(
            record_id,
            status="completed",
            title=payload["title"],
            summary=payload["summary"],
            outline_markdown=payload["outline_markdown"],
            map_payload=payload,
            structure_kind=payload["structure_kind"],
            node_count=payload["node_count"],
            max_depth=payload["max_depth"],
            fingerprint=fingerprint,
            error="",
        )
        sync_generated_mindmap_to_studio(record_id)
    except Exception as exc:
        if mindmap_stop_requested(record_id):
            return
        if fingerprint:
            validation_state = fingerprint.get("validation") if isinstance(fingerprint.get("validation"), dict) else {}
            fingerprint["validation"] = {
                "warnings": validation_state.get("warnings", []),
                "errors": [str(exc)[:240]],
                "repair_attempted": bool(validation_state.get("repair_attempted")),
            }
            update_mindmap_record(record_id, status="error", error=str(exc), fingerprint=fingerprint)
        else:
            update_mindmap_record(record_id, status="error", error=str(exc))
    finally:
        release_mindmap_process(record_id)
        release_mindmap_task(record_id)
        clear_mindmap_stop_request(record_id)


def build_mindmap_page_context(
    *,
    record_id: str | None,
    reports: list[dict[str, Any]] | None = None,
    stock_store: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with MINDMAP_LOCK:
        store = load_mindmap_store()
        if reconcile_stale_mindmap_store(store):
            save_mindmap_store(store)
    reports = reports if reports is not None else collect_reports()
    stock_store = stock_store if stock_store is not None else load_stock_store()
    stock_options = build_stock_selector_options(stock_store)
    known_symbols = {item["symbol"] for item in stock_options}
    draft_scope_settings = load_mindmap_scope_draft(known_symbols=known_symbols)
    active_record = None
    if record_id:
        active_record = get_mindmap_record(store, record_id)
    elif store.get("records"):
        active_record = store["records"][0]

    try:
        active_scope_settings = normalize_ai_scope_settings(
            draft_scope_settings if draft_scope_settings is not None else (active_record or {}).get("scope_settings", {}),
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
    active_model_slug = str((active_record or {}).get("model") or default_model["slug"])
    selected_model_meta = next((item for item in model_catalog if item["slug"] == active_model_slug), default_model)
    active_reasoning = str((active_record or {}).get("reasoning_effort") or selected_model_meta["default_reasoning"])
    if active_reasoning not in (selected_model_meta.get("reasoning_levels") or ["medium"]):
        active_reasoning = selected_model_meta.get("default_reasoning") or "medium"

    return {
        "mindmap_records": build_mindmap_record_cards(store),
        "active_record": active_record,
        "selected_record_id": active_record["id"] if active_record else "",
        "stock_options": stock_options,
        "mindmap_scope_settings": active_scope_settings,
        "mindmap_scope_preview": scope_preview,
        "mindmap_scope_summary": scope_summary,
        "poll_interval_ms": MINDMAP_POLL_INTERVAL_SECONDS * 1000,
        "codex_ready": codex_cli_available(),
        "model_catalog": model_catalog,
        "selected_model_meta": selected_model_meta,
        "selected_model_slug": active_model_slug,
        "selected_model_reasoning_levels": selected_model_meta.get("reasoning_levels") or ["medium"],
        "selected_reasoning_effort": active_reasoning,
        "current_mindmap_url": url_for("mindmap_workspace", map=active_record["id"]) if active_record else url_for("mindmap_workspace"),
    }


def normalize_mindmap_studio_template_key(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_TEMPLATE_META:
        return candidate
    return "blank"


def normalize_mindmap_studio_theme_key(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_THEME_META:
        return candidate
    return "graphite"


def normalize_mindmap_studio_surface_key(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_SURFACE_META:
        return candidate
    return "desktop"


def normalize_mindmap_studio_density_key(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_DENSITY_META:
        return candidate
    return "roomy"


def normalize_mindmap_studio_layout_key(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_LAYOUT_META:
        return candidate
    return "mindmap"


def normalize_mindmap_studio_node_kind(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_NODE_KIND_META:
        return candidate
    return "topic"


def normalize_mindmap_studio_relation_tone(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_RELATION_TONE_META:
        return candidate
    return "support"


def normalize_mindmap_studio_origin_mode(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_ORIGIN_META:
        return candidate
    return "manual"


def normalize_mindmap_studio_verify_state(value: str | None) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MINDMAP_STUDIO_VERIFY_META:
        return candidate
    return "draft"


def normalize_mindmap_studio_side(value: str | None, *, fallback: str = "right") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"left", "right", "center"}:
        return candidate
    if fallback in {"left", "right", "center"}:
        return fallback
    return "right"


def build_mindmap_studio_template_blueprint(template_key: str) -> dict[str, Any]:
    template_key = normalize_mindmap_studio_template_key(template_key)
    if template_key == "thesis":
        return {
            "label": "投资判断主线",
            "kind": "thesis",
            "summary": "把判断、证据、风险和待验证分开。",
            "children": [
                {
                    "label": "判断主轴",
                    "kind": "thesis",
                    "summary": "一句话说清主判断。",
                    "side": "left",
                    "children": [
                        {"label": "为什么现在", "kind": "timeline"},
                        {"label": "最关键支撑", "kind": "evidence"},
                    ],
                },
                {
                    "label": "支撑证据",
                    "kind": "evidence",
                    "summary": "把证据按来源或口径分层。",
                    "side": "right",
                    "children": [
                        {"label": "专家/渠道", "kind": "evidence"},
                        {"label": "公司口径", "kind": "evidence"},
                    ],
                },
                {
                    "label": "风险与反例",
                    "kind": "risk",
                    "summary": "防止导图只剩单边论证。",
                    "side": "left",
                    "children": [
                        {"label": "会推翻判断的信号", "kind": "question"},
                    ],
                },
                {
                    "label": "跟踪清单",
                    "kind": "question",
                    "summary": "把后续要追的资料挂在这里。",
                    "side": "right",
                    "children": [
                        {"label": "下一次验证点", "kind": "timeline"},
                    ],
                },
            ],
        }
    if template_key == "value_chain":
        return {
            "label": "产业链图谱",
            "kind": "topic",
            "summary": "适合把上中下游、价格和传导拆开。",
            "children": [
                {
                    "label": "上游供给",
                    "kind": "topic",
                    "side": "left",
                    "children": [
                        {"label": "约束点", "kind": "risk"},
                        {"label": "放量节点", "kind": "catalyst"},
                    ],
                },
                {
                    "label": "中游制造",
                    "kind": "topic",
                    "side": "right",
                    "children": [
                        {"label": "良率/产能", "kind": "evidence"},
                    ],
                },
                {
                    "label": "下游需求",
                    "kind": "topic",
                    "side": "left",
                    "children": [
                        {"label": "客户结构", "kind": "thesis"},
                    ],
                },
                {
                    "label": "价格与利润率",
                    "kind": "thesis",
                    "side": "right",
                    "children": [
                        {"label": "传导节奏", "kind": "timeline"},
                    ],
                },
            ],
        }
    if template_key == "debrief":
        return {
            "label": "访谈复盘",
            "kind": "topic",
            "summary": "把结论、分歧和待跟进动作拆开。",
            "children": [
                {
                    "label": "核心结论",
                    "kind": "thesis",
                    "side": "left",
                    "children": [
                        {"label": "最强一句话", "kind": "thesis"},
                    ],
                },
                {
                    "label": "新增信息",
                    "kind": "evidence",
                    "side": "right",
                    "children": [
                        {"label": "与旧判断不同", "kind": "evidence"},
                    ],
                },
                {
                    "label": "分歧与疑点",
                    "kind": "question",
                    "side": "left",
                    "children": [
                        {"label": "需要交叉验证", "kind": "question"},
                    ],
                },
                {
                    "label": "后续动作",
                    "kind": "timeline",
                    "side": "right",
                    "children": [
                        {"label": "谁来跟", "kind": "timeline"},
                    ],
                },
            ],
        }

    return {
        "label": "研究主题",
        "kind": "topic",
        "summary": "从这里开始搭你的导图。",
        "children": [
            {"label": "主线", "kind": "thesis", "side": "left"},
            {"label": "证据", "kind": "evidence", "side": "right"},
            {"label": "风险", "kind": "risk", "side": "left"},
            {"label": "待验证", "kind": "question", "side": "right"},
        ],
    }


def instantiate_mindmap_studio_blueprint(
    blueprint: dict[str, Any],
    *,
    nodes: list[dict[str, Any]],
    parent_id: str | None,
    side: str,
    order: int,
) -> str:
    node_id = uuid.uuid4().hex[:10]
    label = re.sub(r"\s+", " ", str(blueprint.get("label") or "").strip())[:80] or "未命名节点"
    summary = re.sub(r"\s+", " ", str(blueprint.get("summary") or "").strip())[:240]
    note = trim_note_content(str(blueprint.get("note") or "").strip(), limit=2000)
    node_side = "center" if parent_id is None else normalize_mindmap_studio_side(blueprint.get("side"), fallback=side)
    node = {
        "id": node_id,
        "parent_id": parent_id,
        "side": node_side,
        "order": max(order, 0),
        "label": label,
        "summary": summary,
        "note": note,
        "kind": normalize_mindmap_studio_node_kind(blueprint.get("kind")),
        "origin_mode": "seed",
        "verify_state": "draft",
        "origin_snapshot_node_id": "",
        "symbols": normalize_stock_symbol_list(blueprint.get("symbols", []))[:10],
        "tags": normalize_tag_list(blueprint.get("tags", []))[:12],
        "time_hint": re.sub(r"\s+", " ", str(blueprint.get("time_hint") or "").strip())[:120],
        "collapsed": bool(blueprint.get("collapsed")),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    nodes.append(node)

    for child_index, raw_child in enumerate(blueprint.get("children", []) if isinstance(blueprint.get("children"), list) else []):
        if not isinstance(raw_child, dict):
            continue
        instantiate_mindmap_studio_blueprint(
            raw_child,
            nodes=nodes,
            parent_id=node_id,
            side=node_side if node_side in {"left", "right"} else normalize_mindmap_studio_side(raw_child.get("side"), fallback="right"),
            order=child_index,
        )

    return node_id


def build_mindmap_studio_document(*, template_key: str = "blank", title: str | None = None) -> dict[str, Any]:
    template_key = normalize_mindmap_studio_template_key(template_key)
    template_meta = MINDMAP_STUDIO_TEMPLATE_META[template_key]
    layout_key = {
        "blank": "mindmap",
        "thesis": "mindmap",
        "value_chain": "lanes",
        "debrief": "logic",
    }.get(template_key, "mindmap")
    nodes: list[dict[str, Any]] = []
    instantiate_mindmap_studio_blueprint(
        build_mindmap_studio_template_blueprint(template_key),
        nodes=nodes,
        parent_id=None,
        side="center",
        order=0,
    )
    root_id = nodes[0]["id"]
    return {
        "id": uuid.uuid4().hex[:12],
        "source_record_id": "",
        "title": re.sub(r"\s+", " ", str(title or template_meta["label"]).strip())[:120] or "新导图",
        "template_key": template_key,
        "theme_key": "graphite",
        "surface_key": "embedded",
        "density_key": "roomy",
        "layout_key": layout_key,
        "active_node_id": root_id,
        "root_id": root_id,
        "reference_document_ids": [],
        "generated_snapshot": None,
        "nodes": nodes,
        "relationships": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def normalize_mindmap_studio_node(raw_node: Any) -> dict[str, Any] | None:
    if not isinstance(raw_node, dict):
        return None

    label = re.sub(r"\s+", " ", str(raw_node.get("label") or "").strip())[:80]
    if not label:
        return None

    try:
        order = max(int(raw_node.get("order") or 0), 0)
    except (TypeError, ValueError):
        order = 0

    return {
        "id": str(raw_node.get("id") or uuid.uuid4().hex[:10]).strip()[:24] or uuid.uuid4().hex[:10],
        "parent_id": str(raw_node.get("parent_id") or "").strip()[:24] or None,
        "side": normalize_mindmap_studio_side(raw_node.get("side")),
        "order": order,
        "label": label,
        "summary": re.sub(r"\s+", " ", str(raw_node.get("summary") or "").strip())[:240],
        "note": trim_note_content(str(raw_node.get("note") or "").strip(), limit=5000),
        "kind": normalize_mindmap_studio_node_kind(raw_node.get("kind")),
        "origin_mode": normalize_mindmap_studio_origin_mode(raw_node.get("origin_mode")),
        "verify_state": normalize_mindmap_studio_verify_state(raw_node.get("verify_state")),
        "origin_snapshot_node_id": str(raw_node.get("origin_snapshot_node_id") or "").strip()[:24],
        "symbols": normalize_stock_symbol_list(raw_node.get("symbols", []))[:10],
        "tags": normalize_tag_list(raw_node.get("tags", []))[:12],
        "time_hint": re.sub(r"\s+", " ", str(raw_node.get("time_hint") or "").strip())[:120],
        "collapsed": bool(raw_node.get("collapsed")),
        "created_at": str(raw_node.get("created_at") or now_iso()),
        "updated_at": str(raw_node.get("updated_at") or now_iso()),
    }


def normalize_mindmap_studio_relationship(raw_relationship: Any, *, node_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(raw_relationship, dict):
        return None

    from_node_id = str(raw_relationship.get("from_node_id") or raw_relationship.get("from") or "").strip()[:24]
    to_node_id = str(raw_relationship.get("to_node_id") or raw_relationship.get("to") or "").strip()[:24]
    if not from_node_id or not to_node_id or from_node_id == to_node_id:
        return None
    if from_node_id not in node_ids or to_node_id not in node_ids:
        return None

    label = re.sub(r"\s+", " ", str(raw_relationship.get("label") or "").strip())[:60]
    if not label:
        return None

    return {
        "id": str(raw_relationship.get("id") or uuid.uuid4().hex[:10]).strip()[:24] or uuid.uuid4().hex[:10],
        "from_node_id": from_node_id,
        "to_node_id": to_node_id,
        "label": label,
        "tone": normalize_mindmap_studio_relation_tone(raw_relationship.get("tone")),
    }


def normalize_mindmap_studio_snapshot(raw_snapshot: Any) -> dict[str, Any] | None:
    if not isinstance(raw_snapshot, dict):
        return None

    nodes = [
        node
        for raw_node in raw_snapshot.get("nodes", []) if isinstance(raw_snapshot.get("nodes"), list)
        if (node := normalize_mindmap_studio_node(raw_node)) is not None
    ][:240]
    node_ids = {node["id"] for node in nodes}
    relationships = [
        relationship
        for raw_relationship in raw_snapshot.get("relationships", []) if isinstance(raw_snapshot.get("relationships"), list)
        if (relationship := normalize_mindmap_studio_relationship(raw_relationship, node_ids=node_ids)) is not None
    ][:48]
    return {
        "generated_at": str(raw_snapshot.get("generated_at") or now_iso()),
        "reference_document_ids": normalize_identifier_list(raw_snapshot.get("reference_document_ids", []), max_items=16),
        "nodes": nodes,
        "relationships": relationships,
    }


def group_mindmap_studio_children(document: dict[str, Any]) -> dict[str | None, list[dict[str, Any]]]:
    children: defaultdict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for node in document.get("nodes", []):
        children[node.get("parent_id")].append(node)
    for parent_id, items in children.items():
        items.sort(key=lambda item: (item.get("order", 0), item.get("label", "").casefold(), item.get("id", "")))
        for index, item in enumerate(items):
            item["order"] = index
    return dict(children)


def collect_mindmap_studio_subtree_ids(document: dict[str, Any], node_id: str) -> set[str]:
    children = group_mindmap_studio_children(document)
    collected: set[str] = set()

    def walk(current_id: str) -> None:
        if current_id in collected:
            return
        collected.add(current_id)
        for child in children.get(current_id, []):
            walk(child["id"])

    walk(node_id)
    return collected


def normalize_mindmap_studio_document(raw_document: Any) -> dict[str, Any]:
    if not isinstance(raw_document, dict):
        return build_mindmap_studio_document()

    title = re.sub(r"\s+", " ", str(raw_document.get("title") or "").strip())[:120] or "新导图"
    template_key = normalize_mindmap_studio_template_key(raw_document.get("template_key"))

    nodes = [
        node
        for raw_node in raw_document.get("nodes", []) if isinstance(raw_document.get("nodes"), list)
        if (node := normalize_mindmap_studio_node(raw_node)) is not None
    ][:240]
    if not nodes:
        seeded = build_mindmap_studio_document(template_key=template_key, title=title)
        seeded["id"] = str(raw_document.get("id") or seeded["id"])[:12]
        return seeded

    root_candidates = [node for node in nodes if not node.get("parent_id")]
    root = root_candidates[0] if root_candidates else nodes[0]
    root["parent_id"] = None
    root["side"] = "center"

    node_lookup = {node["id"]: node for node in nodes}
    root_id = root["id"]
    for node in nodes:
        if node["id"] == root_id:
            continue
        if not node.get("parent_id") or node["parent_id"] not in node_lookup or node["parent_id"] == node["id"]:
            node["parent_id"] = root_id

    node_lookup = {node["id"]: node for node in nodes}
    children = group_mindmap_studio_children({"nodes": nodes})
    ordered_ids: list[str] = []
    seen: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in seen or node_id not in node_lookup:
            return
        seen.add(node_id)
        ordered_ids.append(node_id)
        for child in children.get(node_id, []):
            visit(child["id"])

    visit(root_id)
    for node in nodes:
        if node["id"] not in seen:
            node["parent_id"] = root_id
    node_lookup = {node["id"]: node for node in nodes}
    children = group_mindmap_studio_children({"nodes": nodes})
    ordered_ids = []
    seen = set()
    visit(root_id)
    normalized_nodes = [node_lookup[node_id] for node_id in ordered_ids]

    node_lookup = {node["id"]: node for node in normalized_nodes}
    for node in normalized_nodes:
        if node["id"] == root_id:
            node["side"] = "center"
            continue
        parent = node_lookup.get(node.get("parent_id") or "")
        if parent and parent["id"] == root_id:
            node["side"] = normalize_mindmap_studio_side(node.get("side"), fallback="right")
        else:
            node["side"] = parent["side"] if parent else "right"

    node_ids = {node["id"] for node in normalized_nodes}
    relationships: list[dict[str, Any]] = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for raw_relationship in raw_document.get("relationships", []) if isinstance(raw_document.get("relationships"), list) else []:
        relationship = normalize_mindmap_studio_relationship(raw_relationship, node_ids=node_ids)
        if relationship is None:
            continue
        dedupe_key = (
            relationship["from_node_id"],
            relationship["to_node_id"],
            relationship["label"].casefold(),
        )
        if dedupe_key in seen_relationships:
            continue
        seen_relationships.add(dedupe_key)
        relationships.append(relationship)

    active_node_id = str(raw_document.get("active_node_id") or "").strip()
    if active_node_id not in node_ids:
        active_node_id = root_id

    return {
        "id": str(raw_document.get("id") or uuid.uuid4().hex[:12]).strip()[:12] or uuid.uuid4().hex[:12],
        "title": title,
        "source_record_id": str(raw_document.get("source_record_id") or "").strip()[:24],
        "template_key": template_key,
        "theme_key": normalize_mindmap_studio_theme_key(raw_document.get("theme_key")),
        "surface_key": normalize_mindmap_studio_surface_key(raw_document.get("surface_key")),
        "density_key": normalize_mindmap_studio_density_key(raw_document.get("density_key")),
        "layout_key": normalize_mindmap_studio_layout_key(raw_document.get("layout_key")),
        "active_node_id": active_node_id,
        "root_id": root_id,
        "reference_document_ids": normalize_identifier_list(raw_document.get("reference_document_ids", []), max_items=16),
        "generated_snapshot": normalize_mindmap_studio_snapshot(raw_document.get("generated_snapshot")),
        "nodes": normalized_nodes,
        "relationships": relationships[:48],
        "created_at": str(raw_document.get("created_at") or now_iso()),
        "updated_at": str(raw_document.get("updated_at") or now_iso()),
    }


def build_mindmap_studio_tree(document: dict[str, Any]) -> dict[str, Any]:
    node_lookup = {node["id"]: deepcopy(node) for node in document.get("nodes", [])}
    children = group_mindmap_studio_children(document)

    def attach(node_id: str, depth: int, branch_side: str) -> dict[str, Any]:
        node = deepcopy(node_lookup[node_id])
        side = node["side"] if node["side"] in {"left", "right"} else branch_side
        node["branch_side"] = side
        node["depth"] = depth
        node["children"] = [
            attach(child["id"], depth + 1, side)
            for child in children.get(node_id, [])
        ]
        return node

    return attach(document["root_id"], 0, "center")


def compute_mindmap_studio_depth(node: dict[str, Any]) -> int:
    children = node.get("children", [])
    if not children:
        return 1
    return 1 + max(compute_mindmap_studio_depth(child) for child in children)


def count_mindmap_studio_leaf_nodes(node: dict[str, Any]) -> int:
    children = node.get("children", [])
    if not children:
        return 1
    return sum(count_mindmap_studio_leaf_nodes(child) for child in children)


def build_mindmap_studio_outline_lines(node: dict[str, Any], *, depth: int = 0) -> list[str]:
    indent = "  " * depth
    summary = str(node.get("summary") or "").strip()
    line = f"{indent}- {node['label']}"
    if summary:
        line += f": {summary}"
    lines = [line]
    for child in node.get("children", []):
        lines.extend(build_mindmap_studio_outline_lines(child, depth=depth + 1))
    return lines


def build_mindmap_studio_document_stats(document: dict[str, Any]) -> dict[str, Any]:
    tree = build_mindmap_studio_tree(document)
    return {
        "node_count": len(document.get("nodes", [])),
        "relationship_count": len(document.get("relationships", [])),
        "leaf_count": count_mindmap_studio_leaf_nodes(tree),
        "max_depth": compute_mindmap_studio_depth(tree),
        "outline_markdown": "\n".join(build_mindmap_studio_outline_lines(tree)),
        "tree": tree,
    }


def build_mindmap_studio_document_card(document: dict[str, Any]) -> dict[str, Any]:
    stats = build_mindmap_studio_document_stats(document)
    return {
        "id": document["id"],
        "title": document["title"],
        "template_key": document["template_key"],
        "template_label": MINDMAP_STUDIO_TEMPLATE_META.get(document["template_key"], MINDMAP_STUDIO_TEMPLATE_META["blank"])["label"],
        "theme_key": document["theme_key"],
        "theme_label": MINDMAP_STUDIO_THEME_META[document["theme_key"]]["label"],
        "surface_key": document["surface_key"],
        "surface_label": MINDMAP_STUDIO_SURFACE_META[document["surface_key"]]["label"],
        "density_key": document["density_key"],
        "density_label": MINDMAP_STUDIO_DENSITY_META[document["density_key"]]["label"],
        "layout_key": document["layout_key"],
        "layout_label": MINDMAP_STUDIO_LAYOUT_META[document["layout_key"]]["label"],
        "updated_at": document["updated_at"],
        "updated_label": format_iso_timestamp(document["updated_at"]),
        "node_count": stats["node_count"],
        "relationship_count": stats["relationship_count"],
        "max_depth": stats["max_depth"],
        "has_generated_snapshot": bool(document.get("generated_snapshot")),
    }


def serialize_mindmap_studio_document(document: dict[str, Any]) -> dict[str, Any]:
    stats = build_mindmap_studio_document_stats(document)
    return {
        **deepcopy(document),
        "theme_label": MINDMAP_STUDIO_THEME_META[document["theme_key"]]["label"],
        "surface_label": MINDMAP_STUDIO_SURFACE_META[document["surface_key"]]["label"],
        "density_label": MINDMAP_STUDIO_DENSITY_META[document["density_key"]]["label"],
        "layout_label": MINDMAP_STUDIO_LAYOUT_META[document["layout_key"]]["label"],
        "stats": {
            "node_count": stats["node_count"],
            "relationship_count": stats["relationship_count"],
            "leaf_count": stats["leaf_count"],
            "max_depth": stats["max_depth"],
        },
        "outline_markdown": stats["outline_markdown"],
        "tree": stats["tree"],
    }


def normalize_mindmap_studio_store(data: Any) -> dict[str, Any]:
    source = data if isinstance(data, dict) else {}
    documents = [
        document
        for raw_document in source.get("documents", []) if isinstance(source.get("documents"), list)
        if (document := normalize_mindmap_studio_document(raw_document)) is not None
    ]
    documents.sort(key=lambda item: (coerce_sort_timestamp(item.get("updated_at")), item["id"]), reverse=True)
    return {
        "documents": documents,
        "updated_at": str(source.get("updated_at") or now_iso()),
    }


def load_mindmap_studio_store() -> dict[str, Any]:
    if not MINDMAP_STUDIO_STORE_PATH.exists():
        return normalize_mindmap_studio_store({})
    try:
        raw_data = json.loads(MINDMAP_STUDIO_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return normalize_mindmap_studio_store({})
    return normalize_mindmap_studio_store(raw_data)


def save_mindmap_studio_store(store: dict[str, Any]) -> None:
    normalized = normalize_mindmap_studio_store(store)
    normalized["updated_at"] = now_iso()
    MINDMAP_STUDIO_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MINDMAP_STUDIO_STORE_PATH.with_suffix(MINDMAP_STUDIO_STORE_PATH.suffix + ".tmp")
    temp_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(MINDMAP_STUDIO_STORE_PATH)


def ensure_mindmap_studio_seeded(store: dict[str, Any]) -> dict[str, Any]:
    if store.get("documents"):
        return store
    store["documents"] = [
        build_mindmap_studio_document(template_key="thesis", title="研究导图工作台"),
    ]
    store["updated_at"] = now_iso()
    return store


def get_mindmap_studio_document(store: dict[str, Any], document_id: str) -> dict[str, Any]:
    for document in store.get("documents", []):
        if document["id"] == document_id:
            return document
    raise KeyError(document_id)


def build_mindmap_studio_bootstrap_payload(store: dict[str, Any], *, document_id: str | None = None) -> dict[str, Any]:
    store = ensure_mindmap_studio_seeded(store)
    documents = store.get("documents", [])
    active_document = None
    if document_id:
        active_document = next((item for item in documents if item["id"] == document_id), None)
    if active_document is None and documents:
        active_document = documents[0]

    return {
        "documents": [build_mindmap_studio_document_card(document) for document in documents],
        "active_document": serialize_mindmap_studio_document(active_document) if active_document else None,
        "theme_options": [
            {"key": key, **value}
            for key, value in MINDMAP_STUDIO_THEME_META.items()
        ],
        "surface_options": [
            {"key": key, **value}
            for key, value in MINDMAP_STUDIO_SURFACE_META.items()
        ],
        "density_options": [
            {"key": key, **value}
            for key, value in MINDMAP_STUDIO_DENSITY_META.items()
        ],
        "layout_options": [
            {"key": key, **value}
            for key, value in MINDMAP_STUDIO_LAYOUT_META.items()
        ],
        "kind_options": [
            {"key": key, "label": value}
            for key, value in MINDMAP_STUDIO_NODE_KIND_META.items()
        ],
        "relation_tones": [
            {"key": key, "label": value}
            for key, value in MINDMAP_STUDIO_RELATION_TONE_META.items()
        ],
        "origin_options": [
            {"key": key, "label": value}
            for key, value in MINDMAP_STUDIO_ORIGIN_META.items()
        ],
        "verify_options": [
            {"key": key, "label": value}
            for key, value in MINDMAP_STUDIO_VERIFY_META.items()
        ],
        "template_options": [
            {"key": key, **value}
            for key, value in MINDMAP_STUDIO_TEMPLATE_META.items()
        ],
    }


def build_mindmap_studio_note_from_generated_node(node: dict[str, Any]) -> str:
    sections: list[str] = []
    confidence = normalize_mindmap_confidence(node.get("confidence"))
    source_refs = [str(item).strip() for item in node.get("source_refs", []) if str(item).strip()]
    if source_refs:
        sections.append("来源引用\n" + "\n".join(f"- {item}" for item in source_refs[:8]))
    if confidence:
        sections.append(f"置信度\n- {confidence}")

    evidence = [str(item).strip() for item in node.get("evidence", []) if str(item).strip()]
    if evidence:
        sections.append("证据\n" + "\n".join(f"- {item}" for item in evidence[:6]))

    source_notes = [str(item).strip() for item in node.get("source_notes", []) if str(item).strip()]
    if source_notes:
        sections.append("资料关系\n" + "\n".join(f"- {item}" for item in source_notes[:6]))

    time_signals = [str(item).strip() for item in node.get("time_signals", []) if str(item).strip()]
    if len(time_signals) > 1:
        sections.append("时间信号\n" + "\n".join(f"- {item}" for item in time_signals[:6]))

    return trim_note_content("\n\n".join(sections).strip(), limit=5000)


def mindmap_confidence_to_verify_state(confidence: str | None) -> str:
    normalized = normalize_mindmap_confidence(confidence)
    if normalized == "high":
        return "verified"
    if normalized == "low":
        return "needs_verify"
    return "draft"


def infer_mindmap_studio_relation_tone(label: str) -> str:
    normalized = str(label or "").casefold()
    if any(token in normalized for token in ("冲突", "矛盾", "相反", "对冲", "修正")):
        return "conflict"
    if any(token in normalized for token in ("传导", "上游", "下游", "因果", "驱动", "影响")):
        return "flow"
    if any(token in normalized for token in ("补充", "验证", "支持", "印证")):
        return "support"
    return "compare"


def convert_generated_mindmap_to_studio_document(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("map_payload") or {}
    root = payload.get("root")
    if not isinstance(root, dict):
        raise ValueError("导图结果里缺少可用的根节点。")

    structure_kind = str(payload.get("structure_kind") or "").strip().lower()
    template_key = {
        "single_stock": "thesis",
        "peer_group": "thesis",
        "value_chain": "value_chain",
        "theme_bundle": "debrief",
    }.get(structure_kind, "thesis")
    layout_key = {
        "single_stock": "mindmap",
        "peer_group": "mindmap",
        "value_chain": "lanes",
        "theme_bundle": "logic",
    }.get(structure_kind, "mindmap")

    document = build_mindmap_studio_document(template_key=template_key, title=payload.get("title") or record.get("title"))
    document["source_record_id"] = record["id"]
    document["template_key"] = template_key
    document["layout_key"] = layout_key
    document["theme_key"] = "graphite"
    document["surface_key"] = "embedded"
    document["density_key"] = "roomy"

    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def walk(raw_node: dict[str, Any], *, parent_id: str | None, order: int, side: str) -> str:
        raw_id = str(raw_node.get("id") or "").strip()
        node_id = ensure_unique_id(raw_id, node_ids, length=10)
        node_ids.add(node_id)
        time_signals = [
            re.sub(r"\s+", " ", str(item or "").strip())[:120]
            for item in raw_node.get("time_signals", [])
            if re.sub(r"\s+", " ", str(item or "").strip())[:120]
        ]
        studio_node = {
            "id": node_id,
            "parent_id": parent_id,
            "side": "center" if parent_id is None else side,
            "order": max(order, 0),
            "label": re.sub(r"\s+", " ", str(raw_node.get("label") or "").strip())[:80] or "未命名节点",
            "summary": re.sub(r"\s+", " ", str(raw_node.get("summary") or "").strip())[:240],
            "note": build_mindmap_studio_note_from_generated_node(raw_node),
            "kind": {
                "root": "thesis",
                "theme": "topic",
                "topic": "topic",
                "question": "question",
                "risk": "risk",
                "catalyst": "catalyst",
                "evidence": "evidence",
                "timeline": "timeline",
            }.get(str(raw_node.get("kind") or "").strip().lower(), "topic"),
            "origin_mode": "generated",
            "verify_state": mindmap_confidence_to_verify_state(raw_node.get("confidence")),
            "origin_snapshot_node_id": node_id,
            "symbols": normalize_stock_symbol_list(raw_node.get("symbols", []))[:10],
            "tags": [],
            "time_hint": time_signals[0] if time_signals else "",
            "collapsed": False,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        nodes.append(studio_node)

        for child_index, child in enumerate(raw_node.get("children", []) if isinstance(raw_node.get("children"), list) else []):
            child_side = side
            if parent_id is None and layout_key == "mindmap":
                child_side = "left" if child_index % 2 == 0 else "right"
            elif parent_id is None:
                child_side = "right"
            walk(child, parent_id=node_id, order=child_index, side=child_side)
        return node_id

    root_id = walk(root, parent_id=None, order=0, side="center")
    document["nodes"] = nodes
    document["root_id"] = root_id
    document["active_node_id"] = root_id

    relationships: list[dict[str, Any]] = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for raw_link in payload.get("cross_links", []) if isinstance(payload.get("cross_links"), list) else []:
        from_node_id = str(raw_link.get("from") or "").strip()
        to_node_id = str(raw_link.get("to") or "").strip()
        label = re.sub(r"\s+", " ", str(raw_link.get("label") or "").strip())[:60]
        if not from_node_id or not to_node_id or not label:
            continue
        if from_node_id not in node_ids or to_node_id not in node_ids or from_node_id == to_node_id:
            continue
        dedupe_key = (from_node_id, to_node_id, label.casefold())
        if dedupe_key in seen_relationships:
            continue
        seen_relationships.add(dedupe_key)
        relationships.append(
            {
                "id": uuid.uuid4().hex[:10],
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "label": label,
                "tone": infer_mindmap_studio_relation_tone(label),
            }
        )
    document["relationships"] = relationships[:48]
    document["generated_snapshot"] = {
        "generated_at": now_iso(),
        "reference_document_ids": [],
        "nodes": deepcopy(document["nodes"]),
        "relationships": deepcopy(document["relationships"]),
    }
    document["updated_at"] = now_iso()
    return normalize_mindmap_studio_document(document)


def sync_generated_mindmap_to_studio(record_id: str) -> str | None:
    record = read_mindmap_record(record_id)
    if not record or not record.get("map_payload"):
        return None

    document = convert_generated_mindmap_to_studio_document(record)
    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        existing = next((item for item in store.get("documents", []) if item.get("source_record_id") == record_id), None)
        if existing is not None:
            document["id"] = existing["id"]
            document["created_at"] = str(existing.get("created_at") or document["created_at"])
            document["reference_document_ids"] = existing.get("reference_document_ids", [])
            store["documents"] = [document if item["id"] == existing["id"] else item for item in store.get("documents", [])]
        else:
            store.setdefault("documents", []).insert(0, document)
        save_mindmap_studio_store(store)
    return document["id"]


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
        package_title = f"{normalized_symbol} 近 7 天会议资料包"
        export_slug = f"gpt-{normalized_symbol.lower()}-transcripts-week-{now.strftime('%Y%m%d')}"
        report_items = [item for item in find_related_reports(normalized_symbol, limit=12) if float(item.get("sort_key") or 0) >= cutoff_timestamp]
    else:
        raise RuntimeError("暂不支持这个导出类型。")

    notes: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    earnings_calls: list[dict[str, Any]] = []
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

        for call in entry["earnings_calls"]:
            call_item = build_stock_earnings_call_material_item(item_symbol, call)
            if package_kind in {"weekly", "stock_transcripts_week"} and float(call_item.get("sort_value") or 0) < cutoff_timestamp:
                continue
            earnings_calls.append(call_item)

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
    earnings_calls.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    transcripts.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    report_items.sort(key=lambda item: (float(item.get("sort_key") or 0), item["title"]), reverse=True)

    included_symbols = ordered_unique(
        [item["symbol"] for item in notes if item["symbol"]]
        + [item["symbol"] for item in files if item["symbol"]]
        + [item["symbol"] for item in earnings_calls if item["symbol"]]
        + [linked_symbol for item in transcripts for linked_symbol in item.get("symbols", [])]
    )
    tag_summary = collect_tag_counts(notes + files + earnings_calls + transcripts)[:16]

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
    for call in earnings_calls:
        timeline.append(
            {
                "kind": "电话会议",
                "symbol": call["symbol"],
                "title": call["title"],
                "summary": call["summary"],
                "display_time": call["display_time"],
                "sort_value": call["sort_value"],
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
        "earnings_calls": earnings_calls,
        "transcripts": transcripts,
        "included_symbols": included_symbols,
        "tag_summary": tag_summary,
        "timeline": timeline[:80],
        "counts": {
            "reports": len(report_items),
            "notes": len(notes),
            "files": len(files),
            "earnings_calls": len(earnings_calls),
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
        f"- 包含管理层电话会议: {context['counts'].get('earnings_calls', 0)} 条",
        f"- 包含会议转录: {context['counts']['transcripts']} 条",
        "",
        "## 建议上传顺序",
        "1. 先上传 `01_PACKAGE_SUMMARY.md`，让外部 GPT 快速建立全局上下文。",
        "2. 如果需要原文对照，再追加 `reports/`、`notes/`、`earnings_calls/`、`transcripts/` 里的 markdown。",
        "3. 如果还要核对原始文档，再上传 `files/` 下的原文件；语音相关问题可再补 `media/`。",
        "",
        "## 推荐提问方式",
        "- 先让它基于 `01_PACKAGE_SUMMARY.md` 做总览判断。",
        "- 再追加一两份关键原文，让它做对比、找矛盾、找遗漏证据。",
        "- 如果是会议场景，优先上传 `earnings_calls/` 的管理层电话会议稿，其次再补 `transcripts/` 的整理稿和音频源文件。",
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
        f"- 管理层电话会议: {context['counts'].get('earnings_calls', 0)} 条",
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

    if context["earnings_calls"]:
        lines.extend(["", "## 管理层电话会议摘要"])
        for call in context["earnings_calls"][:20]:
            lines.append(f"- [{call['symbol']}] {call['display_time']} | {call['title']} | {call['summary']}")

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


def build_ai_export_earnings_call_markdown(call: dict[str, Any]) -> str:
    lines = [
        f"# {call['title']}",
        "",
        f"- 股票: {call['symbol'] or '未关联'}",
        f"- 日期: {call['display_time']}",
        f"- 财季: {call.get('fiscal_label') or '待补充'}",
        f"- 来源: {call.get('source_label') or '未标注'}",
        f"- 来源链接: {call.get('source_url') or '无'}",
        f"- 完整性: {'已校验正文' if call.get('is_complete') else '待复核'}",
        f"- 问答: {'含问答' if call.get('has_question_section') else '未识别'}",
        f"- 质量提示: {'；'.join(call.get('quality_chips') or []) or '无'}",
        "",
        "## 摘要",
        call.get("summary") or "当前电话会议还没有可导出的摘要。",
        "",
        "## 电话会议正文",
        call.get("transcript_text") or "当前电话会议还没有可导出的正文。",
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
    include_earnings_calls: bool | None = None,
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
    include_earnings_calls = bool(include_earnings_calls)
    include_transcripts = bool(include_transcripts)
    if not any([include_reports, include_notes, include_files, include_earnings_calls, include_transcripts]):
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
    earnings_calls: list[dict[str, Any]] = []
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

        if include_earnings_calls:
            for call in entry["earnings_calls"]:
                call_item = build_stock_earnings_call_material_item(item_symbol, call)
                if not in_selected_range(float(call_item.get("sort_value") or 0)):
                    continue
                earnings_calls.append(call_item)

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
    earnings_calls.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)
    transcripts.sort(key=lambda item: (item["sort_value"], item["title"]), reverse=True)

    included_symbols = ordered_unique(
        [item["symbol"] for item in notes if item["symbol"]]
        + [item["symbol"] for item in files if item["symbol"]]
        + [item["symbol"] for item in earnings_calls if item["symbol"]]
        + [linked_symbol for item in transcripts for linked_symbol in item.get("symbols", [])]
    )
    tag_summary = collect_tag_counts(notes + files + earnings_calls + transcripts)[:16]

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
    for call in earnings_calls:
        timeline.append(
            {
                "kind": "电话会议",
                "symbol": call["symbol"],
                "title": call["title"],
                "summary": call["summary"],
                "display_time": call["display_time"],
                "sort_value": call["sort_value"],
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
            ("电话会议", include_earnings_calls),
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
            ("earnings-calls", include_earnings_calls),
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
        "earnings_calls": earnings_calls,
        "transcripts": transcripts,
        "included_symbols": included_symbols,
        "tag_summary": tag_summary,
        "timeline": timeline[:80],
        "counts": {
            "reports": len(report_items),
            "notes": len(notes),
            "files": len(files),
            "earnings_calls": len(earnings_calls),
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
            "include_earnings_calls": include_earnings_calls,
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
        f"- 内容类型: {'、'.join(filters.get('content_labels') or ['日报', '笔记', '资料', '电话会议', '转录'])}",
        f"- 包含日报: {context['counts']['reports']} 篇",
        f"- 包含笔记: {context['counts']['notes']} 条",
        f"- 包含研究资料: {context['counts']['files']} 份",
        f"- 包含管理层电话会议: {context['counts'].get('earnings_calls', 0)} 条",
        f"- 包含会议转录: {context['counts']['transcripts']} 条",
        "",
        "## 建议上传顺序",
        "1. 先上传 `01_PACKAGE_SUMMARY.md`，让外部 GPT 先建立整体上下文。",
        "2. 如果需要原文对照，再补 `reports/`、`notes/`、`earnings_calls/`、`transcripts/` 目录下的 markdown。",
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
        f"- 内容类型: {'、'.join(filters.get('content_labels') or ['日报', '笔记', '资料', '电话会议', '转录'])}",
        f"- 涵盖股票: {', '.join(context['included_symbols']) or '无'}",
        f"- 日报: {context['counts']['reports']} 篇",
        f"- 笔记: {context['counts']['notes']} 条",
        f"- 研究资料: {context['counts']['files']} 份",
        f"- 管理层电话会议: {context['counts'].get('earnings_calls', 0)} 条",
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

    if context["earnings_calls"]:
        lines.extend(["", "## 管理层电话会议摘要"])
        for call in context["earnings_calls"][:20]:
            lines.append(f"- [{call['symbol']}] {call['display_time']} | {call['title']} | {call['summary']}")

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
    include_earnings_calls: bool | None = None,
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
        include_earnings_calls=include_earnings_calls,
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

            for call in context["earnings_calls"]:
                stem = build_export_file_stem(call["call_date"] or call["published_at"], call["id"], call["title"])
                archive.writestr(
                    f"earnings_calls/{call['symbol'] or 'unlinked'}/{stem}.md",
                    build_ai_export_earnings_call_markdown(call),
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
    content_kinds = request.args.get("content_kinds", "").strip() or ", ".join(AI_SCOPE_DEFAULT_CONTENT_KINDS)
    scope_settings = normalize_ai_scope_settings(
        {
            "use_stock_scope": request.args.get("use_stock_scope"),
            "symbols": request.args.get("symbols", ""),
            "content_kinds": content_kinds,
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
    elif str(request.form.get("scope_owner") or "").strip().lower() == "mindmap":
        save_mindmap_scope_draft(scope_settings)

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
    include_earnings_calls_raw = request.form.get("include_earnings_calls")
    include_transcripts_raw = request.form.get("include_transcripts")

    include_reports = None if include_reports_raw is None else include_reports_raw == "1"
    include_notes = None if include_notes_raw is None else include_notes_raw == "1"
    include_files = None if include_files_raw is None else include_files_raw == "1"
    include_earnings_calls = None if include_earnings_calls_raw is None else include_earnings_calls_raw == "1"
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
            symbol=storage_symbol,
            days=days,
            include_reports=include_reports,
            include_notes=include_notes,
            include_files=include_files,
            include_earnings_calls=include_earnings_calls,
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
    submitted_scope = extract_mindmap_scope_request_payload(request.form)
    try:
        scope_settings = normalize_ai_scope_settings(
            {
                "use_stock_scope": submitted_scope.get("use_stock_scope"),
                "symbols": submitted_scope.get("scope_symbols", ""),
                "content_kinds": submitted_scope.get("scope_content_kinds", ""),
                "use_date_scope": submitted_scope.get("use_date_scope"),
                "start_date": submitted_scope.get("scope_start_date"),
                "end_date": submitted_scope.get("scope_end_date"),
                "preview_month": submitted_scope.get("scope_preview_month"),
                "selected_date": submitted_scope.get("scope_selected_date"),
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


@app.get("/mindmaps")
def mindmap_workspace() -> str:
    reports = collect_reports()
    stock_store = load_stock_store()
    record_id = request.args.get("map", "").strip() or None
    return render_template(
        "mindmaps.html",
        **build_mindmap_page_context(record_id=record_id, reports=reports, stock_store=stock_store),
        **build_navigation_context(active_page="mindmaps", reports=reports, stock_store=stock_store),
    )


@app.get("/mindmaps/scope/preview")
def mindmap_scope_preview() -> str:
    stock_store = load_stock_store()
    reports = collect_reports()
    known_symbols = {item["symbol"] for item in build_stock_selector_options(stock_store)}
    content_kinds = request.args.get("content_kinds", "").strip() or ", ".join(AI_SCOPE_DEFAULT_CONTENT_KINDS)
    scope_settings = normalize_ai_scope_settings(
        {
            "use_stock_scope": request.args.get("use_stock_scope"),
            "symbols": request.args.get("symbols", ""),
            "content_kinds": content_kinds,
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


@app.post("/mindmaps/generate")
def generate_mindmap():
    if not codex_cli_available():
        flash("当前电脑还没有可用的本地 Codex，暂时无法生成思维图。", "error")
        return redirect(url_for("mindmap_workspace"))

    stock_store = load_stock_store()
    reports = collect_reports()
    known_symbols = {item["symbol"] for item in build_stock_selector_options(stock_store)}
    submitted_scope = extract_mindmap_scope_request_payload(request.form)
    draft_scope_settings = load_mindmap_scope_draft(known_symbols=known_symbols)
    try:
        scope_settings = normalize_ai_scope_settings(
            {
                "use_stock_scope": submitted_scope.get("use_stock_scope"),
                "symbols": submitted_scope.get("scope_symbols", ""),
                "content_kinds": submitted_scope.get("scope_content_kinds", ""),
                "use_date_scope": submitted_scope.get("use_date_scope"),
                "start_date": submitted_scope.get("scope_start_date"),
                "end_date": submitted_scope.get("scope_end_date"),
                "preview_month": submitted_scope.get("scope_preview_month"),
                "selected_date": submitted_scope.get("scope_selected_date"),
            },
            known_symbols=known_symbols,
        )
    except ValueError as exc:
        if should_use_mindmap_scope_draft_fallback(submitted_scope, draft_scope_settings):
            scope_settings = draft_scope_settings or normalize_ai_scope_settings({})
        else:
            flash(str(exc), "error")
            return redirect(url_for("mindmap_workspace"))
    save_mindmap_scope_draft(scope_settings)

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

    materials = collect_ai_scope_materials(stock_store, reports, scope_settings=scope_settings)
    if (
        materials["report_count"]
        + materials["note_count"]
        + materials["file_count"]
        + materials["earnings_call_count"]
        + materials["transcript_count"]
        <= 0
    ):
        flash("当前范围内还没有可用资料，先放宽股票范围或调整时间窗口再生成。", "error")
        return redirect(url_for("mindmap_workspace"))

    scope_summary = build_ai_scope_summary(scope_settings, materials)
    record = normalize_mindmap_record(
        {
            "id": uuid.uuid4().hex[:12],
            "title": build_mindmap_seed_title(scope_settings),
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "status": "pending",
            "model": model_slug,
            "reasoning_effort": reasoning_effort,
            "scope_settings": scope_settings,
            "scope_summary": scope_summary,
            "summary": "",
            "map_payload": None,
            "fingerprint": {
                "generated_at": now_iso(),
                "pipeline_version": MINDMAP_PIPELINE_VERSION,
                "prompt_version": MINDMAP_PROMPT_VERSION,
                "schema_version": MINDMAP_SCHEMA_VERSION,
                "validation": {
                    "warnings": [],
                    "errors": [],
                    "repair_attempted": False,
                },
            },
        }
    )
    if record is None:
        abort(500)

    with MINDMAP_LOCK:
        store = load_mindmap_store()
        store.setdefault("records", []).insert(0, record)
        save_mindmap_store(store)

    worker = threading.Thread(
        target=run_mindmap_generation,
        args=(record["id"],),
        kwargs={
            "model": model_slug,
            "reasoning_effort": reasoning_effort,
        },
        daemon=True,
    )
    worker.start()

    flash("\u5bfc\u56fe\u4efb\u52a1\u5df2\u63d0\u4ea4\uff0c\u6b63\u5728\u542f\u52a8\u3002", "success")
    return redirect(url_for("mindmap_workspace", map=record["id"]))


@app.post("/mindmaps/<record_id>/delete")
def delete_mindmap(record_id: str):
    redirect_id = ""
    running = False
    with MINDMAP_LOCK:
        store = load_mindmap_store()
        record = get_mindmap_record(store, record_id)
        running = record["status"] in {"pending", "running"}
        store["records"] = [item for item in store.get("records", []) if item["id"] != record_id]
        if store["records"]:
            redirect_id = store["records"][0]["id"]
        save_mindmap_store(store)

    if running:
        process = request_mindmap_stop(record_id)
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass

    if redirect_id:
        return redirect(url_for("mindmap_workspace", map=redirect_id))
    return redirect(url_for("mindmap_workspace"))


@app.post("/mindmaps/<record_id>/stop")
def stop_mindmap(record_id: str):
    with MINDMAP_LOCK:
        store = load_mindmap_store()
        record = get_mindmap_record(store, record_id)
        if record["status"] not in {"pending", "running"}:
            return redirect(url_for("mindmap_workspace", map=record_id))
        record["status"] = "cancelled"
        record["error"] = ""
        touch_mindmap_record(record)
        save_mindmap_store(store)

    process = request_mindmap_stop(record_id)
    if process is not None:
        try:
            process.terminate()
        except OSError:
            pass

    return redirect(url_for("mindmap_workspace", map=record_id))


@app.get("/mindmaps/<record_id>/status")
def mindmap_status(record_id: str):
    with MINDMAP_LOCK:
        store = load_mindmap_store()
        if reconcile_stale_mindmap_store(store):
            save_mindmap_store(store)
        record = get_mindmap_record(store, record_id)
    return jsonify(
        {
            "record_id": record["id"],
            "status": record["status"],
            "has_pending": record["status"] in {"pending", "running"},
            "updated_at": record["updated_at"],
        }
    )


@app.get("/labs/mindmap-studio")
def mindmap_studio_workspace() -> str:
    requested_document_id = request.args.get("doc", "").strip()
    return render_template(
        "mindmap_studio.html",
        requested_document_id=requested_document_id,
        mindmap_studio_bootstrap_url=url_for("mindmap_studio_bootstrap"),
        mindmap_studio_create_url=url_for("create_mindmap_studio_document"),
        mindmap_studio_current_url=url_for("mindmap_studio_workspace"),
    )


@app.get("/labs/mindmap-studio/bootstrap")
def mindmap_studio_bootstrap():
    requested_document_id = request.args.get("doc", "").strip() or None
    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        seeded = ensure_mindmap_studio_seeded(store)
        if seeded is store and (not MINDMAP_STUDIO_STORE_PATH.exists() or not store.get("documents")):
            save_mindmap_studio_store(store)
        payload = build_mindmap_studio_bootstrap_payload(store, document_id=requested_document_id)
    return jsonify({"ok": True, **payload})


@app.post("/labs/mindmap-studio/documents")
def create_mindmap_studio_document():
    payload = request.get_json(silent=True) or {}
    template_key = normalize_mindmap_studio_template_key(payload.get("template_key"))
    title = re.sub(r"\s+", " ", str(payload.get("title") or "").strip())[:120] or MINDMAP_STUDIO_TEMPLATE_META[template_key]["label"]

    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        document = build_mindmap_studio_document(template_key=template_key, title=title)
        store.setdefault("documents", []).insert(0, document)
        save_mindmap_studio_store(store)
        response_payload = build_mindmap_studio_bootstrap_payload(store, document_id=document["id"])

    return jsonify({"ok": True, **response_payload})


@app.post("/labs/mindmap-studio/documents/<document_id>/duplicate")
def duplicate_mindmap_studio_document(document_id: str):
    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        source_document = deepcopy(get_mindmap_studio_document(store, document_id))
        source_document["id"] = uuid.uuid4().hex[:12]
        source_document["title"] = (source_document["title"] + " 副本")[:120]
        source_document["created_at"] = now_iso()
        source_document["updated_at"] = now_iso()
        store.setdefault("documents", []).insert(0, normalize_mindmap_studio_document(source_document))
        save_mindmap_studio_store(store)
        response_payload = build_mindmap_studio_bootstrap_payload(store, document_id=source_document["id"])

    return jsonify({"ok": True, **response_payload})


@app.post("/labs/mindmap-studio/documents/<document_id>/delete")
def delete_mindmap_studio_document(document_id: str):
    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        get_mindmap_studio_document(store, document_id)
        store["documents"] = [item for item in store.get("documents", []) if item["id"] != document_id]
        if not store.get("documents"):
            ensure_mindmap_studio_seeded(store)
        save_mindmap_studio_store(store)
        next_document_id = store["documents"][0]["id"] if store.get("documents") else None
        response_payload = build_mindmap_studio_bootstrap_payload(store, document_id=next_document_id)

    return jsonify({"ok": True, **response_payload})


@app.post("/labs/mindmap-studio/documents/<document_id>/save")
def save_mindmap_studio_document(document_id: str):
    payload = request.get_json(silent=True) or {}
    raw_document = payload.get("document") if isinstance(payload, dict) else None
    if not isinstance(raw_document, dict):
        return jsonify({"ok": False, "message": "缺少可保存的导图数据。"}), 400

    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        existing_document = deepcopy(get_mindmap_studio_document(store, document_id))
        merged_document = {
            **raw_document,
            "id": existing_document["id"],
            "created_at": existing_document["created_at"],
            "updated_at": now_iso(),
            "generated_snapshot": (
                raw_document.get("generated_snapshot")
                if "generated_snapshot" in raw_document
                else existing_document.get("generated_snapshot")
            ),
            "reference_document_ids": (
                raw_document.get("reference_document_ids")
                if "reference_document_ids" in raw_document
                else existing_document.get("reference_document_ids", [])
            ),
        }
        normalized_document = normalize_mindmap_studio_document(merged_document)
        normalized_document["updated_at"] = now_iso()
        store["documents"] = [
            normalized_document if item["id"] == document_id else item
            for item in store.get("documents", [])
        ]
        save_mindmap_studio_store(store)
        response_payload = build_mindmap_studio_bootstrap_payload(store, document_id=document_id)

    return jsonify({"ok": True, **response_payload})


@app.get("/labs/mindmap-studio/documents/<document_id>/export.json")
def export_mindmap_studio_document(document_id: str):
    with MINDMAP_STUDIO_LOCK:
        store = load_mindmap_studio_store()
        document = deepcopy(get_mindmap_studio_document(store, document_id))
    export_payload = serialize_mindmap_studio_document(document)
    buffer = io.BytesIO(json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8"))
    filename = secure_filename(document["title"]) or f"mindmap-{document['id']}"
    return send_file(
        buffer,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"{filename}.json",
    )


@app.route("/")
def index() -> str:
    selected_name = str(request.args.get("report") or "").strip()
    if selected_name:
        return redirect(url_for("monitor_page", report=selected_name))
    return redirect(url_for("monitor_page"))


@app.get("/monitor")
def monitor_page() -> str:
    store = load_stock_store()
    reports = collect_reports()
    selected_signal_report = str(request.args.get("signal_report") or "").strip()
    active_tab = normalize_monitor_workspace_tab(
        request.args.get("tab"),
        fallback="signals" if selected_signal_report else "info",
    )
    return render_template(
        "monitor.html",
        reports_dir=str(REPORTS_DIR),
        signal_reports_dir=str(SIGNAL_MONITOR_REPORTS_DIR),
        monitor_active_tab=active_tab,
        **build_monitor_page_context(store, all_reports=reports),
        **build_signal_monitor_page_context(selected_name=selected_signal_report),
        **build_navigation_context(active_page="monitor", reports=reports, stock_store=store),
    )


@app.get("/data-monitor")
def data_monitor_page() -> str:
    reports = collect_reports()
    stock_store = load_stock_store()
    active_tab = normalize_data_monitor_tab(request.args.get("tab"))
    return render_template(
        "data_monitor.html",
        data_monitor_active_tab=active_tab,
        **build_stablecoin_data_monitor_context(),
        **build_navigation_context(active_page="data_monitor", reports=reports, stock_store=stock_store),
    )


@app.get("/data-monitor/stablecoins/status")
def stablecoin_monitor_status():
    cache = load_stablecoin_market_cache()
    runtime = sync_stablecoin_monitor_runtime()
    latest_snapshot = cache.get("latest_snapshot", {}) if isinstance(cache.get("latest_snapshot"), dict) else {}
    return jsonify(
        {
            "ok": True,
            "runtime": {
                **runtime,
                "status_label": monitor_runtime_status_label(runtime["status"]),
                "status_tone": monitor_runtime_status_tone(runtime["status"]),
                "is_running": runtime["status"] == "running",
                "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未刷新",
                "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未刷新",
            },
            "updated_at_label": format_iso_timestamp(cache.get("updated_at")) if cache.get("updated_at") else "尚未抓取",
            "is_stale": stablecoin_market_cache_is_stale(cache),
            "latest_market_cap_label": format_compact_currency(latest_snapshot.get("total_market_cap") or 0.0),
            "latest_volume_label": format_compact_currency(latest_snapshot.get("total_volume") or 0.0),
        }
    )


@app.post("/data-monitor/stablecoins/refresh")
def refresh_stablecoin_monitor():
    runtime = sync_stablecoin_monitor_runtime()
    started = False
    if runtime["status"] != "running":
        runtime = start_stablecoin_market_refresh("manual_refresh")
        started = True

    message = "稳定币数据刷新已启动。" if started else "稳定币数据正在刷新中。"
    if expects_json_response():
        return jsonify(
            {
                "ok": True,
                "started": started,
                "message": message,
                "runtime": {
                    **runtime,
                    "status_label": monitor_runtime_status_label(runtime["status"]),
                    "status_tone": monitor_runtime_status_tone(runtime["status"]),
                    "is_running": runtime["status"] == "running",
                    "started_at_label": format_iso_timestamp(runtime.get("started_at")) if runtime.get("started_at") else "尚未刷新",
                    "finished_at_label": format_iso_timestamp(runtime.get("finished_at")) if runtime.get("finished_at") else "尚未刷新",
                },
            }
        )

    flash(message, "success")
    return redirect(url_for("data_monitor_page", tab="stablecoins"))


@app.get("/reports/<path:filename>/preview-fragment")
def preview_report_fragment(filename: str):
    report = load_report(filename)
    if request.headers.get("X-Requested-With") != "XMLHttpRequest":
        return redirect(url_for("monitor_page", report=report["filename"]))
    return render_template(
        "report_modal.html",
        report=report,
        is_monitor_report=is_monitor_report_entry(report),
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
    selected_name = str(request.args.get("report") or request.args.get("signal_report") or "").strip()
    return redirect_to_monitor_workspace(tab="signals", signal_report=selected_name or None)


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
        return redirect_to_monitor_workspace(tab="signals")
    if not any(source.get("enabled", True) for source in sources):
        flash("请至少保留一个启用中的来源。", "error")
        return redirect_to_monitor_workspace(tab="signals")

    try:
        default_window_days = min(max(int(request.form.get("default_window_days") or config.get("default_window_days") or SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS), 1), 30)
    except (TypeError, ValueError):
        default_window_days = SIGNAL_MONITOR_DEFAULT_WINDOW_DAYS

    config["sources"] = sources
    config["default_window_days"] = default_window_days
    config["updated_at"] = now_iso()
    save_signal_monitor_config(config)
    flash("信息监控默认来源已更新。", "success")
    return redirect_to_monitor_workspace(tab="signals")


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
        return redirect_to_monitor_workspace(tab="signals")
    if not any(source.get("enabled", True) for source in sources):
        flash("请至少保留一个启用中的来源。", "error")
        return redirect_to_monitor_workspace(tab="signals")

    runtime = sync_signal_monitor_runtime()
    if runtime["status"] == "running":
        flash("程序已在运行，是否终止。", "error")
        return redirect_to_monitor_workspace(tab="signals")

    today_reports = collect_today_signal_reports()
    if today_reports and request.form.get("confirm_existing_today") != "1":
        flash("当天已经存在一份监测结果，是否继续运行。", "error")
        return redirect_to_monitor_workspace(tab="signals")

    enabled_sources = [source for source in sources if source.get("enabled", True)]
    cooldown_hits = get_signal_monitor_cooldown_hits(enabled_sources)
    if cooldown_hits and len(cooldown_hits) == len(enabled_sources):
        earliest_label = "；".join(
            f"{item['display_name']} 最早可在 {item['cooldown_until']} 后重跑"
            for item in cooldown_hits[:3]
        )
        flash(f"这些来源刚跑过，不建议高频扫描。{earliest_label}", "error")
        return redirect_to_monitor_workspace(tab="signals")

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
        return redirect_to_monitor_workspace(tab="signals")

    flash("信息监控任务已经在后台启动。跑完后会自动写入独立归档，不会混进正式研究报告。", "success")
    return redirect_to_monitor_workspace(tab="signals")


@app.post("/signals/terminate")
def terminate_signal_monitor_job():
    current = sync_signal_monitor_runtime()
    if current["status"] != "running":
        flash("当前没有正在运行的信息监控任务。", "error")
        return redirect_to_monitor_workspace(tab="signals")

    terminate_signal_monitor_process(current)
    flash("后台信息监控任务已终止。", "success")
    return redirect_to_monitor_workspace(tab="signals")


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
    return redirect_to_monitor_workspace(tab="signals")


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


@app.post("/stocks/earnings/sync")
def sync_all_stock_earnings():
    next_url = safe_next_url(request.form.get("next_url"), url_for("stocks_workspace"))
    store = load_stock_store()
    symbols = list_stock_symbols(store)
    if not symbols:
        flash("当前股票工作台里还没有可同步业绩期的股票。", "error")
        return redirect(next_url)

    snapshots, errors = collect_stock_earnings_snapshots(symbols)
    if not snapshots:
        flash("业绩期同步失败，暂时没有拿到可写入的数据。", "error")
        if errors:
            flash("；".join(errors[:3]), "error")
        return redirect(next_url)

    with STOCK_STORE_LOCK:
        writable_store = load_stock_store()
        for symbol, earnings_info in snapshots.items():
            apply_stock_earnings_snapshot(writable_store, symbol, earnings_info)
        save_stock_store(writable_store)

    flash(f"已同步 {len(snapshots)} 只股票的下一次业绩，并更新到日程里。", "success")
    if errors:
        flash("部分股票同步失败：" + "；".join(errors[:3]), "error")
    return redirect(next_url)


@app.get("/schedule")
def schedule_page() -> str:
    store = load_stock_store()
    current_view = normalize_schedule_view(request.args.get("view"))
    page_return_url = request.full_path if request.query_string else request.path
    schedule_context = build_schedule_page_context(
        store,
        month_param=request.args.get("month"),
        year_param=request.args.get("year"),
        month_number_param=request.args.get("month_number"),
        date_param=request.args.get("date"),
        focus_item_id=request.args.get("focus", "").strip(),
    )
    selected_date = schedule_context.get("selected_schedule_date") or ""
    focus_item_id = schedule_context.get("focus_schedule_item_id") or ""
    board_params = {"view": "board", "month": schedule_context["month_key"]}
    form_params = {"view": "form", "month": schedule_context["month_key"]}
    if selected_date:
        board_params["date"] = selected_date
        form_params["date"] = selected_date
    if focus_item_id:
        board_params["focus"] = focus_item_id
        form_params["focus"] = focus_item_id

    return render_template(
        "schedule.html",
        stock_options=build_stock_selector_options(store),
        today_date=today_date_iso(),
        page_return_url=page_return_url,
        current_schedule_view=current_view,
        schedule_view_links={
            "board": url_for("schedule_page", **board_params),
            "form": url_for("schedule_page", **form_params),
        },
        **schedule_context,
        **build_navigation_context(active_page="schedule", stock_store=store),
    )


@app.post("/schedule/items")
def create_schedule_item():
    store = load_stock_store()
    next_url = safe_next_url(request.form.get("next_url"), url_for("schedule_page"))
    normalized_item = normalize_schedule_item(
        {
            "title": request.form.get("title"),
            "kind": request.form.get("kind"),
            "status": "planned",
            "priority": request.form.get("priority"),
            "symbol": request.form.get("symbol"),
            "company": request.form.get("company"),
            "scheduled_date": request.form.get("scheduled_date"),
            "has_time_range": request.form.get("has_time_range") == "on",
            "start_time": request.form.get("start_time"),
            "end_time": request.form.get("end_time"),
            "all_day": request.form.get("all_day") == "on",
            "location": request.form.get("location"),
            "note": request.form.get("note"),
            "tags": request.form.get("tags"),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )

    if normalized_item is None:
        flash("请至少填写标题和日期，这样日程才能真正落下来。", "error")
        return redirect(next_url)

    store.setdefault("schedule_items", []).append(normalized_item)
    save_stock_store(store)
    flash(f'日程“{normalized_item["title"]}”已加入。', "success")
    return redirect(
        url_for(
            "schedule_page",
            view="board",
            month=normalized_item["scheduled_date"][:7],
            date=normalized_item["scheduled_date"],
            focus=normalized_item["id"],
        )
    )


@app.post("/schedule/items/<item_id>/update")
def update_schedule_item(item_id: str):
    store = load_stock_store()
    item = get_schedule_item(store, item_id)
    next_url = safe_next_url(
        request.form.get("next_url"),
        url_for(
            "schedule_page",
            month=str(item.get("scheduled_date") or "")[:7],
            date=item.get("scheduled_date"),
            focus=item_id,
        ),
    )
    normalized_item = normalize_schedule_item(
        {
            "id": item["id"],
            "created_at": item.get("created_at"),
            "title": request.form.get("title"),
            "kind": request.form.get("kind"),
            "status": request.form.get("status") or item.get("status"),
            "priority": request.form.get("priority"),
            "symbol": request.form.get("symbol"),
            "company": request.form.get("company"),
            "scheduled_date": request.form.get("scheduled_date"),
            "has_time_range": request.form.get("has_time_range") == "on",
            "start_time": request.form.get("start_time"),
            "end_time": request.form.get("end_time"),
            "all_day": request.form.get("all_day") == "on",
            "location": request.form.get("location"),
            "note": request.form.get("note"),
            "tags": request.form.get("tags"),
            "updated_at": now_iso(),
        }
    )

    if normalized_item is None:
        flash("请至少保留标题和日期，避免这条日程变成空壳。", "error")
        return redirect(next_url)

    item.update(normalized_item)
    save_stock_store(store)
    flash(f'日程“{item["title"]}”已更新。', "success")
    return redirect(
        url_for(
            "schedule_page",
            view="board",
            month=item["scheduled_date"][:7],
            date=item["scheduled_date"],
            focus=item["id"],
        )
    )


@app.post("/schedule/items/<item_id>/status")
def update_schedule_item_status(item_id: str):
    store = load_stock_store()
    item = get_schedule_item(store, item_id)
    next_url = safe_next_url(
        request.form.get("next_url"),
        url_for(
            "schedule_page",
            month=str(item.get("scheduled_date") or "")[:7],
            date=item.get("scheduled_date"),
            focus=item_id,
        ),
    )
    status = str(request.form.get("status") or "").strip()
    if status not in SCHEDULE_STATUS_META:
        flash("这次状态更新没有识别出来，请再试一次。", "error")
        return redirect(next_url)

    item["status"] = status
    item["updated_at"] = now_iso()
    save_stock_store(store)
    flash(f'日程“{item["title"]}”状态已更新为 {SCHEDULE_STATUS_META[status]["label"]}。', "success")
    return redirect(next_url)


@app.post("/schedule/items/<item_id>/delete")
def delete_schedule_item(item_id: str):
    store = load_stock_store()
    item = get_schedule_item(store, item_id)
    append_to_trash(
        store,
        create_trash_entry(
            "schedule_item",
            item,
            symbol=str(item.get("symbol") or ""),
            title=str(item.get("title") or "日程"),
        ),
    )
    store["schedule_items"] = [
        schedule_item for schedule_item in store.get("schedule_items", []) if schedule_item["id"] != item_id
    ]
    save_stock_store(store)
    flash(f'日程“{item["title"]}”已移入回收站。', "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("schedule_page")))


@app.get("/experts")
def experts_page() -> str:
    store = load_stock_store()
    selected_expert_id = str(request.args.get("expert") or "").strip()
    current_expert_view = normalize_expert_view(request.args.get("view"), has_experts=bool(store.get("experts")))
    manage_params: dict[str, str] = {"view": "manage"}
    create_params: dict[str, str] = {"view": "create"}
    if selected_expert_id:
        manage_params["expert"] = selected_expert_id

    return render_template(
        "experts.html",
        today_date=today_date_iso(),
        page_return_url=request.full_path if request.query_string else request.path,
        current_expert_view=current_expert_view,
        expert_view_links={
            "manage": url_for("experts_page", **manage_params),
            "create": url_for("experts_page", **create_params),
        },
        **build_experts_page_context(store, selected_expert_id=selected_expert_id),
        **build_navigation_context(active_page="experts", stock_store=store),
    )


@app.get("/experts/resources/preview")
def expert_resource_preview() -> str:
    store = load_stock_store()
    resource_ref = parse_expert_resource_token(request.args.get("token"))
    if resource_ref is None:
        abort(404)

    return render_template(
        "expert_resource_modal.html",
        **build_expert_resource_preview_context(store, resource_ref),
    )


@app.post("/experts")
def create_expert():
    store = load_stock_store()
    normalized_expert = normalize_expert_entry(
        {
            "name": request.form.get("name"),
            "organization": request.form.get("organization"),
            "title": request.form.get("title"),
            "category": request.form.get("category"),
            "stage": request.form.get("stage"),
            "region": request.form.get("region"),
            "source": request.form.get("source"),
            "related_symbols": request.form.get("related_symbols"),
            "tags": request.form.get("tags"),
            "expertise": request.form.get("expertise"),
            "contact_notes": request.form.get("contact_notes"),
            "resource_refs": [],
            "interviews": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    if normalized_expert is None:
        flash("请至少填写专家姓名，才能建立这条专家档案。", "error")
        return redirect(url_for("experts_page"))

    store.setdefault("experts", []).append(normalized_expert)
    save_stock_store(store)
    flash(f'专家“{normalized_expert["name"]}”已加入专家记录。', "success")
    return redirect(url_for("experts_page", view="manage", expert=normalized_expert["id"]))


@app.post("/experts/<expert_id>/update")
def update_expert(expert_id: str):
    store = load_stock_store()
    expert = get_expert_entry(store, expert_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("experts_page", expert=expert_id))
    normalized_expert = normalize_expert_entry(
        {
            "id": expert["id"],
            "name": request.form.get("name"),
            "organization": request.form.get("organization"),
            "title": request.form.get("title"),
            "category": request.form.get("category"),
            "stage": request.form.get("stage"),
            "region": request.form.get("region"),
            "source": request.form.get("source"),
            "related_symbols": request.form.get("related_symbols"),
            "tags": request.form.get("tags"),
            "expertise": request.form.get("expertise"),
            "contact_notes": request.form.get("contact_notes"),
            "resource_refs": expert.get("resource_refs", []),
            "interviews": expert.get("interviews", []),
            "created_at": expert.get("created_at"),
            "updated_at": now_iso(),
        }
    )
    if normalized_expert is None:
        flash("专家档案没有保存成功，请检查姓名和字段内容。", "error")
        return redirect(next_url)

    expert.update(normalized_expert)
    save_stock_store(store)
    flash(f'专家“{expert["name"]}”档案已更新。', "success")
    return redirect(url_for("experts_page", view="manage", expert=expert_id))


@app.post("/experts/<expert_id>/archive")
def archive_expert(expert_id: str):
    store = load_stock_store()
    expert = get_expert_entry(store, expert_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("experts_page", expert=expert_id))
    expert["stage"] = "archived"
    expert["updated_at"] = now_iso()
    save_stock_store(store)
    flash(f'专家“{expert["name"]}”已标记为归档。', "success")
    return redirect(next_url)


@app.post("/experts/<expert_id>/resources")
def update_expert_resources(expert_id: str):
    store = load_stock_store()
    expert = get_expert_entry(store, expert_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("experts_page", expert=expert_id))
    resource_refs = normalize_expert_resource_refs(request.form.getlist("resource_ref_tokens"))
    expert["resource_refs"] = resource_refs
    expert["updated_at"] = now_iso()
    save_stock_store(store)
    flash(f'专家“{expert["name"]}”的关联资料已更新。', "success")
    return redirect(next_url)


@app.post("/experts/<expert_id>/interviews")
def create_expert_interview(expert_id: str):
    store = load_stock_store()
    expert = get_expert_entry(store, expert_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("experts_page", expert=expert_id))
    normalized_interview = normalize_expert_interview(
        {
            "title": request.form.get("title"),
            "kind": request.form.get("kind"),
            "status": request.form.get("status"),
            "interview_date": request.form.get("interview_date"),
            "summary": request.form.get("summary"),
            "follow_up": request.form.get("follow_up"),
            "tags": request.form.get("tags"),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    if normalized_interview is None:
        flash("请至少填写访谈标题和日期，时间线里才不会留下空记录。", "error")
        return redirect(next_url)

    expert.setdefault("interviews", []).append(normalized_interview)
    expert["updated_at"] = now_iso()
    save_stock_store(store)
    flash(f'已为“{expert["name"]}”新增一条访谈记录。', "success")
    return redirect(url_for("experts_page", view="manage", expert=expert_id))


@app.post("/experts/<expert_id>/interviews/<interview_id>/update")
def update_expert_interview(expert_id: str, interview_id: str):
    store = load_stock_store()
    expert = get_expert_entry(store, expert_id)
    interview = get_expert_interview_entry(expert, interview_id)
    next_url = safe_next_url(request.form.get("next_url"), url_for("experts_page", expert=expert_id))
    normalized_interview = normalize_expert_interview(
        {
            "id": interview["id"],
            "title": request.form.get("title"),
            "kind": request.form.get("kind"),
            "status": request.form.get("status"),
            "interview_date": request.form.get("interview_date"),
            "summary": request.form.get("summary"),
            "follow_up": request.form.get("follow_up"),
            "tags": request.form.get("tags"),
            "created_at": interview.get("created_at"),
            "updated_at": now_iso(),
        }
    )
    if normalized_interview is None:
        flash("这条访谈记录没有保存成功，请检查标题和日期。", "error")
        return redirect(next_url)

    interview.update(normalized_interview)
    expert["updated_at"] = now_iso()
    save_stock_store(store)
    flash("访谈记录已更新。", "success")
    return redirect(url_for("experts_page", view="manage", expert=expert_id))


@app.post("/experts/<expert_id>/interviews/<interview_id>/delete")
def delete_expert_interview(expert_id: str, interview_id: str):
    store = load_stock_store()
    expert = get_expert_entry(store, expert_id)
    before_count = len(expert.get("interviews", []))
    expert["interviews"] = [
        interview for interview in expert.get("interviews", []) if interview["id"] != interview_id
    ]
    if len(expert["interviews"]) == before_count:
        abort(404)

    expert["updated_at"] = now_iso()
    save_stock_store(store)
    flash("这条访谈记录已删除。", "success")
    return redirect(safe_next_url(request.form.get("next_url"), url_for("experts_page", expert=expert_id)))


@app.get("/search")
def global_search() -> str:
    store = load_stock_store()
    report_entries, _ = get_report_catalog()
    reports = [serialize_report_entry(report) for report in report_entries]
    search_context = build_global_search_context(
        store,
        report_entries,
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
        storage_symbol = stock_file_storage_symbol(payload, symbol) or symbol
        if not storage_symbol:
            abort(400)
        entry = ensure_stock_entry(store, storage_symbol)
        payload["id"] = ensure_unique_id(payload.get("id", ""), {item["id"] for item in entry["files"]})
        entry["files"].append(payload)
        touch_stock_symbols(store, stock_file_linked_symbols(payload, storage_symbol))
    elif item_type == "transcript":
        payload["id"] = ensure_unique_id(payload.get("id", ""), {item["id"] for item in store.get("transcripts", [])})
        store.setdefault("transcripts", []).append(payload)
        touch_transcript_stocks(store, payload)
    elif item_type == "group":
        payload["id"] = ensure_unique_id(payload.get("id", ""), {group["id"] for group in store["groups"]}, length=8)
        store["groups"].append(payload)
    elif item_type == "schedule_item":
        payload["id"] = ensure_unique_id(
            payload.get("id", ""),
            {item["id"] for item in store.get("schedule_items", [])},
        )
        store.setdefault("schedule_items", []).append(payload)
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
    folded_terms = fold_search_terms(terms)
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
            if terms and not text_contains_all_terms(
                search_text,
                terms,
                text_casefolded=search_text.casefold(),
                folded_terms=folded_terms,
            ):
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

        for call in build_stock_earnings_call_cards(entry):
            if selected_kind and selected_kind != "earnings_call":
                continue
            if normalized_symbol and symbol != normalized_symbol:
                continue
            if normalized_tag:
                continue

            search_text = " ".join(
                [
                    symbol,
                    str(call.get("display_title") or ""),
                    str(call.get("original_title") or ""),
                    str(call.get("transcript_text") or ""),
                    str(call.get("source_query_label") or ""),
                ]
            )
            if terms and not text_contains_all_terms(
                search_text,
                terms,
                text_casefolded=search_text.casefold(),
                folded_terms=folded_terms,
            ):
                continue

            results.append(
                {
                    "kind": "earnings_call",
                    "kind_label": SEARCH_KIND_META["earnings_call"]["label"],
                    "kind_tone": SEARCH_KIND_META["earnings_call"]["tone"],
                    "title": call["display_title"],
                    "summary": build_match_excerpt(
                        call.get("transcript_text") or "",
                        terms,
                        call["summary_excerpt"],
                    ),
                    "symbol": symbol,
                    "display_time": call.get("display_call_date") or call.get("display_published_at"),
                    "sort_value": coerce_sort_timestamp(call.get("call_date") or call.get("published_at")),
                    "tags": [],
                    "url": build_stock_detail_deep_link(
                        symbol=symbol,
                        panel="earnings-calls",
                        item_kind="earnings_call",
                        item_id=str(call.get("id") or ""),
                        anchor=f"earnings-call-{call.get('id')}",
                    ),
                    "secondary_url": call.get("source_url") or "",
                    "secondary_label": "打开来源",
                }
            )

    for record in iter_stock_file_records(store, symbol_filter=normalized_symbol or None):
        if selected_kind and selected_kind != "file":
            continue

        file_entry = record["file_entry"]
        access_symbol = normalized_symbol or record["storage_symbol"]
        tags = normalize_tag_list(file_entry.get("tags", []))
        search_text = " ".join(
            [
                " ".join(record["linked_symbols"]),
                file_entry.get("original_name") or "",
                file_entry.get("description") or "",
                file_entry.get("linked_note_title") or "",
                " ".join(tags),
            ]
        )
        if normalized_tag and not tag_match(tags, normalized_tag):
            continue
        if terms and not text_contains_all_terms(
            search_text,
            terms,
            text_casefolded=search_text.casefold(),
            folded_terms=folded_terms,
        ):
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
                "symbol": access_symbol,
                "display_time": file_display_time(file_entry),
                "sort_value": coerce_sort_timestamp(file_entry.get("uploaded_at")),
                "tags": tags,
                "url": build_stock_detail_deep_link(
                    symbol=access_symbol,
                    panel="files",
                    item_kind="file",
                    item_id=str(file_entry.get("id") or ""),
                    anchor=f"file-{file_entry.get('id')}",
                ),
                "secondary_url": url_for("download_stock_file", symbol=access_symbol, file_id=file_entry["id"]),
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
        if terms and not text_contains_all_terms(
            search_text,
            terms,
            text_casefolded=search_text.casefold(),
            folded_terms=folded_terms,
        ):
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

    for schedule_item in store.get("schedule_items", []):
        if selected_kind and selected_kind != "schedule":
            continue
        tags = normalize_tag_list(schedule_item.get("tags", []))
        symbol = str(schedule_item.get("symbol") or "")
        search_text = " ".join(
            [
                symbol,
                str(schedule_item.get("company") or ""),
                str(schedule_item.get("title") or ""),
                str(schedule_item.get("note") or ""),
                str(schedule_item.get("location") or ""),
                " ".join(tags),
            ]
        )
        if normalized_symbol and symbol != normalized_symbol:
            continue
        if normalized_tag and not tag_match(tags, normalized_tag):
            continue
        if terms and not text_contains_all_terms(
            search_text,
            terms,
            text_casefolded=search_text.casefold(),
            folded_terms=folded_terms,
        ):
            continue

        schedule_date = str(schedule_item.get("scheduled_date") or "")
        results.append(
            {
                "kind": "schedule",
                "kind_label": SEARCH_KIND_META["schedule"]["label"],
                "kind_tone": SEARCH_KIND_META["schedule"]["tone"],
                "title": str(schedule_item.get("title") or "未命名日程"),
                "summary": build_match_excerpt(
                    " ".join(
                        [
                            str(schedule_item.get("note") or ""),
                            str(schedule_item.get("location") or ""),
                            str(schedule_item.get("company") or ""),
                        ]
                    ),
                    terms,
                    summarize_text_block(
                        str(schedule_item.get("note") or "")
                        or str(schedule_item.get("location") or "")
                        or build_schedule_time_label(schedule_item)
                    ),
                ),
                "symbol": symbol,
                "display_time": f"{schedule_date} 路 {build_schedule_time_label(schedule_item)}",
                "sort_value": schedule_item_sort_datetime(schedule_item).timestamp(),
                "tags": tags,
                "url": (
                    url_for("schedule_page", month=schedule_date[:7], date=schedule_date, focus=schedule_item["id"])
                    + f"#schedule-item-{schedule_item['id']}"
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
        content = str(report.get("content") or "") or read_report_text(REPORTS_DIR / report["filename"])
        combined_text = " ".join([report["title"], report["summary"], report["filename"], content])
        if normalized_symbol and report_symbol_pattern and not report_symbol_pattern.search(combined_text):
            continue
        if terms and not text_contains_all_terms(
            combined_text,
            terms,
            text_casefolded=combined_text.casefold(),
            folded_terms=folded_terms,
        ):
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
        transcript_category_options=TRANSCRIPT_CATEGORY_OPTIONS,
        transcript_status_poll_seconds=TRANSCRIPT_STATUS_POLL_INTERVAL_SECONDS,
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
    uploaded_files = [
        uploaded
        for uploaded in request.files.getlist("transcript_media")
        if uploaded is not None and str(uploaded.filename or "").strip()
    ]
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))

    if not uploaded_files:
        flash("请先选择要上传的音频或视频文件。", "error")
        return redirect(next_url)

    invalid_filenames = [
        str(uploaded.filename or "").strip()
        for uploaded in uploaded_files
        if not is_transcript_source_allowed(str(uploaded.filename or ""))
    ]
    if invalid_filenames:
        preview_names = "; ".join(invalid_filenames[:3])
        suffix = " 等文件" if len(invalid_filenames) > 3 else ""
        flash(f"以下文件格式暂不支持：{preview_names}{suffix}。当前支持常见音频/视频格式，如 mp3、wav、mp4、mov、mkv。", "error")
        return redirect(next_url)

    file_url_hint = request.form.get("file_url_hint", "").strip()[:2000]
    if file_url_hint and len(uploaded_files) > 1:
        flash("批量上传本地文件时，请不要同时填写公网文件地址。这个高级选项目前只适合单个文件。", "error")
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

    transcript_category = normalize_transcript_category(request.form.get("transcript_category"))

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

    base_title = request.form.get("transcript_title", "").strip()[:160]
    first_filename_date = infer_date_from_filename(uploaded_files[0].filename)
    meeting_date_is_manual = request.form.get("meeting_date_is_manual") == "1"
    submitted_meeting_date = normalize_date_field(request.form.get("meeting_date"))
    meeting_date_has_custom_value = bool(submitted_meeting_date and submitted_meeting_date != today_date_iso())
    resolved_meeting_date = (
        submitted_meeting_date
        if meeting_date_is_manual or meeting_date_has_custom_value
        else (first_filename_date or submitted_meeting_date)
    ) or today_date_iso()
    is_batch_upload = len(uploaded_files) > 1

    transcript_base_payload = {
        "provider": "tingwu",
        "status": "pending_api",
        "provider_task_id": "",
        "provider_task_status": "not_submitted",
        "provider_request_id": "",
        "submitted_at": "",
        "last_synced_at": "",
        "last_error": "",
        "provider_result_urls": {},
        "file_url_hint": file_url_hint,
        "source_bucket_name": "",
        "source_object_key": "",
        "source_endpoint": "",
        "source_region_id": "",
        "source_url_expires_at": "",
        "linked_symbol": linked_symbols[0] if linked_symbols else "",
        "linked_symbols": linked_symbols,
        "category": transcript_category,
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

    tingwu_status = build_tingwu_status()
    oss_status = build_oss_status()
    normalized_transcripts: list[dict[str, Any]] = []
    auto_submitted_count = 0
    auto_source_ready_count = 0
    auto_submit_errors: list[str] = []

    TRANSCRIPT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    for uploaded in uploaded_files:
        original_name = str(uploaded.filename or "").strip()
        safe_name = secure_filename(original_name)
        original_suffix = Path(original_name).suffix.lower()
        if not safe_name:
            safe_name = f"meeting-recording{original_suffix or '.bin'}"
        elif original_suffix and not safe_name.lower().endswith(original_suffix):
            safe_name = f"{Path(safe_name).stem}{original_suffix}"

        timestamp = now_iso()
        stored_name = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}-{safe_name}"
        target_path = TRANSCRIPT_UPLOADS_DIR / stored_name
        uploaded.save(target_path)

        transcript_title = base_title
        if is_batch_upload and transcript_title:
            title_suffix = fallback_title(Path(original_name))
            if title_suffix:
                transcript_title = f"{transcript_title} - {title_suffix}"[:160]

        transcript_entry = {
            "id": uuid.uuid4().hex[:10],
            "title": transcript_title,
            "meeting_date": resolved_meeting_date or iso_to_date(timestamp) or today_date_iso(),
            "created_at": timestamp,
            "updated_at": timestamp,
            "stored_name": stored_name,
            "original_name": original_name[:240],
            "media_kind": detect_transcript_media_kind(original_name),
            **deepcopy(transcript_base_payload),
        }

        normalized_transcript = normalize_transcript_entry(transcript_entry)
        if normalized_transcript is None:
            auto_submit_errors.append(f"{original_name or '未命名文件'}: 任务写入失败")
            continue

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
                auto_submitted_count += 1
            except Exception as exc:
                normalized_transcript["last_error"] = str(exc)[:2000]
                normalized_transcript["updated_at"] = now_iso()
                auto_submit_error = str(exc)

        if auto_source_ready:
            auto_source_ready_count += 1
        if auto_submit_error:
            auto_submit_errors.append(f"{original_name or '未命名文件'}: {auto_submit_error}")

        normalized_transcripts.append(normalized_transcript)

    if not normalized_transcripts:
        flash("转录任务写入失败，请重试。", "error")
        return redirect(next_url)

    with STOCK_STORE_LOCK:
        store = load_stock_store()
        transcript_entries = store.setdefault("transcripts", [])
        for transcript in normalized_transcripts:
            transcript_entries.append(transcript)
            touch_transcript_stocks(store, transcript)
        save_stock_store(store)

    if len(normalized_transcripts) == 1:
        normalized_transcript = normalized_transcripts[0]
        if auto_submitted_count:
            flash("会议转录任务已保存，并已提交到听悟。后续请用“刷新状态”主动轮询结果。", "success")
        elif auto_submit_errors:
            flash(f"任务已保存，但提交到听悟失败：{auto_submit_errors[0].split(': ', 1)[-1]}", "error")
        elif auto_source_ready_count:
            flash("会议转录任务已保存，源文件也已自动上传到 OSS。你可以稍后继续提交到听悟。", "success")
        elif normalized_transcript["file_url_hint"]:
            flash("会议转录任务已保存。当前可以随时手动提交到听悟。", "success")
        else:
            flash("会议转录任务已保存。系统还没拿到可用的云端地址，稍后可以直接点“提交到听悟”再试。", "success")
    else:
        flash(f"已批量保存 {len(normalized_transcripts)} 个会议转录任务。", "success")
        if auto_submitted_count:
            flash(f"其中 {auto_submitted_count} 个任务已自动提交到听悟。", "success")
        elif auto_source_ready_count:
            flash(f"其中 {auto_source_ready_count} 个任务的源文件已自动上传到 OSS，可以稍后继续提交。", "success")
        elif file_url_hint:
            flash("这批任务已沿用你填写的公网文件地址保存。", "success")

        if auto_submit_errors:
            preview_errors = "; ".join(auto_submit_errors[:2])
            suffix = " 等" if len(auto_submit_errors) > 2 else ""
            flash(f"{len(auto_submit_errors)} 个任务自动处理失败：{preview_errors}{suffix}", "error")
    return redirect(next_url)


@app.post("/transcripts/<transcript_id>/submit")
def submit_transcript_job(transcript_id: str):
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))

    with STOCK_STORE_LOCK:
        store = load_stock_store()
        transcript = get_transcript_entry(store, transcript_id)

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
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))

    with STOCK_STORE_LOCK:
        store = load_stock_store()
        transcript = get_transcript_entry(store, transcript_id)

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
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))
    scope_symbol = normalize_stock_symbol(request.form.get("scope_symbol", "")) or ""
    refreshed = 0
    completed = 0
    terminal_failed = 0
    sync_errors = 0
    scope_completed = 0
    scope_terminal_failed = 0

    with STOCK_STORE_LOCK:
        store = load_stock_store()

        for transcript in store.get("transcripts", []):
            if transcript.get("status") not in {"queued", "processing"}:
                continue
            if not transcript.get("provider_task_id"):
                continue
            try:
                sync_transcript_job_from_tingwu(transcript)
                refreshed += 1
                in_scope = not scope_symbol or transcript_matches_symbol(transcript, scope_symbol)
                if transcript["status"] == "completed":
                    completed += 1
                    if in_scope:
                        scope_completed += 1
                elif transcript["status"] == "failed":
                    terminal_failed += 1
                    if in_scope:
                        scope_terminal_failed += 1
                touch_transcript_stocks(store, transcript)
            except Exception as exc:
                transcript["last_error"] = str(exc)[:2000]
                transcript["updated_at"] = now_iso()
                sync_errors += 1

        save_stock_store(store)
        transcript_cards = build_transcript_cards(store, symbol_filter=scope_symbol or None)
    counts = build_transcript_stats_payload(transcript_cards)

    if expects_json_response():
        has_terminal_updates = scope_completed > 0 or scope_terminal_failed > 0
        should_reload = has_terminal_updates
        return jsonify(
            {
                "ok": True,
                "refreshed": refreshed,
                "completed": completed,
                "failed": terminal_failed,
                "sync_errors": sync_errors,
                "counts": counts,
                "has_terminal_updates": has_terminal_updates,
                "should_reload": should_reload,
                "polled_at": now_iso(),
            }
        )

    if refreshed:
        flash(
            f"已轮询 {refreshed} 个进行中任务，其中完成 {completed} 个，失败 {terminal_failed} 个。",
            "success",
        )
    elif sync_errors:
        flash(f"轮询时有 {sync_errors} 个任务暂时同步失败，请稍后再试。", "error")
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


@app.post("/transcripts/<transcript_id>/category")
def update_transcript_category(transcript_id: str):
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))
    scope_symbol = normalize_stock_symbol(request.form.get("scope_symbol", "")) or ""
    raw_category = str(request.form.get("category") or "").strip()
    if raw_category not in TRANSCRIPT_CATEGORY_META:
        message = "无效的转录分类。"
        if expects_json_response():
            return jsonify({"ok": False, "message": message}), 400
        flash(message, "error")
        return redirect(next_url)

    next_category = raw_category
    with STOCK_STORE_LOCK:
        store = load_stock_store()
        transcript = get_transcript_entry(store, transcript_id)
        transcript["category"] = next_category
        transcript["updated_at"] = now_iso()
        touch_transcript_stocks(store, transcript)
        save_stock_store(store)

        category_payload = build_transcript_category_payload(next_category)
        message = f"已切换到“{category_payload['label']}”。"

        if expects_json_response():
            transcript_cards = build_transcript_cards(store, symbol_filter=scope_symbol or None)
            return jsonify(
                {
                    "ok": True,
                    "transcript_id": transcript_id,
                    "category": category_payload,
                    "counts": build_transcript_stats_payload(transcript_cards),
                }
            )

    flash(message, "success")
    return redirect(next_url)


@app.post("/transcripts/<transcript_id>/links")
def update_transcript_links(transcript_id: str):
    next_url = safe_next_url(request.form.get("next_url"), url_for("transcripts_page"))
    scope_symbol = normalize_stock_symbol(request.form.get("scope_symbol", "")) or ""

    with STOCK_STORE_LOCK:
        store = load_stock_store()
        transcript = get_transcript_entry(store, transcript_id)
        previous_symbols = transcript_linked_symbols(transcript)

        link_to_stock = request.form.get("link_to_stock") == "on"
        linked_symbols: list[str] = []
        if link_to_stock:
            linked_symbols = parse_symbol_list(request.form.get("linked_symbols_text", ""))
            if not linked_symbols:
                message = "如果要关联股票，请先填写一个或多个股票代码。"
                if expects_json_response():
                    return jsonify({"ok": False, "message": message}), 400
                flash(message, "error")
                return redirect(next_url)

            known_symbols = set(list_stock_symbols(store))
            missing_symbols = [symbol for symbol in linked_symbols if symbol not in known_symbols]
            if missing_symbols:
                message = f"未找到对应股票：{'、'.join(missing_symbols)}"
                if expects_json_response():
                    return jsonify({"ok": False, "message": message}), 400
                flash(message, "error")
                return redirect(next_url)

            for symbol in linked_symbols:
                ensure_stock_entry(store, symbol)

        transcript["linked_symbol"] = linked_symbols[0] if linked_symbols else ""
        transcript["linked_symbols"] = linked_symbols
        transcript["updated_at"] = now_iso()
        touch_stock_symbols(store, previous_symbols + linked_symbols)
        save_stock_store(store)

        transcript_card = build_transcript_card(transcript)
        message = "会议转录的关联股票已更新。"

        if expects_json_response():
            transcript_cards = build_transcript_cards(store, symbol_filter=scope_symbol or None)
            return jsonify(
                {
                    "ok": True,
                    "message": message,
                    "transcript_id": transcript_id,
                    "linked_symbols": transcript_card.get("linked_symbols", []),
                    "linked_symbols_label": transcript_card.get("linked_symbols_label", ""),
                    "counts": build_transcript_stats_payload(transcript_cards),
                }
            )

    flash(message, "success")
    return redirect(next_url)


@app.get("/transcripts/<transcript_id>/export.pdf")
def export_transcript_pdf(transcript_id: str):
    store = load_stock_store()
    transcript = get_transcript_entry(store, transcript_id)

    try:
        pdf_buffer, download_name = build_transcript_pdf_buffer(transcript)
    except RuntimeError as exc:
        flash(str(exc), "error")
        next_url = request.args.get("next") or url_for("transcripts_page")
        return redirect(safe_next_url(next_url, url_for("transcripts_page")))

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
        max_age=0,
    )


@app.post("/transcripts/<transcript_id>/delete")
def delete_transcript_job(transcript_id: str):
    scope_symbol = normalize_stock_symbol(request.form.get("scope_symbol", "")) or ""
    with STOCK_STORE_LOCK:
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
            transcript_cards = build_transcript_cards(store, symbol_filter=scope_symbol or None)
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
    if not build_stock_earnings_view(ensure_stock_entry(store, symbol)).get("has_date"):
        try:
            earnings_info = fetch_next_stock_earnings(symbol)
        except Exception:
            earnings_info = None
        if earnings_info:
            with STOCK_STORE_LOCK:
                writable_store = load_stock_store()
                apply_stock_earnings_snapshot(writable_store, symbol, earnings_info)
                save_stock_store(writable_store)
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
        stock_options=build_stock_selector_options(store),
        related_reports=detail["related_reports"],
        available_groups=available_groups,
        stock_calendar=stock_calendar,
        today_date=today_date_iso(),
        return_to=request.full_path if request.query_string else request.path,
        **build_navigation_context(active_page="stocks", stock_store=store),
    )


@app.post("/stocks/<symbol>/earnings/sync")
def sync_stock_earnings(symbol: str):
    symbol = require_stock_symbol(symbol)
    next_url = safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol))

    try:
        earnings_info = fetch_next_stock_earnings(symbol)
    except Exception as exc:
        flash(f"{symbol} 的业绩期同步失败：{exc}", "error")
        return redirect(next_url)

    with STOCK_STORE_LOCK:
        store = load_stock_store()
        apply_stock_earnings_snapshot(store, symbol, earnings_info)
        save_stock_store(store)

    flash(f"{symbol} 的下一次业绩已同步，并写入日程。", "success")
    return redirect(next_url)


@app.post("/stocks/<symbol>/earnings-calls/sync")
def sync_stock_earnings_calls(symbol: str):
    symbol = require_stock_symbol(symbol)
    next_url = safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol))
    with STOCK_STORE_LOCK:
        store = load_stock_store()
        existing_calls = list(store.get("stocks", {}).get(symbol, {}).get("earnings_calls", []))

    try:
        payload = fetch_recent_stock_earnings_calls(symbol, existing_calls=existing_calls)
    except Exception as exc:
        with STOCK_STORE_LOCK:
            store = load_stock_store()
            note_stock_earnings_call_sync_failure(
                store,
                symbol,
                str(exc),
                source_label="The Motley Fool",
                source_url="https://www.fool.com/earnings-call-transcripts/",
            )
            save_stock_store(store)
        flash(f"{symbol} 的电话会议同步失败：{exc}", "error")
        return redirect(next_url)

    calls = payload.get("calls", []) if isinstance(payload, dict) else []
    if not calls:
        warnings = payload.get("warnings", []) if isinstance(payload, dict) else []
        error_message = "最近两年未找到适合展示的完整电话会议。"
        if warnings:
            error_message = f"{error_message} 最近提示：{warnings[0]}"
        with STOCK_STORE_LOCK:
            store = load_stock_store()
            note_stock_earnings_call_sync_failure(
                store,
                symbol,
                error_message,
                source_label=str(payload.get("source_label") or "Pineify") if isinstance(payload, dict) else "Pineify",
                source_url=str(payload.get("source_url") or "https://pineify.app/earnings-transcript")
                if isinstance(payload, dict)
                else "https://pineify.app/earnings-transcript",
                lookback_days=int(payload.get("lookback_days") or 730) if isinstance(payload, dict) else 730,
            )
            save_stock_store(store)
        flash(f"{symbol} 的电话会议暂无可写入内容。", "error")
        return redirect(next_url)

    with STOCK_STORE_LOCK:
        store = load_stock_store()
        apply_stock_earnings_call_snapshot(store, symbol, payload)
        save_stock_store(store)

    warning_count = len(payload.get("warnings", [])) if isinstance(payload, dict) else 0
    warning_suffix = f"（另有 {warning_count} 条未采用的候选）" if warning_count else ""
    flash(f"{symbol} 的电话会议已同步 {len(calls)} 条{warning_suffix}", "success")
    return redirect(next_url)


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

    touch_stock_symbols(store, stock_file_linked_symbols(file_entry, storage_symbol))
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
    linked_symbols = ordered_unique([symbol] + normalize_stock_symbol_list(request.form.getlist("linked_symbols")))
    known_symbols = set(list_stock_symbols(store))
    missing_symbols = [item for item in linked_symbols if item not in known_symbols]

    if missing_symbols:
        flash(f"These stocks are not in the workspace yet: {', '.join(missing_symbols)}", "error")
        return redirect(next_url)

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
        "storage_symbol": symbol,
        "linked_symbols": linked_symbols,
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
    touch_stock_symbols(store, linked_symbols)
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


def get_stock_file_entry(store: dict[str, Any], symbol: str, file_id: str) -> dict[str, Any]:
    return get_stock_file_record(store, symbol, file_id)["file_entry"]


def build_stock_file_preview_context(
    store: dict[str, Any],
    symbol: str,
    file_record: dict[str, Any],
) -> dict[str, Any]:
    file_entry = file_record["file_entry"]
    linked_note = get_stock_file_linked_note(store, file_record)
    original_name = str(file_entry.get("original_name") or "")
    file_path = stock_upload_dir(file_record["storage_symbol"]) / str(file_entry.get("stored_name") or "")
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
        "file_entry": build_stock_file_card(store, file_record, access_symbol=symbol),
        "preview_text": preview_text,
        "is_truncated": is_truncated,
        "preview_note_html": preview_note_html,
        "image_url": url_for("inline_stock_file", symbol=symbol, file_id=file_entry["id"])
        if is_image_previewable(original_name)
        else "",
    }


@app.post("/stocks/<symbol>/files/<file_id>/links")
def update_stock_file_links(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    record = get_stock_file_record(store, symbol, file_id)
    file_entry = record["file_entry"]
    next_url = safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol))
    known_symbols = set(list_stock_symbols(store))
    selected_symbols = normalize_stock_symbol_list(request.form.getlist("linked_symbols"))
    missing_symbols = [item for item in selected_symbols if item not in known_symbols]

    if missing_symbols:
        flash(f"These stocks are not in the workspace yet: {', '.join(missing_symbols)}", "error")
        return redirect(next_url)

    previous_symbols = stock_file_linked_symbols(file_entry, record["storage_symbol"])
    linked_symbols = ordered_unique([record["storage_symbol"]] + selected_symbols)
    file_entry["storage_symbol"] = record["storage_symbol"]
    file_entry["linked_symbols"] = linked_symbols
    touch_stock_symbols(store, previous_symbols + linked_symbols)
    save_stock_store(store)
    flash("Research file links updated.", "success")
    return redirect(next_url)


@app.get("/stocks/<symbol>/files/<file_id>")
def download_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_record = get_stock_file_record(store, symbol, file_id)
    file_entry = file_record["file_entry"]
    return send_from_directory(
        stock_upload_dir(file_record["storage_symbol"]),
        file_entry["stored_name"],
        as_attachment=True,
        download_name=file_entry["original_name"],
    )


@app.get("/stocks/<symbol>/files/<file_id>/inline")
def inline_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_record = get_stock_file_record(store, symbol, file_id)
    file_entry = file_record["file_entry"]
    return send_from_directory(
        stock_upload_dir(file_record["storage_symbol"]),
        file_entry["stored_name"],
        as_attachment=False,
        download_name=file_entry["original_name"],
    )


@app.get("/stocks/<symbol>/files/<file_id>/preview")
def preview_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_record = get_stock_file_record(store, symbol, file_id)
    file_entry = file_record["file_entry"]

    if not is_file_previewable(file_entry["original_name"]):
        flash("该文件类型暂不支持在线预览。", "error")
        return redirect(url_for("stock_detail", symbol=symbol))

    return render_template(
        "stock_file_preview.html",
        stock=build_stock_detail(store, symbol),
        **build_stock_file_preview_context(store, symbol, file_record),
        **build_navigation_context(active_page="stocks", stock_store=store),
    )


@app.get("/stocks/<symbol>/files/<file_id>/preview-fragment")
def preview_stock_file_fragment(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_record = get_stock_file_record(store, symbol, file_id)
    file_entry = file_record["file_entry"]

    if not is_file_previewable(file_entry["original_name"]):
        abort(404)

    return render_template(
        "stock_file_modal.html",
        stock_symbol=symbol,
        **build_stock_file_preview_context(store, symbol, file_record),
    )


@app.post("/stocks/<symbol>/files/<file_id>/delete")
def delete_stock_file(symbol: str, file_id: str):
    store = load_stock_store()
    symbol = require_stock_symbol(symbol)
    file_record = get_stock_file_record(store, symbol, file_id)
    file_entry = file_record["file_entry"]
    storage_symbol = file_record["storage_symbol"]
    if storage_symbol != symbol:
        flash("请回到这份资料最初上传的股票页再删除文件。", "error")
        return redirect(safe_next_url(request.form.get("next_url"), url_for("stock_detail", symbol=symbol)))

    entry = ensure_stock_entry(store, storage_symbol)
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


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "mindmap-studio-favicon.svg", mimetype="image/svg+xml")


if __name__ == "__main__":
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STOCK_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    TRANSCRIPT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    maybe_start_stablecoin_monitor_scheduler()
    host = os.getenv("HOST", "0.0.0.0")
    port = current_port()
    app.run(host=host, port=port, debug=False)
