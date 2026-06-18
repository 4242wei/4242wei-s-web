from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app as app_module


def build_minimal_stock_store() -> dict:
    return {
        "groups": [],
        "favorites": [],
        "stocks": {},
        "experts": [],
        "schedule_items": [],
        "trash": [],
        "transcripts": [],
    }


def build_sample_cdn_cache() -> dict:
    return {
        "updated_at": "2026-04-07T10:00:00",
        "source": {
            "name": "Local HTTP + DNS Probe",
            "url": "",
            "endpoint": "requests.get(url) + homepage asset host scan + nslookup(host)",
        },
        "notes": "sample cache",
        "summary": {
            "tracked_count": 2,
            "reachable_count": 2,
            "detected_count": 2,
            "provider_count": 2,
            "multi_provider_count": 1,
            "changed_count": 1,
        },
        "tracked_sites": [
            {
                "id": "openai-home",
                "label": "OpenAI",
                "category": "AI",
                "rank": 1,
                "rank_label": "#1",
                "bucket": "Rank 1-50",
                "url": "https://www.openai.com/",
                "requested_host": "www.openai.com",
                "final_url": "https://openai.com/",
                "final_host": "openai.com",
                "status_code": 403,
                "status_label": "HTTP 403",
                "is_reachable": True,
                "provider": "Cloudflare",
                "provider_confidence": "high",
                "provider_evidence": ["Header server: cloudflare"],
                "observed_providers": ["Cloudflare"],
                "is_multi_provider": False,
                "asset_hosts": [],
                "error": "",
            },
            {
                "id": "fastly",
                "label": "Fastly",
                "category": "Infrastructure",
                "rank": 2,
                "rank_label": "#2",
                "bucket": "Rank 1-50",
                "url": "https://www.fastly.com/",
                "requested_host": "www.fastly.com",
                "final_url": "https://www.fastly.com/",
                "final_host": "www.fastly.com",
                "status_code": 200,
                "status_label": "HTTP 200",
                "is_reachable": True,
                "provider": "Fastly",
                "provider_confidence": "high",
                "provider_evidence": ["Header x-served-by: cache-sjc10029-SJC"],
                "observed_providers": ["Fastly", "Cloudflare"],
                "is_multi_provider": True,
                "asset_hosts": [
                    {
                        "host": "www.fastly.com",
                        "provider": "Fastly",
                        "provider_color": "#ef6b57",
                        "evidence": ["DNS alias: prod.www-fastly-com.map.fastly.net"],
                    }
                ],
                "error": "",
            },
        ],
        "provider_rows": [
            {
                "provider": "Cloudflare",
                "count": 1,
                "share_pct": 50.0,
                "share_label": "50.0%",
                "color": "#4f8df7",
                "site_labels": ["OpenAI"],
            },
            {
                "provider": "Fastly",
                "count": 1,
                "share_pct": 50.0,
                "share_label": "50.0%",
                "color": "#ef6b57",
                "site_labels": ["Fastly"],
            },
        ],
        "category_rows": [
            {
                "category": "AI",
                "tracked_count": 1,
                "reachable_count": 1,
                "multi_provider_count": 0,
                "top_providers": [
                    {"provider": "Cloudflare", "count": 1, "share_label": "100%", "color": "#4f8df7"}
                ],
            },
            {
                "category": "Infrastructure",
                "tracked_count": 1,
                "reachable_count": 1,
                "multi_provider_count": 1,
                "top_providers": [
                    {"provider": "Fastly", "count": 1, "share_label": "100%", "color": "#ef6b57"}
                ],
            },
        ],
        "recent_changes": [
            {"label": "Fastly", "category": "Infrastructure", "summary": "Observed providers: Fastly -> Fastly, Cloudflare"}
        ],
        "history": [
            {
                "updated_at": "2026-03-28T10:00:00",
                "tracked_count": 1,
                "sample_target_count": 1,
                "target_source_name": "Tranco Top Sites",
                "reachable_count": 1,
                "multi_provider_count": 0,
                "provider_counts": {"Cloudflare": 1},
            },
            {
                "updated_at": "2026-04-01T10:00:00",
                "tracked_count": 2,
                "sample_target_count": 2,
                "target_source_name": "Tranco Top Sites",
                "reachable_count": 2,
                "multi_provider_count": 0,
                "provider_counts": {"Cloudflare": 2},
            },
            {
                "updated_at": "2026-04-04T10:00:00",
                "tracked_count": 2,
                "sample_target_count": 2,
                "target_source_name": "Tranco Top Sites",
                "reachable_count": 2,
                "multi_provider_count": 1,
                "provider_counts": {"Cloudflare": 1, "Fastly": 1},
            },
            {
                "updated_at": "2026-04-07T10:00:00",
                "tracked_count": 2,
                "sample_target_count": 2,
                "target_source_name": "Tranco Top Sites",
                "reachable_count": 2,
                "multi_provider_count": 1,
                "provider_counts": {"Cloudflare": 1, "Fastly": 1},
            },
        ],
        "target_catalog": {
            "source_name": "Tranco Top Sites",
            "source_url": "https://tranco-list.eu/top-1m.csv.zip",
            "updated_at": "2026-04-07T09:50:00",
            "target_count": 2,
        },
    }


