from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interview_summary import InterviewSummaryError, generate_interview_summary, transcript_digest


class _Response:
    status_code = 200

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "overview": "总体判断。",
                                "conclusions": [
                                    {
                                        "title": "成本策略",
                                        "conclusion": "团队按任务选择模型。",
                                        "evidence": "受访者说明不同任务采用不同模型。",
                                        "uncertainty": "没有提供具体金额。",
                                        "source_ref": "Speaker 1",
                                    }
                                ],
                                "follow_ups": ["核对实际成本区间"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
            "usage": {"total_tokens": 321},
        }


class InterviewSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "providers.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "deepseek": {
                            "label": "DeepSeek",
                            "enabled": True,
                            "base_url": "https://example.test",
                            "chat_path": "/chat/completions",
                            "api_key_env": "TEST_INTERVIEW_SUMMARY_KEY",
                            "model": "test-model",
                            "supports_thinking": True,
                            "thinking": "enabled",
                            "reasoning_effort": "low",
                            "response_path": "choices.0.message.content",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generates_normalized_conclusions_without_exposing_key(self) -> None:
        captured = {}

        def fake_post(*args, **kwargs):
            captured.update(kwargs)
            return _Response()

        source = "专家说明团队会根据不同任务选择不同模型。" * 20
        with patch.dict(os.environ, {"TEST_INTERVIEW_SUMMARY_KEY": "secret-key"}):
            result = generate_interview_summary(
                self.config_path,
                provider_id="deepseek",
                transcript_text=source,
                expert_name="测试专家",
                http_post=fake_post,
            )
        self.assertEqual(result["conclusions"][0]["title"], "成本策略")
        self.assertEqual(result["usage"]["total_tokens"], 321)
        self.assertEqual(result["source_digest"], transcript_digest(source))
        self.assertEqual(captured["json"]["thinking"], {"type": "enabled"})
        self.assertNotIn("secret-key", json.dumps(captured["json"], ensure_ascii=False))

    def test_missing_key_is_safe_error(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(InterviewSummaryError, "API Key"):
                generate_interview_summary(
                    self.config_path,
                    provider_id="deepseek",
                    transcript_text="足够长的转录正文" * 20,
                )


if __name__ == "__main__":
    unittest.main()
