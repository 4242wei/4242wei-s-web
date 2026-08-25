from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from expert_intake import ExpertIntakeError, parse_expert_source, provider_catalog


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class ExpertIntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "providers.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "compatible": {
                            "label": "兼容接口",
                            "adapter": "openai_compatible",
                            "base_url": "https://llm.example.test/v1",
                            "chat_path": "/chat/completions",
                            "api_key_env": "EXPERT_INTAKE_UNIT_KEY",
                            "model": "extractor-model",
                            "supports_thinking": True,
                            "thinking": "enabled",
                            "reasoning_efforts": ["low", "high", "max"],
                            "reasoning_effort": "low",
                            "json_mode": True,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_catalog_only_reports_key_presence(self) -> None:
        with patch.dict(os.environ, {"EXPERT_INTAKE_UNIT_KEY": ""}, clear=False):
            catalog = provider_catalog(self.config_path)
        self.assertEqual(catalog[0]["model"], "extractor-model")
        self.assertFalse(catalog[0]["configured"])
        self.assertTrue(catalog[0]["supports_thinking"])
        self.assertTrue(catalog[0]["default_thinking"])
        self.assertEqual(catalog[0]["reasoning_efforts"], ["low", "high", "max"])
        self.assertEqual(catalog[0]["default_reasoning_effort"], "low")
        self.assertNotIn("api_key", catalog[0])

    def test_compatible_adapter_normalizes_preview_without_writing(self) -> None:
        captured = {}

        def fake_post(url, *, headers, json, timeout):
            captured.update(url=url, headers=headers, request=json, timeout=timeout)
            model_result = {
                "experts": [
                    {
                        "name": "Kevin Cassar",
                        "current_title": "Chief Data and AI Officer",
                        "current_employer": "TalkTalk",
                        "industry": "电信",
                        "region": "英国",
                        "status": "completed",
                        "data_quality_status": "verified",
                        "expert_comment": "We do not have locally deployed models.",
                        "job_history": [
                            {"title": "Head of Data Science", "company": "AXA Health UK", "dates": "2024–2025"}
                        ],
                    }
                ],
                "warnings": ["任职月份需人工核对"],
            }
            return FakeResponse(
                {
                    "choices": [{"message": {"content": __import__("json").dumps(model_result)}}],
                    "usage": {"total_tokens": 321},
                }
            )

        with patch.dict(os.environ, {"EXPERT_INTAKE_UNIT_KEY": "secret-for-test"}, clear=False):
            result = parse_expert_source(
                self.config_path,
                provider_id="compatible",
                source_text="Expert Name: Kevin Cassar; Chief Data and AI Officer at TalkTalk.",
                http_post=fake_post,
            )

        self.assertEqual(captured["url"], "https://llm.example.test/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-for-test")
        self.assertEqual(captured["request"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["request"]["thinking"], {"type": "enabled"})
        self.assertEqual(captured["request"]["reasoning_effort"], "low")
        self.assertEqual(result["experts"][0]["name"], "Kevin Cassar")
        self.assertEqual(result["experts"][0]["status"], "not-reviewed")
        self.assertEqual(result["experts"][0]["data_quality_status"], "needs-review")
        self.assertEqual(result["experts"][0]["data_quality_notes"], "")
        self.assertEqual(result["experts"][0]["expert_comment"], "We do not have locally deployed models.")
        self.assertEqual(result["experts"][0]["job_history"][0]["company"], "AXA Health UK")
        self.assertEqual(result["warnings"], ["任职月份需人工核对"])

        with patch.dict(os.environ, {"EXPERT_INTAKE_UNIT_KEY": "secret-for-test"}, clear=False):
            parse_expert_source(
                self.config_path,
                provider_id="compatible",
                source_text="Expert Name: Kevin Cassar; Chief Data and AI Officer at TalkTalk.",
                thinking_mode="enabled",
                reasoning_effort="max",
                http_post=fake_post,
            )
        self.assertEqual(captured["request"]["thinking"], {"type": "enabled"})
        self.assertEqual(captured["request"]["reasoning_effort"], "max")

    def test_invalid_model_json_returns_safe_error(self) -> None:
        def fake_post(*args, **kwargs):
            return FakeResponse({"choices": [{"message": {"content": "not-json"}}]})

        with patch.dict(os.environ, {"EXPERT_INTAKE_UNIT_KEY": "secret-for-test"}, clear=False):
            with self.assertRaisesRegex(ExpertIntakeError, "有效 JSON"):
                parse_expert_source(
                    self.config_path,
                    provider_id="compatible",
                    source_text="This is a complete expert profile with a name.",
                    http_post=fake_post,
                )

    def test_structured_header_and_comments_are_preserved_locally(self) -> None:
        def fake_post(*args, **kwargs):
            model_result = {
                "experts": [
                    {
                        "name": "Mr. Klotz",
                        "current_employer": "RMB - Rand Merchant Bank",
                        "industry": "金融",
                        "region": "Johannesburg, South Africa",
                        "expert_comment": "AI rewritten comment",
                    }
                ]
            }
            return FakeResponse({"choices": [{"message": {"content": json.dumps(model_result)}}]})

        source = """#12【金融-大型-非洲】
Expert Name: Mr. Klotz
Base: Johannesburg, South Africa
Language: English
Rate: 430 USD/h
【Comment】:
-financial numbers are off limits.
【Availability】:
15:00–17:00 Tue Aug 11 2026 (Beijing Time)
"""
        with patch.dict(os.environ, {"EXPERT_INTAKE_UNIT_KEY": "secret-for-test"}, clear=False):
            result = parse_expert_source(
                self.config_path,
                provider_id="compatible",
                source_text=source,
                http_post=fake_post,
            )

        expert = result["experts"][0]
        self.assertEqual(expert["source_record_id"], "#12")
        self.assertEqual(expert["industry"], "金融")
        self.assertEqual(expert["company_scale"], "大型")
        self.assertEqual(expert["region"], "非洲")
        self.assertEqual(expert["expert_comment"], "-financial numbers are off limits.")
        self.assertIn("Base: Johannesburg, South Africa", expert["notes"])
        self.assertIn("Language: English", expert["notes"])
        self.assertIn("Rate: 430 USD/h", expert["notes"])
        self.assertIn("Availability: 15:00–17:00 Tue Aug 11 2026 (Beijing Time)", expert["notes"])


if __name__ == "__main__":
    unittest.main()
