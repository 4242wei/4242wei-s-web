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


def build_applovin_row(
    *,
    rank: int,
    name: str,
    app_share_pct: float,
    total_apps: int,
    download_share_pct: float,
    total_downloads: int,
    website_url: str,
    is_applovin: bool,
) -> dict:
    return {
        "rank": rank,
        "rank_label": f"#{rank}",
        "slug": name.casefold().replace(" ", "-"),
        "name": name,
        "website": "",
        "website_url": website_url,
        "description": "",
        "app_share_pct": app_share_pct,
        "app_share_label": app_module.format_percent_label(app_share_pct),
        "total_apps": total_apps,
        "total_apps_label": app_module.format_compact_number(total_apps),
        "apps": total_apps // 2,
        "games": total_apps // 2,
        "download_share_pct": download_share_pct,
        "download_share_label": app_module.format_percent_label(download_share_pct),
        "total_downloads": total_downloads,
        "total_downloads_label": app_module.format_compact_number(total_downloads),
        "app_downloads": total_downloads // 2,
        "game_downloads": total_downloads // 2,
        "icon": "",
        "is_applovin": is_applovin,
    }


def build_sample_applovin_page(platform_id: str, platform_title: str, category_id: str, category_title: str, row: dict) -> dict:
    leader = build_applovin_row(
        rank=1,
        name="Leader SDK",
        app_share_pct=40.0,
        total_apps=240000,
        download_share_pct=44.0,
        total_downloads=220000000000,
        website_url="https://42matters.com/sdks/android/leader",
        is_applovin=False,
    )
    rows = [leader, row]
    return {
        "selection_key": f"{platform_id}::{category_id}",
        "platform_id": platform_id,
        "platform_title": platform_title,
        "platform_long_title": platform_title,
        "category_id": category_id,
        "category_title": category_title,
        "category_reason": "sample reason",
        "page_title": f"{category_title} / {platform_title}",
        "source_url": "https://42matters.com/sdk-analysis/top-ad-mediation-sdks",
        "source_updated_at": "2026-04-11",
        "crawled_at": "2026-04-13T10:00:00",
        "sdk_count": len(rows),
        "top_sdk_name": leader["name"],
        "sdks": rows,
        "applovin_match_count": 1,
        "applovin_rows": [row],
        "primary_applovin": row,
    }


