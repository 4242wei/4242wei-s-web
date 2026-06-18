from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import app as app_module
import gpu_price_tracker


def build_flight_fixture(*, price: float = 2.5, provider_id: str = "fixture-cloud", provider_name: str = "Fixture Cloud") -> str:
    offering = {
        "id": 101,
        "providerOfferingId": "101",
        "gpuCount": 1,
        "vcpu": 24,
        "ram": {"size": 192, "unit": "GB"},
        "bootDisk": {"size": 500, "unit": "GB"},
        "pricePerGpuHour": {"usd": price},
        "regions": ["us"],
        "available": True,
        "provider": {
            "id": provider_id,
            "name": provider_name,
            "website": "https://example.com",
            "offerings": [],
        },
    }
    rsc_text = json.dumps({"sortedGroupedOfferings": [{"primaryOffering": offering}]}, separators=(",", ":"))
    return f"<html><body><script>self.__next_f.push({json.dumps([1, rsc_text])})</script></body></html>"


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


def build_sample_gpu_cache() -> dict:
    h100_html = build_flight_fixture()
    b200_html = build_flight_fixture(price=5.0, provider_id="fixture-b-cloud", provider_name="Fixture B Cloud")
    offers = []
    offers.extend(
        gpu_price_tracker.parse_gpusio_offers(
            h100_html,
            family="H100",
            source_url="https://gpus.io/en/gpus/h100",
            fetch_ts="2026-04-16T10:00:00",
        )
    )
    spot_offer = deepcopy(offers[0])
    spot_offer.update(
        {
            "id": "fixture-h100-spot",
            "provider_name": "Fixture Spot",
            "provider_slug": "fixture_spot",
            "billing_type": "spot",
            "price_per_gpu_hour_usd": 1.2,
            "price_total_hour_usd": 1.2,
            "contract_term_bucket": "none",
            "quality_exclusion_reason": None,
        }
    )
    offers.append(spot_offer)
    offers.extend(
        gpu_price_tracker.parse_gpusio_offers(
            b200_html,
            family="B200",
            source_url="https://gpus.io/en/gpus/b200",
            fetch_ts="2026-04-16T10:00:00",
        )
    )
    daily_index = gpu_price_tracker.build_daily_index(offers, fetch_ts="2026-04-16T10:00:00")
    csp_daily_index: list[dict] = []
    return {
        "version": 1,
        "updated_at": "2026-04-16T10:00:00",
        "families": ["H100", "B200"],
        "source": {
            "name": "GPUs.io + GetDeploying",
            "url": "https://gpus.io/en/gpus/h100",
            "endpoint": "fixture",
        },
        "notes": "fixture cache",
        "summary": {
            "offer_count": len(offers),
            "raw_snapshot_count": len(offers),
            "daily_index_count": len(daily_index),
            "csp_daily_index_count": len(csp_daily_index),
            "source_health_count": 1,
            "provider_count": 1,
        },
        "latest": gpu_price_tracker.build_latest_summary(offers, daily_index, fetch_ts="2026-04-16T10:00:00"),
        "raw_snapshots": gpu_price_tracker.build_raw_snapshots(offers),
        "normalized_offers": offers,
        "daily_index": daily_index,
        "csp_daily_index": csp_daily_index,
        "source_health": [
            {
                "date": "2026-04-16",
                "source_name": "gpusio",
                "gpu_family": "H100",
                "source_page_url": "https://gpus.io/en/gpus/h100",
                "fetch_ok": True,
                "status_code": 200,
                "rows_parsed": 1,
                "providers_found": 1,
                "sample_last_updated_age_hours": None,
                "schema_changed": False,
                "cross_source_median_gap": None,
                "notes": "",
            }
        ],
        "history": [],
    }


