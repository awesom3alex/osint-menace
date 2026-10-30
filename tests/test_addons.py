import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import addon_tools as addons
import app


class AddonTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.history_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.history_dir.cleanup)
        history_patch = patch(
            "workspace_store.DB_PATH", Path(self.history_dir.name) / "history.sqlite3"
        )
        history_patch.start()
        self.addCleanup(history_patch.stop)

    def test_inventory_and_ui(self):
        response = self.client.get("/api/addons")
        self.assertEqual(len(response.json), 17)
        self.assertEqual({t["id"]: t["installed"] for t in response.json},
                         {key: addons.executable(key).is_file() for key in addons.TOOLS})
        page = self.client.get("/addons")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"WhatsMyName Search", page.data)
        with patch("addon_tools.executable") as binary, patch("tool_credentials.values", return_value={}):
            binary.return_value.is_file.return_value = True
            self.assertIn(b"Needs session", self.client.get("/addons").data)
        self.assertIn(b"/addons", self.client.get("/").data)

    def test_input_validation(self):
        for data in [
            [1, 2],
            dict(tool="unknown", kind="username", target="test"),
            dict(tool="sherlock", kind="username", target="--help"),
            dict(tool="sherlock", kind="username", target="x;touch/tmp/no"),
            dict(tool="holehe", kind="username", target="user"),
            dict(tool="clank", kind="phone", target="abc"),
            dict(tool="sherlock", kind="username", target=["user"]),
            dict(tool="ignorant", kind="phone", target="+14155552671", country="44"),
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post("/api/addons/run", json=data).status_code, 400)

    def test_no_session_exposure(self):
        with patch.dict("os.environ", {"INSTAGRAM_SESSION_ID": ""}):
            response = self.client.post(
                "/api/addons/run", json=dict(tool="toutatis", kind="username", target="example")
            )
            self.assertEqual(response.status_code, 400)
        with patch.dict("os.environ", {"INSTAGRAM_SESSION_ID": "private-session"}):
            self.assertNotIn(b"private-session", self.client.get("/api/addons").data)

    def test_ignorant_country_split(self):
        cmd = addons.command("ignorant", "+14155552671", "phone", "1")
        self.assertEqual(cmd[1:3], ["1", "4155552671"])

    def test_capacity(self):
        with patch("addon_tools.executable") as binary:
            binary.return_value.is_file.return_value = True
            self.check_capacity()

    def check_capacity(self):
        with patch.dict(
            addons.JOBS,
            {str(i): {"status": "running", "created": time.time()} for i in range(2)},
            clear=True,
        ):
            self.assertEqual(
                self.client.post(
                    "/api/addons/run", json=dict(tool="clank", kind="phone", target="+14155552671")
                ).status_code,
                429,
            )

    @unittest.skipUnless(addons.executable("clank").is_file(), "Requires installed Clank")
    def test_local_clank_run_and_case_capture(self):
        # Reserved fictional number; Clank's --local mode stays offline.
        response = self.client.post(
            "/api/addons/run", json=dict(tool="clank", kind="phone", target="+14155552671")
        )
        self.assertEqual(response.status_code, 202)
        job_id = response.json["id"]
        for _ in range(150):
            job = self.client.get("/api/addons/jobs/" + job_id).json
            if job["status"] not in ("queued", "running"):
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "completed", job["output"])
        self.assertIn("4155552671", job["output"])
        with tempfile.TemporaryDirectory() as folder, patch.object(app, "CASES_DIR", Path(folder)):
            case = app.create_case("Addon smoke test")
            section = dict(
                name="Clank smoke test",
                findings=[dict(label="Output", value=job["output"], source="Clank")],
                links=[],
                notes=[],
            )
            saved = self.client.post(
                "/cases/add-result",
                data=dict(
                    case_id=case["id"],
                    query=job["target"],
                    search_type="addon:clank",
                    section_json=json.dumps(section),
                ),
            )
            self.assertEqual(saved.status_code, 302)
            stored = app.load_case(case["id"])
            self.assertEqual(
                stored["searches"][0]["results"][0]["findings"][0]["value"], job["output"]
            )

    def test_failed_process_reported(self):
        with patch.dict(addons.JOBS, {"failure": {"tool": "clank"}}, clear=True):
            addons.execute("failure", ["/bin/sh", "-c", "echo failed-test; exit 2"])
            self.assertEqual(addons.JOBS["failure"]["status"], "failed")
            self.assertEqual(addons.JOBS["failure"]["exit_code"], 2)

    def test_missing_job(self):
        self.assertEqual(self.client.get("/api/addons/jobs/missing").status_code, 404)


if __name__ == "__main__":
    unittest.main()
