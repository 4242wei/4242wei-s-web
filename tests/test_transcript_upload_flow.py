from __future__ import annotations

import io
import json
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
        self.original_transcript_pdf_archive_dir = app_module.TRANSCRIPT_PDF_ARCHIVE_DIR
        self.original_direct_upload_enabled = app_module.TRANSCRIPT_DIRECT_OSS_UPLOAD_ENABLED
        self.original_background_pipeline_enabled = app_module.TRANSCRIPT_BACKGROUND_PIPELINE_ENABLED
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.TRANSCRIPT_UPLOADS_DIR = temp_root / "uploads" / "transcripts"
        app_module.TRANSCRIPT_PDF_ARCHIVE_DIR = temp_root / "uploads" / "transcripts" / "pdf"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        app_module.TRANSCRIPT_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        app_module.TRANSCRIPT_PDF_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        app_module.TRANSCRIPT_DIRECT_OSS_UPLOAD_ENABLED = False
        app_module.TRANSCRIPT_BACKGROUND_PIPELINE_ENABLED = False
        app_module.save_stock_store(build_transcript_upload_test_store())

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        app_module.STOCK_STORE_PATH = self.original_stock_store_path
        app_module.TRANSCRIPT_UPLOADS_DIR = self.original_transcript_uploads_dir
        app_module.TRANSCRIPT_PDF_ARCHIVE_DIR = self.original_transcript_pdf_archive_dir
        app_module.TRANSCRIPT_DIRECT_OSS_UPLOAD_ENABLED = self.original_direct_upload_enabled
        app_module.TRANSCRIPT_BACKGROUND_PIPELINE_ENABLED = self.original_background_pipeline_enabled
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

    def test_direct_upload_creates_one_durable_task_and_is_idempotent(self) -> None:
        app_module.TRANSCRIPT_DIRECT_OSS_UPLOAD_ENABLED = True
        app_module.TRANSCRIPT_BACKGROUND_PIPELINE_ENABLED = True
        original_queue = app_module.queue_transcript_background_pipeline
        queued_ids: list[str] = []

        token_payload = {
            "version": 1,
            "upload_id": "upload-123",
            "transcript_id": "direct1234",
            "stored_name": "20260807-direct-meeting.mp3",
            "original_name": "meeting.mp3",
            "content_type": "audio/mpeg",
            "file_size": 16,
            "client_fingerprint": "meeting.mp3:16:1:audio/mpeg",
            "bucket_name": "test-bucket",
            "object_key": "transcripts/2026/08/07/direct1234/meeting.mp3",
            "endpoint": "https://oss-cn-beijing.aliyuncs.com",
            "region_id": "cn-beijing",
            "prepared_at": "2026-08-07T12:00:00",
        }
        token = app_module.sign_transcript_direct_upload(token_payload)
        payload = {
            "transcript_title": "Direct Upload Test",
            "meeting_date": "2026-08-07",
            "meeting_date_is_manual": "1",
            "auto_process_after_upload": "on",
            "direct_upload_payload": json.dumps([{"token": token}]),
        }

        try:
            app_module.queue_transcript_background_pipeline = lambda transcript_id: queued_ids.append(transcript_id) or True

            first_response = self.client.post("/transcripts", data=payload)
            second_response = self.client.post("/transcripts", data=payload)
            self.assertEqual(first_response.status_code, 302)
            self.assertEqual(second_response.status_code, 302)

            store = app_module.load_stock_store()
            self.assertEqual(len(store["transcripts"]), 1)
            transcript = store["transcripts"][0]
            self.assertEqual(transcript["id"], "direct1234")
            self.assertEqual(transcript["direct_upload_id"], "upload-123")
            self.assertEqual(transcript["source_object_key"], token_payload["object_key"])
            self.assertEqual(transcript["local_archive_status"], "pending")
            self.assertTrue(transcript["auto_process_requested"])
            self.assertFalse(app_module.transcript_local_path(transcript).exists())
            self.assertEqual(queued_ids, ["direct1234"])
        finally:
            app_module.queue_transcript_background_pipeline = original_queue

    def test_direct_upload_prepare_returns_short_lived_signed_token(self) -> None:
        app_module.TRANSCRIPT_DIRECT_OSS_UPLOAD_ENABLED = True
        original_prepare = app_module.prepare_browser_upload
        try:
            app_module.prepare_browser_upload = lambda **kwargs: {
                "bucket_name": "test-bucket",
                "object_key": "transcripts/direct/test.mp3",
                "endpoint": "https://oss-cn-beijing.aliyuncs.com",
                "region_id": "cn-beijing",
                "upload_url": "https://test-bucket.example.com/signed-put",
                "upload_headers": {"Content-Type": "audio/mpeg"},
                "expires_at": "2026-08-07T12:30:00Z",
            }
            response = self.client.post(
                "/transcripts/direct-upload/prepare",
                json={
                    "filename": "meeting.mp3",
                    "size": 16,
                    "content_type": "audio/mpeg",
                    "client_fingerprint": "meeting.mp3:16:1:audio/mpeg",
                },
                headers={"Origin": "http://localhost"},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["upload_headers"]["Content-Type"], "audio/mpeg")
            token_payload = app_module.load_transcript_direct_upload_token(payload["token"])
            self.assertEqual(token_payload["bucket_name"], "test-bucket")
            self.assertEqual(token_payload["file_size"], 16)
        finally:
            app_module.prepare_browser_upload = original_prepare

    def test_background_failure_keeps_oss_reference_after_local_archive(self) -> None:
        original_download = app_module.download_uploaded_object
        original_submit = app_module.submit_transcript_job_to_tingwu
        transcript = app_module.normalize_transcript_entry(
            {
                "id": "pipeline12",
                "title": "Pipeline Test",
                "meeting_date": "2026-08-07",
                "created_at": "2026-08-07T12:00:00",
                "updated_at": "2026-08-07T12:00:00",
                "stored_name": "pipeline-audio.mp3",
                "original_name": "pipeline-audio.mp3",
                "source_bucket_name": "test-bucket",
                "source_object_key": "transcripts/pipeline-audio.mp3",
                "direct_upload_id": "pipeline-upload-1",
                "source_file_size": 16,
                "local_archive_status": "pending",
                "auto_process_requested": True,
            }
        )
        self.assertIsNotNone(transcript)
        store = app_module.load_stock_store()
        store["transcripts"].append(transcript)
        app_module.save_stock_store(store)

        try:
            def fake_download(**kwargs):
                target_path = Path(kwargs["target_path"])
                target_path.write_bytes(b"fake audio bytes")
                return {"content_length": 16, "path": str(target_path)}

            def fake_submit(entry):
                raise RuntimeError("simulated Tingwu outage")

            app_module.download_uploaded_object = fake_download
            app_module.submit_transcript_job_to_tingwu = fake_submit
            app_module.run_transcript_background_pipeline("pipeline12")

            persisted = app_module.load_stock_store()["transcripts"][0]
            self.assertTrue(app_module.transcript_local_path(persisted).exists())
            self.assertEqual(persisted["local_archive_status"], "ready")
            self.assertEqual(persisted["source_bucket_name"], "test-bucket")
            self.assertEqual(persisted["source_object_key"], "transcripts/pipeline-audio.mp3")
            self.assertIn("simulated Tingwu outage", persisted["last_error"])
        finally:
            app_module.download_uploaded_object = original_download
            app_module.submit_transcript_job_to_tingwu = original_submit

    def test_completed_transcript_pdf_is_archived_on_mac(self) -> None:
        transcript = app_module.normalize_transcript_entry(
            {
                "id": "pdfarchive1",
                "title": "中文访谈归档测试",
                "meeting_date": "2026-08-07",
                "created_at": "2026-08-07T12:00:00",
                "updated_at": "2026-08-07T12:00:00",
                "stored_name": "pdf-source.mp3",
                "original_name": "pdf-source.mp3",
                "status": "completed",
                "transcript_text": "[00:00 | 说话人 1] 这是 PDF 本地归档测试。\n\n[00:08 | 说话人 2] 内容应当可以正常阅读。",
            }
        )
        self.assertIsNotNone(transcript)
        archive_path = app_module.archive_transcript_pdf(transcript)
        self.assertIsNotNone(archive_path)
        self.assertTrue(archive_path.exists())
        self.assertGreater(archive_path.stat().st_size, 1000)
        self.assertEqual(archive_path.read_bytes()[:4], b"%PDF")
        self.assertEqual(transcript["pdf_archive_status"], "ready")

    def test_background_pipeline_syncs_result_and_archives_pdf_without_open_page(self) -> None:
        original_sync = app_module.sync_transcript_job_from_tingwu
        transcript = app_module.normalize_transcript_entry(
            {
                "id": "autosyncpdf",
                "title": "Background Sync Test",
                "meeting_date": "2026-08-07",
                "created_at": "2026-08-07T12:00:00",
                "updated_at": "2026-08-07T12:00:00",
                "stored_name": "autosync-source.mp3",
                "original_name": "autosync-source.mp3",
                "status": "processing",
                "provider_task_id": "task-auto-sync",
                "provider_task_status": "ONGOING",
                "auto_process_requested": True,
                "local_archive_status": "ready",
            }
        )
        self.assertIsNotNone(transcript)
        app_module.transcript_local_path(transcript).write_bytes(b"local audio")
        store = app_module.load_stock_store()
        store["transcripts"].append(transcript)
        app_module.save_stock_store(store)

        try:
            def fake_sync(entry):
                entry["provider_task_status"] = "COMPLETED"
                entry["status"] = "completed"
                entry["transcript_text"] = "后台轮询已取得完整转录结果。"
                entry["transcript_html"] = app_module.plain_text_to_html(entry["transcript_text"])
                entry["updated_at"] = app_module.now_iso()
                return {"task_status": "COMPLETED"}

            app_module.sync_transcript_job_from_tingwu = fake_sync
            app_module.run_transcript_background_pipeline("autosyncpdf")

            persisted = app_module.load_stock_store()["transcripts"][0]
            self.assertEqual(persisted["status"], "completed")
            self.assertEqual(persisted["pdf_archive_status"], "ready")
            self.assertTrue(app_module.transcript_pdf_archive_path(persisted).is_file())
        finally:
            app_module.sync_transcript_job_from_tingwu = original_sync


if __name__ == "__main__":
    unittest.main()
