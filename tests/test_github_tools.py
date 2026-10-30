"""Offline contracts and retained-evidence integration for the six GitHub additions."""

import base64
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

from reportlab.pdfgen import canvas

import addon_tools as addons
import app
import case_backups
import github_tools
import tests.test_case_research as fixtures
import workspace_features
import workspace_store
from demo import DEMO_ID

spec = importlib.util.spec_from_file_location(
    "github_worker", addons.ROOT / "scripts/github_worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


class GitHubToolTests(TestCase):
    setUp = fixtures.ResearchTests.setUp

    def test_inventory_and_navigation(self):
        inventory = github_tools.inventory()
        self.assertEqual(
            {t["id"] for t in inventory},
            {
                "unfurl",
                "waymore",
                "exiftool",
                "subfinder",
                "dnstwist",
                "theharvester",
                "mail-parser",
            },
        )
        self.assertTrue(all(len(t["revision"]) == 40 and t["license"] for t in inventory))
        with patch.object(addons.POOL, "submit") as submit:
            for url in ("/github-tools", "/addons", "/unified", self.base):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
            submit.assert_not_called()
        self.assertIn(b">Research</a>", self.client.get(self.base).data)
        self.assertIn(b"Brand Impersonation", self.client.get("/github-tools").data)
        self.assertIn(b"17 tools.", self.client.get("/addons").data)

    def test_health_checks_launch_tool_entrypoints(self):
        for tool in addons.GITHUB_TOOLS:
            expected = (
                addons.PREFIX / "bin/subfinder" if tool == "subfinder"
                else addons.PREFIX / tool / "bin" / (
                    "theHarvester" if tool == "theharvester" else tool
                )
            )
            with self.subTest(tool=tool), patch("workspace_features.subprocess.run") as process:
                process.return_value.returncode = 0
                response = self.client.post(f"/tools/{tool}/check")
                self.assertEqual(response.json["startup_check"], "passed")
                self.assertEqual(process.call_args.args[0], [str(expected), "--help"])
                process.return_value.returncode = 1
                response = self.client.post(f"/tools/{tool}/check")
                self.assertEqual(response.json["startup_check"], "failed")

    def test_domains_and_url_validation(self):
        for target in (
            "--help",
            "/etc/passwd",
            "example.com/x",
            "localhost",
            "a.local",
            "a.internal",
            "127.0.0.1",
            "https://example.com",
            "example.com;id",
            "*.example.com",
            "a..com",
            "x.com\n-a",
        ):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    addons.command("waymore", target, "domain")
        for target in (
            "file:///etc/passwd",
            "https://user:password@example.com",
            "/etc/passwd",
            "https://example.com\nnext",
        ):
            with self.assertRaises(ValueError):
                addons.command("unfurl", target, "url")
        self.assertEqual(github_tools.validate_target("subfinder", "EXAMPLE.COM."), "example.com")
        command = addons.command("unfurl", "https://example.com/?q=%24%28id%29", "url")
        self.assertEqual(command[-1], "https://example.com/?q=%24%28id%29")
        self.assertIn("github_worker.py", command[1])

    def test_case_scoped_queue_and_review(self):
        with (
            patch.dict(addons.JOBS, {}, clear=True),
            patch.object(addons.POOL, "submit"),
            patch.object(addons, "executable", return_value=Path(sys.executable)),
        ):
            response = self.client.post(
                "/api/github-tools/run",
                json=dict(
                    tool="unfurl",
                    kind="url",
                    target="https://example.com/?ts=1700000000",
                    case_id=self.case["id"],
                ),
            )
            self.assertEqual(response.status_code, 202, response.data)
            key = response.json["id"]
            job = addons.JOBS[key]
            self.assertEqual(job["origin_case_id"], self.case["id"])
            payload = dict(
                menace_github_tool="unfurl",
                records=[dict(label="Decoded timestamp", value="2023-11-14T22:13:20Z")],
                providers=[],
                mode="Local decoding",
            )
            job.update(status="completed", output=json.dumps(payload))
            workspace_store.put(key, "addon", job)
            page = self.client.get(response.json["url"])
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"Decoded timestamp", page.data)
            self.assertIn(b"Decoded timestamp", self.client.get(self.base + "/inbox").data)
            import case_review

            with app.app.test_request_context():
                items = case_review.inbox_items(app.load_case(self.case["id"]))
            self.assertEqual(len(items), 1)
            decision = self.client.post(
                self.base + "/inbox",
                data=dict(
                    key=items[0]["key"],
                    action="accept",
                    notes="Reviewed decoded URL field.",
                    updated_at=app.load_case(self.case["id"])["updated_at"],
                ),
            )
            self.assertEqual(decision.status_code, 302)
            saved = app.load_case(self.case["id"])
            self.assertEqual(len(saved["searches"]), 2)
            self.assertEqual(
                saved["searches"][-1]["results"][0]["findings"][0]["verification_status"],
                "Unverified",
            )
            case_backups.validate_case(saved)

    def test_invalid_launch_and_demo_never_enqueue(self):
        with patch.object(addons.POOL, "submit") as submit:
            for data in (
                [],
                dict(tool=[]),
                dict(tool="exiftool"),
                dict(tool="unfurl", target="file:///etc/passwd", kind="url"),
                dict(tool="waymore", target="x.com", kind="domain", case_id=DEMO_ID),
            ):
                response = self.client.post("/api/github-tools/run", json=data)
                self.assertIn(response.status_code, (400, 403))
            submit.assert_not_called()

    def test_provider_contracts_are_fixed_and_passive_except_disclosed_dns(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(worker, "run", return_value=(0, "", False)) as run,
        ):
            old = os.getcwd()
            os.chdir(folder)
            try:
                for tool in ("waymore", "subfinder", "dnstwist", "theharvester"):
                    worker.external(tool, "example.com")
                    args = run.call_args.args[0]
                    self.assertNotIn("--active", args)
                    self.assertNotIn("--screenshot", args)
                    if tool == "waymore":
                        self.assertEqual(args[args.index("-mode") + 1], "U")
                        self.assertIn("wayback,commoncrawl", args)
                    if tool == "subfinder":
                        self.assertIn("crtsh,hackertarget", args)
                        self.assertIn("-duc", args)
                    if tool == "dnstwist":
                        self.assertIn("--registered", args)
                        self.assertNotIn("--lsh", args)
                        self.assertNotIn("--phash", args)
                    if tool == "theharvester":
                        self.assertIn("crtsh,otx", args)
                        self.assertNotIn("-r", args)
                        self.assertNotIn("-n", args)
            finally:
                os.chdir(old)

    def test_fixture_outputs_keep_provider_details_and_historical_status(self):
        with patch.object(
            worker,
            "run",
            return_value=(0, "https://example.com/old\nhttps://example.com/old\n", False),
        ):
            result, code = worker.external("waymore", "example.com")
        self.assertEqual(code, 0)
        self.assertEqual(len(result["records"]), 1)
        self.assertTrue(result["records"][0]["historical"])
        with patch.object(
            worker,
            "run",
            return_value=(
                0,
                json.dumps(dict(host="a.example.com", sources=["hackertarget"])),
                False,
            ),
        ):
            result, _ = worker.external("subfinder", "example.com")
        self.assertEqual(result["records"][0]["provider_details"], ["hackertarget"])
        self.assertEqual(result["records"][0]["source_url"], "")
        job = dict(
            tool="subfinder",
            target="example.com",
            status="completed",
            timestamp=app.utc_now(),
            output=json.dumps(dict(menace_github_tool="subfinder", **result)),
        )
        section = workspace_features.finding_section(job)
        self.assertEqual(section["findings"][0]["verification_status"], "Unverified")
        self.assertEqual(
            section["findings"][0]["provider_details"]["provider_details"], ["hackertarget"]
        )

    @skipUnless(
        (addons.PREFIX / "unfurl/bin/python").is_file(),
        "Install pinned Unfurl for local extraction integration",
    )
    def test_real_unfurl_offline_worker(self):
        env = dict(os.environ, MENACE_ADDON_PREFIX=str(addons.PREFIX), UNFURL_REMOTE_LOOKUPS="true")
        result = subprocess.run(
            addons.command("unfurl", "https://example.com/?ts=1700000000", "url"),
            capture_output=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["providers"])
        self.assertIn("2023-11-14", json.dumps(payload))
        self.assertIn("remote lookups disabled", payload["mode"])

    @skipUnless(
        (addons.PREFIX / "bin/exiftool").is_file(),
        "Install pinned ExifTool for original-file integration",
    )
    def test_real_metadata_preserves_original_and_supports_review_and_exports(self):
        data = io.BytesIO()
        pdf = canvas.Canvas(data)
        pdf.setAuthor("Fictional Analyst")
        pdf.drawString(72, 720, "Public fixture document")
        pdf.save()
        raw = data.getvalue()
        doc = dict(
            id="c" * 32,
            filename="fictional.pdf",
            mime="application/pdf",
            sha256=hashlib.sha256(raw).hexdigest(),
            original=base64.b64encode(raw).decode(),
            created_at=app.utc_now(),
            ref=self.ref,
            pages=[dict(number=1, text="Public fixture document", method="Fixture")],
        )
        case = app.load_case(self.case["id"])
        case["reader_documents"] = [doc]
        app.save_case(case)
        response = self.client.post(
            self.base + "/reader/" + doc["id"] + "/metadata",
            data=dict(updated_at=case["updated_at"]),
        )
        self.assertEqual(response.status_code, 302, response.data)
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Fictional Analyst", page.data)
        key = response.location.rsplit("/", 1)[-1]
        record = workspace_store.get(key)
        self.assertEqual(record["collector"], "exiftool")
        self.assertEqual(app.load_case(case["id"])["reader_documents"][0], doc)
        self.assertEqual(self.client.get("/history/" + key).status_code, 302)
        entry = next(e for e in record["entries"] if "Author" in e["finding"]["label"])
        exported = self.client.post(
            "/research/results/" + key + "/action", data=dict(selected=[entry["id"]], action="json")
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn(doc["sha256"].encode(), exported.data)
        queued = self.client.post(
            "/research/results/" + key + "/action",
            data=dict(selected=[entry["id"]], action="inbox", case_id=case["id"]),
        )
        self.assertEqual(queued.status_code, 302)
        self.assertIn(b"Author", self.client.get(self.base + "/inbox").data)
        case_backups.validate_case(app.load_case(case["id"]))

    def test_cancel_queued_github_job(self):
        with (
            patch.dict(addons.JOBS, {}, clear=True),
            patch.object(addons.POOL, "submit"),
            patch.object(addons, "executable", return_value=Path(sys.executable)),
        ):
            response = self.client.post(
                "/api/github-tools/run",
                json=dict(tool="unfurl", kind="url", target="https://example.com"),
            )
            key = response.json["id"]
            self.assertEqual(response.status_code, 202)
            response = self.client.post("/api/addons/jobs/" + key + "/cancel")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(workspace_store.get(key)["status"], "cancelled")

    def test_provider_rate_limits_and_partial_output_are_preserved(self):
        with patch.object(worker, "run", return_value=(0, "HTTP 429 Too Many Requests\n", False)):
            result, _ = worker.external("subfinder", "example.com")
        payload = json.dumps(dict(menace_github_tool="subfinder", **result))
        self.assertTrue(addons.observed_rate_limit(payload))
        job = dict(
            tool="subfinder",
            target="example.com",
            timestamp=app.utc_now(),
            status="completed",
            output=payload,
        )
        self.assertIn("rate limit", " ".join(workspace_features.finding_section(job)["notes"]))
