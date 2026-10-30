"""Original retention, offline mail parsing, safe previews, and reviewed case findings."""

import copy
import hashlib
import io
import json
import subprocess
from email.message import EmailMessage
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch

import app
import case_backups
import email_evidence as evidence
import tests.test_case_research as fixtures
import workspace_store
from demo import DEMO_ID


def message():
    mail = EmailMessage()
    mail["From"] = "Harbor Billing <billing@harbor.example>"
    mail["Reply-To"] = "support@vendor.example"
    mail["Return-Path"] = "<bounce@mailer.example>"
    mail["To"] = "analyst@example.com"
    mail["Subject"] = "Fictional invoice review"
    mail["Date"] = "Thu, 29 Oct 2026 12:00:00 -0500"
    mail["Message-ID"] = "<fixture-001@harbor.example>"
    mail["Received"] = (
        "from sender.example (sender.example [192.0.2.10]) by inbox.example with ESMTP; Thu, 29 Oct 2026 12:00:01 -0500"
    )
    mail["Authentication-Results"] = "inbox.example; spf=pass smtp.mailfrom=harbor.example"
    mail.set_content("Fictional fixture. https://example.com/invoice?ts=1700000000")
    mail.add_alternative(
        '<p>Fictional <b>HTML</b> body</p><img src="https://tracker.example/pixel"><script>alert("NO_EXECUTION")</script><a href="https://example.com/check">Inspect link</a>',
        subtype="html",
    )
    mail.add_attachment(
        b"Fictional attachment.",
        maintype="application",
        subtype="octet-stream",
        filename="../../fixture.txt",
    )
    return mail.as_bytes()


def parsed():
    return dict(
        subject="Fictional invoice review",
        headers=[dict(name="From", value="billing@harbor.example")],
        selected_headers={
            "From": ["billing@harbor.example"],
            "Reply-To": ["support@vendor.example"],
        },
        addresses=[
            dict(field="from_", display_name="Harbor Billing", address="billing@harbor.example")
        ],
        received=[dict(hop=1, **{"from": "sender.example", "by": "inbox.example"})],
        plain_text="https://example.com/check",
        html_text="Inert HTML text",
        urls=["https://example.com/check"],
        ips=["192.0.2.10"],
        attachments=[
            dict(
                filename="fixture.txt",
                content_type="text/plain",
                disposition="attachment",
                size=20,
                sha256=hashlib.sha256(b"Fictional attachment.").hexdigest(),
                content_id="",
                note="Metadata only; not opened or executed.",
            )
        ],
        defects={"has_defects": False},
        date="2026-10-29T17:00:00+00:00",
        warnings=[],
        trust_note="Header claims are not authenticated.",
    )


