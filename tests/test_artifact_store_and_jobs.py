from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import app as app_module


def build_artifact_job_stock_store() -> dict:
    return {
        "groups": [],
        "favorites": ["NET", "FSLY"],
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


class ArtifactStoreAndJobQueueTests(unittest.TestCase):
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
            "AI_ARTIFACT_STORE_PATH": app_module.AI_ARTIFACT_STORE_PATH,
            "AI_JOB_STORE_PATH": app_module.AI_JOB_STORE_PATH,
            "STABLECOIN_MONITOR_CACHE_PATH": app_module.STABLECOIN_MONITOR_CACHE_PATH,
            "STABLECOIN_MONITOR_RUNTIME_PATH": app_module.STABLECOIN_MONITOR_RUNTIME_PATH,
        }
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.SIGNAL_MONITOR_REPORTS_DIR = temp_root / "signal_reports"
        app_module.AI_NATIVE_DATA_DIR = temp_root / "ai_native"
        app_module.AI_NATIVE_DOCS_DIR = app_module.AI_NATIVE_DATA_DIR / "documents"
        app_module.AI_NATIVE_INDEX_DB_PATH = app_module.AI_NATIVE_DATA_DIR / "search-index.sqlite3"
        app_module.AI_ARTIFACT_STORE_PATH = app_module.AI_NATIVE_DATA_DIR / "artifacts.json"
        app_module.AI_JOB_STORE_PATH = app_module.AI_NATIVE_DATA_DIR / "jobs.json"
        app_module.STABLECOIN_MONITOR_CACHE_PATH = temp_root / "stablecoins.json"
        app_module.STABLECOIN_MONITOR_RUNTIME_PATH = temp_root / "stablecoins_runtime.json"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}

        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.SIGNAL_MONITOR_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.AI_NATIVE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        app_module.save_stock_store(build_artifact_job_stock_store())

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

    def wait_for_job_completion(self, job_id: str, timeout_seconds: float = 8.0) -> dict:
        deadline = time.time() + timeout_seconds
        last_payload: dict | None = None
        while time.time() < deadline:
            response = self.client.get(f"/api/jobs/{job_id}.json")
            self.assertEqual(response.status_code, 200)
            last_payload = response.get_json()
            status = last_payload["job"]["status"]
            if status in {"completed", "failed", "cancelled"}:
                return last_payload
            time.sleep(0.08)
        self.fail(f"job {job_id} did not finish in time; last payload={last_payload}")

    def test_queue_timeline_job_persists_saved_artifact(self) -> None:
        queue_response = self.client.post(
            "/api/jobs/artifacts/timeline.json",
            json={
                "symbols": ["NET"],
                "query": "security",
                "limit": 4,
            },
        )
        self.assertEqual(queue_response.status_code, 202)
        queue_payload = queue_response.get_json()
        job_id = queue_payload["job"]["id"]

        final_payload = self.wait_for_job_completion(job_id)
        self.assertEqual(final_payload["job"]["status"], "completed")
        artifact_id = final_payload["job"]["artifact_id"]
        self.assertTrue(artifact_id)

        artifact_response = self.client.get(f"/api/artifacts/{artifact_id}.json")
        self.assertEqual(artifact_response.status_code, 200)
        artifact_payload = artifact_response.get_json()["artifact"]
        self.assertEqual(artifact_payload["kind"], "timeline_analysis")
        self.assertIn("NET", artifact_payload["symbols"])
        self.assertIn("# Timeline Artifact", artifact_payload["markdown"])

        markdown_response = self.client.get(f"/api/artifacts/{artifact_id}.md")
        self.assertEqual(markdown_response.status_code, 200)
        self.assertIn("# Timeline Artifact", markdown_response.data.decode("utf-8"))

    def test_compare_job_is_visible_in_bootstrap_and_lists(self) -> None:
        queue_response = self.client.post(
            "/api/jobs/artifacts/compare.json",
            json={
                "symbols": "NET,FSLY",
                "query": "security",
                "per_symbol_limit": 2,
            },
        )
        self.assertEqual(queue_response.status_code, 202)
        job_id = queue_response.get_json()["job"]["id"]

        final_payload = self.wait_for_job_completion(job_id)
        self.assertEqual(final_payload["job"]["status"], "completed")

        bootstrap_response = self.client.get("/api/artifacts/bootstrap.json")
        self.assertEqual(bootstrap_response.status_code, 200)
        bootstrap_payload = bootstrap_response.get_json()
        self.assertTrue(bootstrap_payload["recent_jobs"])
        self.assertTrue(bootstrap_payload["recent_artifacts"])
        self.assertIn("timeline_job_url", bootstrap_payload["entrypoints"])
        self.assertIn("compare_job_url", bootstrap_payload["entrypoints"])

        artifact_list_response = self.client.get("/api/artifacts/list.json?kinds=compare_analysis")
        self.assertEqual(artifact_list_response.status_code, 200)
        artifact_list_payload = artifact_list_response.get_json()
        self.assertGreaterEqual(artifact_list_payload["counts"]["matched_artifacts"], 1)
        self.assertEqual(artifact_list_payload["artifacts"][0]["kind"], "compare_analysis")

        job_list_response = self.client.get("/api/jobs/list.json?statuses=completed")
        self.assertEqual(job_list_response.status_code, 200)
        job_list_payload = job_list_response.get_json()
        self.assertTrue(any(item["id"] == job_id for item in job_list_payload["jobs"]))

    def test_exports_page_exposes_artifact_queue_hooks(self) -> None:
        response = self.client.get("/exports")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("/api/artifacts/bootstrap.json", html)
        self.assertIn("/api/jobs/artifacts/timeline.json", html)
        self.assertIn("/api/jobs/artifacts/compare.json", html)
        self.assertIn("分析产物与后台队列", html)


if __name__ == "__main__":
    unittest.main()
