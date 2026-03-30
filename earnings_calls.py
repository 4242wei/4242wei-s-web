from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from html import escape, unescape
from typing import Any

import requests
from lxml import etree, html as lxml_html
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

PINEIFY_SOURCE_LABEL = "Pineify"
PINEIFY_SOURCE_SHORT_LABEL = "pineify"
PINEIFY_SOURCE_URL = "https://pineify.app/earnings-transcript"
PINEIFY_WAIT_SECONDS = 12
PINEIFY_PAGE_LOAD_TIMEOUT = 90
PINEIFY_TERMINATOR_TOKENS = (
    "\nWhat is an Earnings Call Transcript?",
    "\nWhat is an earnings call transcript?",
    "\nGo Beyond Reading Transcripts",
    "\nTry Pineify Free",
    "\nFrequently Asked Questions",
    "\nMore Free Tools",
)

SEEKING_ALPHA_SOURCE_LABEL = "Seeking Alpha"
SEEKING_ALPHA_SOURCE_SHORT_LABEL = "sa"
SEEKING_ALPHA_BASE_URL = "https://seekingalpha.com"
SEEKING_ALPHA_DEBUGGER_ADDRESS = os.getenv("SEEKING_ALPHA_DEBUGGER_ADDRESS", "127.0.0.1:9222")
SEEKING_ALPHA_HEADERS = {
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
    ),
    "accept-language": "en-US,en;q=0.9",
}
FOOL_SOURCE_LABEL = "The Motley Fool"
FOOL_SOURCE_SHORT_LABEL = "fool"
FOOL_SOURCE_URL = "https://www.fool.com/earnings-call-transcripts/"
FOOL_SITEMAP_INDEX_URL = "https://www.fool.com/sitemap/"
FOOL_HEADERS = dict(SEEKING_ALPHA_HEADERS)
FOOL_SITEMAP_NS = {"sm": "http://www.google.com/schemas/sitemap/0.84"}
FOOL_TITLE_PATTERN = re.compile(
    r"(?P<title>.+?)\s*\((?P<symbol>[A-Z.\-]+)\)\s+Q(?P<quarter>[1-4])\s+(?P<year>20\d{2})\s+Earnings(?:\s+Call)?\s+Transcript",
    re.IGNORECASE,
)
FOOL_URL_QUARTER_PATTERN = re.compile(
    r"/earnings/call-transcripts/\d{4}/\d{2}/\d{2}/[^/]*-q(?P<quarter>[1-4])-(?P<year>20\d{2})-earnings(?:-call)?-transcript/?$",
    re.IGNORECASE,
)
FOOL_SECTION_LABELS = {
    "full conference call transcript": "Presentation",
    "presentation": "Presentation",
    "prepared remarks": "Prepared Remarks",
    "questions and answers": "Question-and-Answer Session",
    "questions & answers": "Question-and-Answer Session",
    "question-and-answer session": "Question-and-Answer Session",
    "question and answer session": "Question-and-Answer Session",
}
FOOL_STOP_HEADINGS = {"call participants", "takeaways", "industry glossary"}
FOOL_ROLE_KEYWORDS = (
    "chief",
    "officer",
    "president",
    "investor relations",
    "relations",
    "analyst",
    "director",
    "treasurer",
    "chair",
    "cofounder",
    "research division",
    "operator",
)
FOOL_CALL_DATE_PATTERN = re.compile(
    r"\b(?P<month>"
    r"Jan(?:uary)?\.?|Feb(?:ruary)?\.?|Mar(?:ch)?\.?|Apr(?:il)?\.?|May|"
    r"Jun(?:e)?\.?|Jul(?:y)?\.?|Aug(?:ust)?\.?|Sep(?:t(?:ember)?)?\.?|"
    r"Oct(?:ober)?\.?|Nov(?:ember)?\.?|Dec(?:ember)?\.?"
    r")\s+(?P<day>\d{1,2}),\s+(?P<year>20\d{2})\b"
)
_FOOL_MONTH_SITEMAP_CACHE: dict[str, list[dict[str, str]]] = {}

QUARTER_CN = {1: "第一", 2: "第二", 3: "第三", 4: "第四"}
SSR_DATA_PATTERN = re.compile(r"window\.SSR_DATA\s*=\s*(\{.*?\});</script>", re.DOTALL)
SPEAKER_LINE_PATTERN = re.compile(r"^(?P<speaker>[A-Z][A-Za-z0-9 .,&'()/-]{1,120}):\s*(?P<body>.*)$")
SA_QUARTERLY_EARNINGS_TITLE_PATTERN = re.compile(
    r"\bQ(?P<quarter>[1-4])\s+(?P<year>20\d{2})\b.*\bearnings(?:\s+conference)?\s+call\s+transcript\b",
    re.IGNORECASE,
)
SECTION_TITLES = {
    "presentation",
    "prepared remarks",
    "question-and-answer session",
    "questions and answers",
    "question and answer session",
    "q&a",
}
QUESTION_SECTION_PATTERN = re.compile(
    r"\b(?:"
    r"question-and-answer session|questions and answers|question and answer session|q&a|"
    r"we will now take (?:our |the )?first question|"
    r"we will now begin the question-and-answer session|"
    r"we will now open the line for questions|"
    r"we will now open the call for questions|"
    r"our first question comes from|"
    r"your first question comes from|"
    r"the first question comes from|"
    r"our next question comes from|"
    r"the next question comes from"
    r")\b",
    re.IGNORECASE,
)


def build_driver() -> webdriver.Remote:
    errors: list[str] = []

    edge_options = webdriver.EdgeOptions()
    edge_options.add_argument("--headless=new")
    edge_options.add_argument("--disable-gpu")
    edge_options.add_argument("--window-size=1440,3200")
    edge_options.add_argument("--log-level=3")
    try:
        driver = webdriver.Edge(options=edge_options)
        driver.set_page_load_timeout(PINEIFY_PAGE_LOAD_TIMEOUT)
        return driver
    except Exception as exc:
        errors.append(f"Edge: {exc}")

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1440,3200")
    chrome_options.add_argument("--log-level=3")
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(PINEIFY_PAGE_LOAD_TIMEOUT)
        return driver
    except Exception as exc:
        errors.append(f"Chrome: {exc}")

    raise RuntimeError("; ".join(errors) or "Unable to launch a browser for Pineify.")