def build_sample_stablecoin_cache() -> dict:
    return {
        "updated_at": "2026-04-07T10:05:00",
        "coverage_start": "2026-03",
        "coverage_end": "2026-04",
        "source": {
            "name": "DefiLlama",
            "url": "https://defillama.com/stablecoins",
            "endpoint": "https://stablecoins.llama.fi/stablecoins",
        },
        "coins": [
            {
                "symbol": "USDT",
                "latest_market_cap": 144000000000.0,
                "latest_volume": 56000000000.0,
                "latest_point_at": "2026-04-07T10:05:00",
                "history_latest_point_at": "2026-04-07T10:05:00",
            },
            {
                "symbol": "USDC",
                "latest_market_cap": 61000000000.0,
                "latest_volume": 12000000000.0,
                "latest_point_at": "2026-04-07T10:05:00",
                "history_latest_point_at": "2026-04-07T10:05:00",
            },
        ],
        "monthly_series": [
            {
                "month": "2026-03",
                "volume_available": True,
                "coins": [
                    {"symbol": "USDT", "market_cap": 142000000000.0, "volume": 52000000000.0},
                    {"symbol": "USDC", "market_cap": 59000000000.0, "volume": 11000000000.0},
                ],
            },
            {
                "month": "2026-04",
                "volume_available": True,
                "coins": [
                    {"symbol": "USDT", "market_cap": 144000000000.0, "volume": 56000000000.0},
                    {"symbol": "USDC", "market_cap": 61000000000.0, "volume": 12000000000.0},
                ],
            },
        ],
        "latest_snapshot": {
            "month": "2026-04",
            "total_market_cap": 205000000000.0,
            "total_volume": 68000000000.0,
            "latest_point_at": "2026-04-07T10:05:00",
            "market_cap_change_24h_pct": 0.8,
            "is_realtime": True,
        },
        "latest_month_snapshot": {
            "month": "2026-04",
            "total_market_cap": 205000000000.0,
            "total_volume": 68000000000.0,
            "latest_point_at": "2026-04-07T10:05:00",
        },
    }


