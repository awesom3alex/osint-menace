import tempfile
import threading
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import addon_tools as addons
import app
import case_features
import workspace_features as features
import workspace_store as store


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.patches = [
            patch.object(store, "DB_PATH", folder / "history.sqlite3"),
            patch.object(app, "CASES_DIR", folder / "cases"),
            patch.object(case_features, "EVIDENCE_DIR", folder / "evidence"),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.client = app.app.test_client()
        self.case = app.create_case("Workspace validation", "Authorized local test")
        self.section = dict(
            name="Test results",
            module=dict(name="Clank", mode="local"),
            findings=[
                dict(
                    label="Number", value={"valid": True, "region": "US"}, source="Local metadata"
                ),
                dict(label="Exclude this secret finding", value="DO_NOT_PRINT", source="Test"),
            ],
            links=[dict(label="Source", value="https://example.com/source", source="Test")],
            notes=["Retrieved from test fixture"],
        )
        search = app.make_search_record(
            "phone", "+14155552671", [self.section], app.result_summary([self.section])
        )
        app.append_search_to_case(self.case, search)
        self.search = search
        self.review_url = f"/cases/{self.case['id']}/review/{search['id']}/0/0"
        self.evidence_url = f"/cases/{self.case['id']}/evidence/{search['id']}/0/0"

    def test_unified_persists_and_reopens_without_rerun(self):
        with patch.object(addons.POOL, "submit") as submit:
            response = self.client.post(
                "/api/unified",
                json=dict(target="+14155552671", kind="phone", tools=["clank", "phoneinfoga"]),
            )
            self.assertEqual(response.status_code, 202, response.data)
            group = store.get(response.json["id"])
            self.assertEqual(len(group["job_ids"]), 2)
            self.assertEqual(submit.call_count, 2)
            for key in group["job_ids"]:
                job = store.get(key)
                job.update(status="completed", output='{"valid":true}')
                store.put(key, "addon", job)
            with patch.dict(addons.JOBS, {}, clear=True):
                history = self.client.get(response.json["url"])
                self.assertEqual(history.status_code, 200)
                self.assertIn(b"Valid number", history.data)
                self.assertEqual(submit.call_count, 2)
            self.assertEqual(len(store.history()), 1)

    def test_invalid_batch_is_atomic(self):
        with patch.object(addons.POOL, "submit") as submit:
            for payload in [
                dict(target="abc", kind="username", tools=["clank"]),
                dict(target="abc", kind="username", tools=["sherlock", "unknown"]),
                dict(target="abc", kind="username", tools=["sherlock", "sherlock"]),
            ]:
                self.assertEqual(self.client.post("/api/unified", json=payload).status_code, 400)
            submit.assert_not_called()
            self.assertEqual(store.history(), [])

    def test_restart_recovery(self):
        store.put(
            "job", "addon", dict(id="job", tool="clank", target="test", status="running", output="")
        )
        store.recover()
        self.assertEqual(store.get("job")["status"], "interrupted")

    def test_parallel_health_and_history(self):
        errors = []

        def write(i):
            try:
                store.put(str(i), "console", dict(id=str(i), target=str(i), timestamp=store.now()))
                store.update_health("clank", last_status="completed", last_success=store.now())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(store.history()), 8)
        self.assertEqual(store.health()["clank"]["last_status"], "completed")

    def test_review_and_report_selection(self):
        self.assertEqual(
            self.client.post(
                self.review_url,
                data=dict(
                    status="Confirmed", analyst_notes="Checked source", include_in_report="on"
                ),
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                self.review_url[:-1] + "1",
                data=dict(status="False positive", analyst_notes="Exclude this"),
            ).status_code,
            200,
        )
        case = app.load_case(self.case["id"])
        finding = case["searches"][0]["results"][0]["findings"][0]
        self.assertEqual(finding["verification_status"], "Confirmed")
        self.assertIn("reviewed_at", finding)
        html = self.client.get(f"/cases/{self.case['id']}/report.html")
        self.assertEqual(html.status_code, 200)
        self.assertIn(b"Checked source", html.data)
        self.assertNotIn(b"DO_NOT_PRINT", html.data)
        markdown = app.render_markdown_report(case)
        self.assertNotIn("DO_NOT_PRINT", markdown)
        self.assertIn("Confirmed", markdown)
        self.assertEqual(
            self.client.post(self.review_url, data=dict(status="invalid")).status_code, 400
        )

    def test_evidence_validation_and_serving(self):
        image = Image.new("RGB", (200, 100), "white")
        buffer = BytesIO()
        image.save(buffer, "PNG")
        buffer.seek(0)
        response = self.client.post(
            self.evidence_url,
            data={
                "screenshot": (buffer, "evidence.png"),
                "caption": "Screenshot source: https://example.com",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200, response.data)
        url = response.json["evidence"]["url"]
        served = self.client.get(url)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.mimetype, "image/png")
        served.close()
        self.assertEqual(self.client.get(url.replace(self.case["id"], "0" * 36)).status_code, 404)
        invalid = self.client.post(
            self.evidence_url,
            data={"screenshot": (BytesIO(b"<script>bad</script>"), "bad.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 400)

    def test_pdf_download(self):
        self.client.post(
            self.review_url,
            data=dict(status="Confirmed", analyst_notes="PDF analyst note", include_in_report="on"),
        )
        self.client.post(self.review_url[:-1] + "1", data=dict(status="False positive"))
        response = self.client.get(f"/cases/{self.case['id']}/report.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.data.startswith(b"%PDF"))
        self.assertIn("attachment;", response.headers["Content-Disposition"])
        # Poppler verifies content and selection using an independent parser.
        import subprocess

        file = Path(self.temp.name) / "report.pdf"
        file.write_bytes(response.data)
        text = subprocess.check_output(["pdftotext", str(file), "-"], text=True)
        self.assertIn("PDF analyst note", text)
        self.assertIn("Confirmed", text)
        self.assertNotIn("DO_NOT_PRINT", text)

    def test_pages_and_local_check(self):
        for url in ("/unified", "/history", "/tools", f"/cases/{self.case['id']}"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        response = self.client.post("/tools/clank/check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.health()["clank"]["startup_check"], "passed")
        self.assertEqual(self.client.post("/tools/unknown/check").status_code, 404)

    def test_case_notes(self):
        self.assertEqual(
            self.client.post(
                f"/cases/{self.case['id']}/notes", data=dict(notes="Updated case context")
            ).status_code,
            200,
        )
        self.assertEqual(app.load_case(self.case["id"])["notes"], "Updated case context")

    def test_rate_limit_detection(self):
        self.assertFalse(addons.observed_rate_limit('{"rateLimit":false}'))
        self.assertTrue(addons.observed_rate_limit('{"rateLimit":true}'))
        self.assertTrue(addons.observed_rate_limit("HTTP 429: too many requests"))

    def test_reported_urls_can_be_reviewed_individually(self):
        job = dict(
            tool="sherlock",
            target="example",
            timestamp=store.now(),
            status="completed",
            output="[+] GitHub: https://example.com/profile1\n[+] Reddit: https://example.com/profile2",
        )
        section = features.finding_section(job)
        self.assertEqual(len(section["findings"]), 2)
        self.assertEqual(len(section["links"]), 2)

    def test_concurrent_case_captures_preserve_both_writes(self):
        import copy

        stale_a = copy.deepcopy(self.case)
        stale_b = copy.deepcopy(self.case)

        def add(case, label):
            search = app.make_search_record(
                "username", label, [self.section], app.result_summary([self.section])
            )
            app.append_search_to_case(case, search)

        threads = [
            threading.Thread(target=add, args=(stale_a, "first")),
            threading.Thread(target=add, args=(stale_b, "second")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(app.load_case(self.case["id"])["searches"]), 3)

    def test_case_deletion_removes_its_evidence(self):
        image = Image.new("RGB", (20, 20), "white")
        buffer = BytesIO()
        image.save(buffer, "PNG")
        buffer.seek(0)
        response = self.client.post(
            self.evidence_url,
            data={"screenshot": (buffer, "evidence.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        folder = case_features.EVIDENCE_DIR / self.case["id"]
        self.assertTrue(folder.exists())
        response = self.client.post(
            f"/cases/{self.case['id']}/delete", data={"confirm_name": self.case["name"]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(folder.exists())
