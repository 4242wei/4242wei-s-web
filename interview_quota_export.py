from __future__ import annotations

import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from region_normalization import normalize_region_label


QUOTA_STATUS_AUTO = ""
QUOTA_STATUS_COMPLETED = "completed"
QUOTA_STATUS_SCHEDULED = "scheduled"
QUOTA_STATUS_EXCLUDED = "excluded"
QUOTA_STATUS_CODES = {
    QUOTA_STATUS_AUTO,
    QUOTA_STATUS_COMPLETED,
    QUOTA_STATUS_SCHEDULED,
    QUOTA_STATUS_EXCLUDED,
}
QUOTA_STATUS_OPTIONS = [
    {"value": QUOTA_STATUS_AUTO, "label": "自动判断"},
    {"value": QUOTA_STATUS_COMPLETED, "label": "已完成访谈"},
    {"value": QUOTA_STATUS_SCHEDULED, "label": "已排期待访"},
    {"value": QUOTA_STATUS_EXCLUDED, "label": "不计入（失败/取消）"},
]
QUOTA_STATUS_LABELS = {
    QUOTA_STATUS_COMPLETED: "已完成访谈",
    QUOTA_STATUS_SCHEDULED: "已排期待访",
}

KNOWN_SCALE_ORDER = {
    "超大型": 10,
    "大型": 20,
    "中型": 30,
    "中小型": 40,
    "小型": 50,
    "未分类": 900,
}


@dataclass(frozen=True)
class QuotaRecord:
    expert_id: str
    expert_number: str
    name: str
    company: str
    title: str
    scale: str
    industry: str
    region: str
    quota_status: str
    interview_id: str
    interview_time: str
    interview_title: str
    interviewer: str
    interview_dates: tuple[str, ...] = ()


def normalize_quota_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    return status if status in QUOTA_STATUS_CODES else QUOTA_STATUS_AUTO


def _parse_local_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def classify_quota_interview(interview: dict[str, Any], *, now: datetime | None = None) -> str:
    """Return a stable quota code without relying on any display label."""
    explicit = normalize_quota_status(interview.get("quota_status"))
    if explicit:
        return explicit

    interview_status = str(interview.get("status") or "").strip().lower()
    if interview_status == "cancelled":
        return QUOTA_STATUS_EXCLUDED
    if interview.get("transcript_id") or interview_status == "completed":
        return QUOTA_STATUS_COMPLETED
    if interview_status != "scheduled":
        return QUOTA_STATUS_AUTO

    scheduled_at = _parse_local_datetime(interview.get("occurred_at"))
    reference = now or datetime.now()
    if reference.tzinfo is not None:
        reference = reference.astimezone().replace(tzinfo=None)
    if scheduled_at is not None and scheduled_at < reference:
        return QUOTA_STATUS_AUTO
    return QUOTA_STATUS_SCHEDULED


def _record_number(expert: dict[str, Any]) -> str:
    raw = str(expert.get("source_record_id") or "").strip()
    match = re.search(r"\d+", raw)
    return f"#{int(match.group())}" if match else raw


def _record_priority(record: QuotaRecord) -> tuple[int, str]:
    priority = 2 if record.quota_status == QUOTA_STATUS_COMPLETED else 1
    return priority, record.interview_time


def _compact_interview_date(value: Any) -> str:
    text = str(value or "").strip()
    match = re.search(r"\d{4}[-./](\d{1,2})[-./](\d{1,2})(?=\D|$)", text)
    if match:
        return f"{int(match.group(1)):02d}.{int(match.group(2)):02d}"
    return text[:24]