def build_debugger_driver(debugger_address: str | None = None) -> webdriver.Remote:
    options = webdriver.EdgeOptions()
    options.add_experimental_option("debuggerAddress", debugger_address or SEEKING_ALPHA_DEBUGGER_ADDRESS)
    driver = webdriver.Edge(options=options)
    driver.set_page_load_timeout(PINEIFY_PAGE_LOAD_TIMEOUT)
    return driver


def build_candidate_fiscal_years(as_of: date | None = None) -> list[int]:
    reference_date = as_of or datetime.now().date()
    return list(range(reference_date.year - 2, reference_date.year + 1))


def normalize_page_text(value: str) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n")


def normalize_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(str(value or ""))).strip()


def build_http_session(*, headers: dict[str, str] | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(headers or SEEKING_ALPHA_HEADERS)
    return session


def iter_month_starts_between(start_date: date, end_date: date) -> list[date]:
    current = date(start_date.year, start_date.month, 1)
    limit = date(end_date.year, end_date.month, 1)
    months: list[date] = []
    while current <= limit:
        months.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def parse_month_date_token(value: str) -> str | None:
    compact = str(value or "").strip().replace("Sept.", "Sep.").replace("Sept", "Sep")
    if not compact:
        return None

    candidates = (
        "%b. %d, %Y",
        "%b %d, %Y",
        "%B %d, %Y",
    )
    for fmt in candidates:
        try:
            return datetime.strptime(compact, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_fool_month_sitemap(
    session: requests.Session,
    year: int,
    month: int,
) -> list[dict[str, str]]:
    cache_key = f"{year:04d}-{month:02d}"
    if cache_key in _FOOL_MONTH_SITEMAP_CACHE:
        return [dict(item) for item in _FOOL_MONTH_SITEMAP_CACHE[cache_key]]

    response = session.get(f"{FOOL_SITEMAP_INDEX_URL}{year:04d}/{month:02d}", timeout=30)
    response.raise_for_status()
    root = etree.fromstring(response.content)
    items: list[dict[str, str]] = []
    for url_el in root.findall("sm:url", FOOL_SITEMAP_NS):
        loc = normalize_inline_text(url_el.findtext("sm:loc", default="", namespaces=FOOL_SITEMAP_NS))
        lastmod = normalize_inline_text(
            url_el.findtext("sm:lastmod", default="", namespaces=FOOL_SITEMAP_NS)
        )
        if not loc:
            continue
        items.append({"loc": loc, "lastmod": lastmod})

    _FOOL_MONTH_SITEMAP_CACHE[cache_key] = [dict(item) for item in items]
    return items


def looks_like_fool_role_line(text: str) -> bool:
    compact = normalize_inline_text(text)
    if not compact or len(compact) > 90:
        return False
    lowered = compact.casefold()
    return any(keyword in lowered for keyword in FOOL_ROLE_KEYWORDS)


def looks_like_fool_prompt_line(text: str) -> bool:
    compact = normalize_inline_text(text)
    return bool(compact.endswith("?") and len(compact) <= 32 and len(compact.split()) <= 4)


def extract_fool_speaker_label(text: str) -> str | None:
    compact = normalize_inline_text(text)
    if not compact or len(compact) > 120 or compact.endswith(":"):
        return None

    match = re.match(r"^(?P<speaker>[A-Z][A-Za-z0-9 .,&'()/:-]{0,100}?)(?:\s+--\s+.+)?$", compact)
    if match is None:
        return None

    speaker = match.group("speaker").strip(" :-")
    if not speaker or len(speaker.split()) > 8:
        return None
    lowered = speaker.casefold()
    if lowered in {"contents", "prepared remarks", "questions and answers", "call participants"}:
        return None
    return speaker


def build_fool_transcript_source_text(container: lxml_html.HtmlElement) -> tuple[str, str]:
    started = False
    pending_speaker = ""
    prelude_parts: list[str] = []
    transcript_lines: list[str] = []

    def push_section(title: str) -> None:
        normalized = normalize_section_title(title)
        if transcript_lines and transcript_lines[-1]:
            transcript_lines.append("")
        transcript_lines.append(normalized)
        transcript_lines.append("")

    for child in container.getchildren():
        tag = child.tag.lower() if isinstance(child.tag, str) else ""
        text = normalize_inline_text(" ".join(child.xpath(".//text()")))
        if not text:
            continue

        heading_key = text.rstrip(":").strip().casefold()
        if tag in {"h2", "h3"}:
            if heading_key in FOOL_STOP_HEADINGS and started:
                break

            section_label = FOOL_SECTION_LABELS.get(heading_key)
            if section_label:
                started = True
                pending_speaker = ""
                push_section(section_label)
                continue

            if not started:
                prelude_parts.append(text)
            continue

        if not started:
            prelude_parts.append(text)
            continue

        if tag == "ul":
            continue

        if looks_like_fool_prompt_line(text):
            continue

        strong_text = normalize_inline_text(" ".join(child.xpath("./strong//text()")))
        if strong_text:
            speaker = strong_text.rstrip(":").strip()
            body_text = normalize_inline_text(text[len(strong_text) :].lstrip(" :.-"))
            if body_text:
                transcript_lines.append(f"{speaker}: {body_text}")
            else:
                pending_speaker = speaker
            continue

        speaker_label = extract_fool_speaker_label(text)
        if speaker_label:
            pending_speaker = speaker_label
            continue

        if pending_speaker and looks_like_fool_role_line(text):
            continue

        if pending_speaker:
            transcript_lines.append(f"{pending_speaker}: {text}")
            pending_speaker = ""
            continue

        transcript_lines.append(text)

    return "\n".join(prelude_parts), "\n".join(transcript_lines).strip()


def extract_fool_title_metadata(title: str) -> tuple[int, int] | None:
    match = FOOL_TITLE_PATTERN.search(normalize_inline_text(title))
    if match is None:
        return None
    return int(match.group("year")), int(match.group("quarter"))


def extract_fool_quarter_from_url(url: str) -> tuple[int, int] | None:
    match = FOOL_URL_QUARTER_PATTERN.search(str(url or "").strip())
    if match is None:
        return None
    return int(match.group("year")), int(match.group("quarter"))


def extract_fool_call_date(prelude_text: str, transcript_text: str, published_date: str) -> str:
    for source_text in (prelude_text, transcript_text[:400]):
        match = FOOL_CALL_DATE_PATTERN.search(source_text)
        if match is None:
            continue
        month_token = f"{match.group('month')} {match.group('day')}, {match.group('year')}"
        if parsed := parse_month_date_token(month_token):
            return parsed
    return str(published_date or "").strip()[:10]


def fetch_fool_article_call(
    session: requests.Session,
    article_url: str,
    *,
    expected_symbol: str,
) -> dict[str, Any] | None:
    response = session.get(article_url, timeout=30)
    response.raise_for_status()
    root = lxml_html.fromstring(response.text)
    container_nodes = root.xpath('//div[contains(@class,"article-body") and contains(@class,"transcript-content")]')
    if not container_nodes:
        return None

    title = normalize_inline_text(root.xpath("string(//h1)"))
    title_meta = extract_fool_title_metadata(title)
    if title_meta is None:
        return None
    fiscal_year, quarter = title_meta
    symbol_match = FOOL_TITLE_PATTERN.search(title)
    page_symbol = str(symbol_match.group("symbol") if symbol_match else "").upper()
    if page_symbol != str(expected_symbol or "").upper():
        return None

    published_at = normalize_inline_text(
        root.xpath('string(//meta[@property="article:published_time"]/@content)')
    )[:40]
    published_date = published_at[:10]
    prelude_text, raw_transcript_text = build_fool_transcript_source_text(container_nodes[0])
    if not raw_transcript_text:
        return None

    call_date = extract_fool_call_date(prelude_text, raw_transcript_text, published_date)
    return build_call_record_from_text(
        symbol=page_symbol,
        fiscal_year=fiscal_year,
        quarter=quarter,
        call_date=call_date,
        transcript_text=raw_transcript_text,
        title=build_display_title(page_symbol, fiscal_year, quarter, call_date),
        original_title=title[:220],
        source_label=FOOL_SOURCE_LABEL,
        source_short_label=FOOL_SOURCE_SHORT_LABEL,
        source_url=article_url[:600],
        source_query_label=f"{page_symbol} / FY{fiscal_year} / Q{quarter}",
        published_at=published_at,
        published_date=published_date,
    )

def build_summary_excerpt(text: str, *, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def build_display_title(symbol: str, fiscal_year: int, quarter: int, call_date: str) -> str:
    if call_date and call_date[:4].isdigit() and call_date[:4] != str(fiscal_year):
        return f"{symbol} FY{fiscal_year} Q{quarter} 财报电话会议记录"
    quarter_label = QUARTER_CN.get(quarter)
    if quarter_label:
        return f"{symbol} {fiscal_year}年{quarter_label}季度财报电话会议记录"
    return f"{symbol} FY{fiscal_year} Q{quarter} 财报电话会议记录"


def build_original_title(symbol: str, fiscal_year: int, quarter: int) -> str:
    return f"{symbol} Q{quarter} {fiscal_year} Earnings Call Transcript"


def split_long_speech(text: str, *, max_chars: int = 520, max_sentences: int = 4) -> list[str]:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return []

    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", compact)
        if item.strip()
    ]
    if len(sentences) <= 1:
        return [compact]

    paragraphs: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in sentences:
        sentence_len = len(sentence)
        should_flush = (
            current
            and (current_len + sentence_len + 1 > max_chars or len(current) >= max_sentences)
        )
        if should_flush:
            paragraphs.append(" ".join(current).strip())
            current = []
            current_len = 0
        current.append(sentence)
        current_len += sentence_len + 1

    if current:
        paragraphs.append(" ".join(current).strip())
    return paragraphs or [compact]


def normalize_section_title(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or "")).strip()
    if not compact:
        return ""
    lowered = compact.casefold()
    if lowered == "q&a":
        return "Q&A"
    if lowered == "question-and-answer session":
        return "Question-and-Answer Session"
    if lowered == "question and answer session":
        return "Question and Answer Session"
    if lowered == "questions and answers":
        return "Questions and Answers"
    if lowered == "presentation":
        return "Presentation"
    if lowered == "prepared remarks":
        return "Prepared Remarks"
    return compact


def parse_transcript_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_speaker = ""
    current_parts: list[str] = []

    def flush_current() -> None:
        nonlocal current_speaker, current_parts
        body = re.sub(r"\s+", " ", " ".join(current_parts)).strip()
        if current_speaker and body:
            blocks.append({"kind": "speech", "speaker": current_speaker, "body": body})
        current_speaker = ""
        current_parts = []

    for raw_line in normalize_page_text(text).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        if line.casefold() in SECTION_TITLES:
            flush_current()
            blocks.append({"kind": "section", "title": normalize_section_title(line)})
            continue

        speaker_match = SPEAKER_LINE_PATTERN.match(line)
        if speaker_match:
            flush_current()
            current_speaker = speaker_match.group("speaker").strip()
            initial_body = speaker_match.group("body").strip()
            current_parts = [initial_body] if initial_body else []
            continue

        if current_speaker:
            current_parts.append(line)

    flush_current()
    return blocks


def infer_transcript_sections(blocks: list[dict[str, str]]) -> list[dict[str, str]]:
    if not blocks:
        return []

    explicit_question_section = any(
        block.get("kind") == "section"
        and (
            "question" in str(block.get("title") or "").casefold()
            or str(block.get("title") or "").casefold() == "q&a"
        )
        for block in blocks
    )
    if explicit_question_section:
        return blocks

    inferred_blocks: list[dict[str, str]] = []
    question_section_inserted = False
    for block in blocks:
        if (
            not question_section_inserted
            and block.get("kind") == "speech"
            and QUESTION_SECTION_PATTERN.search(str(block.get("body") or ""))
            and len([item for item in inferred_blocks if item.get("kind") == "speech"]) >= 2
        ):
            inferred_blocks.append({"kind": "section", "title": "Question-and-Answer Session"})
            question_section_inserted = True
        inferred_blocks.append(block)

    return inferred_blocks


def render_transcript_text(blocks: list[dict[str, str]]) -> str:
    if not blocks:
        return ""

    lines: list[str] = []
    seen_section = False
    for block in blocks:
        if block.get("kind") == "section":
            if lines and lines[-1]:
                lines.append("")
            lines.append(block["title"])
            lines.append("")
            seen_section = True
            continue

        if block.get("kind") != "speech":
            continue

        if not seen_section:
            lines.append("Presentation")
            lines.append("")
            seen_section = True

        lines.append(f"{block['speaker']}:")
        for paragraph in split_long_speech(block["body"]):
            lines.append(paragraph)
        lines.append("")

    return "\n".join(lines).strip()


def render_transcript_html(blocks: list[dict[str, str]]) -> str:
    if not blocks:
        return ""

    html_parts = ["<div>"]
    seen_section = False
    for block in blocks:
        if block.get("kind") == "section":
            html_parts.append(f"<h3>{escape(block['title'])}</h3>")
            seen_section = True
            continue

        if block.get("kind") != "speech":
            continue

        if not seen_section:
            html_parts.append("<h3>Presentation</h3>")
            seen_section = True

        html_parts.append(f"<h4>{escape(block['speaker'])}</h4>")
        for paragraph in split_long_speech(block["body"]):
            html_parts.append(f"<p>{escape(paragraph)}</p>")

    html_parts.append("</div>")
    return "".join(html_parts)


def format_transcript_content(text: str) -> tuple[str, str, int, bool]:
    raw_text = normalize_page_text(text)
    blocks = parse_transcript_blocks(raw_text)
    if not blocks:
        compact = re.sub(r"\n{3,}", "\n\n", raw_text).strip()
        if not compact:
            return "", "", 0, False
        return compact, "".join(f"<p>{escape(item)}</p>" for item in compact.split("\n\n") if item.strip()), 0, False

    blocks = infer_transcript_sections(blocks)
    formatted_text = render_transcript_text(blocks)
    formatted_html = render_transcript_html(blocks)
    speaker_turn_count = sum(1 for block in blocks if block.get("kind") == "speech")
    has_question_section = any(
        "question" in str(block.get("title") or "").casefold()
        or str(block.get("title") or "").casefold() == "q&a"
        for block in blocks
        if block.get("kind") == "section"
    )
    return formatted_text, formatted_html, speaker_turn_count, has_question_section


def build_quality_notes(
    transcript_text: str,
    *,
    speaker_turn_count: int,
    has_question_section: bool,
) -> list[str]:
    quality_notes: list[str] = []
    if len(transcript_text) < 3000:
        quality_notes.append("正文长度偏短")
    if speaker_turn_count < 6:
        quality_notes.append("说话人轮次偏少")
    if not has_question_section:
        quality_notes.append("未识别到问答分段")
    return quality_notes


def html_to_plain_text(value: str) -> str:
    html = str(value or "").strip()
    if not html:
        return ""
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</div\s*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</h[1-6]\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    return normalize_page_text(unescape(html)).strip()


def choose_display_call_date(call_date: str, article: dict[str, Any] | None = None) -> str:
    compact = str(call_date or "").strip()
    if compact:
        return compact[:10]
    article_date = str((article or {}).get("published_date") or "").strip()
    return article_date[:10]


def build_call_record_from_text(
    *,
    symbol: str,
    fiscal_year: int,
    quarter: int,
    call_date: str,
    transcript_text: str,
    title: str | None = None,
    original_title: str | None = None,
    source_label: str,
    source_short_label: str,
    source_url: str,
    source_query_label: str,
    published_at: str,
    published_date: str,
    quality_notes: list[str] | None = None,
    call_id: str | None = None,
) -> dict[str, Any] | None:
    formatted_text, formatted_html, speaker_turn_count, has_question_section = format_transcript_content(
        transcript_text
    )
    if not formatted_text:
        return None

    merged_quality_notes = merge_quality_notes(
        build_quality_notes(
            formatted_text,
            speaker_turn_count=speaker_turn_count,
            has_question_section=has_question_section,
        ),
        quality_notes or [],
    )
    normalized_call_date = choose_display_call_date(call_date)
    display_title = title or build_display_title(symbol, fiscal_year, quarter, normalized_call_date)
    display_original_title = original_title or build_original_title(symbol, fiscal_year, quarter)

    return {
        "id": call_id
        or hashlib.sha1(f"{symbol}:{fiscal_year}:Q{quarter}:{normalized_call_date}".encode("utf-8")).hexdigest()[:12],
        "symbol": symbol,
        "title": display_title,
        "original_title": display_original_title,
        "source_label": source_label,
        "source_short_label": source_short_label,
        "source_url": source_url,
        "source_query_label": source_query_label,
        "published_at": published_at,
        "published_date": published_date,
        "call_date": normalized_call_date,
        "call_date_label": normalized_call_date,
        "summary_text": "",
        "summary_excerpt": build_summary_excerpt(formatted_text),
        "transcript_text": formatted_text,
        "transcript_html": formatted_html,
        "word_count": len(re.findall(r"\b\w+\b", formatted_text)),
        "speaker_turn_count": speaker_turn_count,
        "has_question_section": has_question_section,
        "is_complete": len(merged_quality_notes) == 0,
        "quality_notes": merged_quality_notes,
        "fiscal_year": fiscal_year,
        "fiscal_quarter": quarter,
    }


def parse_pineify_transcript_text(
    body_text: str,
    *,
    symbol: str,
    fiscal_year: int,
    quarter: int,
) -> dict[str, Any] | None:
    normalized_text = normalize_page_text(body_text)
    marker = f"Transcripts for {symbol}"
    period_marker = f"{symbol}\nQ{quarter} {fiscal_year}\n"

    if marker not in normalized_text or period_marker not in normalized_text:
        return None

    relevant_text = normalized_text[normalized_text.find(marker) :]
    header_pattern = re.compile(
        rf"{re.escape(symbol)}\nQ{quarter} {fiscal_year}\n(?P<call_date>\d{{4}}-\d{{2}}-\d{{2}})\n",
        re.MULTILINE,
    )
    header_match = header_pattern.search(relevant_text)
    if header_match is None:
        return None

    call_date = header_match.group("call_date")
    transcript_text = relevant_text[header_match.end() :]
    transcript_end = len(transcript_text)
    for token in PINEIFY_TERMINATOR_TOKENS:
        token_index = transcript_text.find(token)
        if token_index >= 0:
            transcript_end = min(transcript_end, token_index)
    transcript_text = transcript_text[:transcript_end].strip()
    return build_call_record_from_text(
        symbol=symbol,
        fiscal_year=fiscal_year,
        quarter=quarter,
        call_date=call_date,
        transcript_text=transcript_text,
        source_label=PINEIFY_SOURCE_LABEL,
        source_short_label=PINEIFY_SOURCE_SHORT_LABEL,
        source_url=PINEIFY_SOURCE_URL,
        source_query_label=f"{symbol} / FY{fiscal_year} / Q{quarter}",
        published_at=f"{call_date}T00:00:00",
        published_date=call_date,
    )


def run_pineify_query(
    driver: webdriver.Remote,
    *,
    symbol: str,
    fiscal_year: int,
    quarter: int,
) -> dict[str, Any] | None:
    driver.get(PINEIFY_SOURCE_URL)
    time.sleep(2.5)

    input_el = driver.find_element(By.TAG_NAME, "input")
    input_el.clear()
    input_el.send_keys(symbol)

    selects = driver.find_elements(By.TAG_NAME, "select")
    if len(selects) < 2:
        raise RuntimeError("Pineify page does not expose the year/quarter selectors.")

    Select(selects[0]).select_by_visible_text(str(fiscal_year))
    Select(selects[1]).select_by_visible_text(f"Q{quarter}")

    search_clicked = False
    for button in driver.find_elements(By.TAG_NAME, "button"):
        if button.text.strip() == "Search Transcripts":
            button.click()
            search_clicked = True
            break

    if not search_clicked:
        raise RuntimeError("Pineify page did not expose the search button.")

    body_text = ""
    deadline = time.time() + PINEIFY_WAIT_SECONDS
    while time.time() < deadline:
        body_text = normalize_page_text(driver.find_element(By.TAG_NAME, "body").text)
        if f"Transcripts for {symbol}" in body_text and f"Q{quarter} {fiscal_year}" in body_text:
            break
        time.sleep(1)

    return parse_pineify_transcript_text(
        body_text,
        symbol=symbol,
        fiscal_year=fiscal_year,
        quarter=quarter,
    )


def extract_ssr_data(page_html: str) -> dict[str, Any]:
    match = SSR_DATA_PATTERN.search(page_html)
    if match is None:
        raise RuntimeError("Seeking Alpha page is missing SSR transcript data.")
    return json.loads(match.group(1))


def open_debugger_work_tab(driver: webdriver.Remote) -> tuple[str, str]:
    original_handle = driver.current_window_handle
    existing_handles = set(driver.window_handles)
    driver.execute_script("window.open('about:blank', '_blank');")
    deadline = time.time() + 5
    work_handle = ""
    while time.time() < deadline:
        new_handles = [handle for handle in driver.window_handles if handle not in existing_handles]
        if new_handles:
            work_handle = new_handles[-1]
            break
        time.sleep(0.1)

    if not work_handle:
        work_handle = driver.window_handles[-1]
    driver.switch_to.window(work_handle)
    return original_handle, work_handle


def close_debugger_work_tab(driver: webdriver.Remote, *, original_handle: str, work_handle: str) -> None:
    try:
        if work_handle in driver.window_handles:
            driver.switch_to.window(work_handle)
            driver.close()
    except Exception:
        pass

    try:
        if original_handle in driver.window_handles:
            driver.switch_to.window(original_handle)
    except Exception:
        pass


def fetch_seeking_alpha_symbol_transcript_page(
    driver: webdriver.Remote,
    symbol: str,
    *,
    page_number: int,
) -> dict[str, Any]:
    url = f"{SEEKING_ALPHA_BASE_URL}/symbol/{symbol}/earnings/transcripts"
    if page_number > 1:
        url = f"{url}?page={page_number}"

    driver.get(url)
    deadline = time.time() + 20
    last_error = "Seeking Alpha transcript page did not finish loading."
    while time.time() < deadline:
        page_html = driver.page_source
        if "Access Denied" in page_html or "captcha" in page_html.casefold():
            last_error = "Seeking Alpha session is blocked by verification. Please keep the logged-in browser open."
            time.sleep(0.5)
            continue
        if "window.SSR_DATA" not in page_html or "symbolTranscripts" not in page_html:
            time.sleep(0.5)
            continue
        ssr_data = extract_ssr_data(page_html)
        transcript_payload = ssr_data.get("symbolTranscripts")
        if not isinstance(transcript_payload, list) or not transcript_payload:
            last_error = "Seeking Alpha transcript list payload is missing."
            time.sleep(0.5)
            continue
        page_payload = transcript_payload[0]
        if not isinstance(page_payload, dict):
            last_error = "Seeking Alpha transcript page payload is invalid."
            time.sleep(0.5)
            continue
        return page_payload

    raise RuntimeError(last_error)


def extract_article_quarter(title: str) -> tuple[int, int] | None:
    match = SA_QUARTERLY_EARNINGS_TITLE_PATTERN.search(str(title or ""))
    if match is None:
        return None
    return int(match.group("year")), int(match.group("quarter"))


def build_seeking_alpha_article_url(path: str) -> str:
    compact = str(path or "").strip()
    if compact.startswith("http://") or compact.startswith("https://"):
        return compact
    return f"{SEEKING_ALPHA_BASE_URL}{compact}"


def collect_recent_seeking_alpha_quarterly_articles(
    driver: webdriver.Remote,
    symbol: str,
    *,
    cutoff_date: date,
) -> tuple[list[dict[str, Any]], list[str]]:
    candidates: dict[tuple[int, int], dict[str, Any]] = {}
    warnings: list[str] = []
    page_number = 1
    total_pages = 1

    while page_number <= total_pages:
        page_payload = fetch_seeking_alpha_symbol_transcript_page(driver, symbol, page_number=page_number)
        response_payload = page_payload.get("response") if isinstance(page_payload.get("response"), dict) else {}
        items = response_payload.get("data") if isinstance(response_payload.get("data"), list) else []
        meta_page = response_payload.get("meta", {}).get("page", {})
        total_pages = int(meta_page.get("totalPages") or total_pages or 1)

        oldest_publish_date_on_page: date | None = None
        for item in items:
            if not isinstance(item, dict) or str(item.get("type") or "") != "transcript":
                continue

            title = str(item.get("attributes", {}).get("title") or "").strip()
            quarter_info = extract_article_quarter(title)
            if quarter_info is None:
                continue

            published_at = str(item.get("attributes", {}).get("publishOn") or "").strip()
            published_date_text = published_at[:10]
            try:
                published_date = date.fromisoformat(published_date_text)
            except ValueError:
                warnings.append(f"{symbol} page {page_number}: invalid publish date for {title}")
                continue

            if oldest_publish_date_on_page is None or published_date < oldest_publish_date_on_page:
                oldest_publish_date_on_page = published_date

            if published_date < cutoff_date:
                continue

            fiscal_year, fiscal_quarter = quarter_info
            candidate_key = (fiscal_year, fiscal_quarter)
            if candidate_key in candidates:
                continue

            article_path = str(item.get("links", {}).get("self") or "").strip()
            candidates[candidate_key] = {
                "article_id": str(item.get("id") or "").strip(),
                "article_url": build_seeking_alpha_article_url(article_path),
                "title": title[:220],
                "published_at": published_at[:40],
                "published_date": published_date_text,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
            }

        if oldest_publish_date_on_page is not None and oldest_publish_date_on_page < cutoff_date:
            break
        page_number += 1

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            str(item.get("published_date") or ""),
            int(item.get("fiscal_year") or 0),
            int(item.get("fiscal_quarter") or 0),
        ),
        reverse=True,
    )
    return ordered_candidates, warnings