class EmailEvidenceTests(TestCase):
    def setUp(self):
        fixtures.ResearchTests.setUp(self)
        self.raw = message()

    def upload(self, raw=None, **extra):
        data = dict(
            updated_at=app.load_case(self.case["id"])["updated_at"],
            email=(io.BytesIO(self.raw if raw is None else raw), "fixture.eml"),
        )
        data.update(extra)
        return self.client.post(self.base + "/email-evidence", data=data)

    def retain(self):
        with patch.object(evidence, "parse_original", return_value=parsed()):
            response = self.upload()
        self.assertEqual(response.status_code, 302, response.data)
        return app.load_case(self.case["id"])["email_evidence"][0]

    def test_pages_and_case_navigation_do_not_parse(self):
        with patch.object(evidence, "parse_original") as parse:
            for url in ("/email-evidence", self.base + "/email-evidence", "/github-tools"):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
            parse.assert_not_called()
        self.assertIn(b"Email Evidence", self.client.get(self.base).data)
        self.assertEqual(self.client.post("/cases/" + DEMO_ID + "/email-evidence").status_code, 403)

    def test_original_retention_hash_download_and_case_zip(self):
        item = self.retain()
        case = app.load_case(self.case["id"])
        response = self.client.get(self.base + "/email-evidence/" + item["id"])
        self.assertEqual(response.status_code, 200)
        original = self.client.get(self.base + "/email-evidence/" + item["id"] + "/original")
        self.assertEqual(original.data, self.raw)
        self.assertIn("attachment", original.headers["Content-Disposition"])
        case_backups.validate_case(case)
        archive = case_backups.archive_case(case)
        path = self.root / "email-case.zip"
        with archive:
            path.write_bytes(archive.read())
        restored, _, _ = case_backups.checked_zip(path)
        self.assertEqual(restored["email_evidence"][0], item)
        self.assertIn(
            b"Fictional invoice review", self.client.get(self.base + "/search?q=fixture.txt").data
        )
        case["email_evidence"][0]["sha256"] = "0" * 64
        app.save_case(case)
        self.assertEqual(
            self.client.get(self.base + "/email-evidence/" + item["id"] + "/original").status_code,
            409,
        )
        with self.assertRaises(ValueError):
            case_backups.validate_case(case)

    def test_duplicate_stale_bad_extension_and_failed_parse_do_not_save(self):
        self.retain()
        with patch.object(evidence, "parse_original") as parse:
            self.assertEqual(self.upload().status_code, 409)
            self.assertEqual(self.upload(updated_at="stale").status_code, 409)
            self.assertEqual(self.upload(email=(io.BytesIO(b"bad"), "mail.msg")).status_code, 400)
            parse.assert_not_called()
        self.assertEqual(len(app.load_case(self.case["id"])["email_evidence"]), 1)
        with patch.object(
            evidence,
            "parse_original",
            side_effect=ValueError("No recognizable email headers were found."),
        ):
            response = self.upload(raw=b"From: new@example.com\nSubject: Other\n\nbody")
            self.assertEqual(response.status_code, 400)
            self.assertIn(b"No recognizable email headers", response.data)
        self.assertEqual(len(app.load_case(self.case["id"])["email_evidence"]), 1)

    def test_selected_review_and_exports_keep_original_provenance(self):
        item = self.retain()
        url = self.base + "/email-evidence/" + item["id"] + "/review"
        response = self.client.post(
            url, data=dict(updated_at=app.load_case(self.case["id"])["updated_at"])
        )
        self.assertEqual(response.status_code, 302)
        key = response.location.rsplit("/", 1)[-1]
        record = workspace_store.get(key)
        entry = next(e for e in record["entries"] if e["finding"]["label"] == "Email")
        self.assertEqual(entry["finding"]["email_provenance"]["original_sha256"], item["sha256"])
        second = self.client.post(
            url, data=dict(updated_at=app.load_case(self.case["id"])["updated_at"])
        )
        self.assertEqual(second.location, response.location)
        export = self.client.post(
            "/research/results/" + key + "/action", data=dict(selected=[entry["id"]], action="json")
        )
        self.assertEqual(export.status_code, 200)
        self.assertIn(item["sha256"].encode(), export.data)
        queued = self.client.post(
            "/research/results/" + key + "/action",
            data=dict(selected=[entry["id"]], action="inbox", case_id=self.case["id"]),
        )
        self.assertEqual(queued.status_code, 302)
        self.assertIn(b"billing@harbor.example", self.client.get(self.base + "/inbox").data)
        self.assertEqual(len(app.load_case(self.case["id"])["searches"]), 1)
        import case_review

        with app.app.test_request_context():
            pending = case_review.inbox_items(app.load_case(self.case["id"]))
        self.assertEqual(len(pending), 1)
        accepted = self.client.post(
            self.base + "/inbox",
            data=dict(
                key=pending[0]["key"],
                action="accept",
                notes="Reviewed the claimed sender from the retained fixture.",
                updated_at=app.load_case(self.case["id"])["updated_at"],
            ),
        )
        self.assertEqual(accepted.status_code, 302)
        case = app.load_case(self.case["id"])
        finding = case["searches"][-1]["results"][0]["findings"][0]
        self.assertEqual(finding["verification_status"], "Unverified")
        self.assertEqual(finding["email_provenance"]["original_sha256"], item["sha256"])
        case_backups.validate_case(case)

    def test_invalid_import_shapes_and_size_limits(self):
        item = self.retain()
        case = app.load_case(self.case["id"])
        for field, value in [
            ("received", ["bad"]),
            ("urls", ["javascript:alert(1)"]),
            ("attachments", [{"filename": "x"}]),
        ]:
            bad = copy.deepcopy(case)
            bad["email_evidence"][0]["parsed"][field] = value
            with self.assertRaises(ValueError):
                case_backups.validate_case(bad)
        with patch.object(evidence, "MAX_FILE", 100):
            self.assertEqual(self.upload().status_code, 400)
        with patch.object(evidence, "MAX_EMAILS", 1):
            self.assertEqual(self.upload().status_code, 400)

    @skipUnless(
        evidence.runtime().is_file(), "Install isolated Mail-Parser for full import integration"
    )
    def test_real_import_renders_inert_content_and_validates_backup(self):
        from bs4 import BeautifulSoup

        response = self.upload()
        self.assertEqual(response.status_code, 302, response.data)
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200)
        soup = BeautifulSoup(page.data, "html.parser")
        self.assertFalse(soup.find_all("img"))
        self.assertFalse(soup.select('a[href="https://tracker.example/pixel"]'))
        self.assertIn(b"Inspect URL locally", page.data)
        self.assertIn(b"has not verified", page.data)
        case_backups.validate_case(app.load_case(self.case["id"]))