def build_sample_applovin_cache() -> dict:
    mediation_row = build_applovin_row(
        rank=2,
        name="AppLovin Mediation Adapters",
        app_share_pct=19.25,
        total_apps=118680,
        download_share_pct=48.45,
        total_downloads=453470000000,
        website_url="https://42matters.com/sdks/android/applovin-mediation-adapters",
        is_applovin=True,
    )
    network_row = build_applovin_row(
        rank=5,
        name="AppLovin MAX",
        app_share_pct=17.02,
        total_apps=118545,
        download_share_pct=43.86,
        total_downloads=457300000000,
        website_url="https://42matters.com/sdks/android/applovin",
        is_applovin=True,
    )
    attribution_row = build_applovin_row(
        rank=12,
        name="AppLovin",
        app_share_pct=4.12,
        total_apps=24010,
        download_share_pct=9.34,
        total_downloads=88100000000,
        website_url="https://42matters.com/sdks/android/applovin",
        is_applovin=True,
    )

    pages = {
        "gplay::top-ad-mediation-sdks": build_sample_applovin_page(
            "gplay", "Google Play", "top-ad-mediation-sdks", "Ad Mediation", mediation_row
        ),
        "gplay::top-ad-networks-sdks": build_sample_applovin_page(
            "gplay", "Google Play", "top-ad-networks-sdks", "Ad Networks", network_row
        ),
        "gplay::top-attribution-sdks": build_sample_applovin_page(
            "gplay", "Google Play", "top-attribution-sdks", "Attribution", attribution_row
        ),
        "ios::top-ad-mediation-sdks": build_sample_applovin_page(
            "ios", "App Store", "top-ad-mediation-sdks", "Ad Mediation", mediation_row
        ),
        "ios::top-ad-networks-sdks": build_sample_applovin_page(
            "ios", "App Store", "top-ad-networks-sdks", "Ad Networks", network_row
        ),
        "ios::top-attribution-sdks": build_sample_applovin_page(
            "ios", "App Store", "top-attribution-sdks", "Attribution", attribution_row
        ),
    }

    return {
        "updated_at": "2026-04-13T10:05:00",
        "source": {
            "name": "42matters SDK Analysis",
            "url": "https://42matters.com/sdk-analysis/top-ad-mediation-sdks",
            "endpoint": "Curated 42matters ranking pages + __NEXT_DATA__ extraction",
        },
        "notes": "sample applovin cache",
        "summary": {
            "tracked_page_count": 6,
            "available_page_count": 6,
            "fresh_page_count": 6,
            "stale_page_count": 0,
            "applovin_present_page_count": 6,
            "page_error_count": 0,
        },
        "pages": pages,
        "recent_changes": {
            "gplay::top-ad-mediation-sdks": [
                {
                    "label": "Rank Shift",
                    "summary": "AppLovin Mediation Adapters moved from #3 to #2.",
                }
            ]
        },
        "history": [
            {
                "selection_key": "gplay::top-ad-mediation-sdks",
                "platform_id": "gplay",
                "platform_title": "Google Play",
                "category_id": "top-ad-mediation-sdks",
                "category_title": "Ad Mediation",
                "page_title": "Ad Mediation / Google Play",
                "crawled_at": "2026-04-10T10:00:00",
                "source_updated_at": "2026-04-10",
                "sdk_count": 20,
                "top_sdk_name": "Leader SDK",
                "applovin_present": True,
                "applovin_match_count": 1,
                "applovin_primary_name": "AppLovin Mediation Adapters",
                "applovin_rank": 4,
                "applovin_app_share_pct": 18.10,
                "applovin_total_apps": 114200,
                "applovin_apps": 53600,
                "applovin_games": 60600,
                "applovin_download_share_pct": 46.70,
                "applovin_total_downloads": 441000000000,
                "applovin_app_downloads": 143000000000,
                "applovin_game_downloads": 298000000000,
            },
            {
                "selection_key": "gplay::top-ad-mediation-sdks",
                "platform_id": "gplay",
                "platform_title": "Google Play",
                "category_id": "top-ad-mediation-sdks",
                "category_title": "Ad Mediation",
                "page_title": "Ad Mediation / Google Play",
                "crawled_at": "2026-04-11T10:00:00",
                "source_updated_at": "2026-04-11",
                "sdk_count": 20,
                "top_sdk_name": "Leader SDK",
                "applovin_present": True,
                "applovin_match_count": 1,
                "applovin_primary_name": "AppLovin Mediation Adapters",
                "applovin_rank": 3,
                "applovin_app_share_pct": 18.45,
                "applovin_total_apps": 115200,
                "applovin_apps": 54200,
                "applovin_games": 61000,
                "applovin_download_share_pct": 46.95,
                "applovin_total_downloads": 444000000000,
                "applovin_app_downloads": 144000000000,
                "applovin_game_downloads": 300000000000,
            },
            {
                "selection_key": "gplay::top-ad-mediation-sdks",
                "platform_id": "gplay",
                "platform_title": "Google Play",
                "category_id": "top-ad-mediation-sdks",
                "category_title": "Ad Mediation",
                "page_title": "Ad Mediation / Google Play",
                "crawled_at": "2026-04-12T10:00:00",
                "source_updated_at": "2026-04-11",
                "sdk_count": 20,
                "top_sdk_name": "Leader SDK",
                "applovin_present": True,
                "applovin_match_count": 1,
                "applovin_primary_name": "AppLovin Mediation Adapters",
                "applovin_rank": 3,
                "applovin_app_share_pct": 18.80,
                "applovin_total_apps": 116000,
                "applovin_apps": 54800,
                "applovin_games": 61200,
                "applovin_download_share_pct": 47.10,
                "applovin_total_downloads": 448000000000,
                "applovin_app_downloads": 146000000000,
                "applovin_game_downloads": 302000000000,
            },
            {
                "selection_key": "gplay::top-ad-mediation-sdks",
                "platform_id": "gplay",
                "platform_title": "Google Play",
                "category_id": "top-ad-mediation-sdks",
                "category_title": "Ad Mediation",
                "page_title": "Ad Mediation / Google Play",
                "crawled_at": "2026-04-13T08:00:00",
                "source_updated_at": "2026-04-11",
                "sdk_count": 20,
                "top_sdk_name": "Leader SDK",
                "applovin_present": True,
                "applovin_match_count": 1,
                "applovin_primary_name": "AppLovin Mediation Adapters",
                "applovin_rank": 3,
                "applovin_app_share_pct": 19.05,
                "applovin_total_apps": 117400,
                "applovin_apps": 55200,
                "applovin_games": 62200,
                "applovin_download_share_pct": 47.90,
                "applovin_total_downloads": 451000000000,
                "applovin_app_downloads": 147000000000,
                "applovin_game_downloads": 304000000000,
            },
            {
                "selection_key": "gplay::top-ad-mediation-sdks",
                "platform_id": "gplay",
                "platform_title": "Google Play",
                "category_id": "top-ad-mediation-sdks",
                "category_title": "Ad Mediation",
                "page_title": "Ad Mediation / Google Play",
                "crawled_at": "2026-04-13T10:00:00",
                "source_updated_at": "2026-04-11",
                "sdk_count": 20,
                "top_sdk_name": "Leader SDK",
                "applovin_present": True,
                "applovin_match_count": 1,
                "applovin_primary_name": "AppLovin Mediation Adapters",
                "applovin_rank": 2,
                "applovin_app_share_pct": 19.25,
                "applovin_total_apps": 118680,
                "applovin_download_share_pct": 48.45,
                "applovin_total_downloads": 453470000000,
            },
        ],
        "page_errors": [],
    }


class DataMonitorAppLovinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_paths = {
            "STOCK_STORE_PATH": app_module.STOCK_STORE_PATH,
            "REPORTS_DIR": app_module.REPORTS_DIR,
            "SIGNAL_MONITOR_REPORTS_DIR": app_module.SIGNAL_MONITOR_REPORTS_DIR,
            "APPLOVIN_MONITOR_CACHE_PATH": app_module.APPLOVIN_MONITOR_CACHE_PATH,
            "APPLOVIN_MONITOR_RUNTIME_PATH": app_module.APPLOVIN_MONITOR_RUNTIME_PATH,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)
        self.original_scheduler_started = app_module.APPLOVIN_MONITOR_SCHEDULER_STARTED
        self.original_scheduler_thread = app_module.APPLOVIN_MONITOR_SCHEDULER_THREAD
        self.original_active_thread = app_module.APPLOVIN_MONITOR_ACTIVE_THREAD
        self.original_refresh_hours = app_module.APPLOVIN_MONITOR_REFRESH_INTERVAL_HOURS

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.SIGNAL_MONITOR_REPORTS_DIR = temp_root / "signal_reports"
        app_module.APPLOVIN_MONITOR_CACHE_PATH = temp_root / "applovin_sdk_tracker.json"
        app_module.APPLOVIN_MONITOR_RUNTIME_PATH = temp_root / "applovin_sdk_tracker_runtime.json"
        app_module.APPLOVIN_MONITOR_REFRESH_INTERVAL_HOURS = 24 * 365
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        app_module.APPLOVIN_MONITOR_SCHEDULER_STARTED = True
        app_module.APPLOVIN_MONITOR_SCHEDULER_THREAD = None
        app_module.APPLOVIN_MONITOR_ACTIVE_THREAD = None

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.save_stock_store(build_minimal_stock_store())
        app_module.save_applovin_tracker_cache(build_sample_applovin_cache())
        app_module.save_applovin_monitor_runtime(
            {
                "status": "completed",
                "started_at": "2026-04-13T09:58:00",
                "finished_at": "2026-04-13T10:00:00",
                "reason": "manual_refresh",
                "message": "AppLovin tracker refreshed.",
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
        app_module.APPLOVIN_MONITOR_SCHEDULER_STARTED = self.original_scheduler_started
        app_module.APPLOVIN_MONITOR_SCHEDULER_THREAD = self.original_scheduler_thread
        app_module.APPLOVIN_MONITOR_ACTIVE_THREAD = self.original_active_thread
        app_module.APPLOVIN_MONITOR_REFRESH_INTERVAL_HOURS = self.original_refresh_hours
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_applovin_tab_renders_filters_and_leaderboard(self) -> None:
        response = self.client.get("/data-monitor?tab=applovin&platform=gplay&category=top-ad-mediation-sdks")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("AppLovin SDK", html)
        self.assertIn("Platform", html)
        self.assertIn("Category", html)
        self.assertIn("AppLovin Mediation Adapters", html)
        self.assertIn("Ad Networks", html)
        self.assertIn("/data-monitor/applovin/status", html)
        self.assertIn("data-applovin-panel-shell", html)
        self.assertIn("Share Through Time", html)
        self.assertIn("Apps vs Games", html)
        self.assertIn("data-applovin-donut-seed", html)
        self.assertIn("Tracker Health", html)
        self.assertIn("JSON Export", html)
        self.assertIn("Markdown Export", html)
        self.assertIn('data-trend-controls', html)
        self.assertIn('/api/ai/data/applovin.json?platform=gplay&amp;category=top-ad-mediation-sdks', html)

    def test_applovin_status_endpoint_returns_summary_counts(self) -> None:
        response = self.client.get("/data-monitor/applovin/status")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["tracked_page_count"], 6)
        self.assertEqual(payload["available_page_count"], 6)
        self.assertEqual(payload["fresh_page_count"], 6)
        self.assertEqual(payload["applovin_present_page_count"], 6)
        self.assertEqual(payload["runtime"]["status"], "completed")

    def test_applovin_context_builds_cross_category_rows(self) -> None:
        with app_module.app.test_request_context("/data-monitor?tab=applovin&platform=gplay&category=top-ad-mediation-sdks"):
            context = app_module.build_applovin_data_monitor_context(
                platform_id="gplay",
                category_id="top-ad-mediation-sdks",
            )

        self.assertEqual(context["applovin_selected_platform_id"], "gplay")
        self.assertEqual(context["applovin_selected_category_id"], "top-ad-mediation-sdks")
        self.assertEqual(len(context["applovin_cross_category_rows"]), 3)
        self.assertEqual(context["applovin_primary_rank_label"], "#2")
        self.assertEqual(context["applovin_cross_category_rows"][1]["category_title"], "Ad Networks")
        self.assertEqual(len(context["applovin_mix_donuts"]), 4)
        self.assertEqual(context["applovin_history_point_count"], 4)
        self.assertEqual(len(context["applovin_confidence_items"]), 5)
        self.assertGreaterEqual(len(context["applovin_signal_items"]), 1)
        self.assertEqual(context["applovin_share_trend_chart"]["points"][-1]["label"], "04-13")
        self.assertEqual(context["applovin_share_trend_chart"]["title"], "Share Through Time")

    def test_applovin_ai_export_and_manifest_include_dataset(self) -> None:
        response = self.client.get("/api/ai/data/applovin.json?platform=gplay&category=top-ad-mediation-sdks")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["dataset"], "applovin")
        self.assertEqual(payload["filters"]["platform"], "gplay")
        self.assertEqual(payload["filters"]["category"], "top-ad-mediation-sdks")
        self.assertEqual(payload["primary_entry"]["rank_label"], "#2")
        self.assertEqual(payload["counts"]["history_points"], 4)
        self.assertEqual(len(payload["confidence_items"]), 5)
        self.assertGreaterEqual(len(payload["signal_items"]), 1)

        manifest_response = self.client.get("/api/ai/data/manifest.json")
        self.assertEqual(manifest_response.status_code, 200)
        manifest_payload = manifest_response.get_json()
        dataset_ids = {item["dataset_id"] for item in manifest_payload["datasets"]}
        self.assertIn("applovin", dataset_ids)


if __name__ == "__main__":
    unittest.main()