def score_existing_call(raw_call: dict[str, Any]) -> tuple[int, int, int]:
    transcript_text = str(raw_call.get("transcript_text") or "").strip()
    transcript_html = str(raw_call.get("transcript_html") or "").strip()
    return (
        len(transcript_text),
        int(bool(transcript_html)),
        int(bool(raw_call.get("is_complete"))),
    )


def build_existing_call_index(existing_calls: list[dict[str, Any]] | None) -> dict[tuple[int, int], dict[str, Any]]:
    indexed: dict[tuple[int, int], dict[str, Any]] = {}
    for raw_call in existing_calls or []:
        if not isinstance(raw_call, dict):
            continue
        try:
            fiscal_year = int(raw_call.get("fiscal_year") or 0)
            fiscal_quarter = int(raw_call.get("fiscal_quarter") or 0)
        except (TypeError, ValueError):
            continue
        if fiscal_year <= 0 or fiscal_quarter not in {1, 2, 3, 4}:
            continue

        key = (fiscal_year, fiscal_quarter)
        if key not in indexed or score_existing_call(raw_call) > score_existing_call(indexed[key]):
            indexed[key] = raw_call
    return indexed


def build_call_from_existing(
    raw_call: dict[str, Any],
    *,
    symbol: str,
    fiscal_year: int,
    quarter: int,
    article: dict[str, Any] | None = None,
    source_label: str | None = None,
    source_short_label: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any] | None:
    transcript_text = normalize_page_text(str(raw_call.get("transcript_text") or "").strip())
    if not transcript_text:
        transcript_text = html_to_plain_text(str(raw_call.get("transcript_html") or ""))
    if not transcript_text:
        return None

    article = article or {}
    call_date = choose_display_call_date(str(raw_call.get("call_date") or ""), article)
    return build_call_record_from_text(
        symbol=symbol,
        fiscal_year=fiscal_year,
        quarter=quarter,
        call_date=call_date,
        transcript_text=transcript_text,
        title=build_display_title(symbol, fiscal_year, quarter, call_date),
        original_title=str(article.get("title") or raw_call.get("original_title") or "").strip()[:220],
        source_label=str(source_label or article.get("source_label") or raw_call.get("source_label") or "").strip()
        or "Seeking Alpha + Pineify",
        source_short_label=str(
            source_short_label or article.get("source_short_label") or raw_call.get("source_short_label") or ""
        ).strip()
        or "sa+p",
        source_url=str(source_url or article.get("article_url") or raw_call.get("source_url") or "").strip()[:600],
        source_query_label=f"{symbol} / FY{fiscal_year} / Q{quarter}",
        published_at=str(article.get("published_at") or raw_call.get("published_at") or "").strip()[:40],
        published_date=str(article.get("published_date") or raw_call.get("published_date") or "").strip()[:40],
        call_id=str(raw_call.get("id") or "").strip()[:40] or None,
        quality_notes=list(raw_call.get("quality_notes", [])),
    )


