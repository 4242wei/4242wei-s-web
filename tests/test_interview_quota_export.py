from __future__ import annotations

import unittest
import zipfile
from datetime import datetime
from io import BytesIO
from xml.etree import ElementTree

from interview_quota_export import (
    QUOTA_STATUS_COMPLETED,
    QUOTA_STATUS_SCHEDULED,
    build_interview_quota_records,
    build_interview_quota_view,
    build_interview_quota_workbook,
)


class InterviewQuotaExportTest(unittest.TestCase):
    def fixture(self):
        return [
            {
                "id": "exp-1",
                "source_record_id": "#1",
                "name": "Completed Expert",
                "current_employer": "Example Bank",
                "company_scale": "超大型",
                "industry": "金融",
                "region": "欧洲",
                "interviews": [
                    {
                        "id": "int-1",
                        "status": "a-renamed-status-key",
                        "quota_status": "completed",
                        "occurred_at": "2026-08-01T10:00",
                    }
                ],
            },
            {
                "id": "exp-2",
                "source_record_id": "#2",
                "name": "Scheduled Expert",
                "current_employer": "Example Telco",
                "company_scale": "大型",
                "industry": "电信",
                "region": "北美",
                "interviews": [
                    {
                        "id": "int-2",
                        "status": "another-renamed-status-key",
                        "quota_status": "scheduled",
                        "occurred_at": "2026-09-01T10:00",
                    }
                ],
            },
            {
                "id": "exp-3",
                "source_record_id": "#3",
                "name": "Excluded Expert",
                "company_scale": "大型",
                "industry": "电信",
                "region": "北美",
                "interviews": [
                    {
                        "id": "int-3",
                        "status": "completed",
                        "quota_status": "excluded",
                        "transcript_id": "transcript-3",
                    }
                ],
            },
            {
                "id": "exp-4",
                "source_record_id": "#4",
                "name": "Transcript Expert",
                "company_scale": "中型",
                "industry": "软件",
                "region": "亚洲",
                "interviews": [
                    {
                        "id": "int-4",
                        "status": "planned",
                        "quota_status": "",
                        "transcript_id": "transcript-4",
                    }
                ],
            },
        ]

    def test_explicit_quota_codes_are_independent_from_expert_status_labels(self) -> None:
        records = build_interview_quota_records(
            self.fixture(), now=datetime(2026, 8, 10, 9, 0)
        )
        by_name = {record.name: record for record in records}
        self.assertEqual(by_name["Completed Expert"].quota_status, QUOTA_STATUS_COMPLETED)
        self.assertEqual(by_name["Scheduled Expert"].quota_status, QUOTA_STATUS_SCHEDULED)
        self.assertEqual(by_name["Transcript Expert"].quota_status, QUOTA_STATUS_COMPLETED)
        self.assertNotIn("Excluded Expert", by_name)

    def test_xlsx_package_has_matrix_detail_and_status_colors(self) -> None:
        payload, records = build_interview_quota_workbook(
            self.fixture(), generated_at=datetime(2026, 8, 10, 9, 0)
        )
        self.assertEqual(len(records), 3)
        self.assertTrue(payload.startswith(b"PK"))
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            required = {
                "[Content_Types].xml",
                "xl/workbook.xml",
                "xl/styles.xml",
                "xl/worksheets/sheet1.xml",
                "xl/worksheets/sheet2.xml",
            }
            self.assertTrue(required.issubset(archive.namelist()))
            for name in required:
                ElementTree.fromstring(archive.read(name))
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            matrix_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            styles_xml = archive.read("xl/styles.xml").decode("utf-8")
        self.assertIn("约访进度", workbook_xml)
        self.assertIn("记录明细", workbook_xml)
        self.assertIn("Completed Expert", matrix_xml)
        self.assertIn("Scheduled Expert", matrix_xml)
        self.assertNotIn("Excluded Expert", matrix_xml)
        self.assertIn("FF16805D", matrix_xml)
        self.assertIn("FF2F6FED", matrix_xml)
        self.assertIn("FFE5F6EE", styles_xml)
        self.assertIn("FFE8F1FF", styles_xml)

    def test_page_view_uses_companies_and_compact_dates(self) -> None:
        experts = self.fixture()
        experts[0]["interviews"].append(
            {
                "id": "int-1b",
                "status": "completed",
                "quota_status": "completed",
                "occurred_at": "2026-08-02T11:00",
            }
        )
        experts.append(
            {
                "id": "exp-5",
                "source_record_id": "#5",
                "name": "Second Completed Expert",
                "current_employer": "Second Bank",
                "company_scale": "超大型",
                "industry": "金融",
                "region": "欧洲",
                "interviews": [
                    {
                        "id": "int-5",
                        "status": "completed",
                        "quota_status": "completed",
                        "occurred_at": "2026-08-03T09:00",
                    }
                ],
            }
        )
        view = build_interview_quota_view(
            experts, now=datetime(2026, 8, 10, 9, 0)
        )
        rendered_records = [
            record
            for group in view["groups"]
            for row in group["rows"]
            for cell in row["cells"]
            for record in cell["records"]
        ]
        completed = next(item for item in rendered_records if item["company"] == "Example Bank")
        self.assertEqual(completed["interview_dates"], ["08.01", "08.02"])
        self.assertEqual(completed["interview_count"], 2)
        self.assertNotIn("name", completed)
        shared_cell = next(
            cell
            for group in view["groups"]
            if group["scale"] == "超大型"
            for row in group["rows"]
            if row["industry"] == "金融"
            for cell in row["cells"]
            if cell["region"] == "欧洲"
        )
        self.assertEqual(
            [item["company"] for item in shared_cell["records"]],
            ["Example Bank", "Second Bank"],
        )


if __name__ == "__main__":
    unittest.main()
