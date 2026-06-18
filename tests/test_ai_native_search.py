from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import app as app_module


def build_sample_stock_store() -> dict:
    return {
        "groups": [],
        "favorites": [],
        "stocks": {
            "NET": {
                "display_name": "Cloudflare",
                "notes": [
                    {
                        "id": "note-net-1",
                        "title": "Pricing Power Notes",
                        "content_text": (
                            "Pricing power improved after enterprise attach expanded. "
                            "Security bundle adoption kept net retention elevated."
                        ),
                        "content_html": "<p>Pricing power improved after enterprise attach expanded. Security bundle adoption kept net retention elevated.</p>",
                        "created_at": "2026-04-05T10:00:00",
                        "record_date": "2026-04-05",
                        "tags": ["pricing", "security"],
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


class AINativeSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_paths = {
            "STOCK_STORE_PATH": app_module.STOCK_STORE_PATH,
            "REPORTS_DIR": app_module.REPORTS_DIR,
            "SIGNAL_MONITOR_REPORTS_DIR": app_module.SIGNAL_MONITOR_REPORTS_DIR,
            "STOCK_UPLOADS_DIR": app_module.STOCK_UPLOADS_DIR,
            "AI_NATIVE_DATA_DIR": app_module.AI_NATIVE_DATA_DIR,
            "AI_NATIVE_DOCS_DIR": app_module.AI_NATIVE_DOCS_DIR,
            "AI_NATIVE_INDEX_DB_PATH": app_module.AI_NATIVE_INDEX_DB_PATH,
            "STABLECOIN_MONITOR_CACHE_PATH": app_module.STABLECOIN_MONITOR_CACHE_PATH,
            "STABLECOIN_MONITOR_RUNTIME_PATH": app_module.STABLECOIN_MONITOR_RUNTIME_PATH,
            "STOCK_SETUPS_DIR": app_module.STOCK_SETUPS_DIR,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.SIGNAL_MONITOR_REPORTS_DIR = temp_root / "signal_reports"
        app_module.STOCK_UPLOADS_DIR = temp_root / "uploads" / "stocks"
        app_module.AI_NATIVE_DATA_DIR = temp_root / "ai_native"
        app_module.AI_NATIVE_DOCS_DIR = app_module.AI_NATIVE_DATA_DIR / "documents"
        app_module.AI_NATIVE_INDEX_DB_PATH = app_module.AI_NATIVE_DATA_DIR / "search-index.sqlite3"
        app_module.STABLECOIN_MONITOR_CACHE_PATH = temp_root / "stablecoins.json"
        app_module.STABLECOIN_MONITOR_RUNTIME_PATH = temp_root / "stablecoins_runtime.json"
        app_module.STOCK_SETUPS_DIR = temp_root / "stock_setups"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.STOCK_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.AI_NATIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        app_module.STOCK_SETUPS_DIR.mkdir(parents=True, exist_ok=True)

        app_module.save_stock_store(build_sample_stock_store())

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

    def test_search_endpoint_builds_sqlite_sidecar_and_returns_matches(self) -> None:
        response = self.client.get("/api/ai/search.json?q=pricing%20power&symbols=NET&limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["query"], "pricing power")
        self.assertGreaterEqual(payload["counts"]["matched_documents"], 1)
        self.assertTrue(payload["documents"])
        self.assertEqual(payload["documents"][0]["kind"], "note")
        self.assertEqual(payload["documents"][0]["title"], "Pricing Power Notes")
        self.assertIn("Pricing power improved", payload["documents"][0]["match_excerpt"])
        self.assertTrue(app_module.AI_NATIVE_INDEX_DB_PATH.exists())

        connection = sqlite3.connect(app_module.AI_NATIVE_INDEX_DB_PATH)
        try:
            row = connection.execute("SELECT COUNT(*) FROM ai_native_documents").fetchone()
        finally:
            connection.close()
        self.assertGreaterEqual(int(row[0] or 0), 1)

    def test_context_pack_returns_ranked_chunks_for_selected_documents(self) -> None:
        response = self.client.get(
            "/api/ai/context-pack.json?query=pricing%20power&symbols=NET&document_limit=2&chunk_limit=3"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertGreaterEqual(payload["counts"]["selected_documents"], 1)
        self.assertGreaterEqual(payload["counts"]["selected_chunks"], 1)
        self.assertTrue(payload["documents"][0]["selected_chunk_count"] >= 1)
        self.assertTrue(
            any("Pricing power improved" in item["text"] for item in payload["chunks"]),
        )
        self.assertIn("/api/ai/json/note/", payload["chunks"][0]["json_url"])
        self.assertIn("# AI Context Pack", payload["pack_markdown"])

        connection = sqlite3.connect(app_module.AI_NATIVE_INDEX_DB_PATH)
        try:
            row = connection.execute("SELECT COUNT(*) FROM ai_native_document_chunks").fetchone()
        finally:
            connection.close()
        self.assertGreaterEqual(int(row[0] or 0), 1)

    def test_search_and_context_pack_can_discover_supported_file_text_via_local_cache(self) -> None:
        store = build_sample_stock_store()
        file_id = "file-net-1"
        stored_name = "20260411-120000-search-discovery.txt"
        file_body = (
            "Quantum lattice routing notes for edge caching.\n"
            "The relay mesh keeps inference traffic close to the user."
        )
        stock_dir = app_module.stock_upload_dir("NET")
        stock_dir.mkdir(parents=True, exist_ok=True)
        (stock_dir / stored_name).write_text(file_body, encoding="utf-8")
        store["stocks"]["NET"]["files"].append(
            {
                "id": file_id,
                "stored_name": stored_name,
                "original_name": "search-discovery.txt",
                "description": "Unlinked file for AI-native discovery",
                "uploaded_at": "2026-04-11T12:00:00",
                "record_date": "2026-04-11",
                "linked_note_id": "",
                "linked_note_title": "",
                "extract_text": False,
                "tags": ["research"],
                "storage_symbol": "NET",
                "linked_symbols": ["NET"],
            }
        )
        app_module.save_stock_store(store)

        search_response = self.client.get("/api/ai/search.json?q=quantum%20lattice&symbols=NET&kinds=file&limit=5")
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.get_json()

        self.assertGreaterEqual(search_payload["counts"]["matched_documents"], 1)
        self.assertEqual(search_payload["documents"][0]["kind"], "file")
        self.assertEqual(search_payload["documents"][0]["doc_id"], "NET--file-net-1")
        self.assertIn("Quantum lattice routing notes", search_payload["documents"][0]["match_excerpt"])

        cache_dir = app_module.AI_NATIVE_DATA_DIR / "file-text-cache"
        cache_files = list(cache_dir.glob("*.json"))
        self.assertEqual(len(cache_files), 1)
        cache_payload = app_module.load_json(cache_files[0])
        self.assertEqual(cache_payload["status"], "ok")
        self.assertIn("Quantum lattice routing notes", cache_payload["text"])

        context_response = self.client.get(
            "/api/ai/context-pack.json?query=quantum%20lattice&symbols=NET&kinds=file&document_limit=2&chunk_limit=3"
        )
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.get_json()

        self.assertGreaterEqual(context_payload["counts"]["selected_documents"], 1)
        self.assertTrue(any(item["kind"] == "file" for item in context_payload["documents"]))
        self.assertTrue(any("Quantum lattice routing notes" in item["text"] for item in context_payload["chunks"]))

        file_response = self.client.get("/api/ai/json/file/NET--file-net-1")
        self.assertEqual(file_response.status_code, 200)
        file_payload = file_response.get_json()
        self.assertEqual(file_payload["document"]["kind"], "file")
        self.assertEqual(file_payload["document"]["extra"]["download_url"], "/stocks/NET/files/file-net-1")
        self.assertEqual(file_payload["document"]["extra"]["inline_url"], "/stocks/NET/files/file-net-1/inline")
        self.assertEqual(file_payload["document"]["extra"]["preview_url"], "/stocks/NET/files/file-net-1/preview")
        self.assertEqual(
            file_payload["document"]["extra"]["preview_fragment_url"],
            "/stocks/NET/files/file-net-1/preview-fragment",
        )
        self.assertIn("Quantum lattice routing notes", file_payload["markdown"])

    def test_path_aliases_return_same_core_ai_native_payloads_without_query_strings(self) -> None:
        search_response = self.client.get("/api/ai/search/pricing%20power.json?symbols=NET&limit=5")
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.get_json()
        self.assertEqual(search_payload["query"], "pricing power")
        self.assertGreaterEqual(search_payload["counts"]["matched_documents"], 1)

        context_response = self.client.get(
            "/api/ai/context-pack/pricing%20power/symbols/NET.json?document_limit=2&chunk_limit=3"
        )
        self.assertEqual(context_response.status_code, 200)
        context_payload = context_response.get_json()
        self.assertGreaterEqual(context_payload["counts"]["selected_documents"], 1)
        self.assertGreaterEqual(context_payload["counts"]["selected_chunks"], 1)

        brief_response = self.client.get("/api/ai/brief/NET.json")
        self.assertEqual(brief_response.status_code, 200)
        brief_payload = brief_response.get_json()
        self.assertEqual(brief_payload["symbol"], "NET")

        compact_stock_response = self.client.get("/api/ai/stock/NET.json")
        self.assertEqual(compact_stock_response.status_code, 200)
        compact_stock_payload = compact_stock_response.get_json()
        self.assertTrue(compact_stock_payload["ok"])
        self.assertEqual(compact_stock_payload["symbol"], "NET")
        self.assertTrue(compact_stock_payload["latest_documents"])

        compact_stock_markdown_response = self.client.get("/api/ai/stock/NET.md")
        self.assertEqual(compact_stock_markdown_response.status_code, 200)
        compact_stock_markdown = compact_stock_markdown_response.data.decode("utf-8")
        self.assertIn("# AI Stock Compact", compact_stock_markdown)
        self.assertIn("symbol: NET", compact_stock_markdown)

        experts_response = self.client.get("/api/ai/experts/NET.json")
        self.assertEqual(experts_response.status_code, 200)
        experts_payload = experts_response.get_json()
        self.assertEqual(experts_payload["filters"]["symbol"], "NET")

        latest_note_response = self.client.get("/api/ai/latest/NET/note.json")
        self.assertEqual(latest_note_response.status_code, 200)
        latest_note_payload = latest_note_response.get_json()
        self.assertTrue(latest_note_payload["ok"])
        self.assertEqual(latest_note_payload["selected_symbol"], "NET")
        self.assertEqual(latest_note_payload["selected_kind"], "note")
        self.assertEqual(latest_note_payload["document"]["kind"], "note")
        self.assertIn("Pricing power improved", latest_note_payload["markdown"])

        latest_note_markdown_response = self.client.get("/api/ai/latest/NET/note.md")
        self.assertEqual(latest_note_markdown_response.status_code, 200)
        latest_note_markdown = latest_note_markdown_response.data.decode("utf-8")
        self.assertIn("Pricing Power Notes", latest_note_markdown)

    def test_bootstrap_and_readme_expose_search_and_context_pack_entrypoints(self) -> None:
        bootstrap_response = self.client.get("/api/ai/bootstrap.json")
        self.assertEqual(bootstrap_response.status_code, 200)
        bootstrap_payload = bootstrap_response.get_json()
        self.assertIn("search_url", bootstrap_payload["entrypoints"])
        self.assertIn("context_pack_url", bootstrap_payload["entrypoints"])
        self.assertIn("search_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("search_path_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("context_pack_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("context_pack_path_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("brief_path_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("latest_document_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("latest_document_markdown_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("stock_compact_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("stock_compact_markdown_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("experts_path_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("timeline_analysis_path_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("compare_analysis_path_url_template", bootstrap_payload["entrypoints"])
        self.assertIn("readme_json_url", bootstrap_payload["entrypoints"])

        readme_response = self.client.get("/api/ai/readme.md")
        self.assertEqual(readme_response.status_code, 200)
        readme_text = readme_response.data.decode("utf-8")
        self.assertIn("/api/ai/search.json", readme_text)
        self.assertIn("/api/ai/context-pack.json", readme_text)
        self.assertIn("/api/ai/brief/<SYMBOL>.json", readme_text)
        self.assertIn("/api/ai/latest/<SYMBOL>/<KIND>.json", readme_text)
        self.assertIn("/api/ai/stock/<SYMBOL>.json", readme_text)
        self.assertIn("/api/ai/search/<URL_ENCODED_QUERY>.json", readme_text)

        readme_json_response = self.client.get("/api/ai/readme.json")
        self.assertEqual(readme_json_response.status_code, 200)
        readme_payload = readme_json_response.get_json()
        self.assertEqual(readme_payload["content_type"], "text/markdown; charset=utf-8")
        self.assertIn("/api/ai/search.json", readme_payload["content"])
        self.assertIn("/api/ai/context-pack.json", readme_payload["content"])
        self.assertIn("/api/ai/brief/<SYMBOL>.json", readme_payload["content"])
        self.assertIn("/api/ai/latest/<SYMBOL>/<KIND>.json", readme_payload["content"])
        self.assertIn("/api/ai/stock/<SYMBOL>.json", readme_payload["content"])
        self.assertEqual(readme_payload["readme_markdown_url"], "/api/ai/readme.md")


if __name__ == "__main__":
    unittest.main()
