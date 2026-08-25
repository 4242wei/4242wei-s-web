from __future__ import annotations

import tempfile
import unittest
import json
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

from expert_interview_linker import apply_safe_links, build_link_scan, load_link_cache, save_link_cache


class ExpertInterviewLinkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.experts = [
            {
                "id": "exp-1",
                "name": "Eddie Dang",
                "current_employer": "AT&T",
                "interviews": [
                    {"id": "int-1", "occurred_at": "2026-08-07T10:00", "status": "completed", "transcript_id": "tr-1"},
                    {"id": "int-2", "occurred_at": "2026-08-12T11:00", "status": "completed", "transcript_id": ""},
                ],
            }
        ]

    def test_unique_name_and_date_links_second_interview_idempotently(self) -> None:
        transcripts = [
            {"id": "tr-1", "title": "企业AI_ATT_Eddie Dang_20260807", "original_name": "a.mp3", "meeting_date": "2026-08-07"},
            {"id": "tr-2", "title": "企业AI_ATT_Eddie Dang_第二次_20260812", "original_name": "b.mp3", "meeting_date": "2026-08-12"},
        ]
        first = build_link_scan(self.experts, transcripts, allow_model=False)
        self.assertEqual(first["actions"][0]["interview_id"], "int-2")
        self.assertEqual(first["actions"][0]["interview_sequence"], 2)
        applied = apply_safe_links(self.experts, first["actions"], now_iso="2026-08-13T00:00:00")
        self.assertEqual(len(applied), 1)
        second = build_link_scan(self.experts, transcripts, allow_model=False)
        self.assertEqual(second["actions"], [])
        self.assertEqual([item for item in second["results"] if item["transcript_id"] == "tr-2"][0]["status"], "linked")

    def test_duplicate_upload_does_not_create_an_action(self) -> None:
        transcripts = [
            {"id": "tr-1", "title": "Eddie", "original_name": "same.mp3", "meeting_date": "2026-08-07", "source_file_size": 10},
            {"id": "tr-copy", "title": "Eddie copy", "original_name": "same.mp3", "meeting_date": "2026-08-07", "source_file_size": 10},
        ]
        scan = build_link_scan(self.experts, transcripts, allow_model=False)
        duplicate = next(item for item in scan["results"] if item["transcript_id"] == "tr-copy")
        self.assertEqual(duplicate["status"], "duplicate_transcript")
        self.assertFalse(any(item["transcript_id"] == "tr-copy" for item in scan["actions"]))

    def test_ambiguous_model_result_is_only_a_suggestion(self) -> None:
        experts = [
            {"id": "exp-a", "name": "Alice", "current_employer": "Beta", "interviews": [{"id": "i-a", "occurred_at": "2026-08-10T10:00", "status": "completed", "transcript_id": ""}]},
            {"id": "exp-b", "name": "Bob", "current_employer": "Beta", "interviews": [{"id": "i-b", "occurred_at": "2026-08-10T11:00", "status": "completed", "transcript_id": ""}]},
        ]
        transcript = {"id": "tr-x", "title": "Beta专家访谈", "original_name": "recording.mp3", "meeting_date": "2026-08-10"}
        scan = build_link_scan(experts, [transcript], allow_model=False)
        # Local company matching can suggest a candidate, but same-day ambiguity
        # and any future model path must never bypass the safe-action contract.
        self.assertEqual(scan["actions"], [])
        self.assertEqual(scan["results"][0]["status"], "pending_review")

    def test_deepseek_can_narrow_ambiguous_names_but_cannot_auto_write(self) -> None:
        experts = [
            {"id": "exp-a", "name": "Alex Lee", "current_employer": "Beta", "interviews": [{"id": "i-a", "occurred_at": "2026-08-10T10:00", "status": "completed", "transcript_id": ""}]},
            {"id": "exp-b", "name": "Alex Lee", "current_employer": "Beta", "interviews": [{"id": "i-b", "occurred_at": "2026-08-10T11:00", "status": "completed", "transcript_id": ""}]},
        ]
        transcript = {"id": "tr-x", "title": "Beta - Alex Lee 专家访谈", "original_name": "recording.mp3", "meeting_date": "2026-08-10"}

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": json.dumps({"expert_id": "exp-b", "confidence": 0.98, "evidence": "Beta"})}}]}

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "providers.json"
            config_path.write_text(json.dumps({"providers": {"deepseek": {"enabled": True, "api_key_env": "TEST_DEEPSEEK_KEY", "base_url": "https://api.deepseek.com", "chat_path": "/chat/completions", "model": "deepseek-test"}}}))
            with mock.patch.dict("os.environ", {"TEST_DEEPSEEK_KEY": "secret"}):
                scan = build_link_scan(
                    experts,
                    [transcript],
                    provider_config_path=config_path,
                    allow_model=True,
                    http_post=lambda *args, **kwargs: Response(),
                )

        self.assertEqual(scan["actions"], [])
        self.assertEqual(scan["results"][0]["status"], "suggested")
        self.assertEqual(scan["results"][0]["expert_id"], "exp-b")
        self.assertIn("DeepSeek", scan["results"][0]["evidence"])

    def test_cache_is_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "links.json"
            save_link_cache(path, {"status": "ready", "results": []})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(load_link_cache(path)["status"], "ready")


if __name__ == "__main__":
    unittest.main()