def build_interview_quota_records(
    experts: list[dict[str, Any]], *, now: datetime | None = None
) -> list[QuotaRecord]:
    records: list[QuotaRecord] = []
    for expert in experts:
        candidates: list[QuotaRecord] = []
        interview_dates: list[str] = []
        for interview in expert.get("interviews", []) if isinstance(expert.get("interviews"), list) else []:
            if not isinstance(interview, dict):
                continue
            quota_status = classify_quota_interview(interview, now=now)
            if quota_status not in {QUOTA_STATUS_COMPLETED, QUOTA_STATUS_SCHEDULED}:
                continue
            compact_date = _compact_interview_date(
                interview.get("occurred_at") or interview.get("display_time")
            )
            if compact_date:
                interview_dates.append(compact_date)
            candidates.append(
                QuotaRecord(
                    expert_id=str(expert.get("id") or ""),
                    expert_number=_record_number(expert),
                    name=str(expert.get("name") or "未命名专家").strip(),
                    company=str(expert.get("current_employer") or expert.get("main_company") or "").strip(),
                    title=str(expert.get("current_title") or "").strip(),
                    scale=str(expert.get("company_scale") or "未分类").strip() or "未分类",
                    industry=str(expert.get("industry") or "未分类").strip() or "未分类",
                    region=normalize_region_label(expert.get("region")) or "未分类",
                    quota_status=quota_status,
                    interview_id=str(interview.get("id") or ""),
                    interview_time=str(interview.get("display_time") or interview.get("occurred_at") or "").strip(),
                    interview_title=str(interview.get("title") or "专家访谈").strip(),
                    interviewer=str(interview.get("interviewer") or "").strip(),
                )
            )
        if candidates:
            records.append(
                replace(
                    max(candidates, key=_record_priority),
                    interview_dates=tuple(sorted(interview_dates)),
                )
            )

    def sort_key(record: QuotaRecord) -> tuple[Any, ...]:
        number_match = re.search(r"\d+", record.expert_number)
        number = int(number_match.group()) if number_match else 999999
        return (
            KNOWN_SCALE_ORDER.get(record.scale, 500),
            record.scale.casefold(),
            record.industry.casefold(),
            record.region.casefold(),
            number,
            record.name.casefold(),
        )

    return sorted(records, key=sort_key)


def build_interview_quota_view(
    experts: list[dict[str, Any]], *, now: datetime | None = None
) -> dict[str, Any]:
    records = build_interview_quota_records(experts, now=now)
    scales = sorted(
        {record.scale for record in records},
        key=lambda value: (KNOWN_SCALE_ORDER.get(value, 500), value.casefold()),
    )
    regions = sorted({record.region for record in records}, key=str.casefold)
    groups: list[dict[str, Any]] = []
    for scale in scales:
        scale_records = [record for record in records if record.scale == scale]
        industries = sorted({record.industry for record in scale_records}, key=str.casefold)
        rows: list[dict[str, Any]] = []
        for industry in industries:
            cells = []
            for region in regions:
                cell_records = [
                    record
                    for record in scale_records
                    if record.industry == industry and record.region == region
                ]
                cells.append(
                    {
                        "region": region,
                        "records": [
                            {
                                "expert_id": record.expert_id,
                                "company": record.company or "公司待补充",
                                "quota_status": record.quota_status,
                                "interview_dates": list(record.interview_dates),
                                "interview_count": len(record.interview_dates),
                            }
                            for record in cell_records
                        ],
                    }
                )
            rows.append({"industry": industry, "cells": cells})
        groups.append({"scale": scale, "regions": regions, "rows": rows})
    return {
        "groups": groups,
        "completed": sum(record.quota_status == QUOTA_STATUS_COMPLETED for record in records),
        "scheduled": sum(record.quota_status == QUOTA_STATUS_SCHEDULED for record in records),
        "total": len(records),
    }


def _xml_text(value: Any) -> str:
    text = str(value or "")
    text = "".join(character for character in text if character in "\t\n\r" or ord(character) >= 32)
    return escape(text)


def _column_name(index: int) -> str:
    result = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_ref(row: int, column: int) -> str:
    return f"{_column_name(column)}{row}"


def _inline_cell(row: int, column: int, value: Any, *, style: int = 0) -> str:
    reference = _cell_ref(row, column)
    return (
        f'<c r="{reference}" s="{style}" t="inlineStr"><is>'
        f'<t xml:space="preserve">{_xml_text(value)}</t></is></c>'
    )


def _rich_cell(row: int, column: int, records: list[QuotaRecord], *, style: int = 5) -> str:
    reference = _cell_ref(row, column)
    runs: list[str] = []
    for index, record in enumerate(records):
        if index:
            runs.append('<r><t xml:space="preserve">\n</t></r>')
        color = "FF16805D" if record.quota_status == QUOTA_STATUS_COMPLETED else "FF2F6FED"
        prefix = "●" if record.quota_status == QUOTA_STATUS_COMPLETED else "◆"
        number = f"{record.expert_number} " if record.expert_number else ""
        runs.append(
            '<r><rPr><b/><sz val="10"/><color rgb="'
            + color
            + '"/><rFont val="Aptos"/></rPr><t xml:space="preserve">'
            + _xml_text(f"{prefix} {number}{record.name}")
            + "</t></r>"
        )
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is>{"".join(runs)}</is></c>'


