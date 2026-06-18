from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app as app_module


def build_agent_write_stock_store() -> dict:
    return {
        "groups": [],
        "favorites": ["NET"],
        "stocks": {
            "NET": {
                "display_name": "Cloudflare",
                "notes": [
                    {
                        "id": "note-net-1",
                        "title": "Existing Note",
                        "content_text": "Existing thesis text before preview.",
                        "content_html": "<p>Existing thesis text before preview.</p>",
                        "created_at": "2026-04-05T10:00:00",
                        "record_date": "2026-04-05",
                        "tags": ["existing"],
                    }
                ],
                "files": [],
                "earnings_calls": [],
            }
        },
        "experts": [],
        "schedule_items": [],
        "trash": [],
        "transcripts": [],
    }


class AgentWriteToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_paths = {
            "STOCK_STORE_PATH": app_module.STOCK_STORE_PATH,
            "AI_NATIVE_DATA_DIR": app_module.AI_NATIVE_DATA_DIR,
            "AI_NATIVE_DOCS_DIR": app_module.AI_NATIVE_DOCS_DIR,
            "AI_NATIVE_INDEX_DB_PATH": app_module.AI_NATIVE_INDEX_DB_PATH,
            "AI_AGENT_OPS_PATH": app_module.AI_AGENT_OPS_PATH,
            "CLIPBOARD_STORE_PATH": app_module.CLIPBOARD_STORE_PATH,
            "CLIPBOARD_UPLOADS_DIR": app_module.CLIPBOARD_UPLOADS_DIR,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.AI_NATIVE_DATA_DIR = temp_root / "ai_native"
        app_module.AI_NATIVE_DOCS_DIR = app_module.AI_NATIVE_DATA_DIR / "documents"
        app_module.AI_NATIVE_INDEX_DB_PATH = app_module.AI_NATIVE_DATA_DIR / "search-index.sqlite3"
        app_module.AI_AGENT_OPS_PATH = app_module.AI_NATIVE_DATA_DIR / "agent_ops.json"
        app_module.CLIPBOARD_STORE_PATH = temp_root / "clipboard.json"
        app_module.CLIPBOARD_UPLOADS_DIR = temp_root / "clipboard_uploads"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}

        app_module.AI_NATIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        app_module.CLIPBOARD_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.save_stock_store(build_agent_write_stock_store())

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        for key, value in self.original_paths.items():
            setattr(app_module, key, value)
        app_module.STOCK_STORE_CACHE = self.original_stock_cache
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_clipboard_preview_commit_roundtrip(self) -> None:
        preview_response = self.client.post(
            "/api/agent/writes/clipboard/preview.json",
            json={"text": "Agent draft for later reuse."},
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = preview_response.get_json()
        operation_id = preview_payload["operation"]["id"]

        operations_response = self.client.get("/api/agent/writes/operations.json")
        self.assertEqual(operations_response.status_code, 200)
        operations_payload = operations_response.get_json()
        self.assertEqual(operations_payload["counts"]["pending_previews"], 1)

        commit_response = self.client.post(f"/api/agent/writes/operations/{operation_id}/commit.json")
        self.assertEqual(commit_response.status_code, 200)
        commit_payload = commit_response.get_json()
        self.assertEqual(commit_payload["operation"]["status"], "committed")
        self.assertEqual(commit_payload["result"]["target_kind"], "clipboard_item")

        clipboard_store = app_module.load_clipboard_store()
        self.assertEqual(len(clipboard_store["items"]), 1)
        self.assertEqual(clipboard_store["items"][0]["text"], "Agent draft for later reuse.")

    def test_stock_note_preview_commit_creates_note(self) -> None:
        preview_response = self.client.post(
            "/api/agent/writes/stock-note/preview.json",
            json={
                "symbol": "NET",
                "title": "AI Draft Note",
                "text": "Fresh comparison note for the workspace.",
                "tags": ["draft", "compare"],
                "record_date": "2026-04-06",
            },
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = preview_response.get_json()
        operation = preview_payload["operation"]
        self.assertEqual(operation["target_kind"], "stock_note")
        self.assertEqual(operation["operation"], "create")

        commit_response = self.client.post(f"/api/agent/writes/operations/{operation['id']}/commit.json")
        self.assertEqual(commit_response.status_code, 200)
        commit_payload = commit_response.get_json()
        self.assertEqual(commit_payload["result"]["symbol"], "NET")
        self.assertEqual(commit_payload["result"]["note"]["title"], "AI Draft Note")

        stock_store = app_module.load_stock_store()
        notes = stock_store["stocks"]["NET"]["notes"]
        self.assertEqual(len(notes), 2)
        self.assertTrue(any(note["title"] == "AI Draft Note" for note in notes))

    def test_stock_note_commit_detects_conflict_after_preview(self) -> None:
        preview_response = self.client.post(
            "/api/agent/writes/stock-note/preview.json",
            json={
                "symbol": "NET",
                "note_id": "note-net-1",
                "title": "Updated Existing Note",
                "text": "Preview wanted to replace this note.",
                "tags": ["updated"],
            },
        )
        self.assertEqual(preview_response.status_code, 200)
        operation_id = preview_response.get_json()["operation"]["id"]

        stock_store = app_module.load_stock_store()
        stock_store["stocks"]["NET"]["notes"][0]["content_text"] = "Somebody else changed the note first."
        stock_store["stocks"]["NET"]["notes"][0]["content_html"] = "<p>Somebody else changed the note first.</p>"
        stock_store["stocks"]["NET"]["notes"][0]["updated_at"] = "2026-04-06T09:00:00"
        app_module.save_stock_store(stock_store)

        commit_response = self.client.post(f"/api/agent/writes/operations/{operation_id}/commit.json")
        self.assertEqual(commit_response.status_code, 409)
        commit_payload = commit_response.get_json()
        self.assertFalse(commit_payload["ok"])
        self.assertIn("changed after preview", commit_payload["error"])

        refreshed_store = app_module.load_stock_store()
        self.assertEqual(
            refreshed_store["stocks"]["NET"]["notes"][0]["content_text"],
            "Somebody else changed the note first.",
        )


if __name__ == "__main__":
    unittest.main()
