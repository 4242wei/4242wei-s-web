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
                "category": "AI / 开发",
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
                "category": "基础设施",
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
                "category": "AI / 开发",
                "tracked_count": 1,
                "reachable_count": 1,
                "multi_provider_count": 0,
                "top_providers": [
                    {"provider": "Cloudflare", "count": 1, "share_label": "100%", "color": "#4f8df7"}
                ],
            },
            {
                "category": "基础设施",
                "tracked_count": 1,
                "reachable_count": 1,
                "multi_provider_count": 1,
                "top_providers": [
                    {"provider": "Fastly", "count": 1, "share_label": "100%", "color": "#ef6b57"}
                ],
            },
        ],
        "recent_changes": [
            {"label": "Fastly", "category": "基础设施", "summary": "Observed providers: Fastly -> Fastly, Cloudflare"}
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
                "updated_at": "2026-04-07T08:00:00",
                "tracked_count": 2,
                "sample_target_count": 2,
                "target_source_name": "Tranco Top Sites",
                "reachable_count": 2,
                "multi_provider_count": 0,
                "provider_counts": {"Fastly": 2},
            },
            {
                "updated_at": "2026-04-07T10:00:00",
                "tracked_count": 2,
                "sample_target_count": 2,
                "target_source_name": "Tranco Top Sites",
                "reachable_count": 2,
                "multi_provider_count": 1,
                "provider_counts": {"Cloudflare": 1, "Fastly": 1},
            }
        ],
        "target_catalog": {
            "source_name": "Tranco Top Sites",
            "source_url": "https://tranco-list.eu/top-1m.csv.zip",
            "updated_at": "2026-04-07T09:50:00",
            "target_count": 2,
        },
    }


class DataMonitorCdnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_paths = {
            "STOCK_STORE_PATH": app_module.STOCK_STORE_PATH,
            "REPORTS_DIR": app_module.REPORTS_DIR,
            "SIGNAL_MONITOR_REPORTS_DIR": app_module.SIGNAL_MONITOR_REPORTS_DIR,
            "CDN_MONITOR_CACHE_PATH": app_module.CDN_MONITOR_CACHE_PATH,
            "CDN_MONITOR_RUNTIME_PATH": app_module.CDN_MONITOR_RUNTIME_PATH,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)
        self.original_cdn_scheduler_started = app_module.CDN_MONITOR_SCHEDULER_STARTED
        self.original_cdn_scheduler_thread = app_module.CDN_MONITOR_SCHEDULER_THREAD
        self.original_cdn_active_thread = app_module.CDN_MONITOR_ACTIVE_THREAD
        self.original_cdn_target_count = app_module.CDN_MONITOR_TARGET_COUNT
        self.original_cdn_refresh_interval_hours = app_module.CDN_MONITOR_REFRESH_INTERVAL_HOURS

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.SIGNAL_MONITOR_REPORTS_DIR = temp_root / "signal_reports"
        app_module.CDN_MONITOR_CACHE_PATH = temp_root / "cdn_tracker.json"
        app_module.CDN_MONITOR_RUNTIME_PATH = temp_root / "cdn_tracker_runtime.json"
        app_module.CDN_MONITOR_TARGET_COUNT = 2
        app_module.CDN_MONITOR_REFRESH_INTERVAL_HOURS = 24 * 365
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        app_module.CDN_MONITOR_SCHEDULER_STARTED = True
        app_module.CDN_MONITOR_SCHEDULER_THREAD = None
        app_module.CDN_MONITOR_ACTIVE_THREAD = None

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.save_stock_store(build_minimal_stock_store())
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
        app_module.CDN_MONITOR_SCHEDULER_STARTED = self.original_cdn_scheduler_started
        app_module.CDN_MONITOR_SCHEDULER_THREAD = self.original_cdn_scheduler_thread
        app_module.CDN_MONITOR_ACTIVE_THREAD = self.original_cdn_active_thread
        app_module.CDN_MONITOR_TARGET_COUNT = self.original_cdn_target_count
        app_module.CDN_MONITOR_REFRESH_INTERVAL_HOURS = self.original_cdn_refresh_interval_hours
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_cdn_tab_defers_site_rows_until_expanded(self) -> None:
        response = self.client.get("/data-monitor?tab=cdn")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("CDN 追踪", html)
        self.assertIn("Cloudflare", html)
        self.assertIn("Provider Share Through Time", html)
        self.assertIn("Provider Count Through Time", html)
        self.assertIn("展开 bucket 统计", html)
        self.assertIn('data-cdn-sites-details', html)
        self.assertIn('/data-monitor/cdn/sites', html)
        self.assertIn('data-cdn-sites-body', html)
        self.assertIn('data-cdn-chart-scrollbar', html)
        self.assertIn('data-trend-controls', html)
        self.assertIn("Monitor Health", html)
        self.assertIn("JSON Export", html)
        self.assertIn("/api/ai/data/cdn.json", html)
        self.assertNotIn('>OpenAI<', html)

    def test_cdn_sites_endpoint_returns_lazy_loaded_rows(self) -> None:
        response = self.client.get("/data-monitor/cdn/sites")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tracked_count"], 2)
        self.assertEqual(payload["site_count"], 2)
        self.assertEqual(payload["sites"][0]["label"], "OpenAI")
        self.assertEqual(payload["sites"][0]["provider"], "Cloudflare")
        self.assertEqual(payload["sites"][1]["label"], "Fastly")
        self.assertEqual(payload["sites"][1]["observed_provider_extra_count"], 0)
        self.assertEqual(len(payload["sites"][1]["observed_provider_badges_compact"]), 2)

    def test_cdn_status_endpoint_returns_summary_counts(self) -> None:
        response = self.client.get("/data-monitor/cdn/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tracked_count"], 2)
        self.assertEqual(payload["reachable_count"], 2)
        self.assertEqual(payload["detected_count"], 2)
        self.assertEqual(payload["multi_provider_count"], 1)
        self.assertEqual(payload["runtime"]["status"], "completed")

    def test_cdn_trend_charts_ignore_old_sample_size_snapshots(self) -> None:
        context = app_module.build_cdn_data_monitor_context()

        self.assertEqual(context["cdn_history_snapshot_count"], 5)
        self.assertEqual(context["cdn_trend_snapshot_count"], 3)
        self.assertEqual(context["cdn_hidden_history_snapshot_count"], 1)
        self.assertEqual(context["cdn_collapsed_same_day_snapshot_count"], 1)
        self.assertEqual(len(context["cdn_confidence_items"]), 5)
        self.assertGreaterEqual(len(context["cdn_highlight_cards"]), 2)
        self.assertGreaterEqual(len(context["cdn_signal_items"]), 1)
        self.assertTrue(context["cdn_history_span_label"])
        self.assertEqual(len(context["cdn_share_trend_chart"]["points"]), 3)
        self.assertEqual(len(context["cdn_count_trend_chart"]["points"]), 3)
        self.assertEqual(context["cdn_share_trend_chart"]["points"][-1]["label"], "04-07")
        self.assertEqual(
            {item["symbol"]: item["value"] for item in context["cdn_share_trend_chart"]["points"][-1]["series"]},
            {"Cloudflare": 50.0, "Fastly": 50.0},
        )

    def test_cdn_ai_export_endpoint_returns_analysis_fields(self) -> None:
        response = self.client.get("/api/ai/data/cdn.json")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["dataset"], "cdn")
        self.assertEqual(payload["counts"]["history_snapshots"], 5)
        self.assertEqual(payload["counts"]["comparable_history_snapshots"], 3)
        self.assertEqual(len(payload["confidence_items"]), 5)
        self.assertGreaterEqual(len(payload["signal_items"]), 1)


if __name__ == "__main__":
    unittest.main()
