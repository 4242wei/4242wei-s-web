from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app as app_module


def build_agent_tool_stock_store() -> dict:
    return {
        "groups": [],
        "favorites": [],
        "workspace_settings": {"ai_direct_access_enabled": True},
        "stocks": {
            "NET": {
                "display_name": "Cloudflare",
                "notes": [
                    {
                        "id": "note-net-1",
                        "title": "Pricing Power Notes",
                        "content_text": (
                            "Pricing power improved after enterprise attach expanded. "
                            "Security bundle adoption kept edge retention elevated."
                        ),
                        "content_html": (
                            "<p>Pricing power improved after enterprise attach expanded. "
                            "Security bundle adoption kept edge retention elevated.</p>"
                        ),
                        "created_at": "2026-04-05T10:00:00",
                        "record_date": "2026-04-05",
                        "tags": ["pricing", "security", "edge"],
                    }
                ],
                "files": [],
                "earnings_calls": [],
            },
            "FSLY": {
                "display_name": "Fastly",
                "notes": [
                    {
                        "id": "note-fsly-1",
                        "title": "Edge Security Reset",
                        "content_text": (
                            "Edge delivery stabilized and security attach improved after churn reset. "
                            "Management highlighted better enterprise quality."
                        ),
                        "content_html": (
                            "<p>Edge delivery stabilized and security attach improved after churn reset. "
                            "Management highlighted better enterprise quality.</p>"
                        ),
                        "created_at": "2026-04-04T09:00:00",
                        "record_date": "2026-04-04",
                        "tags": ["security", "edge"],
                    }
                ],
                "files": [],
                "earnings_calls": [],
            },
        },
        "experts": [],
        "schedule_items": [],
        "trash": [],
        "transcripts": [],
    }


class AgentToolLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_paths = {
            "STOCK_STORE_PATH": app_module.STOCK_STORE_PATH,
            "REPORTS_DIR": app_module.REPORTS_DIR,
            "SIGNAL_MONITOR_REPORTS_DIR": app_module.SIGNAL_MONITOR_REPORTS_DIR,
            "AI_NATIVE_DATA_DIR": app_module.AI_NATIVE_DATA_DIR,
            "AI_NATIVE_DOCS_DIR": app_module.AI_NATIVE_DOCS_DIR,
            "AI_NATIVE_INDEX_DB_PATH": app_module.AI_NATIVE_INDEX_DB_PATH,
            "AI_AGENT_OPS_PATH": app_module.AI_AGENT_OPS_PATH,
            "AI_CHAT_STORE_PATH": app_module.AI_CHAT_STORE_PATH,
            "STABLECOIN_MONITOR_CACHE_PATH": app_module.STABLECOIN_MONITOR_CACHE_PATH,
            "STABLECOIN_MONITOR_RUNTIME_PATH": app_module.STABLECOIN_MONITOR_RUNTIME_PATH,
            "STOCK_SETUPS_DIR": app_module.STOCK_SETUPS_DIR,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.SIGNAL_MONITOR_REPORTS_DIR = temp_root / "signal_reports"
        app_module.AI_NATIVE_DATA_DIR = temp_root / "ai_native"
        app_module.AI_NATIVE_DOCS_DIR = app_module.AI_NATIVE_DATA_DIR / "documents"
        app_module.AI_NATIVE_INDEX_DB_PATH = app_module.AI_NATIVE_DATA_DIR / "search-index.sqlite3"
        app_module.AI_AGENT_OPS_PATH = app_module.AI_NATIVE_DATA_DIR / "agent_ops.json"
        app_module.AI_CHAT_STORE_PATH = temp_root / "ai_chats.json"
        app_module.STABLECOIN_MONITOR_CACHE_PATH = temp_root / "stablecoins.json"
        app_module.STABLECOIN_MONITOR_RUNTIME_PATH = temp_root / "stablecoins_runtime.json"
        app_module.STOCK_SETUPS_DIR = temp_root / "stock_setups"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.AI_NATIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        app_module.STOCK_SETUPS_DIR.mkdir(parents=True, exist_ok=True)

        app_module.save_stock_store(build_agent_tool_stock_store())

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.anon_client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        for key, value in self.original_paths.items():
            setattr(app_module, key, value)
        app_module.STOCK_STORE_CACHE = self.original_stock_cache
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_timeline_analysis_returns_recent_documents_and_buckets(self) -> None:
        response = self.client.get("/api/analysis/timeline.json?symbols=NET,FSLY&limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["counts"]["returned_documents"], len(payload["timeline"]))
        self.assertGreaterEqual(len(payload["timeline"]), 2)
        self.assertTrue(payload["date_buckets"])
        self.assertEqual(
            [float(item["sort_value"]) for item in payload["timeline"]],
            sorted([float(item["sort_value"]) for item in payload["timeline"]], reverse=True),
        )
        self.assertEqual(payload["symbols_covered"][0]["symbol"], "NET")

    def test_compare_analysis_and_agent_wrapper_return_symbol_deltas(self) -> None:
        response = self.client.get("/api/analysis/compare.json?symbols=NET,FSLY&query=security&per_symbol_limit=2")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["counts"]["symbols"], 2)
        self.assertEqual(len(payload["symbols"]), 2)
        self.assertIn("note", payload["shared_context"]["shared_kinds"])
        self.assertIn("security", payload["shared_context"]["shared_tags"])
        matched_row = next(item for item in payload["comparison_rows"] if item["metric"] == "matched_documents")
        self.assertGreaterEqual(int(matched_row["values"]["NET"]), 1)
        self.assertGreaterEqual(int(matched_row["values"]["FSLY"]), 1)

