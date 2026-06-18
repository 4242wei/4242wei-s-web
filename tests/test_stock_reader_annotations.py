from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import app as app_module


def build_reader_test_store() -> dict:
    return {
        "groups": [],
        "favorites": ["FTAI"],
        "stocks": {
            "FTAI": {
                "display_name": "FTAI",
                "earnings": {
                    "next_date": "2026-05-10",
                    "last_synced_at": "2026-04-01T08:30:00",
                    "source_label": "Manual",
                },
                "setup_reader_annotations": [],
                "setup_reading_record": {},
                "notes": [
                    {
                        "id": "note-1",
                        "title": "Channel Check",
                        "content_text": "Supply improved quickly and buyers returned.",
                        "content_html": "<p>Supply improved quickly and buyers returned.</p>",
                        "created_at": "2026-04-01T08:00:00",
                        "record_date": "2026-04-01",
                        "tags": ["supply"],
                    }
                ],
                "files": [
                    {
                        "id": "file-1",
                        "stored_name": "ftai-brief.txt",
                        "original_name": "ftai-brief.txt",
                        "description": "Prepared notes for the desk.",
                        "uploaded_at": "2026-04-01T07:00:00",
                        "record_date": "2026-04-01",
                        "storage_symbol": "FTAI",
                        "linked_symbols": ["FTAI"],
                    }
                ],
                "earnings_calls": [
                    {
                        "id": "call-1",
                        "title": "FTAI Q4 Earnings Call",
                        "original_title": "FTAI Q4 Earnings Call",
                        "published_at": "2026-04-01T09:00:00",
                        "call_date": "2026-02-27",
                        "summary_text": "Alpha beta gamma delta",
                        "transcript_text": "Alpha beta gamma delta",
                        "transcript_html": "<p>Alpha beta gamma delta</p>",
                    }
                ],
            }
        },
        "experts": [
            {
                "id": "expert-1",
                "name": "Casey Partner",
                "category": "industry",
                "stage": "active",
                "related_symbols": ["FTAI"],
                "resource_refs": [
                    {"kind": "note", "symbol": "FTAI", "resource_id": "note-1"},
                    {"kind": "schedule", "symbol": "", "resource_id": "schedule-1"},
                ],
                "interviews": [],
                "created_at": "2026-04-01T06:00:00",
                "updated_at": "2026-04-01T06:00:00",
            }
        ],
        "schedule_items": [
            {
                "id": "schedule-1",
                "title": "FTAI Call Prep",
                "scheduled_date": "2026-04-02",
                "note": "Prepare follow-up questions about margins and pricing.",
                "created_at": "2026-04-01T06:30:00",
                "updated_at": "2026-04-01T06:30:00",
            }
        ],
        "trash": [],
        "report_reader_state": {},
        "transcripts": [
            {
                "id": "transcript-1",
                "title": "Operator Review",
                "stored_name": "operator-review.mp3",
                "original_name": "operator-review.mp3",
                "created_at": "2026-04-01T10:00:00",
                "updated_at": "2026-04-01T10:00:00",
                "meeting_date": "2026-04-01",
                "status": "completed",
                "linked_symbol": "FTAI",
                "linked_symbols": ["FTAI"],
                "transcript_text": "One two three four",
                "transcript_html": "<p>One two three four</p>",
            }
        ],
    }


class StockReaderAnnotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)

        self.original_stock_store_path = app_module.STOCK_STORE_PATH
        self.original_stock_uploads_dir = app_module.STOCK_UPLOADS_DIR
        self.original_reports_dir = app_module.REPORTS_DIR
        self.original_testing = app_module.app.config.get("TESTING", False)
        self.original_stock_cache = dict(app_module.STOCK_STORE_CACHE)
        self.original_report_index_cache = dict(app_module.REPORT_INDEX_CACHE)
        self.original_report_html_cache = dict(app_module.REPORT_HTML_CACHE)

        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.STOCK_UPLOADS_DIR = temp_root / "uploads"
        app_module.REPORTS_DIR = temp_root / "reports"
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        app_module.REPORT_INDEX_CACHE = {"signature": None, "items": [], "by_filename": {}}
        app_module.REPORT_HTML_CACHE = {}

        (app_module.STOCK_UPLOADS_DIR / "FTAI").mkdir(parents=True, exist_ok=True)
        (app_module.STOCK_UPLOADS_DIR / "FTAI" / "ftai-brief.txt").write_text(
            "Alpha line one\nAlpha line two\nAlpha line three",
            encoding="utf-8",
        )
        app_module.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (app_module.REPORTS_DIR / "2026-04-01-ftai-monitor.md").write_text(
            "# FTAI Monitor\n\nAlpha beta gamma delta",
            encoding="utf-8",
        )

        app_module.save_stock_store(build_reader_test_store())

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        app_module.STOCK_STORE_PATH = self.original_stock_store_path
        app_module.STOCK_UPLOADS_DIR = self.original_stock_uploads_dir
        app_module.REPORTS_DIR = self.original_reports_dir
        app_module.STOCK_STORE_CACHE = self.original_stock_cache
        app_module.REPORT_INDEX_CACHE = self.original_report_index_cache
        app_module.REPORT_HTML_CACHE = self.original_report_html_cache
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_earnings_call_reader_state_persists_open_and_highlight(self) -> None:
        open_response = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={"action": "open"},
        )
        self.assertEqual(open_response.status_code, 200)
        open_payload = open_response.get_json()
        self.assertTrue(open_payload["ok"])
        content_signature = open_payload["state"]["content_signature"]

        save_response = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "highlight",
                "start_offset": 0,
                "end_offset": 5,
                "quote_text": "Alpha",
                "content_signature": content_signature,
            },
        )
        self.assertEqual(save_response.status_code, 200)
        save_payload = save_response.get_json()
        self.assertEqual(len(save_payload["state"]["annotations"]), 1)
        self.assertEqual(save_payload["state"]["activity"]["open_count"], 1)

        store = app_module.load_stock_store()
        call = app_module.get_stock_earnings_call_entry(store, "FTAI", "call-1")
        self.assertEqual(call["reading_record"]["open_count"], 1)
        self.assertEqual(len(call["reader_annotations"]), 1)
        self.assertEqual(call["reader_annotations"][0]["kind"], "highlight")

    def test_transcript_reader_state_persists_note(self) -> None:
        open_response = self.client.post(
            "/transcripts/transcript-1/reader-state",
            json={"action": "open"},
        )
        self.assertEqual(open_response.status_code, 200)
        content_signature = open_response.get_json()["state"]["content_signature"]

        save_response = self.client.post(
            "/transcripts/transcript-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "note",
                "start_offset": 4,
                "end_offset": 7,
                "quote_text": "two",
                "note_text": "check this phrasing",
                "content_signature": content_signature,
            },
        )
        self.assertEqual(save_response.status_code, 200)
        payload = save_response.get_json()
        self.assertEqual(payload["state"]["activity"]["annotation_count"], 1)

        store = app_module.load_stock_store()
        transcript = app_module.get_transcript_entry(store, "transcript-1")
        self.assertEqual(len(transcript["reader_annotations"]), 1)
        self.assertEqual(transcript["reader_annotations"][0]["note_text"], "check this phrasing")

    def test_note_reader_state_persists_highlight(self) -> None:
        open_response = self.client.post(
            "/stocks/FTAI/notes/note-1/reader-state",
            json={"action": "open"},
        )
        self.assertEqual(open_response.status_code, 200)
        signature = open_response.get_json()["state"]["content_signature"]

        save_response = self.client.post(
            "/stocks/FTAI/notes/note-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "highlight",
                "start_offset": 0,
                "end_offset": 6,
                "quote_text": "Supply",
                "content_signature": signature,
            },
        )
        self.assertEqual(save_response.status_code, 200)

        store = app_module.load_stock_store()
        note = app_module.get_stock_note_entry(store, "FTAI", "note-1")
        self.assertEqual(len(note["reader_annotations"]), 1)
        self.assertEqual(note["reader_annotations"][0]["kind"], "highlight")

    def test_note_and_underline_can_share_same_range_and_delete_independently(self) -> None:
        open_response = self.client.post(
            "/stocks/FTAI/notes/note-1/reader-state",
            json={"action": "open"},
        )
        self.assertEqual(open_response.status_code, 200)
        signature = open_response.get_json()["state"]["content_signature"]

        underline_response = self.client.post(
            "/stocks/FTAI/notes/note-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "underline",
                "start_offset": 0,
                "end_offset": 6,
                "quote_text": "Supply",
                "content_signature": signature,
            },
        )
        self.assertEqual(underline_response.status_code, 200)

        note_response = self.client.post(
            "/stocks/FTAI/notes/note-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "note",
                "start_offset": 0,
                "end_offset": 6,
                "quote_text": "Supply",
                "note_text": "track this wording",
                "content_signature": signature,
            },
        )
        self.assertEqual(note_response.status_code, 200)
        payload = note_response.get_json()
        self.assertEqual(len(payload["state"]["annotations"]), 2)
        note_annotation = next(
            annotation
            for annotation in payload["state"]["annotations"]
            if annotation["kind"] == "note"
        )

        delete_response = self.client.post(
            "/stocks/FTAI/notes/note-1/reader-state",
            json={
                "action": "delete_annotation",
                "annotation_id": note_annotation["id"],
                "content_signature": signature,
            },
        )
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.get_json()
        self.assertEqual(len(delete_payload["state"]["annotations"]), 1)
        self.assertEqual(delete_payload["state"]["annotations"][0]["kind"], "underline")

        store = app_module.load_stock_store()
        note = app_module.get_stock_note_entry(store, "FTAI", "note-1")
        self.assertEqual(len(note["reader_annotations"]), 1)
        self.assertEqual(note["reader_annotations"][0]["kind"], "underline")

    def test_highlight_and_underline_can_partially_overlap(self) -> None:
        signature = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={"action": "open"},
        ).get_json()["state"]["content_signature"]

        underline_response = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "underline",
                "start_offset": 0,
                "end_offset": 10,
                "quote_text": "Alpha beta",
                "content_signature": signature,
            },
        )
        self.assertEqual(underline_response.status_code, 200)

        highlight_response = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "highlight",
                "start_offset": 6,
                "end_offset": 16,
                "quote_text": "beta gamma",
                "content_signature": signature,
            },
        )
        self.assertEqual(highlight_response.status_code, 200)
        payload = highlight_response.get_json()
        self.assertEqual(len(payload["state"]["annotations"]), 2)
        self.assertEqual(
            sorted(annotation["kind"] for annotation in payload["state"]["annotations"]),
            ["highlight", "underline"],
        )

    def test_stock_setup_reader_state_persists_progress(self) -> None:
        open_response = self.client.post(
            "/stocks/FTAI/setup/reader-state",
            json={"action": "open"},
        )
        self.assertEqual(open_response.status_code, 200)
        signature = open_response.get_json()["state"]["content_signature"]

        progress_response = self.client.post(
            "/stocks/FTAI/setup/reader-state",
            json={
                "action": "progress",
                "scroll_ratio": 0.42,
                "content_signature": signature,
            },
        )
        self.assertEqual(progress_response.status_code, 200)
        payload = progress_response.get_json()
        self.assertEqual(payload["state"]["activity"]["progress_percent"], 42)

        store = app_module.load_stock_store()
        stock_entry = app_module.ensure_stock_entry(store, "FTAI")
        self.assertAlmostEqual(stock_entry["setup_reading_record"]["last_scroll_ratio"], 0.42)

    def test_report_reader_state_persists_highlight(self) -> None:
        open_response = self.client.post(
            "/reports/2026-04-01-ftai-monitor.md/reader-state",
            json={"action": "open"},
        )
        self.assertEqual(open_response.status_code, 200)
        signature = open_response.get_json()["state"]["content_signature"]

        save_response = self.client.post(
            "/reports/2026-04-01-ftai-monitor.md/reader-state",
            json={
                "action": "add_annotation",
                "kind": "highlight",
                "start_offset": 0,
                "end_offset": 4,
                "quote_text": "FTAI",
                "content_signature": signature,
            },
        )
        self.assertEqual(save_response.status_code, 200)
        payload = save_response.get_json()
        self.assertEqual(len(payload["state"]["annotations"]), 1)

        store = app_module.load_stock_store()
        report_state = store["report_reader_state"]["2026-04-01-ftai-monitor.md"]
        self.assertEqual(len(report_state["reader_annotations"]), 1)
        self.assertEqual(report_state["reader_annotations"][0]["kind"], "highlight")

    def test_reader_state_rejects_overlapping_annotations(self) -> None:
        signature = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={"action": "open"},
        ).get_json()["state"]["content_signature"]

        first_response = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "underline",
                "start_offset": 0,
                "end_offset": 5,
                "quote_text": "Alpha",
                "content_signature": signature,
            },
        )
        self.assertEqual(first_response.status_code, 200)

        overlap_response = self.client.post(
            "/stocks/FTAI/earnings-calls/call-1/reader-state",
            json={
                "action": "add_annotation",
                "kind": "underline",
                "start_offset": 3,
                "end_offset": 8,
                "quote_text": "ha be",
                "content_signature": signature,
            },
        )
        self.assertEqual(overlap_response.status_code, 400)
        self.assertFalse(overlap_response.get_json()["ok"])

    def test_stock_detail_page_lazy_loads_call_and_transcript_bodies(self) -> None:
        response = self.client.get("/stocks/FTAI")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("data-reader-bootstrap", page)
        self.assertIn("/stocks/FTAI/notes/note-1/reader-state", page)
        self.assertIn("/stocks/FTAI/setup/reader-state", page)
        self.assertIn("/stocks/FTAI/earnings-calls/call-1/preview-fragment", page)
        self.assertIn("/transcripts/transcript-1/preview-fragment", page)
        self.assertNotIn("/stocks/FTAI/earnings-calls/call-1/reader-state", page)
        self.assertNotIn("/transcripts/transcript-1/reader-state", page)
        self.assertNotIn("<p>Alpha beta gamma delta</p>", page)
        self.assertNotIn("<p>One two three four</p>", page)

    def test_file_preview_fragment_renders_reader_bootstrap(self) -> None:
        response = self.client.get(
            "/stocks/FTAI/files/file-1/preview-fragment",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("data-reader-bootstrap", page)
        self.assertIn("/stocks/FTAI/files/file-1/reader-state", page)

    def test_expert_resource_preview_renders_reader_bootstrap(self) -> None:
        token = app_module.build_expert_resource_token(
            {"kind": "note", "symbol": "FTAI", "resource_id": "note-1"}
        )
        response = self.client.get(
            f"/experts/resources/preview?token={token}",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("data-reader-bootstrap", page)
        self.assertIn("/stocks/FTAI/notes/note-1/reader-state", page)

    def test_transcript_preview_fragment_renders_reader_bootstrap(self) -> None:
        response = self.client.get(
            "/transcripts/transcript-1/preview-fragment",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("data-reader-bootstrap", page)
        self.assertIn("/transcripts/transcript-1/reader-state", page)

    def test_earnings_call_preview_fragment_renders_reader_bootstrap(self) -> None:
        response = self.client.get(
            "/stocks/FTAI/earnings-calls/call-1/preview-fragment",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("data-reader-bootstrap", page)
        self.assertIn("/stocks/FTAI/earnings-calls/call-1/reader-state", page)

    def test_transcripts_page_does_not_inline_transcript_html(self) -> None:
        response = self.client.get("/transcripts")
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("/transcripts/transcript-1/preview-fragment", page)
        self.assertNotIn("/transcripts/transcript-1/reader-state", page)
        self.assertNotIn("<p>One two three four</p>", page)

    def test_report_preview_fragment_renders_reader_bootstrap(self) -> None:
        response = self.client.get(
            "/reports/2026-04-01-ftai-monitor.md/preview-fragment",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn("data-reader-bootstrap", page)
        self.assertIn("/reports/2026-04-01-ftai-monitor.md/reader-state", page)


if __name__ == "__main__":
    unittest.main()