@skipUnless(
    evidence.runtime().is_file(), "Install isolated Mail-Parser for native integration checks"
)
class RealMailParserTests(TestCase):
    def parse(self, raw, expect=0):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "source.eml"
            path.write_bytes(raw)
            result = subprocess.run(
                [
                    str(evidence.runtime()),
                    str(Path(evidence.__file__).parent / "scripts/mail_evidence_worker.py"),
                    str(path),
                ],
                capture_output=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_real_mime_routing_claims_urls_and_attachment_hashes(self):
        result = self.parse(message())
        self.assertEqual(result["subject"], "Fictional invoice review")
        self.assertTrue(any(a["address"] == "support@vendor.example" for a in result["addresses"]))
        self.assertTrue(result["received"])
        self.assertIn("192.0.2.10", result["ips"])
        self.assertIn("https://tracker.example/pixel", result["urls"])
        self.assertIn("https://example.com/check", result["urls"])
        self.assertNotIn("<img", result["html_text"])
        self.assertNotIn("NO_EXECUTION", result["html_text"])
        attachment = result["attachments"][0]
        self.assertEqual(attachment["sha256"], hashlib.sha256(b"Fictional attachment.").hexdigest())
        self.assertTrue(any("Reply To differ" in w for w in result["warnings"]))
        self.assertIn("has not verified", result["trust_note"])

    def test_malformed_addresses_keep_recovery_and_diagnostics(self):
        result = self.parse(
            b"From: billing@trusted.example < billing@vendor.example >\r\nSubject: Recovery fixture\r\n\r\nBody"
        )
        self.assertTrue(any(a["address"] == "billing@vendor.example" for a in result["addresses"]))
        self.assertTrue(result["defects"]["has_defects"])
        self.assertTrue(result["defects"]["address_header_defects"])
        self.assertIn("billing@trusted.example", result["selected_headers"]["From"][0])

    def test_repeated_headers_and_obsolete_folded_input_retained(self):
        raw = b"From: Example (comment) <sender@example.com>\r\nSubject: Folded\r\n subject\r\nAuthentication-Results: server.example; spf=pass\r\nAuthentication-Results: other.example; spf=fail\r\n\r\nBody"
        result = self.parse(raw)
        self.assertEqual(len(result["selected_headers"]["Authentication-Results"]), 2)
        self.assertIn("Folded", result["subject"])
        self.assertTrue(any(a["address"] == "sender@example.com" for a in result["addresses"]))

    def test_mime_limits_and_non_email_inputs_fail_before_retention(self):
        for raw in (b"not an email", b"%PDF-1.7\nFrom: x@example.com\n\nbody"):
            self.assertIn("error", self.parse(raw, expect=1))
        mail = EmailMessage()
        mail["From"] = "a@example.com"
        mail.set_content("body")
        for n in range(201):
            mail.add_attachment(
                b"x", maintype="application", subtype="octet-stream", filename=str(n)
            )
        result = self.parse(mail.as_bytes(), expect=1)
        self.assertIn("200 MIME parts", result["error"])

    def test_ipv6_hops_are_extracted_as_claims(self):
        raw = b"From: sender@example.com\r\nReceived: from sender.example ([IPv6:2001:db8::10]) by inbox.example; Thu, 29 Oct 2026 12:00:01 -0500\r\nSubject: IPv6 fixture\r\n\r\nBody"
        result = self.parse(raw)
        self.assertIn("2001:db8::10", result["ips"])

    def test_undecodable_header_bytes_preserve_original_review(self):
        result = self.parse(
            b"From: sender@example.com\r\nSubject: Legacy bytes\r\nX-Note: \xff\r\n\r\nBody"
        )
        json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.assertTrue(any("Undecodable header bytes" in w for w in result["warnings"]))