        tool_response = self.client.get("/api/agent/tools/compare.json?symbols=NET,FSLY&q=security")
        self.assertEqual(tool_response.status_code, 200)
        tool_payload = tool_response.get_json()
        self.assertTrue(tool_payload["ok"])
        self.assertEqual(tool_payload["tool"], "compare")
        self.assertEqual(tool_payload["result"]["counts"]["symbols"], 2)

        timeline_alias_response = self.client.get("/api/analysis/timeline/NET,FSLY.json?limit=5")
        self.assertEqual(timeline_alias_response.status_code, 200)
        timeline_alias_payload = timeline_alias_response.get_json()
        self.assertEqual(timeline_alias_payload["counts"]["returned_documents"], len(timeline_alias_payload["timeline"]))

        compare_alias_response = self.client.get("/api/analysis/compare/NET,FSLY.json?q=security&per_symbol_limit=2")
        self.assertEqual(compare_alias_response.status_code, 200)
        compare_alias_payload = compare_alias_response.get_json()
        self.assertEqual(compare_alias_payload["counts"]["symbols"], 2)

    def test_agent_bootstrap_and_ai_page_expose_tool_entrypoints(self) -> None:
        bootstrap_response = self.client.get("/api/agent/bootstrap.json")
        self.assertEqual(bootstrap_response.status_code, 200)
        bootstrap_payload = bootstrap_response.get_json()

        tool_names = [item["name"] for item in bootstrap_payload["tools"]]
        self.assertIn("timeline", tool_names)
        self.assertIn("compare", tool_names)
        self.assertIn("artifact_store", tool_names)
        self.assertIn("job_queue", tool_names)
        self.assertIn("clipboard_item_preview", tool_names)
        self.assertIn("stock_note_preview", tool_names)
        self.assertIn("search_tool_url", bootstrap_payload["entrypoints"])
        self.assertIn("artifact_tool_url", bootstrap_payload["entrypoints"])
        self.assertIn("job_tool_url", bootstrap_payload["entrypoints"])
        self.assertIn("artifact_bootstrap_url", bootstrap_payload["entrypoints"])
        self.assertIn("write_operations_url", bootstrap_payload["entrypoints"])

        search_response = self.client.get("/api/agent/tools/search.json?q=pricing&symbols=NET")
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.get_json()
        self.assertTrue(search_payload["ok"])
        self.assertEqual(search_payload["tool"], "search")
        self.assertTrue(search_payload["result"]["documents"])

        artifact_tool_response = self.client.get("/api/agent/tools/artifacts.json?symbols=NET")
        self.assertEqual(artifact_tool_response.status_code, 200)
        artifact_tool_payload = artifact_tool_response.get_json()
        self.assertTrue(artifact_tool_payload["ok"])
        self.assertEqual(artifact_tool_payload["tool"], "artifacts")

        page_response = self.client.get("/ai")
        self.assertEqual(page_response.status_code, 200)
        html = page_response.data.decode("utf-8")
        self.assertIn("/api/agent/bootstrap.json", html)
        self.assertIn("/api/analysis/timeline.json", html)
        self.assertIn("/api/analysis/compare.json", html)
        self.assertIn("/api/artifacts/bootstrap.json", html)
        self.assertIn("/api/jobs/list.json", html)
        self.assertIn("/api/agent/writes/operations.json", html)

    def test_anonymous_ai_direct_access_allows_read_only_get_routes_and_returns_json_for_blocked_api_paths(self) -> None:
        allowed_urls = [
            "/api/ai/bootstrap.json",
            "/api/analysis/timeline.json?symbols=NET,FSLY&limit=5",
            "/api/analysis/compare.json?symbols=NET,FSLY&query=security&per_symbol_limit=2",
            "/api/ai/brief/NET.json",
            "/api/ai/search/pricing.json?symbols=NET",
            "/api/ai/context-pack/pricing/symbols/NET.json?document_limit=1&chunk_limit=1",
            "/api/analysis/timeline/NET,FSLY.json?limit=5",
            "/api/analysis/compare/NET,FSLY.json?q=security&per_symbol_limit=2",
            "/api/agent/bootstrap.json",
            "/api/agent/tools/search.json?q=pricing&symbols=NET",
            "/api/agent/tools/jobs.json?statuses=completed",
            "/api/artifacts/bootstrap.json",
            "/api/jobs/list.json?statuses=completed",
        ]
        for url in allowed_urls:
            with self.subTest(url=url):
                response = self.anon_client.get(url)
                self.assertEqual(response.status_code, 200)

        blocked_get = self.anon_client.get("/api/agent/writes/operations.json")
        self.assertEqual(blocked_get.status_code, 401)
        blocked_get_payload = blocked_get.get_json()
        self.assertFalse(blocked_get_payload["ok"])
        self.assertIn("/access?next=", blocked_get_payload["access_url"])

        blocked_post = self.anon_client.post(
            "/api/jobs/artifacts/timeline.json",
            json={"symbols": ["NET"], "query": "pricing"},
        )
        self.assertEqual(blocked_post.status_code, 401)
        blocked_post_payload = blocked_post.get_json()
        self.assertFalse(blocked_post_payload["ok"])
        self.assertIn("/access?next=", blocked_post_payload["access_url"])


if __name__ == "__main__":
    unittest.main()