def merge_quality_notes(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for note in group:
            compact = str(note or "").strip()
            if not compact or compact in seen:
                continue
            seen.add(compact)
            merged.append(compact)
    return merged


def collect_recent_fool_quarterly_articles(
    session: requests.Session,
    symbol: str,
    *,
    cutoff_date: date,
    reference_date: date,
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized_symbol = str(symbol or "").strip().upper()
    symbol_slug = normalized_symbol.lower()
    warnings: list[str] = []
    candidates: dict[tuple[int, int], dict[str, Any]] = {}

    month_starts = iter_month_starts_between(cutoff_date, reference_date)
    for month_start in reversed(month_starts):
        try:
            sitemap_items = fetch_fool_month_sitemap(session, month_start.year, month_start.month)
        except Exception as exc:
            warnings.append(f"{month_start:%Y-%m} sitemap fetch failed: {exc}")
            continue

        for item in sitemap_items:
            loc = str(item.get("loc") or "").strip()
            loc_lower = loc.lower()
            if "/earnings/call-transcripts/" not in loc_lower:
                continue
            if f"-{symbol_slug}-" not in loc_lower:
                continue

            quarter_info = extract_fool_quarter_from_url(loc)
            if quarter_info is None:
                continue
            fiscal_year, fiscal_quarter = quarter_info
            candidate_key = (fiscal_year, fiscal_quarter)
            if candidate_key in candidates:
                continue

            published_at = str(item.get("lastmod") or "").strip()[:40]
            published_date = published_at[:10]
            if published_date:
                try:
                    if date.fromisoformat(published_date) < cutoff_date:
                        continue
                except ValueError:
                    pass

            candidates[candidate_key] = {
                "article_url": loc[:600],
                "published_at": published_at,
                "published_date": published_date,
                "fiscal_year": fiscal_year,
                "fiscal_quarter": fiscal_quarter,
            }

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            str(item.get("published_date") or ""),
            int(item.get("fiscal_year") or 0),
            int(item.get("fiscal_quarter") or 0),
        ),
        reverse=True,
    )
    return ordered_candidates, warnings


