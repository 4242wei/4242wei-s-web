from __future__ import annotations

import json
import io
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import app as app_module


def build_sample_record() -> dict:
    return {
        "id": "rec123456789",
        "title": "CDN Platform Upgrade Map",
        "summary": "A reusable peer-group logic map.",
        "fingerprint": {
            "selected_sources": [
                {
                    "source_ref": "M01",
                    "source_key": "note:alpha",
                    "kind": "note",
                    "title": "Alpha note",
                    "activity_date": "2026-04-01",
                    "symbols": ["NET", "AKAM"],
                    "weight_flags": ["recent"],
                    "priority_score": 1.2,
                },
                {
                    "source_ref": "M02",
                    "source_key": "transcript:beta",
                    "kind": "transcript",
                    "title": "Beta transcript",
                    "activity_date": "2026-04-02",
                    "symbols": ["NET"],
                    "weight_flags": ["dense"],
                    "priority_score": 1.1,
                },
            ]
        },
        "map_payload": {
            "title": "CDN Platform Upgrade Map",
            "summary": "A reusable peer-group logic map.",
            "structure_kind": "peer_group",
            "insights": [
                "Security expansion is the clearest monetization bridge.",
                "Edge AI remains promising but still needs verification.",
            ],
            "comparison_axes": [
                {
                    "axis": "Security attach",
                    "takeaway": "NET has the clearest expansion path.",
                    "source_refs": ["M01"],
                    "views": [
                        {
                            "symbol": "NET",
                            "stance": "ahead",
                            "summary": "Clear attach path from CDN to security.",
                            "source_refs": ["M01", "M02"],
                        },
                        {
                            "symbol": "AKAM",
                            "stance": "steady",
                            "summary": "Broader enterprise base but slower narrative shift.",
                            "source_refs": ["M01"],
                        },
                    ],
                }
            ],
            "verification_targets": [
                {
                    "question": "Will edge AI become a near-term revenue driver?",
                    "why_it_matters": "It changes how we weigh upside duration.",
                    "evidence_gap": "Recent external views are ahead of official proof.",
                    "next_check": "Review the next management call and pricing disclosures.",
                    "priority": "high",
                    "symbols": ["NET"],
                    "source_refs": ["M02"],
                }
            ],
            "timeline_highlights": [
                {
                    "date": "2026-03-15",
                    "date_type": "published",
                    "phase": "earliest",
                    "label": "Research framing shifts toward security attach",
                    "summary": "External research starts emphasizing monetization depth.",
                    "source_refs": ["M01"],
                },
                {
                    "date": "2026-04-02",
                    "date_type": "meeting",
                    "phase": "latest",
                    "label": "Management keeps edge AI language exploratory",
                    "summary": "The official tone remains constructive but cautious.",
                    "source_refs": ["M02"],
                },
            ],
            "source_relations": [
                {
                    "label": "verify",
                    "from": "External research",
                    "to": "Management call",
                    "summary": "Cross-check hype against official language.",
                    "source_refs": ["M01", "M02"],
                }
            ],
            "root": {
                "id": "root",
                "label": "CDN upgrade path",
                "kind": "root",
                "summary": "Track the path from delivery to security and edge workloads.",
                "confidence": "high",
                "source_refs": ["M01", "M02"],
                "symbols": ["NET", "AKAM"],
                "evidence": [
                    "Recent notes agree that security cross-sell is becoming the cleaner path."
                ],
                "source_notes": [
                    "Management language is more cautious than the external framing."
                ],
                "time_signals": ["2026-04-02 management call"],
                "children": [
                    {
                        "id": "branch-security",
                        "label": "Security attach path",
                        "kind": "theme",
                        "summary": "Security remains the most validated expansion route.",
                        "confidence": "high",
                        "source_refs": ["M01"],
                        "symbols": ["NET"],
                        "evidence": ["Cross-sell language appears in multiple source types."],
                        "source_notes": ["External and official views mostly align here."],
                        "time_signals": ["2026-03-15 note", "2026-04-02 call"],
                        "children": [],
                    },
                    {
                        "id": "branch-ai",
                        "label": "Edge AI optionality",
                        "kind": "question",
                        "summary": "Potentially large, but still narrative-heavy.",
                        "confidence": "low",
                        "source_refs": ["M02"],
                        "symbols": ["NET"],
                        "evidence": ["Official tone stays exploratory."],
                        "source_notes": ["Needs validation before it becomes a core branch."],
                        "time_signals": ["2026-04-02 call"],
                        "children": [],
                    },
                ],
            },
            "cross_links": [
                {
                    "from": "branch-security",
                    "to": "branch-ai",
                    "label": "supports optionality",
                }
            ],
        },
    }


class MindmapStudioBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_studio_path = app_module.MINDMAP_STUDIO_STORE_PATH
        self.original_testing = app_module.app.config.get("TESTING", False)
        app_module.MINDMAP_STUDIO_STORE_PATH = Path(self.temp_dir.name) / "mindmap_studio.json"
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session[app_module.WEB_ACCESS_SESSION_KEY] = app_module.WEB_ACCESS_PASSWORD_SIGNATURE
            session[app_module.WEB_ACCESS_ROLE_SESSION_KEY] = app_module.WEB_ACCESS_ROLE_ADMIN

    def tearDown(self) -> None:
        app_module.MINDMAP_STUDIO_STORE_PATH = self.original_studio_path
        app_module.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def save_document(self, document: dict) -> None:
        app_module.save_mindmap_studio_store({"documents": [document]})

    def test_convert_generated_mindmap_preserves_structured_fields(self) -> None:
        document = app_module.convert_generated_mindmap_to_studio_document(build_sample_record())

        self.assertEqual(document["structure_kind"], "peer_group")
        self.assertEqual(document["summary"], "A reusable peer-group logic map.")
        self.assertEqual(document["comparison_axes"][0]["axis"], "Security attach")
        self.assertEqual(document["verification_targets"][0]["priority"], "high")
        self.assertEqual(document["timeline_highlights"][0]["phase"], "earliest")
        self.assertEqual(document["source_relations"][0]["label"], "verify")
        self.assertEqual(len(document["fingerprint"]["selected_sources"]), 2)

        root_node = next(node for node in document["nodes"] if node["id"] == document["root_id"])
        self.assertEqual(root_node["confidence"], "high")
        self.assertEqual(root_node["verify_state"], "stable")
        self.assertIn("M01", root_node["source_refs"])
        self.assertTrue(root_node["evidence_items"])
        self.assertTrue(root_node["time_signal_items"])
        self.assertEqual(document["generated_snapshot"]["comparison_axes"][0]["axis"], "Security attach")

    def test_save_route_preserves_structured_fields_when_client_omits_them(self) -> None:
        document = app_module.convert_generated_mindmap_to_studio_document(build_sample_record())
        self.save_document(document)

        payload_document = deepcopy(document)
        payload_document["title"] = "Updated title only"
        for key in [
            "summary",
            "structure_kind",
            "insights",
            "comparison_axes",
            "verification_targets",
            "timeline_highlights",
            "source_relations",
            "fingerprint",
        ]:
            payload_document.pop(key, None)

        response = self.client.post(
            f"/labs/mindmap-studio/documents/{document['id']}/save",
            json={"document": payload_document},
        )
        self.assertEqual(response.status_code, 200)
        response_payload = response.get_json()
        self.assertTrue(response_payload["ok"])
        active_document = response_payload["active_document"]
        self.assertEqual(active_document["title"], "Updated title only")
        self.assertEqual(active_document["structure_kind"], "peer_group")
        self.assertTrue(active_document["comparison_axes"])
        self.assertTrue(active_document["verification_targets"])
        self.assertTrue(active_document["timeline_highlights"])
        self.assertTrue(active_document["source_relations"])
        self.assertEqual(len(active_document["fingerprint"]["selected_sources"]), 2)

    def test_analysis_and_export_routes_return_reusable_outputs(self) -> None:
        document = app_module.convert_generated_mindmap_to_studio_document(build_sample_record())
        self.save_document(document)

        analysis_response = self.client.get(f"/labs/mindmap-studio/documents/{document['id']}/analysis.json")
        self.assertEqual(analysis_response.status_code, 200)
        analysis_payload = analysis_response.get_json()
        self.assertTrue(analysis_payload["ok"])
        self.assertEqual(analysis_payload["analysis"]["coverage"]["with_structured_support"], 2)
        self.assertEqual(analysis_payload["analysis"]["baseline_diff"]["has_snapshot"], True)

        export_json_response = self.client.get(f"/labs/mindmap-studio/documents/{document['id']}/export.json")
        self.assertEqual(export_json_response.status_code, 200)
        export_payload = json.loads(export_json_response.data.decode("utf-8"))
        self.assertIn("analysis", export_payload)
        self.assertEqual(export_payload["comparison_axes"][0]["axis"], "Security attach")

        export_markdown_response = self.client.get(f"/labs/mindmap-studio/documents/{document['id']}/export.md")
        self.assertEqual(export_markdown_response.status_code, 200)
        export_markdown = export_markdown_response.data.decode("utf-8")
        self.assertIn("# CDN Platform Upgrade Map", export_markdown)
        self.assertIn("## Outline", export_markdown)
        self.assertIn("## Verification Targets", export_markdown)

        export_mermaid_response = self.client.get(f"/labs/mindmap-studio/documents/{document['id']}/export.mmd")
        self.assertEqual(export_mermaid_response.status_code, 200)
        export_mermaid = export_mermaid_response.data.decode("utf-8")
        self.assertIn("flowchart", export_mermaid)
        self.assertIn("Security attach path", export_mermaid)

    def test_import_route_accepts_exported_json_file(self) -> None:
        document = app_module.convert_generated_mindmap_to_studio_document(build_sample_record())
        export_payload = app_module.serialize_mindmap_studio_document(document, include_analysis=True)

        response = self.client.post(
            "/labs/mindmap-studio/import",
            data={
                "file": (
                    io.BytesIO(json.dumps(export_payload, ensure_ascii=False).encode("utf-8")),
                    "studio-export.json",
                )
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        imported_document = payload["active_document"]
        self.assertEqual(payload["imported_document_id"], imported_document["id"])
        self.assertNotEqual(imported_document["id"], document["id"])
        self.assertEqual(imported_document["revision"], 1)
        self.assertEqual(len(imported_document["history"]), 1)
        self.assertEqual(imported_document["comparison_axes"][0]["axis"], "Security attach")
        self.assertEqual(imported_document["verification_targets"][0]["priority"], "high")

    def test_history_diff_and_restore_routes_track_revisions(self) -> None:
        document = app_module.convert_generated_mindmap_to_studio_document(build_sample_record())
        self.save_document(document)

        original_title = document["title"]
        original_root_summary = next(node for node in document["nodes"] if node["id"] == document["root_id"])["summary"]

        updated_document = deepcopy(document)
        updated_document["title"] = "Revision Two"
        updated_root = next(node for node in updated_document["nodes"] if node["id"] == updated_document["root_id"])
        updated_root["summary"] = "Revision two summary"

        save_response = self.client.post(
            f"/labs/mindmap-studio/documents/{document['id']}/save",
            json={"document": updated_document},
        )
        self.assertEqual(save_response.status_code, 200)
        save_payload = save_response.get_json()
        saved_document = save_payload["active_document"]
        self.assertEqual(saved_document["revision"], 2)

        history_response = self.client.get(f"/labs/mindmap-studio/documents/{document['id']}/history.json")
        self.assertEqual(history_response.status_code, 200)
        history_payload = history_response.get_json()
        self.assertEqual(history_payload["revision"], 2)
        self.assertEqual(len(history_payload["history"]), 2)
        previous_history_id = history_payload["history"][1]["id"]

        diff_response = self.client.get(f"/labs/mindmap-studio/documents/{document['id']}/diff.json")
        self.assertEqual(diff_response.status_code, 200)
        diff_payload = diff_response.get_json()
        self.assertEqual(diff_payload["left_label"], "Baseline")
        self.assertEqual(diff_payload["right_label"], "Current")
        self.assertTrue(diff_payload["diff"]["document_digest_changed"])
        self.assertTrue(diff_payload["diff"]["metadata_changes"])
        self.assertGreaterEqual(diff_payload["diff"]["node_changes"]["changed_count"], 1)

        history_restore_response = self.client.post(
            f"/labs/mindmap-studio/documents/{document['id']}/restore",
            json={"source": f"history:{previous_history_id}"},
        )
        self.assertEqual(history_restore_response.status_code, 200)
        history_restore_payload = history_restore_response.get_json()
        restored_document = history_restore_payload["active_document"]
        restored_root = next(node for node in restored_document["nodes"] if node["id"] == restored_document["root_id"])
        self.assertEqual(restored_document["title"], original_title)
        self.assertEqual(restored_document["revision"], 3)
        self.assertEqual(restored_root["summary"], original_root_summary)

        changed_again = deepcopy(restored_document)
        changed_again["title"] = "Revision Four"
        changed_again_root = next(node for node in changed_again["nodes"] if node["id"] == changed_again["root_id"])
        changed_again_root["summary"] = "Revision four summary"
        second_save_response = self.client.post(
            f"/labs/mindmap-studio/documents/{document['id']}/save",
            json={"document": changed_again},
        )
        self.assertEqual(second_save_response.status_code, 200)

        baseline_restore_response = self.client.post(
            f"/labs/mindmap-studio/documents/{document['id']}/restore",
            json={"source": "baseline"},
        )
        self.assertEqual(baseline_restore_response.status_code, 200)
        baseline_restore_payload = baseline_restore_response.get_json()
        baseline_document = baseline_restore_payload["active_document"]
        baseline_root = next(node for node in baseline_document["nodes"] if node["id"] == baseline_document["root_id"])
        self.assertEqual(baseline_document["title"], original_title)
        self.assertEqual(baseline_document["revision"], 5)
        self.assertEqual(baseline_root["summary"], original_root_summary)

    def test_mindmap_studio_page_exposes_frontend_hooks_for_new_backend_capabilities(self) -> None:
        response = self.client.get("/labs/mindmap-studio")
        self.assertEqual(response.status_code, 200)
        html = response.data.decode("utf-8")
        self.assertIn("data-import-url=", html)
        self.assertIn("data-history-url-template=", html)
        self.assertIn("data-diff-url-template=", html)
        self.assertIn("data-restore-url-template=", html)
        self.assertIn("data-analysis-url-template=", html)
        self.assertIn("data-export-markdown-url-template=", html)
        self.assertIn("data-export-mermaid-url-template=", html)
        self.assertIn("data-studio-import", html)
        self.assertIn("data-studio-history", html)
        self.assertIn("data-studio-diff", html)
        self.assertIn("data-studio-analysis", html)
        self.assertIn("data-studio-restore-baseline", html)
        self.assertIn("data-studio-import-input", html)


if __name__ == "__main__":
    unittest.main()