class AINativeDataMonitorTests(unittest.TestCase):
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
            "STABLECOIN_MONITOR_CACHE_PATH": app_module.STABLECOIN_MONITOR_CACHE_PATH,
            "STABLECOIN_MONITOR_RUNTIME_PATH": app_module.STABLECOIN_MONITOR_RUNTIME_PATH,
            "CDN_MONITOR_CACHE_PATH": app_module.CDN_MONITOR_CACHE_PATH,
            "CDN_MONITOR_RUNTIME_PATH": app_module.CDN_MONITOR_RUNTIME_PATH,
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
        app_module.STABLECOIN_MONITOR_CACHE_PATH = temp_root / "stablecoins.json"
        app_module.STABLECOIN_MONITOR_RUNTIME_PATH = temp_root / "stablecoins_runtime.json"
        app_module.CDN_MONITOR_CACHE_PATH = temp_root / "cdn_tracker.json"
        app_module.CDN_MONITOR_RUNTIME_PATH = temp_root / "cdn_tracker_runtime.json"
        app_module.STOCK_SETUPS_DIR = temp_root / "stock_setups"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.AI_NATIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        app_module.STOCK_SETUPS_DIR.mkdir(parents=True, exist_ok=True)

        app_module.save_stock_store(build_minimal_stock_store())
        app_module.save_stablecoin_market_cache(build_sample_stablecoin_cache())
        app_module.save_cdn_tracker_cache(build_sample_cdn_cache())
        app_module.save_cdn_monitor_runtime(
            {
                "status": "completed",
                "started_at": "2026-04-07T09:58:00",
                "finished_at": "2026-04-07T10:00:00",
                "reason": "manual_refresh",
                "message": "CDN tracker refreshed.",
                "error": "",
            }
        )

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

    def test_bootstrap_exposes_data_monitor_entrypoints(self) -> None:
        response = self.client.get("/api/ai/bootstrap.json")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertIn("data_manifest_url", payload["entrypoints"])
        self.assertIn("data_search_url", payload["entrypoints"])
        self.assertIn("data_search_url_template", payload["entrypoints"])
        self.assertIn("cdn_json_url", payload["entrypoints"])
        self.assertIn("cdn_markdown_url", payload["entrypoints"])
        self.assertIn("stablecoins_markdown_url", payload["entrypoints"])

    def test_data_manifest_lists_stablecoins_and_cdn(self) -> None:
        response = self.client.get("/api/ai/data/manifest.json")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        dataset_ids = {item["dataset_id"] for item in payload["datasets"]}
        self.assertIn("stablecoins", dataset_ids)
        self.assertIn("cdn", dataset_ids)
        self.assertEqual(payload["search_url"], "/api/ai/data/search.json")
        self.assertIn("/api/ai/data/search.json?q=<QUERY>", payload["search_url_template"])

        cdn_dataset = next(item for item in payload["datasets"] if item["dataset_id"] == "cdn")
        self.assertIn("provider", cdn_dataset["filters_supported"])
        self.assertEqual(cdn_dataset["json_url"], "/api/ai/data/cdn.json")

    def test_cdn_json_endpoint_returns_filtered_sites_and_history(self) -> None:
        response = self.client.get("/api/ai/data/cdn.json?provider=Fastly&site_limit=5")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["dataset"], "cdn")
        self.assertEqual(payload["filters"]["provider"], "Fastly")
        self.assertEqual(payload["counts"]["matched_sites"], 1)
        self.assertEqual(payload["counts"]["returned_sites"], 1)
        self.assertEqual(payload["counts"]["hidden_history_snapshots"], 1)
        self.assertEqual(len(payload["comparable_history"]), 3)
        self.assertEqual(payload["sites"][0]["label"], "Fastly")
        self.assertEqual(payload["sites"][0]["provider"], "Fastly")

    def test_data_search_returns_granular_cdn_and_stablecoin_matches(self) -> None:
        cdn_response = self.client.get("/api/ai/data/search.json?q=openai%20cloudflare&datasets=cdn&types=site&limit=5")
        self.assertEqual(cdn_response.status_code, 200)
        cdn_payload = cdn_response.get_json()

        self.assertEqual(cdn_payload["query"], "openai cloudflare")
        self.assertEqual(cdn_payload["filters"]["datasets"], ["cdn"])
        self.assertEqual(cdn_payload["filters"]["types"], ["site"])
        self.assertGreaterEqual(cdn_payload["counts"]["matched_results"], 1)
        self.assertEqual(cdn_payload["results"][0]["dataset"], "cdn")
        self.assertEqual(cdn_payload["results"][0]["entity_type"], "site")
        self.assertEqual(cdn_payload["results"][0]["title"], "OpenAI")
        self.assertEqual(cdn_payload["results"][0]["related"]["provider"], "Cloudflare")
        self.assertIn("/api/ai/data/cdn.json", cdn_payload["results"][0]["json_url"])

        stablecoin_response = self.client.get("/api/ai/data/search.json?q=usdt&datasets=stablecoins&types=coin&limit=5")
        self.assertEqual(stablecoin_response.status_code, 200)
        stablecoin_payload = stablecoin_response.get_json()

        self.assertEqual(stablecoin_payload["filters"]["datasets"], ["stablecoins"])
        self.assertEqual(stablecoin_payload["filters"]["types"], ["coin"])
        self.assertGreaterEqual(stablecoin_payload["counts"]["matched_results"], 1)
        self.assertEqual(stablecoin_payload["results"][0]["dataset"], "stablecoins")
        self.assertEqual(stablecoin_payload["results"][0]["entity_type"], "coin")
        self.assertIn("USDT", stablecoin_payload["results"][0]["title"])
        self.assertEqual(stablecoin_payload["results"][0]["related"]["symbol"], "USDT")

    def test_cdn_markdown_and_manifest_document_available(self) -> None:
        markdown_response = self.client.get("/api/ai/data/cdn.md")
        self.assertEqual(markdown_response.status_code, 200)
        markdown_text = markdown_response.data.decode("utf-8")
        self.assertIn("# CDN Data Snapshot", markdown_text)
        self.assertIn("## Provider Distribution", markdown_text)

        document_response = self.client.get("/api/ai/json/data_snapshot/cdn")
        self.assertEqual(document_response.status_code, 200)
        document_payload = document_response.get_json()
        self.assertEqual(document_payload["document"]["kind"], "data_snapshot")
        self.assertEqual(document_payload["document"]["doc_id"], "cdn")

        manifest_response = self.client.get("/api/ai/manifest.json?kind=data_snapshot")
        self.assertEqual(manifest_response.status_code, 200)
        manifest_payload = manifest_response.get_json()
        doc_ids = {item["doc_id"] for item in manifest_payload["documents"]}
        self.assertIn("stablecoins", doc_ids)
        self.assertIn("cdn", doc_ids)


if __name__ == "__main__":
    unittest.main()
