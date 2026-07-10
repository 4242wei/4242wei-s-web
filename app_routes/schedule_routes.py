from __future__ import annotations

from flask import flash, jsonify, redirect, render_template, request, url_for


def register_schedule_routes(app, deps) -> None:
    load_stock_store = deps.load_stock_store
    normalize_schedule_view = deps.normalize_schedule_view
    is_visitor_mode = deps.is_visitor_mode
    build_schedule_page_context = deps.build_schedule_page_context
    build_stock_selector_options = deps.build_stock_selector_options
    today_date_iso = deps.today_date_iso
    build_navigation_context = deps.build_navigation_context
    safe_next_url = deps.safe_next_url
    normalize_schedule_item = deps.normalize_schedule_item
    now_iso = deps.now_iso
    save_stock_store = deps.save_stock_store
    get_schedule_item = deps.get_schedule_item
    SCHEDULE_STATUS_META = deps.SCHEDULE_STATUS_META
    append_to_trash = deps.append_to_trash
    create_trash_entry = deps.create_trash_entry
    STOCK_STORE_LOCK = deps.STOCK_STORE_LOCK
    plain_text_to_html = deps.plain_text_to_html
    apply_reader_state_action = deps.apply_reader_state_action
    build_reader_state_payload = deps.build_reader_state_payload

    @app.get("/schedule")
    def schedule_page() -> str:
        store = load_stock_store()
        current_view = normalize_schedule_view(request.args.get("view"))
        if is_visitor_mode():
            current_view = "board"
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

    @app.post("/schedule/items/<item_id>/reader-state")
    def persist_schedule_reader_state(item_id: str):
        payload = request.get_json(silent=True) or {}

        with STOCK_STORE_LOCK:
            store = load_stock_store()
            item = get_schedule_item(store, item_id)
            reader_text = str(item.get("note") or "").strip() or str(item.get("title") or "").strip()
            reader_html = plain_text_to_html(reader_text)
            try:
                apply_reader_state_action(
                    item,
                    payload,
                    content_text=reader_text,
                    content_html=reader_html,
                )
            except ValueError as exc:
                return jsonify({"ok": False, "message": str(exc)}), 400

            save_stock_store(store)

            return jsonify(
                {
                    "ok": True,
                    "state": build_reader_state_payload(
                        item,
                        save_url=url_for("persist_schedule_reader_state", item_id=item_id),
                        kind="schedule",
                        item_id=item_id,
                        content_text=reader_text,
                        content_html=reader_html,
                    ),
                }
            )
