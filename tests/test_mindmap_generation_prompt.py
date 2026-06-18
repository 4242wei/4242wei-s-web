from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app as app_module


def build_sample_record(
    prompt_text: str = "帮我分析新增量/变化",
    brief_text: str = "",
    brief_name: str = "cdn-summary.docx",
) -> dict:
    generation_brief = (
        {
            "original_name": brief_name,
            "stored_name": "stored-brief.docx",
            "uploaded_at": "2026-04-09T10:30:00+08:00",
            "summary": app_module.summarize_text_block(brief_text, limit=140),
            "text": brief_text,
        }
        if brief_text
        else {}
    )
    return {
        "id": "mindmap123456",
        "title": "Changes Map",
        "summary": "Track what changed and why it matters.",
        "status": "completed",
        "model": "gpt-5.4",
        "reasoning_effort": "medium",
        "generation_prompt": prompt_text,
        "generation_brief": generation_brief,
        "scope_settings": app_module.normalize_ai_scope_settings({}),
        "scope_summary": {
            "headline": "当前读取全站资料库",
            "description": "测试用",
            "stock_label": "股票范围：全站",
            "time_label": "时间窗口：不限",
            "content_label": "资料类型：日报；笔记；文件；电话会议；转录",
            "has_filters": False,
            "metrics": [],
        },
        "fingerprint": {
            "generation_prompt": prompt_text,
            "generation_prompt_digest": app_module.sha256_text(prompt_text),
            "generation_brief": generation_brief,
            "generation_brief_digest": app_module.sha256_text(brief_text),
            "selected_sources": [],
        },
        "map_payload": {
            "title": "Changes Map",
            "summary": "Track what changed and why it matters.",
            "structure_kind": "theme_bundle",
            "insights": ["Recent changes matter more than the static snapshot."],
            "comparison_axes": [],
            "verification_targets": [],
            "timeline_highlights": [],
            "source_relations": [],
            "root": {
                "id": "root",
                "label": "Changes",
                "kind": "root",
                "summary": "Focus on changes across the selected materials.",
                "confidence": "medium",
                "source_refs": [],
                "symbols": [],
                "evidence": [],
                "source_notes": [],
                "time_signals": [],
                "children": [],
            },
            "cross_links": [],
        },
    }


class DummyThread:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.started = False

    def start(self) -> None:
        self.started = True


class MindmapGenerationPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_mindmap_path = app_module.MINDMAP_STORE_PATH
        self.original_context_dir = app_module.MINDMAP_CONTEXT_DIR
        self.original_brief_uploads_dir = app_module.MINDMAP_BRIEF_UPLOADS_DIR
        self.original_testing = app_module.app.config.get("TESTING", False)
        app_module.MINDMAP_STORE_PATH = Path(self.temp_dir.name) / "mindmaps.json"
        app_module.MINDMAP_CONTEXT_DIR = Path(self.temp_dir.name) / "mindmap_context"
        app_module.MINDMAP_BRIEF_UPLOADS_DIR = Path(self.temp_dir.name) / "brief_uploads"
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

        self.empty_stock_store = app_module.normalize_stock_store({})
        self.model_catalog = [
            {
                "slug": "gpt-5.4",
                "display_name": "gpt-5.4",
                "reasoning_levels": ["medium"],
                "default_reasoning": "medium",
            }
        ]
        self.preview_context = {
            "month_key": "2026-04",
            "month_label": "2026 年 4 月",
            "selected_date": "",
            "range_scope_active": False,
            "available_years": [2026],
            "selected_year": 2026,
            "month_options": [{"value": "04", "label": "4 月"}],
            "selected_month_number": "04",
            "previous_month_key": "2026-03",
            "current_month_key": "2026-04",
            "next_month_key": "2026-05",
            "calendar_weeks": [
                [
                    {
                        "date": "2026-04-01",
                        "day_number": "1",
                        "is_current_month": True,
                        "is_in_range": True,
                        "is_selected": False,
                        "summary": {"total_count": 1},
                    }
                ]
            ],
            "detail_eyebrow": "范围预览",
            "detail_heading": "当前范围",
            "detail_description": "测试用",
            "detail_totals": {
                "total_count": 1,
                "stock_count": 0,
                "days_count": 1,
                "structure_label": "单日",
            },
            "content_kind_options": [],
            "detail_groups": [],
            "summary": {
                "headline": "当前读取全站资料库",
                "description": "测试用",
                "stock_label": "股票范围：全站",
                "time_label": "时间窗口：不限",
                "content_label": "资料类型：日报；笔记；文件；电话会议；转录",
                "has_filters": False,
                "metrics": [],
            },
        }
        self.materials = {
            "report_count": 1,
            "note_count": 0,
            "file_count": 0,
            "earnings_call_count": 0,
            "transcript_count": 0,
        }

    def tearDown(self) -> None:
        app_module.MINDMAP_STORE_PATH = self.original_mindmap_path
        app_module.MINDMAP_CONTEXT_DIR = self.original_context_dir
        app_module.MINDMAP_BRIEF_UPLOADS_DIR = self.original_brief_uploads_dir
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_research_bundle_includes_generation_prompt(self) -> None:
        bundle_path = app_module.build_mindmap_research_bundle(
            "bundle123",
            scope_summary=self.preview_context["summary"],
            generation_prompt="帮我重点看新增量和最新变化",
            materials=self.materials,
            curated={"stats": {}, "items": []},
        )

        bundle_text = bundle_path.read_text(encoding="utf-8")
        self.assertIn("用户额外要求", bundle_text)
        self.assertIn("帮我重点看新增量和最新变化", bundle_text)

    def test_research_bundle_includes_generation_brief(self) -> None:
        brief_text = "CDN 在AI时代的变化可以从架构、流量调度和边缘推理三条链来看。"
        bundle_path = app_module.build_mindmap_research_bundle(
            "bundle-brief",
            scope_summary=self.preview_context["summary"],
            generation_prompt="",
            generation_brief={
                "original_name": "cdn-summary.docx",
                "stored_name": "stored-brief.docx",
                "uploaded_at": "2026-04-09T10:30:00+08:00",
                "summary": app_module.summarize_text_block(brief_text, limit=140),
                "text": brief_text,
            },
            materials=self.materials,
            curated={"stats": {}, "items": []},
        )

        bundle_text = bundle_path.read_text(encoding="utf-8")
        self.assertIn("用户上传的摘要底稿", bundle_text)
        self.assertIn("cdn-summary.docx", bundle_text)
        self.assertIn("CDN 在AI时代的变化", bundle_text)

    def test_generate_route_persists_generation_prompt_and_brief(self) -> None:
        prompt_text = "帮我分析新增量/变化"
        brief_text = "CDN 在AI时代的变化，先看内容分发，再看边缘资源，最后看网络计费和价值传导。"
        with mock.patch.object(app_module, "codex_cli_available", return_value=True), mock.patch.object(
            app_module, "load_stock_store", return_value=self.empty_stock_store
        ), mock.patch.object(app_module, "collect_reports", return_value=[]), mock.patch.object(
            app_module, "collect_ai_scope_materials", return_value=self.materials
        ), mock.patch.object(
            app_module, "load_codex_model_catalog", return_value=self.model_catalog
        ), mock.patch.object(
            app_module.threading, "Thread", DummyThread
        ), mock.patch.object(
            app_module, "try_extract_file_text", return_value=(brief_text, True)
        ):
            response = self.client.post(
                "/mindmaps/generate",
                data={
                    "model_slug": "gpt-5.4",
                    "reasoning_effort": "medium",
                    "generation_prompt": prompt_text,
                    "generation_brief_file": (io.BytesIO(b"fake-docx"), "cdn-summary.docx"),
                    "scope_content_kinds": ",".join(app_module.AI_SCOPE_DEFAULT_CONTENT_KINDS),
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/mindmaps?map=", response.headers.get("Location", ""))
        store = app_module.load_mindmap_store()
        self.assertEqual(len(store["records"]), 1)
        record = store["records"][0]
        self.assertEqual(record["generation_prompt"], prompt_text)
        self.assertEqual(record["fingerprint"]["generation_prompt"], prompt_text)
        self.assertEqual(record["generation_brief"]["original_name"], "cdn-summary.docx")
        self.assertEqual(record["generation_brief"]["text"], brief_text)
        self.assertEqual(record["fingerprint"]["generation_brief_digest"], app_module.sha256_text(brief_text))
        brief_path = app_module.mindmap_brief_upload_dir(record["id"]) / record["generation_brief"]["stored_name"]
        self.assertTrue(brief_path.exists())

        with self.client.session_transaction() as session:
            self.assertEqual(session[app_module.MINDMAP_GENERATION_PROMPT_DRAFT_SESSION_KEY], prompt_text)

    def test_delete_route_removes_uploaded_brief(self) -> None:
        record = build_sample_record(brief_text="CDN AI change chain")
        brief_dir = app_module.mindmap_brief_upload_dir(record["id"])
        brief_dir.mkdir(parents=True, exist_ok=True)
        brief_path = brief_dir / record["generation_brief"]["stored_name"]
        brief_path.write_text("brief", encoding="utf-8")
        app_module.save_mindmap_store({"records": [record]})

        response = self.client.post(f"/mindmaps/{record['id']}/delete")

        self.assertEqual(response.status_code, 302)
        self.assertFalse(brief_path.exists())
        self.assertFalse(brief_dir.exists())
        self.assertEqual(app_module.load_mindmap_store()["records"], [])

    def test_workspace_renders_prompt_and_brief_inputs_and_notes(self) -> None:
        app_module.save_mindmap_store({"records": [build_sample_record(brief_text="CDN AI chain note")]})

        with mock.patch.object(app_module, "load_stock_store", return_value=self.empty_stock_store), mock.patch.object(
            app_module, "collect_reports", return_value=[]
        ), mock.patch.object(
            app_module, "build_ai_scope_preview_context", return_value=self.preview_context
        ), mock.patch.object(
            app_module, "codex_cli_available", return_value=True
        ), mock.patch.object(
            app_module, "load_codex_model_catalog", return_value=self.model_catalog
        ):
            response = self.client.get("/mindmaps?map=mindmap123456")

        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn('name="generation_prompt"', html)
        self.assertIn('name="generation_brief_file"', html)
        self.assertIn("帮我分析新增量/变化", html)
        self.assertIn("本次归纳要求", html)
        self.assertIn("本次摘要底稿", html)
        self.assertIn("cdn-summary.docx", html)


if __name__ == "__main__":
    unittest.main()
