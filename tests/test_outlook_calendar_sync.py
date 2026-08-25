from __future__ import annotations

import json
import stat
import tempfile
import unittest
from unittest import mock
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from outlook_calendar_sync import (
    CalendarSyncError,
    DEFAULT_POLL_SECONDS,
    MIN_POLL_SECONDS,
    calendar_poll_seconds,
    calendar_view_payload,
    configure_calendar_source,
    import_calendar_content,
    parse_ics_events,
    sanitize_calendar_text,
    save_calendar_config,
)


SAMPLE_ICS = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:private-outlook-id@example.com\r
DTSTART:20260814T100000Z\r
DTEND:20260814T110000Z\r
SUMMARY:FUNDA Expert Interview - Kevin Cassar\r
LOCATION:TalkTalk / Teams https://teams.example/join\r
DESCRIPTION:Kevin Cassar at TalkTalk\\ncontact@example.com\\nhttps://teams.example/join\r
END:VEVENT\r
END:VCALENDAR\r
"""


class OutlookCalendarSyncTest(unittest.TestCase):
    def test_default_polling_is_four_hours_and_invalid_values_are_safe(self):
        self.assertEqual(DEFAULT_POLL_SECONDS, 4 * 60 * 60)
        with mock.patch.dict("os.environ", {"OUTLOOK_CALENDAR_POLL_SECONDS": "invalid"}):
            self.assertEqual(calendar_poll_seconds(), DEFAULT_POLL_SECONDS)
        with mock.patch.dict("os.environ", {"OUTLOOK_CALENDAR_POLL_SECONDS": "30"}):
            self.assertEqual(calendar_poll_seconds(), MIN_POLL_SECONDS)

    def test_parser_converts_to_beijing_and_redacts_sensitive_fields(self):
        events = parse_ics_events(SAMPLE_ICS, now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["start"].startswith("2026-08-14T18:00:00"))
        serialized = json.dumps(events[0], ensure_ascii=False)
        self.assertNotIn("private-outlook-id", serialized)
        self.assertNotIn("contact@example.com", serialized)
        self.assertNotIn("https://teams.example", serialized)
        self.assertEqual(len(events[0]["event_id"]), 24)

    def test_duplicate_calendar_events_are_collapsed_even_when_uid_changes(self):
        duplicate = SAMPLE_ICS.replace(
            b"END:VCALENDAR",
            b"BEGIN:VEVENT\r\nUID:another-id@example.com\r\nDTSTART:20260814T100000Z\r\nDTEND:20260814T110000Z\r\nSUMMARY:FUNDA Expert Interview - Kevin Cassar\r\nLOCATION:TalkTalk / Teams https://teams.example/join\r\nEND:VEVENT\r\nEND:VCALENDAR",
        )
        events = parse_ics_events(duplicate, now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(events), 1)

    def test_duplicate_expert_slot_and_future_communication_numbers_are_stable(self):
        content = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:first\r
DTSTART:20260814T100000Z\r
DTEND:20260814T110000Z\r
SUMMARY:Kevin Cassar TalkTalk interview\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:duplicate-with-new-title\r
DTSTART:20260814T100000Z\r
DTEND:20260814T110000Z\r
SUMMARY:TalkTalk interview with Kevin Cassar\r
LOCATION:Teams room changed\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:follow-up\r
DTSTART:20260815T100000Z\r
DTEND:20260815T110000Z\r
SUMMARY:Kevin Cassar TalkTalk follow-up\r
END:VEVENT\r
END:VCALENDAR\r
"""
        experts = [{"id": "expert-8", "name": "Kevin Cassar", "current_employer": "TalkTalk", "interviews": []}]
        events = parse_ics_events(content, now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")))
        from outlook_calendar_sync import match_calendar_events

        matched = match_calendar_events(events, experts, Path("missing.json"), allow_model=False)
        self.assertEqual(len(matched), 2)
        self.assertEqual([item["interview_sequence"] for item in matched], [1, 2])

    def test_sanitizer_removes_mail_url_and_phone(self):
        text = sanitize_calendar_text("A a@example.com https://example.com +1 212 555 1212")
        self.assertNotIn("example.com", text)
        self.assertNotIn("555", text)

    def test_only_official_https_outlook_url_is_saved_owner_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "calendar.json"
            save_calendar_config(config_path, "https://outlook.live.com/owa/calendar/example/calendar.ics")
            self.assertEqual(stat.S_IMODE(config_path.stat().st_mode), 0o600)
            with self.assertRaises(CalendarSyncError):
                save_calendar_config(config_path, "https://example.com/calendar.ics")
            with self.assertRaises(CalendarSyncError):
                save_calendar_config(config_path, "http://outlook.live.com/calendar.ics")

    def test_import_matches_locally_without_model_and_keeps_cache_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache_path = temp_path / "cache.json"
            result = import_calendar_content(
                SAMPLE_ICS,
                cache_path,
                [{"id": "expert-8", "name": "Kevin Cassar", "current_employer": "TalkTalk", "current_title": "CDAO"}],
                temp_path / "missing-provider.json",
                now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            self.assertEqual(result["events"][0]["expert_id"], "expert-8")
            self.assertEqual(result["events"][0]["match_status"], "matched_local")
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertNotIn("ics_url", cached)
            self.assertNotIn("contact@example.com", json.dumps(cached))

    def test_unrelated_and_company_only_events_never_enter_expert_calendar(self):
        content = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:ordinary-project\r
DTSTART:20260814T030000Z\r
DTEND:20260814T040000Z\r
SUMMARY:TalkTalk project review\r
END:VEVENT\r
BEGIN:VEVENT\r
UID:known-expert\r
DTSTART:20260814T100000Z\r
DTEND:20260814T110000Z\r
SUMMARY:Kevin Cassar at TalkTalk\r
END:VEVENT\r
END:VCALENDAR\r
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache.json"
            result = import_calendar_content(
                content,
                cache_path,
                [{"id": "expert-8", "name": "Kevin Cassar", "current_employer": "TalkTalk"}],
                Path(temp_dir) / "provider.json",
                now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            self.assertEqual(result["event_count"], 1)
            cached = json.loads(cache_path.read_text())
            self.assertEqual(cached["filtered_count"], 1)
            self.assertNotIn("ordinary-project", json.dumps(cached))
            self.assertEqual(cached["events"][0]["expert_id"], "expert-8")

    def test_conflicting_person_or_source_number_is_filtered_even_at_same_company(self):
        content = b"""BEGIN:VCALENDAR\r
VERSION:2.0\r
BEGIN:VEVENT\r
UID:wrong-person\r
DTSTART:20260814T100000Z\r
DTEND:20260814T110000Z\r
SUMMARY:FUNDA Expert Interview - #21 Tom@Novartis\r
END:VEVENT\r
END:VCALENDAR\r
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = import_calendar_content(
                content,
                Path(temp_dir) / "cache.json",
                [{"id": "expert-19", "source_record_id": "#19", "name": "Kevin Charef", "current_employer": "Novartis"}],
                Path(temp_dir) / "provider.json",
                now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")),
            )
            self.assertEqual(result["event_count"], 0)

    def test_job_title_at_company_in_description_is_not_treated_as_person_conflict(self):
        from outlook_calendar_sync import _identity_grounded

        self.assertTrue(
            _identity_grounded(
                {
                    "title": "FUNDA Expert Interview",
                    "location": "",
                    "description": "Expert Profile: Director Of Analytics @ Ares Interactive",
                },
                {
                    "id": "expert-13",
                    "source_record_id": "#13",
                    "name": "Matt Cangialosi",
                    "current_employer": "Ares Interactive",
                },
            )
        )

    def test_view_filters_unmatched_items_from_an_old_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_path = root / "cache.json"
            cache_path.write_text(json.dumps({"status": "ready", "events": [
                {"event_id": "old-unmatched", "title": "ordinary meeting", "start": "2026-08-14T10:00:00+08:00", "end": "2026-08-14T11:00:00+08:00", "match_status": "pending_review", "expert_id": ""},
                {"event_id": "matched", "title": "Kevin", "start": "2026-08-14T18:00:00+08:00", "end": "2026-08-14T19:00:00+08:00", "match_status": "matched_local", "expert_id": "expert-8"},
            ]}))
            payload = calendar_view_payload(root / "config.json", cache_path, allowed_expert_ids={"expert-8"})
            self.assertEqual(payload["event_count"], 1)
            self.assertEqual(payload["filtered_count"], 1)
            self.assertEqual(payload["events"][0]["event_id"], "matched")

    def test_configuration_is_replaced_only_after_new_feed_validates(self):
        class Response:
            status_code = 200
            content = SAMPLE_ICS
            headers = {"ETag": "v1"}

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.json"
            cache_path = temp_path / "cache.json"
            result = configure_calendar_source(
                "https://outlook.live.com/owa/calendar/example/calendar.ics",
                config_path,
                cache_path,
                [{"id": "expert-8", "name": "Kevin Cassar", "current_employer": "TalkTalk"}],
                temp_path / "provider.json",
                now=datetime(2026, 8, 13, tzinfo=ZoneInfo("Asia/Shanghai")),
                http_get=lambda *args, **kwargs: Response(),
            )
            self.assertTrue(result["configured"])
            self.assertEqual(result["event_count"], 1)
            self.assertEqual(json.loads(cache_path.read_text())["etag"], "")
