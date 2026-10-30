"""Behavior checks for cross-case review, documents, questions, schedules and workflows."""

import base64
import copy
import hashlib
import io
import shutil
from unittest import TestCase, skipUnless
from unittest.mock import patch

import advanced_research as advanced
import app
import case_backups
import case_research
import tests.test_case_research as fixtures
from demo import DEMO_ID
from tests.test_case_research import capture


class AdvancedTests(TestCase):
    setUp = fixtures.ResearchTests.setUp

    # Reuse the isolated case/evidence/history fixture without inheriting its tests.
    def post(self, route, **data):
        data.setdefault("updated_at", app.load_case(self.case["id"])["updated_at"])
        return self.client.post(self.base + route, data=data)

    def test_new_pages_and_demo_are_readable_without_network(self):
        with patch.object(case_research, "fetch_public_page") as fetch:
            for route in ("connections", "reader", "questions", "monitors", "workflows"):
                result = self.client.get(self.base + "/" + route)
                self.assertEqual(result.status_code, 200, (route, result.data[:500]))
                self.assertEqual(
                    self.client.post("/cases/" + DEMO_ID + "/" + route).status_code, 403
                )
            fetch.assert_not_called()
        self.assertIn(b"Evidence reader", self.client.get(self.base).data)

    def test_cross_case_scope_decision_and_stale_comparison(self):
        other = app.create_case("Other investigation")
        record = copy.deepcopy(self.case["searches"][0])
        app.append_search_to_case(other, record)
        self.assertNotIn(b"analyst@example.com", self.client.get(self.base + "/connections").data)
        response = self.client.get(self.base + "/connections", query_string={"other": other["id"]})
        self.assertIn(b"analyst@example.com", response.data)
        with app.app.test_request_context():
            candidate = advanced.connection_candidates(
                app.load_case(self.case["id"]), [app.load_case(other["id"])]
            )[0]
        payload = dict(
            key=candidate["key"],
            other_id=other["id"],
            other_updated_at="stale",
            decision="linked",
            reason="Shared published contact; ownership unresolved.",
        )
        self.assertEqual(self.post("/connections", **payload).status_code, 409)
        payload["other_updated_at"] = app.load_case(other["id"])["updated_at"]
        before = copy.deepcopy(app.load_case(other["id"]))
        self.assertEqual(self.post("/connections", **payload).status_code, 302)
        self.assertEqual(app.load_case(other["id"]), before)
        saved = app.load_case(self.case["id"])
        self.assertEqual(saved["cross_case_decisions"][0]["decision"], "linked")
        case_backups.validate_case(saved)
        self.assertEqual(advanced.typed_keys("Full name", "Morgan Example"), set())

    def test_document_search_original_hash_and_backup(self):
        raw = b"%PDF-1.4\n%fixture\n"
        doc = dict(
            id="a" * 32,
            filename="source.pdf",
            mime="application/pdf",
            original=base64.b64encode(raw).decode(),
            sha256=hashlib.sha256(raw).hexdigest(),
            pages=[
                dict(number=1, text="Published company address", method="PDF embedded text"),
                dict(number=2, text="Evidence NEEDLE on page two", method="PDF embedded text"),
            ],
            created_at=app.utc_now(),
        )
        with patch.object(advanced, "extract_document", return_value=doc):
            result = self.post("/reader", document=(io.BytesIO(raw), "source.pdf"), ref=self.ref)
        self.assertEqual(result.status_code, 302)
        page = self.client.get(self.base + "/reader?q=needle")
        self.assertIn(b"Page 2", page.data)
        self.assertNotIn(b"Page 1</h2>", page.data)
        self.assertIn(b"#page=2", page.data)
        source = self.client.get(self.base + "/reader/" + doc["id"] + "/original")
        self.assertEqual(source.data, raw)
        self.assertEqual(source.headers["X-Content-Type-Options"], "nosniff")
        saved = app.load_case(self.case["id"])
        case_backups.validate_case(saved)
        archive = case_backups.archive_case(saved)
        backup_path = self.root / "reader.zip"
        with archive:
            backup_path.write_bytes(archive.read())
        restored, _, _ = case_backups.checked_zip(backup_path)
        self.assertEqual(restored["reader_documents"][0]["original"], doc["original"])
        self.assertIn(b"source.pdf", self.client.get(self.base + "/search?q=needle").data)
        saved["reader_documents"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            case_backups.validate_case(saved)
        app.save_case(saved)
        self.assertEqual(
            self.client.get(self.base + "/reader/" + doc["id"] + "/original").status_code, 409
        )

    def test_reader_limits_dependency_error_and_stale_upload(self):
        self.assertEqual(
            self.post(
                "/reader", document=(io.BytesIO(b"x" * (advanced.MAX_DOCUMENT + 1)), "large.pdf")
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "/reader", updated_at="stale", document=(io.BytesIO(b"x"), "image.png")
            ).status_code,
            409,
        )
        with patch.object(
            advanced,
            "extract_document",
            side_effect=ValueError("Local reader dependency missing: tesseract"),
        ):
            result = self.post("/reader", document=(io.BytesIO(b"bytes"), "image.png"))
        self.assertIn(b"dependency missing", result.data)
        self.assertFalse(app.load_case(self.case["id"]).get("reader_documents"))

    def test_questions_conflicting_refs_and_revision_history(self):
        payload = dict(
            title="Who operates the domain?",
            status="Investigating",
            answer="Working hypothesis",
            unanswered="Ownership",
            next_steps="Review filings",
            supporting=[self.ref],
        )
        self.assertEqual(self.post("/questions", **payload).status_code, 302)
        case = app.load_case(self.case["id"])
        question = case["research_questions"][0]
        payload.update(id=question["id"], status="Answered", answer="Published operator identified")
        self.assertEqual(self.post("/questions", **payload).status_code, 302)
        saved = app.load_case(self.case["id"])
        self.assertEqual(len(saved["research_questions"][0]["history"]), 2)
        case_backups.validate_case(saved)
        self.assertIn(
            b"Published operator identified", self.client.get(self.base + "/questions").data
        )
        self.assertEqual(
            self.post("/questions", **dict(payload, conflicting=[self.ref])).status_code, 400
        )
        self.assertEqual(
            self.post("/questions", **dict(payload, supporting=["missing"])).status_code, 400
        )

    def test_monitor_changed_only_review_inbox_and_pause(self):
        self.assertEqual(self.post("/monitors", ref=self.ref, hours=1).status_code, 302)

        def due():
            case = app.load_case(self.case["id"])
            case["source_monitors"][0]["next_run"] = "2000-01-01T00:00:00+00:00"
            app.save_case(case)

        with patch.object(
            case_research,
            "fetch_public_page",
            side_effect=[capture("baseline"), capture("baseline"), capture("changed")],
        ) as fetch:
            for _ in range(3):
                due()
                advanced.monitor_tick()
            self.assertEqual(fetch.call_count, 3)
        saved = app.load_case(self.case["id"])
        finding = case_research.locate(saved, self.ref)
        self.assertEqual(len(finding["observations"]), 2)
        self.assertIn(b"Source change", self.client.get(self.base + "/inbox").data)
        self.assertEqual(saved["source_monitors"][0]["outcome"], "Changed; review inbox")
        case_backups.validate_case(saved)
        for _ in range(3):
            due()
            with patch.object(
                case_research, "fetch_public_page", side_effect=ValueError("Unavailable")
            ):
                advanced.monitor_tick()
        saved = app.load_case(self.case["id"])
        self.assertFalse(saved["source_monitors"][0]["enabled"])
        self.assertEqual(saved["source_monitors"][0]["failures"], 3)
        self.assertEqual(
            self.post(
                "/monitors", id=saved["source_monitors"][0]["id"], action="resume"
            ).status_code,
            302,
        )
        self.assertEqual(
            self.post(
                "/monitors", id=saved["source_monitors"][0]["id"], action="pause"
            ).status_code,
            302,
        )
        with patch.object(case_research, "fetch_public_page") as fetch:
            advanced.monitor_tick()
            fetch.assert_not_called()

    def test_restored_monitors_and_changed_urls_never_silently_run(self):
        self.post("/monitors", ref=self.ref, hours=24)
        case = app.load_case(self.case["id"])
        case["source_monitors"][0]["owner_case_id"] = "old-case"
        app.save_case(case)
        with patch.object(case_research, "fetch_public_page") as fetch:
            advanced.monitor_tick()
            fetch.assert_not_called()
        self.assertIn(b"Paused", self.client.get(self.base + "/monitors").data)
        self.assertEqual(self.post("/monitors", ref=self.ref, hours=24).status_code, 409)

    def test_workflow_order_progress_reuse_and_prefills(self):
        payload = dict(
            title="Domain review",
            target="example.com",
            kind="domain",
            steps=["review", "search", "archive", "identifiers"],
            order="review,identifiers,search,archive",
        )
        self.assertEqual(self.post("/workflows", **payload).status_code, 302)
        case = app.load_case(self.case["id"])
        workflow = case["research_workflows"][0]
        self.assertEqual(
            [s["kind"] for s in workflow["steps"]], ["review", "identifiers", "search", "archive"]
        )
        url = self.base + "/workflows/" + workflow["id"]
        search = self.client.get(url + "/2/open", follow_redirects=True)
        self.assertIn(b'value="example.com"', search.data)
        archive = self.client.get(url + "/3/open", follow_redirects=True)
        self.assertIn(b'data-selected="archive_history"', archive.data)
        self.assertIn(b"https://example.com", archive.data)
        related = self.client.get(url + "/1/open", follow_redirects=True)
        self.assertIn(b"analyst@example.com", related.data)
        self.assertEqual(
            self.post(
                "/workflows",
                id=workflow["id"],
                action="complete",
                index=0,
                note="Reviewed existing sources",
            ).status_code,
            302,
        )
        self.assertIn(b"Reviewed existing sources", self.client.get(self.base + "/workflows").data)
        self.assertEqual(
            self.post("/workflows", **dict(payload, target="another.example")).status_code, 302
        )
        saved = app.load_case(self.case["id"])
        self.assertEqual(len(saved["research_workflows"]), 2)
        self.assertFalse(saved["research_workflows"][1]["steps"][0]["done"])
        case_backups.validate_case(saved)

    def test_import_rejects_malformed_schedules_and_workflows(self):
        self.post("/monitors", ref=self.ref, hours=24)
        case = app.load_case(self.case["id"])
        case["source_monitors"][0]["next_run"] = "tomorrow"
        with self.assertRaises(ValueError):
            case_backups.validate_case(case)
        case["source_monitors"] = []
        case["research_workflows"] = [
            dict(
                id="a" * 32,
                title="x",
                target="x",
                kind="domain",
                created_at="",
                steps=[dict(kind="execute_shell", done=False, note="", timestamp="")],
            )
        ]
        with self.assertRaises(ValueError):
            case_backups.validate_case(case)

    @skipUnless(
        all(shutil.which(t) for t in ("pdfinfo", "pdftotext", "pdftoppm", "tesseract")),
        "Install local reader dependencies for extraction integration test",
    )
    def test_real_pdf_text_screenshot_and_scanned_pdf(self):
        from PIL import Image, ImageDraw, ImageFont
        from reportlab.pdfgen import canvas

        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.drawString(72, 720, "First page public evidence")
        pdf.showPage()
        pdf.drawString(72, 720, "Second page ALPHA42 evidence")
        pdf.save()
        result = advanced.extract_document(data.getvalue(), "pages.pdf")
        self.assertEqual(len(result["pages"]), 2)
        self.assertIn("ALPHA42", result["pages"][1]["text"])
        self.assertEqual(base64.b64decode(result["original"]), data.getvalue())
        image = Image.new("RGB", (1400, 300), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=64)
        draw.text((40, 90), "PUBLIC EVIDENCE ALPHA42", font=font, fill="black")
        png = io.BytesIO()
        image.save(png, format="PNG")
        result = advanced.extract_document(png.getvalue(), "screenshot.png")
        self.assertIn("ALPHA42", result["pages"][0]["text"])
        scanned = io.BytesIO()
        image.save(scanned, format="PDF", resolution=100)
        result = advanced.extract_document(scanned.getvalue(), "scanned.pdf")
        self.assertIn("ALPHA42", result["pages"][0]["text"])
        self.assertIn("OCR", result["pages"][0]["method"])

    def test_changed_source_is_paused_without_contact(self):
        self.post("/monitors", ref=self.ref, hours=24)
        case = app.load_case(self.case["id"])
        case_research.locate(case, self.ref)["source_url"] = "https://new.example/source"
        app.save_case(case)
        with patch.object(case_research, "fetch_public_page") as fetch:
            advanced.monitor_tick()
            fetch.assert_not_called()
        self.assertFalse(app.load_case(self.case["id"])["source_monitors"][0]["enabled"])

    def test_monitor_retention_limit_preserves_originals(self):
        self.post("/monitors", ref=self.ref, hours=24)
        case = app.load_case(self.case["id"])
        finding = case_research.locate(case, self.ref)
        finding["observations"] = [
            dict(capture(str(i)), id=format(i, "032x"), timestamp=app.utc_now()) for i in range(25)
        ]
        app.save_case(case)
        with patch.object(
            case_research, "fetch_public_page", return_value=capture("new observation")
        ):
            advanced.monitor_tick()
        saved = app.load_case(self.case["id"])
        self.assertFalse(saved["source_monitors"][0]["enabled"])
        self.assertEqual(
            case_research.locate(saved, self.ref)["observations"], finding["observations"]
        )

    def test_monitor_storage_limit_pauses_without_repeated_fetch(self):
        self.post("/monitors", ref=self.ref, hours=24)
        case = app.load_case(self.case["id"])
        limit = len(case_backups.encode(case)) + 1500
        with (
            patch.object(
                case_research, "fetch_public_page", return_value=capture("x" * 5000)
            ) as fetch,
            patch.object(case_backups, "MAX_CASE", limit),
        ):
            advanced.monitor_tick()
            advanced.monitor_tick()
            self.assertEqual(fetch.call_count, 1)
        saved = app.load_case(self.case["id"])
        self.assertFalse(saved["source_monitors"][0]["enabled"])
        self.assertFalse(case_research.locate(saved, self.ref).get("observations"))
        self.assertLessEqual(len(case_backups.encode(saved)), limit)
