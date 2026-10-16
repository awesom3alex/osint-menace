"""Compatibility between the published terminal/dossier and web workspaces."""

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from docx import Document
from PIL import Image

import app
import case_backups
import case_features
import case_workflow
import version
from word_report import build_word_report


class ReleaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, key, value in [
            (app, "CASES_DIR", root / "cases"),
            (case_features, "EVIDENCE_DIR", root / "evidence"),
            (case_backups, "STAGING", root / "previews"),
        ]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.client = app.app.test_client()

    def test_web_and_terminal_share_version(self):
        self.assertEqual(version.__version__, app.APP_VERSION)
        self.assertEqual(self.client.get("/api/version").json["version"], version.__version__)

    def test_demo_is_read_only_with_all_export_links(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Download Word", response.data)
        self.assertIn(b"Download PDF", response.data)
        self.assertNotIn(b"Save case notes", response.data)
        for suffix in ["/delete", "/notes", "/dossier"]:
            self.assertEqual(self.client.post("/cases/" + app.DEMO_ID + suffix).status_code, 403)
        image = BytesIO()
        Image.new("RGB", (20, 20), "white").save(image, "PNG")
        image.seek(0)
        self.assertEqual(
            self.client.post(
                "/cases/" + app.DEMO_ID + "/evidence/fake/0/0",
                data={"screenshot": (image, "sample.png")},
            ).status_code,
            403,
        )
        self.assertFalse(case_features.EVIDENCE_DIR.exists())

    def test_word_report_respects_selection_and_lists_merged_sources(self):
        case = app.create_case("Combined reports")
        for source in ["Tool A", "Tool B"]:
            section = dict(
                name="Profile",
                module=dict(name=source),
                findings=[
                    dict(label="URL", value="https://example.com/profile", source=source),
                    dict(label="Hidden", value="MUST_NOT_APPEAR", include_in_report=False),
                ],
                links=[],
                notes=[],
            )
            record = app.make_search_record(
                "username", "sample", [section], app.result_summary([section])
            )
            app.append_search_to_case(case, record)
        key = next(
            group["key"]
            for group in case_workflow.duplicate_groups(case)
            if group["members"][0]["label"] == "URL"
        )
        self.client.post("/cases/" + case["id"] + "/duplicates/merge", data={"key": key})
        text = "\n".join(
            paragraph.text
            for paragraph in Document(build_word_report(app.load_case(case["id"]))).paragraphs
        )
        self.assertNotIn("MUST_NOT_APPEAR", text)
        self.assertIn("Merged source: Tool A", text)
        self.assertIn("Merged source: Tool B", text)

    def test_dossier_survives_verified_backup(self):
        case = app.create_case("Dossier backup")
        self.client.post(
            "/cases/" + case["id"] + "/dossier", data={"summary": "Synthetic investigation context"}
        )
        with case_backups.archive_case(app.load_case(case["id"])) as archive:
            path = Path(self.temp.name) / "case.zip"
            path.write_bytes(archive.read())
        restored, _, _ = case_backups.checked_zip(path)
        self.assertEqual(restored["dossier"]["summary"], "Synthetic investigation context")