def _row_xml(row_number: int, cells: list[str], *, height: float | None = None) -> str:
    height_attr = f' ht="{height:.1f}" customHeight="1"' if height is not None else ""
    return f'<row r="{row_number}"{height_attr}>{"".join(cells)}</row>'


def _matrix_sheet_xml(records: list[QuotaRecord], generated_label: str) -> str:
    regions = sorted({record.region for record in records}, key=str.casefold) or ["未分类"]
    scales = sorted(
        {record.scale for record in records},
        key=lambda value: (KNOWN_SCALE_ORDER.get(value, 500), value.casefold()),
    ) or ["未分类"]
    last_column = max(4, len(regions) + 1)
    rows: list[str] = []
    merges: list[str] = []

    rows.append(_row_xml(1, [_inline_cell(1, 1, "访谈配额执行进度", style=1)], height=34))
    merges.append(f"A1:{_column_name(last_column)}1")
    completed_count = sum(record.quota_status == QUOTA_STATUS_COMPLETED for record in records)
    scheduled_count = sum(record.quota_status == QUOTA_STATUS_SCHEDULED for record in records)
    kpi_values = [
        f"已完成  {completed_count}",
        f"已排期待访  {scheduled_count}",
        f"合计  {len(records)}",
        f"更新  {generated_label}",
    ]
    rows.append(
        _row_xml(2, [_inline_cell(2, index + 1, value, style=11) for index, value in enumerate(kpi_values)], height=28)
    )
    rows.append(
        _row_xml(
            3,
            [
                _inline_cell(3, 1, "图例", style=4),
                _inline_cell(3, 2, "● 已完成访谈", style=6),
                _inline_cell(3, 3, "◆ 已排期待访", style=7),
            ],
            height=24,
        )
    )

    current_row = 5
    for scale in scales:
        scale_records = [record for record in records if record.scale == scale]
        industries = sorted({record.industry for record in scale_records}, key=str.casefold) or ["未分类"]
        rows.append(_row_xml(current_row, [_inline_cell(current_row, 1, scale, style=2)], height=28))
        merges.append(f"A{current_row}:{_column_name(last_column)}{current_row}")
        current_row += 1
        header_cells = [_inline_cell(current_row, 1, "行业 / 地区", style=3)]
        header_cells.extend(
            _inline_cell(current_row, column + 2, region, style=3)
            for column, region in enumerate(regions)
        )
        rows.append(_row_xml(current_row, header_cells, height=26))
        current_row += 1
        for industry in industries:
            cells = [_inline_cell(current_row, 1, industry, style=4)]
            max_lines = 1
            for column, region in enumerate(regions, start=2):
                cell_records = [
                    record
                    for record in scale_records
                    if record.industry == industry and record.region == region
                ]
                max_lines = max(max_lines, len(cell_records))
                cell_statuses = {record.quota_status for record in cell_records}
                cell_style = (
                    6
                    if cell_statuses == {QUOTA_STATUS_COMPLETED}
                    else 7
                    if cell_statuses == {QUOTA_STATUS_SCHEDULED}
                    else 5
                )
                cells.append(
                    _rich_cell(current_row, column, cell_records, style=cell_style)
                    if cell_records
                    else _inline_cell(current_row, column, "", style=5)
                )
            rows.append(_row_xml(current_row, cells, height=max(28, 19 * max_lines + 9)))
            current_row += 1
        current_row += 1

    columns = ['<col min="1" max="1" width="18" customWidth="1"/>']
    if last_column >= 2:
        columns.append(f'<col min="2" max="{last_column}" width="27" customWidth="1"/>')
    merge_xml = "".join(f'<mergeCell ref="{reference}"/>' for reference in merges)
    dimension = f"A1:{_column_name(last_column)}{max(3, current_row - 1)}"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="{dimension}"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane xSplit="1" ySplit="3" topLeftCell="B4" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="20"/>
  <cols>{''.join(columns)}</cols>
  <sheetData>{''.join(rows)}</sheetData>
  <mergeCells count="{len(merges)}">{merge_xml}</mergeCells>
  <pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''