def fetch_recent_fool_earnings_calls(
    symbol: str,
    *,
    as_of: date | None = None,
    lookback_days: int = 730,
    existing_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("Missing stock symbol.")

    reference_date = as_of or datetime.now().date()
    cutoff_date = reference_date - timedelta(days=max(0, int(lookback_days)))
    warnings: list[str] = []
    session = build_http_session(headers=FOOL_HEADERS)
    articles, article_warnings = collect_recent_fool_quarterly_articles(
        session,
        normalized_symbol,
        cutoff_date=cutoff_date,
        reference_date=reference_date,
    )
    warnings.extend(article_warnings)

    calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    used_quarters: set[tuple[int, int]] = set()
    existing_call_index = build_existing_call_index(existing_calls)

    for article in articles:
        fiscal_year = int(article.get("fiscal_year") or 0)
        fiscal_quarter = int(article.get("fiscal_quarter") or 0)
        if fiscal_year <= 0 or fiscal_quarter not in {1, 2, 3, 4}:
            continue

        call = None
        try:
            call = fetch_fool_article_call(
                session,
                str(article.get("article_url") or ""),
                expected_symbol=normalized_symbol,
            )
        except Exception as exc:
            warnings.append(f"FY{fiscal_year} Q{fiscal_quarter} Fool transcript fetch failed: {exc}")

        if call is None:
            existing_call = existing_call_index.get((fiscal_year, fiscal_quarter))
            if existing_call is not None:
                call = build_call_from_existing(
                    existing_call,
                    symbol=normalized_symbol,
                    fiscal_year=fiscal_year,
                    quarter=fiscal_quarter,
                    article={
                        "title": str(article.get("title") or existing_call.get("original_title") or "").strip()[:220],
                        "published_at": str(article.get("published_at") or existing_call.get("published_at") or "").strip()[:40],
                        "published_date": str(article.get("published_date") or existing_call.get("published_date") or "").strip()[:40],
                    },
                    source_label=f"{FOOL_SOURCE_LABEL} + Archive",
                    source_short_label="fool+arc",
                    source_url=str(article.get("article_url") or existing_call.get("source_url") or "").strip()[:600],
                )
                if call is not None:
                    call["quality_notes"] = merge_quality_notes(
                        list(call.get("quality_notes", [])),
                        ["Motley Fool page was unavailable for parsing; kept the previously stored transcript body."],
                    )

        if call is None:
            continue

        used_quarters.add((fiscal_year, fiscal_quarter))
        call_id = str(call.get("id") or "")
        if call_id in seen_ids:
            continue
        seen_ids.add(call_id)
        calls.append(call)

    for (fiscal_year, fiscal_quarter), existing_call in existing_call_index.items():
        if (fiscal_year, fiscal_quarter) in used_quarters:
            continue
        call_date_text = str(existing_call.get("call_date") or existing_call.get("published_date") or "").strip()
        try:
            parsed_call_date = date.fromisoformat(call_date_text[:10])
        except ValueError:
            parsed_call_date = None
        if parsed_call_date is not None and parsed_call_date < cutoff_date:
            continue

        call = build_call_from_existing(
            existing_call,
            symbol=normalized_symbol,
            fiscal_year=fiscal_year,
            quarter=fiscal_quarter,
            source_label=f"{FOOL_SOURCE_LABEL} + Archive",
            source_short_label="fool+arc",
            source_url=str(existing_call.get("source_url") or FOOL_SOURCE_URL).strip()[:600],
        )
        if call is None:
            continue
        call["quality_notes"] = merge_quality_notes(
            list(call.get("quality_notes", [])),
            ["Kept the previously stored transcript because no free Motley Fool page was found for this quarter."],
        )
        call_id = str(call.get("id") or "")
        if call_id in seen_ids:
            continue
        seen_ids.add(call_id)
        calls.append(call)

    calls.sort(
        key=lambda item: (
            str(item.get("call_date") or item.get("published_date") or ""),
            int(item.get("fiscal_year") or 0),
            int(item.get("fiscal_quarter") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )

    return {
        "source_label": FOOL_SOURCE_LABEL,
        "source_url": FOOL_SOURCE_URL,
        "lookback_days": lookback_days,
        "warnings": warnings,
        "calls": calls,
    }


def build_archive_only_payload(
    symbol: str,
    *,
    as_of: date | None = None,
    lookback_days: int = 730,
    existing_calls: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    reference_date = as_of or datetime.now().date()
    cutoff_date = reference_date - timedelta(days=max(0, int(lookback_days)))
    calls: list[dict[str, Any]] = []
    for (fiscal_year, fiscal_quarter), existing_call in build_existing_call_index(existing_calls).items():
        call = build_call_from_existing(
            existing_call,
            symbol=normalized_symbol,
            fiscal_year=fiscal_year,
            quarter=fiscal_quarter,
            source_label="Archive",
            source_short_label="archive",
            source_url=str(existing_call.get("source_url") or "").strip()[:600],
        )
        if call is None:
            continue
        call_date_text = str(call.get("call_date") or call.get("published_date") or "").strip()
        try:
            if date.fromisoformat(call_date_text[:10]) < cutoff_date:
                continue
        except ValueError:
            pass
        call["quality_notes"] = merge_quality_notes(
            list(call.get("quality_notes", [])),
            ["Using the previously stored transcript because the live free-source refresh failed."],
        )
        calls.append(call)

    calls.sort(
        key=lambda item: (
            str(item.get("call_date") or item.get("published_date") or ""),
            int(item.get("fiscal_year") or 0),
            int(item.get("fiscal_quarter") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )
    return {
        "source_label": "Archive",
        "source_url": FOOL_SOURCE_URL,
        "lookback_days": lookback_days,
        "warnings": list(warnings or []),
        "calls": calls,
    }


def enrich_call_with_seeking_alpha_metadata(call: dict[str, Any], article: dict[str, Any]) -> dict[str, Any]:
    call["original_title"] = str(article.get("title") or call.get("original_title") or "").strip()[:220]
    call["source_label"] = "Seeking Alpha + Pineify"
    call["source_short_label"] = "sa+p"
    call["source_url"] = str(article.get("article_url") or "").strip()[:600]
    call["published_at"] = str(article.get("published_at") or call.get("published_at") or "").strip()[:40]
    call["published_date"] = str(article.get("published_date") or call.get("published_date") or "").strip()[:40]
    return call


def fetch_recent_pineify_earnings_calls(
    symbol: str,
    *,
    as_of: date | None = None,
    lookback_days: int = 730,
) -> dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("Missing stock symbol.")

    reference_date = as_of or datetime.now().date()
    cutoff_date = reference_date - timedelta(days=max(0, int(lookback_days)))
    warnings: list[str] = []
    calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    driver = build_driver()

    try:
        for fiscal_year in sorted(build_candidate_fiscal_years(reference_date), reverse=True):
            for quarter in (4, 3, 2, 1):
                try:
                    call = run_pineify_query(
                        driver,
                        symbol=normalized_symbol,
                        fiscal_year=fiscal_year,
                        quarter=quarter,
                    )
                except Exception as exc:
                    warnings.append(f"FY{fiscal_year} Q{quarter} fetch failed: {exc}")
                    continue

                if call is None:
                    continue

                try:
                    call_date = date.fromisoformat(str(call.get("call_date") or ""))
                except ValueError:
                    warnings.append(f"FY{fiscal_year} Q{quarter} returned an invalid date")
                    continue

                if call_date < cutoff_date or call_date > reference_date:
                    continue
                if str(call.get("id") or "") in seen_ids:
                    continue

                seen_ids.add(str(call["id"]))
                calls.append(call)
    finally:
        driver.quit()

    calls.sort(
        key=lambda item: (
            str(item.get("call_date") or ""),
            int(item.get("fiscal_year") or 0),
            int(item.get("fiscal_quarter") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )

    return {
        "source_label": PINEIFY_SOURCE_LABEL,
        "source_url": PINEIFY_SOURCE_URL,
        "lookback_days": lookback_days,
        "warnings": warnings,
        "calls": calls,
    }


def fetch_recent_seeking_alpha_guided_earnings_calls(
    symbol: str,
    *,
    as_of: date | None = None,
    lookback_days: int = 730,
    debugger_address: str | None = None,
    existing_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        raise ValueError("Missing stock symbol.")

    reference_date = as_of or datetime.now().date()
    cutoff_date = reference_date - timedelta(days=max(0, int(lookback_days)))
    warnings: list[str] = []
    driver = build_debugger_driver(debugger_address=debugger_address)
    original_handle = ""
    work_handle = ""
    try:
        original_handle, work_handle = open_debugger_work_tab(driver)
        articles, sa_warnings = collect_recent_seeking_alpha_quarterly_articles(
            driver,
            normalized_symbol,
            cutoff_date=cutoff_date,
        )
        warnings.extend(sa_warnings)
    finally:
        if original_handle and work_handle:
            close_debugger_work_tab(driver, original_handle=original_handle, work_handle=work_handle)
        driver.quit()

    if not articles:
        raise RuntimeError("No quarterly earnings call transcripts were found on Seeking Alpha.")

    calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    existing_call_index = build_existing_call_index(existing_calls)
    pineify_driver: webdriver.Remote | None = None
    try:
        for article in articles:
            fiscal_year = int(article.get("fiscal_year") or 0)
            fiscal_quarter = int(article.get("fiscal_quarter") or 0)
            if fiscal_year <= 0 or fiscal_quarter not in {1, 2, 3, 4}:
                continue

            call = None
            existing_call = existing_call_index.get((fiscal_year, fiscal_quarter))
            if existing_call is not None:
                call = build_call_from_existing(
                    existing_call,
                    symbol=normalized_symbol,
                    fiscal_year=fiscal_year,
                    quarter=fiscal_quarter,
                    article=article,
                )

            if call is None:
                if pineify_driver is None:
                    pineify_driver = build_driver()
                try:
                    call = run_pineify_query(
                        pineify_driver,
                        symbol=normalized_symbol,
                        fiscal_year=fiscal_year,
                        quarter=fiscal_quarter,
                    )
                except Exception as exc:
                    warnings.append(f"FY{fiscal_year} Q{fiscal_quarter} Pineify full-text fetch failed: {exc}")
                    continue

                if call is None:
                    warnings.append(f"FY{fiscal_year} Q{fiscal_quarter} Pineify did not return a transcript body")
                    continue

                call = enrich_call_with_seeking_alpha_metadata(call, article)

            if str(call.get("id") or "") in seen_ids:
                continue

            seen_ids.add(str(call["id"]))
            calls.append(call)
    finally:
        if pineify_driver is not None:
            pineify_driver.quit()

    calls.sort(
        key=lambda item: (
            str(item.get("call_date") or item.get("published_date") or ""),
            int(item.get("fiscal_year") or 0),
            int(item.get("fiscal_quarter") or 0),
            str(item.get("title") or ""),
        ),
        reverse=True,
    )

    return {
        "source_label": "Seeking Alpha + Pineify",
        "source_url": f"{SEEKING_ALPHA_BASE_URL}/symbol/{normalized_symbol}/earnings/transcripts",
        "lookback_days": lookback_days,
        "warnings": warnings,
        "calls": calls,
    }


def fetch_recent_earnings_calls(
    symbol: str,
    *,
    as_of: date | None = None,
    lookback_days: int = 730,
    debugger_address: str | None = None,
    existing_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []

    try:
        payload = fetch_recent_fool_earnings_calls(
            symbol,
            as_of=as_of,
            lookback_days=lookback_days,
            existing_calls=existing_calls,
        )
    except Exception as exc:
        warnings.append(f"Motley Fool flow unavailable: {exc}")
    else:
        if warnings:
            payload["warnings"] = warnings + list(payload.get("warnings", []))
        return payload

    return build_archive_only_payload(
        symbol,
        as_of=as_of,
        lookback_days=lookback_days,
        existing_calls=existing_calls,
        warnings=warnings,
    )
