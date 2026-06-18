from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

import app as app_module


def build_transcript_upload_test_store() -> dict:
    return {
        "groups": [],
        "favorites": [],
        "stocks": {},
        "experts": [],
        "schedule_items": [],
        "trash": [],
        "transcripts": [],
    }


class TranscriptUploadFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_stock_store_path = app_module.STOCK_STORE_PATH
        self.original_transcript_uploads_dir = app_module.TRANSCRIPT_UPLOADS_DIR
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.TRANSCRIPT_UPLOADS_DIR = temp_root / "uploads" / "transcripts"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        app_module.TRANSCRIPT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.save_stock_store(build_transcript_upload_test_store())

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        app_module.STOCK_STORE_PATH = self.original_stock_store_path
        app_module.TRANSCRIPT_UPLOADS_DIR = self.original_transcript_uploads_dir
        app_module.STOCK_STORE_CACHE = self.original_stock_cache
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def _post_transcript(self, *, auto_process: bool = False):
        payload = {
            "transcript_title": "Remote Upload Test",
            "meeting_date": "2026-04-11",
            "meeting_date_is_manual": "1",
            "transcript_media": (io.BytesIO(b"fake audio bytes"), "meeting.mp3"),
        }
        if auto_process:
            payload["auto_process_after_upload"] = "on"
        return self.client.post("/transcripts", data=payload, content_type="multipart/form-data")

    def test_create_transcript_job_defaults_to_local_only_save(self) -> None:
        calls = {"tingwu_status": 0, "oss_status": 0, "ensure": 0, "submit": 0}
        original_build_tingwu_status = app_module.build_tingwu_status
        original_build_oss_status = app_module.build_oss_status
        original_ensure_transcript_source_url = app_module.ensure_transcript_source_url
        original_submit_transcript_job_to_tingwu = app_module.submit_transcript_job_to_tingwu

        try:
            def fake_tingwu_status():
                calls["tingwu_status"] += 1
                return {"is_ready": True}

            def fake_oss_status():
                calls["oss_status"] += 1
                return {"is_ready": True, "bridge_ready": True, "error_message": ""}

            def fake_ensure_source_url(transcript):
                calls["ensure"] += 1
                transcript["file_url_hint"] = "https://example.com/audio.mp3"
                return transcript["file_url_hint"]

            def fake_submit_job(transcript):
                calls["submit"] += 1
                transcript["provider_task_id"] = "task-1"
                transcript["provider_task_status"] = "SUBMITTED"
                transcript["status"] = app_module.normalize_provider_task_status("SUBMITTED")
                return {"task_id": "task-1"}

            app_module.build_tingwu_status = fake_tingwu_status
            app_module.build_oss_status = fake_oss_status
            app_module.ensure_transcript_source_url = fake_ensure_source_url
            app_module.submit_transcript_job_to_tingwu = fake_submit_job

            response = self._post_transcript()
            self.assertEqual(response.status_code, 302)

            store = app_module.load_stock_store()
            self.assertEqual(len(store.get("transcripts", [])), 1)
            transcript = store["transcripts"][0]
            self.assertEqual(calls["tingwu_status"], 0)
            self.assertEqual(calls["oss_status"], 0)
            self.assertEqual(calls["ensure"], 0)
            self.assertEqual(calls["submit"], 0)
            self.assertEqual(transcript["provider_task_id"], "")
            self.assertEqual(transcript["status"], "pending_api")
            self.assertFalse(transcript["file_url_hint"])
            self.assertTrue((app_module.TRANSCRIPT_UPLOADS_DIR / transcript["stored_name"]).exists())
        finally:
            app_module.build_tingwu_status = original_build_tingwu_status
            app_module.build_oss_status = original_build_oss_status
            app_module.ensure_transcript_source_url = original_ensure_transcript_source_url
            app_module.submit_transcript_job_to_tingwu = original_submit_transcript_job_to_tingwu

    def test_create_transcript_job_can_opt_in_to_auto_process(self) -> None:
        calls = {"tingwu_status": 0, "oss_status": 0, "ensure": 0, "submit": 0}
        original_build_tingwu_status = app_module.build_tingwu_status
        original_build_oss_status = app_module.build_oss_status
        original_ensure_transcript_source_url = app_module.ensure_transcript_source_url
        original_submit_transcript_job_to_tingwu = app_module.submit_transcript_job_to_tingwu

        try:
            def fake_tingwu_status():
                calls["tingwu_status"] += 1
                return {"is_ready": True}

            def fake_oss_status():
                calls["oss_status"] += 1
                return {"is_ready": True, "bridge_ready": True, "error_message": ""}

            def fake_ensure_source_url(transcript):
                calls["ensure"] += 1
                transcript["file_url_hint"] = "https://example.com/audio.mp3"
                transcript["source_object_key"] = "transcripts/audio.mp3"
                return transcript["file_url_hint"]

            def fake_submit_job(transcript):
                calls["submit"] += 1
                transcript["provider_task_id"] = "task-1"
                transcript["provider_task_status"] = "SUBMITTED"
                transcript["provider_request_id"] = "req-1"
                transcript["submitted_at"] = "2026-04-11T12:00:00"
                transcript["last_synced_at"] = "2026-04-11T12:00:00"
                transcript["last_error"] = ""
                transcript["status"] = app_module.normalize_provider_task_status("SUBMITTED")
                transcript["updated_at"] = "2026-04-11T12:00:00"
                return {"task_id": "task-1", "task_status": "SUBMITTED", "request_id": "req-1"}

            app_module.build_tingwu_status = fake_tingwu_status
            app_module.build_oss_status = fake_oss_status
            app_module.ensure_transcript_source_url = fake_ensure_source_url
            app_module.submit_transcript_job_to_tingwu = fake_submit_job

            response = self._post_transcript(auto_process=True)
            self.assertEqual(response.status_code, 302)

            store = app_module.load_stock_store()
            self.assertEqual(len(store.get("transcripts", [])), 1)
            transcript = store["transcripts"][0]
            self.assertEqual(calls["tingwu_status"], 1)
            self.assertEqual(calls["oss_status"], 1)
            self.assertGreaterEqual(calls["ensure"], 1)
            self.assertEqual(calls["submit"], 1)
            self.assertEqual(transcript["provider_task_id"], "task-1")
            self.assertEqual(transcript["provider_task_status"], "SUBMITTED")
            self.assertEqual(transcript["status"], "queued")
            self.assertEqual(transcript["file_url_hint"], "https://example.com/audio.mp3")
        finally:
            app_module.build_tingwu_status = original_build_tingwu_status
            app_module.build_oss_status = original_build_oss_status
            app_module.ensure_transcript_source_url = original_ensure_transcript_source_url
            app_module.submit_transcript_job_to_tingwu = original_submit_transcript_job_to_tingwu

    def test_static_assets_return_cache_friendly_headers(self) -> None:
        versioned_response = self.client.get("/static/flash-messages.js?v=test-build")
        plain_response = self.client.get("/static/flash-messages.js")
        try:
            self.assertEqual(versioned_response.status_code, 200)
            self.assertEqual(
                versioned_response.headers.get("Cache-Control"),
                "public, max-age=31536000, immutable",
            )
            self.assertEqual(plain_response.status_code, 200)
            self.assertEqual(plain_response.headers.get("Cache-Control"), "public, max-age=3600")
        finally:
            versioned_response.close()
            plain_response.close()

    def test_transcripts_page_avoids_loading_cloud_sdks_on_initial_render(self) -> None:
        original_oss_client_api = app_module.OSS_CLIENT_API
        original_tingwu_client_api = app_module.TINGWU_CLIENT_API

        try:
            app_module.OSS_CLIENT_API = None
            app_module.TINGWU_CLIENT_API = None

            response = self.client.get("/transcripts")
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(app_module.OSS_CLIENT_API)
            self.assertIsNone(app_module.TINGWU_CLIENT_API)
        finally:
            app_module.OSS_CLIENT_API = original_oss_client_api
            app_module.TINGWU_CLIENT_API = original_tingwu_client_api


if __name__ == "__main__":
    unittest.main()
