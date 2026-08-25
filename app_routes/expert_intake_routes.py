from __future__ import annotations

from pathlib import Path

from flask import jsonify, request

from expert_intake import ExpertIntakeError, parse_expert_source, provider_catalog


def register_expert_intake_routes(app, deps) -> None:
    get_config_path = deps.get_expert_intake_provider_config_path

    @app.get("/expert-intake/providers")
    def expert_intake_providers():
        try:
            providers = provider_catalog(Path(get_config_path()))
        except ExpertIntakeError as exc:
            return jsonify({"ok": False, "message": str(exc), "providers": []}), 503
        return jsonify({"ok": True, "providers": providers})

    @app.post("/expert-intake/parse")
    def expert_intake_parse():
        payload = request.get_json(silent=True) or {}
        try:
            result = parse_expert_source(
                Path(get_config_path()),
                provider_id=str(payload.get("provider_id") or "").strip(),
                source_text=str(payload.get("source_text") or ""),
                thinking_mode="enabled" if payload.get("thinking_enabled") is True else "disabled",
                reasoning_effort=str(payload.get("reasoning_effort") or "").strip(),
            )
        except ExpertIntakeError as exc:
            return jsonify({"ok": False, "message": str(exc), "experts": []}), 400
        return jsonify({"ok": True, **result})
