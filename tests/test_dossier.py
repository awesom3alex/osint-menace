import tempfile
import unittest
from pathlib import Path

import app


class DossierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_dir = app.CASES_DIR
        app.CASES_DIR = Path(self.temp.name)
        self.client = app.app.test_client()
        self.case = app.create_case("Example investigation")
        self.base = "/cases/" + self.case["id"]

    def tearDown(self):
        app.CASES_DIR = self.original_dir
        self.temp.cleanup()

    def test_legacy_case_and_missing_case(self):
        self.assertEqual(self.client.get(self.base + "/dossier").status_code, 200)
        self.assertEqual(self.client.get(self.base + "/report.html").status_code, 200)
        self.assertEqual(self.client.get("/cases/" + "0" * 36 + "/dossier").status_code, 404)

    def test_save_and_exports_escape_markup(self):
        payload = {"subject_name": "Example Subject", "summary": "<script>alert(1)</script>",
                   "result_other": "Candidate only\nSource: example.com"}
        response = self.client.post(self.base + "/dossier", data=payload)
        self.assertEqual(response.status_code, 302)
        stored = app.load_case(self.case["id"])
        self.assertEqual(stored["dossier"]["subject_name"], "Example Subject")
        self.assertEqual(stored["searches"], [])
        html = self.client.get(self.base + "/report.html").get_data(as_text=True)
        self.assertIn("Example Subject", html)
        self.assertNotIn(payload["summary"], html)
        self.assertIn("&lt;script&gt;", html)
        markdown = self.client.get(self.base + "/report.md").get_data(as_text=True)
        self.assertIn("Candidate only", markdown)
        self.assertIn("Provided Bio Info", markdown)

    def test_invalid_save_does_not_overwrite(self):
        response = self.client.post(self.base + "/dossier", data={"summary": "x" * 20001})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("dossier", app.load_case(self.case["id"]))


if __name__ == "__main__":
    unittest.main()