class GpuPriceTrackerTests(unittest.TestCase):
    def test_gpusio_next_flight_parser_normalizes_primary_offer(self) -> None:
        offers = gpu_price_tracker.parse_gpusio_offers(
            build_flight_fixture(),
            family="H100",
            source_url="https://gpus.io/en/gpus/h100",
            fetch_ts="2026-04-16T10:00:00",
        )

        self.assertEqual(len(offers), 1)
        offer = offers[0]
        self.assertEqual(offer["provider_slug"], "fixture_cloud")
        self.assertEqual(offer["gpu_variant_canonical"], "h100_sxm")
        self.assertEqual(offer["billing_type"], "on_demand")
        self.assertEqual(offer["gpu_count_bucket"], "1gpu")
        self.assertEqual(offer["price_per_gpu_hour_usd"], 2.5)
        self.assertIsNone(offer["quality_exclusion_reason"])

    def test_daily_index_keeps_quality_window_available_series(self) -> None:
        offers = gpu_price_tracker.parse_gpusio_offers(
            build_flight_fixture(),
            family="H100",
            source_url="https://gpus.io/en/gpus/h100",
            fetch_ts="2026-04-16T10:00:00",
        )
        rows = gpu_price_tracker.build_daily_index(offers, fetch_ts="2026-04-16T10:00:00")

        self.assertEqual({row["availability_mode"] for row in rows}, {"posted", "available"})
        available = next(row for row in rows if row["availability_mode"] == "available")
        self.assertEqual(available["price_standardized"], 2.5)
        self.assertEqual(available["sample_size"], 1)

    def test_daily_index_includes_b_series_and_replaces_same_day_rows(self) -> None:
        offers = gpu_price_tracker.parse_gpusio_offers(
            build_flight_fixture(price=5.0, provider_id="fixture-b-cloud", provider_name="Fixture B Cloud"),
            family="B200",
            source_url="https://gpus.io/en/gpus/b200",
            fetch_ts="2026-04-16T10:00:00",
        )
        stale_row = {
            "date": "2026-04-16",
            "series_key": "b200_sxm:on_demand:1gpu:all:available",
            "gpu_family": "B200",
            "gpu_variant_canonical": "b200_sxm",
            "availability_mode": "available",
            "price_standardized": 99.0,
        }
        old_row = {
            "date": "2026-04-15",
            "series_key": "b200_sxm:on_demand:1gpu:all:available",
            "gpu_family": "B200",
            "gpu_variant_canonical": "b200_sxm",
            "availability_mode": "available",
            "price_standardized": 7.5,
        }
        rows = gpu_price_tracker.build_daily_index(
            offers,
            fetch_ts="2026-04-16T12:30:00",
            previous_daily_index=[old_row, stale_row],
        )

        today_rows = [row for row in rows if row["date"] == "2026-04-16" and row["gpu_family"] == "B200"]
        self.assertEqual({row["availability_mode"] for row in today_rows}, {"posted", "available"})
        available = next(row for row in today_rows if row["availability_mode"] == "available")
        self.assertEqual(available["gpu_variant_canonical"], "b200_sxm")
        self.assertEqual(available["price_standardized"], 5.0)
        self.assertEqual(available["updated_at"], "2026-04-16T12:30:00")
        self.assertEqual(len([row for row in rows if row["date"] == "2026-04-15"]), 1)

    def test_daily_index_builds_spot_series_separately(self) -> None:
        offers = gpu_price_tracker.parse_gpusio_offers(
            build_flight_fixture(price=2.5),
            family="H100",
            source_url="https://gpus.io/en/gpus/h100",
            fetch_ts="2026-04-16T10:00:00",
        )
        spot_offer = deepcopy(offers[0])
        spot_offer.update(
            {
                "billing_type": "spot",
                "price_per_gpu_hour_usd": 1.25,
                "price_total_hour_usd": 1.25,
                "provider_slug": "fixture_spot",
                "quality_exclusion_reason": None,
            }
        )
        rows = gpu_price_tracker.build_daily_index([offers[0], spot_offer], fetch_ts="2026-04-16T10:00:00")

        on_demand = next(row for row in rows if row["billing_type"] == "on_demand" and row["availability_mode"] == "available")
        spot = next(row for row in rows if row["billing_type"] == "spot" and row["availability_mode"] == "available")
        self.assertEqual(on_demand["price_standardized"], 2.5)
        self.assertEqual(spot["price_standardized"], 1.25)
        self.assertEqual(spot["series_key"], "h100:spot:allgpu:all:available")

    def test_azure_retail_price_item_normalizes_spot_offer(self) -> None:
        item = {
            "meterId": "azure-h100-spot",
            "armRegionName": "eastus2",
            "productName": "Virtual Machines NCCadsv5 Srs",
            "skuName": "NCC40adsH100v5 Spot",
            "armSkuName": "Standard_NCC40ads_H100_v5",
            "meterName": "NCC40adsH100v5 Spot",
            "type": "Consumption",
            "retailPrice": 1.289904,
            "unitPrice": 1.289904,
            "unitOfMeasure": "1 Hour",
            "currencyCode": "USD",
        }

        offer = gpu_price_tracker.normalize_azure_retail_price_item(item, fetch_ts="2026-04-16T10:00:00")

        self.assertIsNotNone(offer)
        assert offer is not None
        self.assertEqual(offer["source_name"], "azure_retail_prices")
        self.assertEqual(offer["provider_slug"], "azure")
        self.assertEqual(offer["gpu_family"], "H100")
        self.assertEqual(offer["billing_type"], "spot")
        self.assertEqual(offer["gpu_count"], 1)
        self.assertEqual(offer["price_per_gpu_hour_usd"], 1.289904)
        self.assertEqual(offer["region_codes"], ["eastus2"])

    def test_csp_daily_index_builds_azure_reference_rows(self) -> None:
        base_item = {
            "meterId": "azure-h100",
            "armRegionName": "eastus2",
            "productName": "Virtual Machines NCCadsv5 Srs",
            "skuName": "NCC40adsH100v5",
            "armSkuName": "Standard_NCC40ads_H100_v5",
            "meterName": "NCC40adsH100v5",
            "type": "Consumption",
            "retailPrice": 4.0,
            "unitPrice": 4.0,
            "unitOfMeasure": "1 Hour",
            "currencyCode": "USD",
        }
        spot_item = {**base_item, "meterId": "azure-h100-spot", "skuName": "NCC40adsH100v5 Spot", "meterName": "NCC40adsH100v5 Spot", "unitPrice": 1.2, "retailPrice": 1.2}
        offers = [
            gpu_price_tracker.normalize_azure_retail_price_item(base_item, fetch_ts="2026-04-16T10:00:00"),
            gpu_price_tracker.normalize_azure_retail_price_item(spot_item, fetch_ts="2026-04-16T10:00:00"),
        ]
        rows = gpu_price_tracker.build_csp_daily_index(
            [item for item in offers if item],
            fetch_ts="2026-04-16T10:00:00",
            previous_csp_daily_index=[
                {
                    "date": "2026-04-15",
                    "series_key": "azure:h100:on_demand:allgpu:all:available",
                    "gpu_family": "H100",
                    "billing_type": "on_demand",
                    "availability_mode": "available",
                    "price_standardized": 4.5,
                }
            ],
        )

        today_rows = [row for row in rows if row["date"] == "2026-04-16"]
        self.assertEqual({row["billing_type"] for row in today_rows}, {"on_demand", "spot"})
        on_demand = next(row for row in today_rows if row["billing_type"] == "on_demand")
        spot = next(row for row in today_rows if row["billing_type"] == "spot")
        self.assertEqual(on_demand["series_key"], "azure:h100:on_demand:allgpu:all:available")
        self.assertEqual(on_demand["price_standardized"], 4.0)
        self.assertEqual(spot["price_standardized"], 1.2)
        self.assertEqual(on_demand["source_mix_json"], {"azure_retail_prices": 1})
        self.assertEqual(len([row for row in rows if row["date"] == "2026-04-15"]), 1)


class GpuPriceDataMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)
        self.original_paths = {
            "STOCK_STORE_PATH": app_module.STOCK_STORE_PATH,
            "REPORTS_DIR": app_module.REPORTS_DIR,
            "SIGNAL_MONITOR_REPORTS_DIR": app_module.SIGNAL_MONITOR_REPORTS_DIR,
            "GPU_PRICE_MONITOR_CACHE_PATH": app_module.GPU_PRICE_MONITOR_CACHE_PATH,
            "GPU_PRICE_MONITOR_RUNTIME_PATH": app_module.GPU_PRICE_MONITOR_RUNTIME_PATH,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)
        self.original_scheduler_started = app_module.GPU_PRICE_MONITOR_SCHEDULER_STARTED
        self.original_scheduler_thread = app_module.GPU_PRICE_MONITOR_SCHEDULER_THREAD
        self.original_active_thread = app_module.GPU_PRICE_MONITOR_ACTIVE_THREAD
        self.original_refresh_interval = app_module.GPU_PRICE_MONITOR_REFRESH_INTERVAL_HOURS
        self.original_families = list(app_module.GPU_PRICE_MONITOR_FAMILIES)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.SIGNAL_MONITOR_REPORTS_DIR = temp_root / "signal_reports"
        app_module.GPU_PRICE_MONITOR_CACHE_PATH = temp_root / "gpu_price_tracker.json"
        app_module.GPU_PRICE_MONITOR_RUNTIME_PATH = temp_root / "gpu_price_tracker_runtime.json"
        app_module.GPU_PRICE_MONITOR_REFRESH_INTERVAL_HOURS = 24 * 365
        app_module.GPU_PRICE_MONITOR_FAMILIES = ["H100", "B200", "B100"]
        app_module.GPU_PRICE_MONITOR_SCHEDULER_STARTED = True
        app_module.GPU_PRICE_MONITOR_SCHEDULER_THREAD = None
        app_module.GPU_PRICE_MONITOR_ACTIVE_THREAD = None
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.save_stock_store(build_minimal_stock_store())
        app_module.save_gpu_price_tracker_cache(build_sample_gpu_cache())
        app_module.save_gpu_price_monitor_runtime(
            {
                "status": "completed",
                "started_at": "2026-04-16T09:59:00",
                "finished_at": "2026-04-16T10:00:00",
                "reason": "manual_refresh",
                "message": "GPU price tracker refreshed.",
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
        app_module.GPU_PRICE_MONITOR_SCHEDULER_STARTED = self.original_scheduler_started
        app_module.GPU_PRICE_MONITOR_SCHEDULER_THREAD = self.original_scheduler_thread
        app_module.GPU_PRICE_MONITOR_ACTIVE_THREAD = self.original_active_thread
        app_module.GPU_PRICE_MONITOR_REFRESH_INTERVAL_HOURS = self.original_refresh_interval
        app_module.GPU_PRICE_MONITOR_FAMILIES = self.original_families
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_gpu_price_tab_renders_cached_snapshot(self) -> None:
        response = self.client.get("/data-monitor?tab=gpu-prices")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")

        self.assertIn("GPU Price Tracker", html)
        self.assertIn("Fixture Cloud", html)
        self.assertIn("B200", html)
        self.assertIn("B100", html)
        self.assertIn("Spot Index", html)
        self.assertIn("GPU Spot Price Index", html)
        self.assertIn("Azure CSP Reference", html)
        self.assertIn("Azure CSP Price Reference", html)
        self.assertIn("No parsed spot index yet", html)
        self.assertIn("median(price_per_gpu_hour_usd)", html)
        self.assertIn("available on-demand, 1 GPU", html)
        self.assertIn("spot/preemptible/interruptible", html)
        self.assertIn("<details class=\"stablecoin-details gpu-price-details\">", html)
        self.assertIn("$2.50/GPU/h", html)
        self.assertIn("data-gpu-price-chart", html)
        self.assertIn("data-gpu-price-refresh-form", html)
        self.assertIn("/api/ai/data/gpu-prices.json", html)

    def test_gpu_price_ai_export_returns_index_and_offers(self) -> None:
        response = self.client.get("/api/ai/data/gpu-prices.json")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()

        self.assertEqual(payload["dataset"], "gpu_prices")
        self.assertEqual(payload["summary"]["offer_count"], 3)
        self.assertIn("csp_daily_index", payload)
        self.assertIn("Fixture Cloud", {item["provider_name"] for item in payload["normalized_offers"]})
        available_rows = [
            row
            for row in payload["daily_index"]
            if row["gpu_family"] == "H100" and row["availability_mode"] == "available"
            and row["billing_type"] == "on_demand"
        ]
        spot_rows = [
            row
            for row in payload["daily_index"]
            if row["gpu_family"] == "H100" and row["availability_mode"] == "available"
            and row["billing_type"] == "spot"
        ]
        self.assertEqual(available_rows[0]["price_standardized"], 2.5)
        self.assertEqual(spot_rows[0]["price_standardized"], 1.2)


if __name__ == "__main__":
    unittest.main()
