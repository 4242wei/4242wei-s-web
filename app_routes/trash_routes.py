from __future__ import annotations

import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from flask import abort, flash, jsonify, redirect, render_template, request, url_for


def register_trash_routes(app, deps) -> None:
    load_stock_store = deps.load_stock_store
    normalize_stock_symbol = deps.normalize_stock_symbol
    normalize_tag_value = deps.normalize_tag_value
    split_search_terms = deps.split_search_terms
    build_trash_cards = deps.build_trash_cards
    build_trash_stats = deps.build_trash_stats
    tag_match = deps.tag_match
    text_contains_all_terms = deps.text_contains_all_terms
    collect_tag_counts = deps.collect_tag_counts
    TRASH_KIND_META = deps.TRASH_KIND_META
    build_stock_selector_options = deps.build_stock_selector_options
    build_navigation_context = deps.build_navigation_context
    get_trash_entry = deps.get_trash_entry
    ensure_stock_entry = deps.ensure_stock_entry
    ensure_unique_id = deps.ensure_unique_id
    touch_stock = deps.touch_stock
    stock_file_storage_symbol = deps.stock_file_storage_symbol
    stock_file_linked_symbols = deps.stock_file_linked_symbols
    touch_stock_symbols = deps.touch_stock_symbols
    touch_transcript_stocks = deps.touch_transcript_stocks
    REPORTS_DIR = deps.REPORTS_DIR
    SIGNAL_MONITOR_REPORTS_DIR = deps.SIGNAL_MONITOR_REPORTS_DIR
    save_stock_store = deps.save_stock_store
    expects_json_response = deps.expects_json_response
    permanently_delete_trash_entry = deps.permanently_delete_trash_entry
    safe_next_url = deps.safe_next_url

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
