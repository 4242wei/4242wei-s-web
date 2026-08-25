from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import app as app_module
from app_routes.expert_portfolio_routes import _materialize_calendar_events
from interview_summary import transcript_digest


class ExpertPortfolioRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        temp_root = Path(self.temp_dir.name)
        self.original_portfolio_path = app_module.EXPERT_PORTFOLIO_STORE_PATH
        self.original_stock_path = app_module.STOCK_STORE_PATH
        self.original_stock_cache = app_module.STOCK_STORE_CACHE
        self.original_intake_config_path = app_module.EXPERT_INTAKE_PROVIDER_CONFIG_PATH
        self.original_calendar_config_path = app_module.OUTLOOK_CALENDAR_CONFIG_PATH
        self.original_calendar_cache_path = app_module.OUTLOOK_CALENDAR_CACHE_PATH
        self.original_link_cache_path = app_module.EXPERT_INTERVIEW_LINK_CACHE_PATH
        self.original_testing = app_module.app.config.get("TESTING", False)

        app_module.EXPERT_PORTFOLIO_STORE_PATH = temp_root / "expert_portfolio.json"
        app_module.STOCK_STORE_PATH = temp_root / "stocks.json"
        app_module.STOCK_STORE_PATH.write_text("{}\n", encoding="utf-8")
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        app_module.EXPERT_INTAKE_PROVIDER_CONFIG_PATH = temp_root / "llm_providers.json"
        app_module.OUTLOOK_CALENDAR_CONFIG_PATH = temp_root / "outlook_calendar_config.json"
        app_module.OUTLOOK_CALENDAR_CACHE_PATH = temp_root / "outlook_calendar_cache.json"
        app_module.EXPERT_INTERVIEW_LINK_CACHE_PATH = temp_root / "expert_interview_link_cache.json"
        app_module.EXPERT_INTAKE_PROVIDER_CONFIG_PATH.write_text(
            json.dumps(
                {
                    "providers": {
                        "test-provider": {
                            "label": "测试接口",
                            "adapter": "openai_compatible",
                            "base_url": "https://example.test",
                            "chat_path": "/chat/completions",
                            "api_key_env": "EXPERT_INTAKE_TEST_MISSING_KEY",
                            "model": "test-model",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        app_module.app.config["TESTING"] = True

        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        app_module.EXPERT_PORTFOLIO_STORE_PATH = self.original_portfolio_path
        app_module.STOCK_STORE_PATH = self.original_stock_path
        app_module.STOCK_STORE_CACHE = self.original_stock_cache
        app_module.EXPERT_INTAKE_PROVIDER_CONFIG_PATH = self.original_intake_config_path
        app_module.OUTLOOK_CALENDAR_CONFIG_PATH = self.original_calendar_config_path
        app_module.OUTLOOK_CALENDAR_CACHE_PATH = self.original_calendar_cache_path
        app_module.EXPERT_INTERVIEW_LINK_CACHE_PATH = self.original_link_cache_path
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def test_page_is_chinese_and_nav_is_above_monitor(self) -> None:
        response = self.client.get("/expert-portfolio")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("专家组合管理", html)
        self.assertIn("导出访谈表格", html)
        self.assertIn("已访谈信息", html)
        self.assertIn('id="expert-portfolio-quota-dialog"', html)
        self.assertIn("data-quota-fullscreen", html)
        self.assertIn("data-quota-scroll-region", html)
        self.assertNotIn("导入专家邮件", html)
        self.assertIn("访谈日程", html)
        self.assertIn('data-interview-calendar', html)
        self.assertIn("Outlook 未连接", html)
        self.assertIn("北京时间 · 07:00–24:00", html)
        self.assertIn('data-interview-date-part="occurred_at"', html)
        self.assertIn('data-interview-time-part="occurred_at"', html)
        self.assertIn('data-interview-duration="60"', html)
        self.assertIn("草稿仅保存在当前浏览器", html)
        self.assertIn("只读取日历事件；不访问邮箱、联系人、参会者或附件", html)
        self.assertNotIn("西湖·苏堤春晓", html)
        self.assertNotIn("西湖·曲院风荷", html)
        self.assertNotIn("西湖·平湖秋月", html)
        self.assertNotIn("西湖·断桥残雪", html)
        self.assertIn("20260817-quota-modal1", html)
        self.assertIn("20260808-native-prefetch1", html)
        self.assertIn("data-theme-motion-toggle", html)
        self.assertIn("动态效果", html)
        self.assertIn("柑橘花园", html)
        self.assertIn("晴空彩屑", html)
        self.assertIn("极光玻璃", html)
        self.assertIn("延时云层", html)
        self.assertIn("樱桃野餐", html)
        self.assertIn("海盐闪光", html)
        frontend = (Path(app_module.__file__).parent / "static" / "expert-portfolio.js").read_text(encoding="utf-8")
        self.assertIn("const calendarEndHour = 24;", frontend)
        self.assertIn('const interviewDraftPrefix = "expert-interview-draft:v1:";', frontend)
        self.assertIn("}, 1800));", frontend)
        self.assertIn("薰衣汽水", html)
        self.assertNotIn("雾港晨灰", html)
        self.assertNotIn("铜绿书房", html)
        self.assertNotIn("午夜余烬", html)
        self.assertNotIn("春色新绿", html)
        self.assertNotIn("梅雨青岚", html)
        self.assertNotIn("江南烟雨", html)
        self.assertIn('data-sort-key="record-id"', html)
        table_head = html[html.index("<thead>") : html.index("</thead>")]
        self.assertLess(
            table_head.index('data-sort-key="status"'),
            table_head.index('data-sort-key="title"'),
        )
        self.assertIn("data-interview-dialog-back", html)
        self.assertIn('id="expert-portfolio-interviews-dialog"', html)
        self.assertIn('id="expert-interview-summary-dialog"', html)
        self.assertIn("逐项结论只基于关联转录生成", html)
        self.assertEqual(html.count("data-interview-list"), 1)
        detail_start = html.index('id="expert-portfolio-detail-dialog"')
        detail_end = html.index("</dialog>", detail_start)
        self.assertNotIn("data-interview-list", html[detail_start:detail_end])
        self.assertIn("访谈人", html)
        self.assertIn("专家智能录入", html)
        self.assertIn("AI填写", html)
        self.assertIn("data-intake-thinking", html)
        self.assertIn("data-intake-reasoning", html)
        self.assertIn("候选与访谈组合", html)
        for label in ("待审核", "暂不考虑", "安排中", "已完成访谈", "安排追访", "追访中"):
            self.assertIn(label, html)
        for removed_label in ("感兴趣", "待评估", "评估中", "拒绝访谈", "匹配度低", "质量较低", "重复档案"):
            self.assertNotIn(removed_label, html)
        self.assertLess(html.index("专家组合"), html.index("Monitor"))

    def test_verified_calendar_events_materialize_once_and_set_workflow_status(self) -> None:
        store = {
            "experts": [
                {"id": "first", "name": "First Expert", "status": "not-reviewed", "interviews": []},
                {
                    "id": "followup",
                    "name": "Followup Expert",
                    "status": "completed",
                    "interviews": [
                        {
                            "id": "past",
                            "occurred_at": "2026-08-10T10:00",
                            "status": "completed",
                            "title": "首次访谈",
                            "notes": "保留手工内容",
                        }
                    ],
                },
            ]
        }
        events = [
            {
                "event_id": "event-first",
                "expert_id": "first",
                "match_status": "matched_model",
                "start": "2026-08-15T15:00:00+08:00",
                "end": "2026-08-15T16:00:00+08:00",
                "title": "First Expert interview",
            },
            {
                "event_id": "event-followup",
                "expert_id": "followup",
                "match_status": "matched_model",
                "start": "2026-08-16T15:00:00+08:00",
                "end": "2026-08-16T16:00:00+08:00",
                "title": "Followup Expert interview",
            },
        ]
        now = datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        first = _materialize_calendar_events(store, events, now_iso="2026-08-13T12:00:00", now=now)
        second = _materialize_calendar_events(store, events, now_iso="2026-08-13T12:01:00", now=now)
        self.assertEqual(first["created"], 2)
        self.assertEqual(second["created"], 0)
        self.assertEqual(sum(len(expert["interviews"]) for expert in store["experts"]), 3)
        self.assertEqual(store["experts"][0]["status"], "scheduling")
        self.assertEqual(store["experts"][1]["status"], "followup-in-progress")
        self.assertEqual(store["experts"][1]["interviews"][-1]["notes"], "保留手工内容")

    def test_calendar_links_existing_manual_interview_without_overwriting_fields(self) -> None:
        store = {
            "experts": [
                {
                    "id": "expert-1",
                    "name": "Expert One",
                    "status": "scheduling",
                    "interviews": [
                        {
                            "id": "manual",
                            "occurred_at": "2026-08-15T15:05",
                            "ended_at": "2026-08-15T16:05",
                            "status": "scheduled",
                            "title": "手工标题",
                            "interviewer": "Wei",
                            "notes": "手工备注",
                        }
                    ],
                }
            ]
        }
        event = {
            "event_id": "event-manual",
            "expert_id": "expert-1",
            "match_status": "matched_model",
            "start": "2026-08-15T15:00:00+08:00",
            "end": "2026-08-15T16:00:00+08:00",
            "title": "Outlook title",
        }
        result = _materialize_calendar_events(
            store,
            [event],
            now_iso="2026-08-13T12:00:00",
            now=datetime(2026, 8, 13, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        interview = store["experts"][0]["interviews"][0]
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["linked"], 1)
        self.assertEqual(interview["title"], "手工标题")
        self.assertEqual(interview["interviewer"], "Wei")
        self.assertEqual(interview["notes"], "手工备注")
        self.assertEqual(interview["outlook_event_id"], "event-manual")

    def test_create_and_inline_update_are_persisted(self) -> None:
        response = self.client.post(
            "/expert-portfolio/experts",
            data={
                "name": "测试专家",
                "vendors": "GLG, Third Bridge",
                "vendor_index": "GLG: #1, Third Bridge: #2",
                "current_title": "技术副总裁",
                "current_employer": "测试光电",
                "category": "其他激光专家",
                "status": "interested",
                "job_history": "技术副总裁 | 测试光电 | 2024 - 至今",
            },
        )
        self.assertEqual(response.status_code, 302)

        store = json.loads(app_module.EXPERT_PORTFOLIO_STORE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(store["experts"]), 1)
        expert = store["experts"][0]
        self.assertEqual(expert["vendors"], ["GLG", "Third Bridge"])
        self.assertEqual(expert["job_history"][0]["company"], "测试光电")

        response = self.client.post(
            f'/expert-portfolio/experts/{expert["id"]}/field',
            json={"field": "status", "value": "completed"},
        )
        self.assertEqual(response.status_code, 200)
        updated_store = json.loads(app_module.EXPERT_PORTFOLIO_STORE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(updated_store["experts"][0]["status"], "completed")
        self.assertEqual(response.get_json()["stats"]["completed"], 0)

    def test_json_merge_and_export(self) -> None:
        payload = {
            "experts": [
                {
                    "name": "Imported Expert",
                    "vendors": ["Guidepoint"],
                    "category": "OIO Startups",
                }
            ]
        }
        response = self.client.post(
            "/expert-portfolio/import.json",
            data={
                "mode": "merge",
                "portfolio_json": (io.BytesIO(json.dumps(payload).encode("utf-8")), "portfolio.json"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get("/expert-portfolio/export.json")
        self.assertEqual(response.status_code, 200)
        exported = json.loads(response.get_data(as_text=True))
        self.assertEqual(exported["experts"][0]["category"], "光互连初创公司")

    def test_multiple_interviews_can_link_to_a_transcript(self) -> None:
        app_module.STOCK_STORE_PATH.write_text(
            json.dumps(
                {
                    "transcripts": [
                        {
                            "id": "transcript-token-1",
                            "title": "Token economics 访谈",
                            "meeting_date": "2026-08-07",
                            "stored_name": "token-interview.mp3",
                            "original_name": "token-interview.mp3",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        response = self.client.post(
            "/expert-portfolio/experts",
            data={
                "name": "长期跟踪专家",
                "industry": "电信",
                "company_scale": "中型",
                "region": "英国",
                "category": "Token economics",
            },
        )
        self.assertEqual(response.status_code, 302)
        store = json.loads(app_module.EXPERT_PORTFOLIO_STORE_PATH.read_text(encoding="utf-8"))
        expert_id = store["experts"][0]["id"]

        for occurred_at, ended_at, status, interviewer in (
            ("2026-08-07T18:00", "2026-08-07T21:00", "scheduled", "Wei"),
            ("2026-09-08T18:00", "", "completed", "Patrick"),
        ):
            response = self.client.post(
                f"/expert-portfolio/experts/{expert_id}/interviews",
                data={
                    "occurred_at": occurred_at,
                    "ended_at": ended_at,
                    "display_time": occurred_at,
                    "title": "Token economics 专家访谈",
                    "interviewer": interviewer,
                    "status": status,
                    "transcript_id": "transcript-token-1",
                    "transcription_quality": "needs-review",
                    "transcription_notes": "数字和专有名词需回听。",
                },
            )
            self.assertEqual(response.status_code, 302)

        store = json.loads(app_module.EXPERT_PORTFOLIO_STORE_PATH.read_text(encoding="utf-8"))
        interviews = store["experts"][0]["interviews"]
        self.assertEqual(len(interviews), 2)
        self.assertEqual(interviews[0]["occurred_at"], "2026-09-08T18:00")
        self.assertEqual(interviews[0]["interviewer"], "Patrick")
        self.assertEqual(interviews[0]["transcript_id"], "transcript-token-1")
        self.assertEqual(interviews[1]["ended_at"], "2026-08-07T21:00")
        self.assertEqual(interviews[1]["interviewer"], "Wei")
        response = self.client.get("/expert-portfolio")
        html = response.get_data(as_text=True)
        self.assertIn("data-multiple-interviews=\"1\"", html)
        self.assertIn("#transcript-transcript-token-1", html)
        self.assertIn('data-interviews-open=', html)

    def test_ready_summary_is_loaded_only_from_the_separate_endpoint(self) -> None:
        transcript_text = "专家说明企业会按任务复杂度选择模型，并对关键输出保留人工复核。" * 20
        app_module.STOCK_STORE_PATH.write_text(
            json.dumps(
                {
                    "transcripts": [
                        {
                            "id": "transcript-summary-1",
                            "title": "企业 AI 访谈",
                            "stored_name": "summary-interview.mp3",
                            "original_name": "summary-interview.mp3",
                            "status": "completed",
                            "transcript_text": transcript_text,
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        app_module.STOCK_STORE_CACHE = {"signature": None, "data": None}
        raw_store = {
            "experts": [
                {
                    "id": "exp-summary",
                    "name": "摘要测试专家",
                    "interviews": [
                        {
                            "id": "int-summary",
                            "occurred_at": "2026-08-10T10:00",
                            "title": "企业 AI 访谈",
                            "status": "completed",
                            "transcript_id": "transcript-summary-1",
                            "ai_summary": {
                                "status": "ready",
                                "overview": "这是一段只应通过摘要接口加载的独特内容。",
                                "conclusions": [
                                    {
                                        "title": "模型选择",
                                        "conclusion": "企业按任务选择模型。",
                                        "evidence": "专家描述了按复杂度分流。",
                                        "uncertainty": "未提供具体比例。",
                                        "source_ref": "模型策略部分",
                                    }
                                ],
                                "source_transcript_id": "transcript-summary-1",
                                "source_digest": transcript_digest(transcript_text),
                                "provider_label": "DeepSeek",
                                "model": "test-model",
                            },
                        }
                    ],
                }
            ]
        }
        app_module.EXPERT_PORTFOLIO_STORE_PATH.write_text(
            json.dumps(raw_store, ensure_ascii=False),
            encoding="utf-8",
        )

        page = self.client.get("/expert-portfolio")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('"ai_summary_status": "ready"', html)
        self.assertNotIn("这是一段只应通过摘要接口加载的独特内容", html)

        response = self.client.get(
            "/expert-portfolio/experts/exp-summary/interviews/int-summary/summary"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["summary"]["conclusions"][0]["title"], "模型选择")
        self.assertNotIn("transcript_text", json.dumps(payload, ensure_ascii=False))

    def test_legacy_interview_and_hidden_expert_tracking_fields_are_preserved(self) -> None:
        raw_store = {
            "experts": [
                {
                    "id": "exp-legacy",
                    "name": "Legacy Expert",
                    "research_feedback": "旧的专家级调研反馈",
                    "future_tracking": "旧的专家级跟踪信息",
                    "interviews": [
                        {
                            "id": "int-legacy",
                            "occurred_at": "2026-08-01T10:00",
                            "title": "旧访谈",
                            "status": "completed",
                        }
                    ],
                }
            ]
        }
        app_module.EXPERT_PORTFOLIO_STORE_PATH.write_text(
            json.dumps(raw_store, ensure_ascii=False),
            encoding="utf-8",
        )
        response = self.client.get("/expert-portfolio")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-interviews-open="exp-legacy"', html)

        response = self.client.post(
            "/expert-portfolio/experts/exp-legacy/update",
            data={"name": "Legacy Expert", "status": "not-reviewed", "category": "未分类"},
        )
        self.assertEqual(response.status_code, 302)
        stored = json.loads(app_module.EXPERT_PORTFOLIO_STORE_PATH.read_text(encoding="utf-8"))["experts"][0]
        self.assertEqual(stored["research_feedback"], "旧的专家级调研反馈")
        self.assertEqual(stored["future_tracking"], "旧的专家级跟踪信息")
        self.assertEqual(stored["interviews"][0]["interviewer"], "")

    def test_quota_export_replaces_email_import_and_visitor_remains_read_only(self) -> None:
        self.assertEqual(self.client.post("/expert-portfolio/email/parse").status_code, 404)
        response = self.client.get("/expert-portfolio/interview-quota.xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"PK"))
        self.assertIn("spreadsheetml.sheet", response.content_type)

        visitor = app_module.app.test_client()
        with visitor.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_VISITOR_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_VISITOR
        response = visitor.get("/expert-portfolio")
        self.assertEqual(response.status_code, 200)
        self.assertIn("访客模式仅开放查看", response.get_data(as_text=True))
        response = visitor.post("/expert-portfolio/experts", data={"name": "不能写入"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(app_module.EXPERT_PORTFOLIO_STORE_PATH.exists())

    def test_default_sequence_order_quota_modal_and_region_normalization(self) -> None:
        raw_store = {
            "experts": [
                {
                    "id": "exp-11",
                    "source_record_id": "#11",
                    "name": "Eleven Expert",
                    "current_employer": "Eleven Co",
                    "region": "美国",
                },
                {
                    "id": "exp-2",
                    "source_record_id": "#2",
                    "name": "Two Expert",
                    "current_employer": "Two Co",
                    "region": "Boston, USA",
                },
                {
                    "id": "exp-1",
                    "source_record_id": "#1",
                    "name": "One Expert",
                    "current_employer": "One Bank",
                    "current_title": "Chief Information Officer",
                    "company_scale": "大型",
                    "industry": "金融",
                    "region": "美国",
                    "interviews": [
                        {
                            "id": "int-1a",
                            "status": "renamed-status",
                            "quota_status": "completed",
                            "occurred_at": "2026-08-07T14:00",
                        },
                        {
                            "id": "int-1b",
                            "status": "another-status",
                            "quota_status": "completed",
                            "occurred_at": "2026-08-08T15:00",
                        },
                    ],
                },
            ]
        }
        app_module.EXPERT_PORTFOLIO_STORE_PATH.write_text(
            json.dumps(raw_store, ensure_ascii=False), encoding="utf-8"
        )

        response = self.client.get("/expert-portfolio")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertLess(
            html.index('data-sort-record-id="#1"'),
            html.index('data-sort-record-id="#2"'),
        )
        self.assertLess(
            html.index('data-sort-record-id="#2"'),
            html.index('data-sort-record-id="#11"'),
        )
        self.assertIn('data-region="美国"', html)
        self.assertNotIn('data-region="boston, usa"', html.lower())

        quota_start = html.index('id="expert-portfolio-quota-dialog"')
        quota_end = html.index("</dialog>", quota_start)
        quota_html = html[quota_start:quota_end]
        self.assertIn("expert-portfolio-quota-matrix", quota_html)
        self.assertIn("expert-portfolio-quota-axis-column", quota_html)
        self.assertIn("expert-portfolio-quota-region-column", quota_html)
        self.assertIn("One Bank（08.07；08.08）", quota_html)
        self.assertNotIn("One Expert", quota_html)
        self.assertIn('data-quota-expert-open="exp-1"', quota_html)
        self.assertIn("点击查看访谈记录", quota_html)

    def test_intake_without_key_is_isolated_from_portfolio_store(self) -> None:
        response = self.client.get("/expert-intake/providers")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["providers"][0]["configured"])

        response = self.client.post(
            "/expert-intake/parse",
            json={
                "provider_id": "test-provider",
                "source_text": "Expert Name: Example Person\nTitle: Chief AI Officer",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("EXPERT_INTAKE_TEST_MISSING_KEY", response.get_json()["message"])
        self.assertFalse(app_module.EXPERT_PORTFOLIO_STORE_PATH.exists())

    def test_confirmed_intake_preview_uses_existing_merge_path(self) -> None:
        response = self.client.post(
            "/expert-portfolio/intake/import",
            json={
                "experts": [
                    {
                        "name": "AI Preview Expert",
                        "current_employer": "Example Co",
                        "current_title": "Chief AI Officer",
                        "vendors": ["智能录入"],
                        "status": "not-reviewed",
                        "data_quality_status": "needs-review",
                    }
                ]
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["added"], 1)
        stored = json.loads(app_module.EXPERT_PORTFOLIO_STORE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(stored["experts"][0]["name"], "AI Preview Expert")
        self.assertEqual(stored["experts"][0]["data_quality_status"], "needs-review")


if __name__ == "__main__":
    unittest.main()