def _detail_sheet_xml(records: list[QuotaRecord]) -> str:
    headers = [
        "序号",
        "专家序号",
        "专家姓名",
        "公司",
        "职位",
        "规模",
        "行业",
        "地区",
        "配额进度",
        "访谈时间",
        "访谈主题",
        "访谈人",
    ]
    rows = [_row_xml(1, [_inline_cell(1, index + 1, value, style=3) for index, value in enumerate(headers)], height=28)]
    for row_index, record in enumerate(records, start=2):
        style = 9 if record.quota_status == QUOTA_STATUS_COMPLETED else 10
        values = [
            row_index - 1,
            record.expert_number,
            record.name,
            record.company,
            record.title,
            record.scale,
            record.industry,
            record.region,
            QUOTA_STATUS_LABELS[record.quota_status],
            record.interview_time,
            record.interview_title,
            record.interviewer,
        ]
        rows.append(
            _row_xml(
                row_index,
                [
                    _inline_cell(row_index, column + 1, value, style=style if column == 8 else 8)
                    for column, value in enumerate(values)
                ],
                height=25,
            )
        )
    last_row = max(1, len(records) + 1)
    widths = [8, 11, 20, 27, 31, 12, 16, 16, 16, 24, 26, 15]
    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:L{last_row}"/>
  <sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <sheetFormatPr defaultRowHeight="20"/>
  <cols>{columns}</cols>
  <sheetData>{''.join(rows)}</sheetData>
  <autoFilter ref="A1:L{last_row}"/>
  <pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>
  <pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''


def _styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="8">
    <font><sz val="10"/><color rgb="FF17324D"/><name val="Aptos"/><family val="2"/></font>
    <font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/></font>
    <font><b/><sz val="12"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font>
    <font><b/><sz val="10"/><color rgb="FF17324D"/><name val="Aptos"/></font>
    <font><sz val="10"/><color rgb="FF17324D"/><name val="Aptos"/></font>
    <font><b/><sz val="10"/><color rgb="FF146C50"/><name val="Aptos"/></font>
    <font><b/><sz val="10"/><color rgb="FF245AB5"/><name val="Aptos"/></font>
    <font><sz val="9"/><color rgb="FF6C7D93"/><name val="Aptos"/></font>
  </fonts>
  <fills count="10">
    <fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF173E6B"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF536FAE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEAF1FA"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFBFCFE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE5F6EE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE8F1FF"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFF2F4F7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFF3E6"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border><left style="thin"><color rgb="FFD8E2EF"/></left><right style="thin"><color rgb="FFD8E2EF"/></right><top style="thin"><color rgb="FFD8E2EF"/></top><bottom style="thin"><color rgb="FFD8E2EF"/></bottom><diagonal/></border>
  </borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="12">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
    <xf numFmtId="0" fontId="2" fillId="3" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center"/></xf>
    <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="5" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="6" fillId="7" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="4" fillId="5" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="5" fillId="6" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="6" fillId="7" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
    <xf numFmtId="0" fontId="3" fillId="9" borderId="1" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''


def build_interview_quota_workbook(
    experts: list[dict[str, Any]], *, generated_at: datetime | None = None
) -> tuple[bytes, list[QuotaRecord]]:
    timestamp = generated_at or datetime.now()
    records = build_interview_quota_records(experts, now=timestamp)
    generated_label = timestamp.strftime("%Y-%m-%d %H:%M")
    created = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    package = BytesIO()
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        parts = {
            "[Content_Types].xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''',
            "_rels/.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''',
            "docProps/app.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>4242wei Expert Portfolio</Application><AppVersion>1.0</AppVersion></Properties>''',
            "docProps/core.xml": f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>访谈配额执行进度</dc:title><dc:creator>4242wei</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified></cp:coreProperties>''',
            "xl/workbook.xml": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="约访进度" sheetId="1" r:id="rId1"/><sheet name="记录明细" sheetId="2" r:id="rId2"/></sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>''',
            "xl/_rels/workbook.xml.rels": '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''',
            "xl/styles.xml": _styles_xml(),
            "xl/worksheets/sheet1.xml": _matrix_sheet_xml(records, generated_label),
            "xl/worksheets/sheet2.xml": _detail_sheet_xml(records),
        }
        for name, content in parts.items():
            archive.writestr(name, content.encode("utf-8"))
    return package.getvalue(), records
