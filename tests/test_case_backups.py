import hashlib
import json
import os
import re
import stat
import tempfile
import time
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app
import case_backups as backups
import case_features
import case_workflow
import workspace_store


class CaseBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, key, value in [
            (app, "CASES_DIR", root / "cases"),
            (case_features, "EVIDENCE_DIR", root / "evidence"),
            (backups, "STAGING", root / "staging"),
            (workspace_store, "DB_PATH", root / "history.sqlite3"),
        ]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.client = app.app.test_client()
        self.case = app.create_case("Backup fixture", "Retain these notes")
        for source in ["First tool", "Second tool"]:
            section = dict(
                name="Fixture",
                module=dict(name=source, mode="local"),
                findings=[
                    dict(label="Profile", value="https://example.com/profile", source=source)
                ],
                links=[dict(label="Source", value="https://example.com/profile")],
                notes=["Fixture"],
            )
            search = app.make_search_record(
                "username", "sample", [section], app.result_summary([section])
            )
            app.append_search_to_case(self.case, search)
        self.search = self.case["searches"][0]
        buffer = BytesIO()
        Image.new("RGB", (40, 30), "white").save(buffer, "PNG")
        buffer.seek(0)
        response = self.client.post(
            f"/cases/{self.case['id']}/evidence/{self.search['id']}/0/0",
            data={
                "screenshot": (buffer, "sample.png"),
                "source_url": "https://example.com/profile",
            },
        )
        self.evidence = response.json["evidence"]
        groups = case_workflow.duplicate_groups(app.load_case(self.case["id"]))
        self.client.post(
            f"/cases/{self.case['id']}/duplicates/merge", data={"key": groups[0]["key"]}
        )

    def download(self):
        response = self.client.get(f"/cases/{self.case['id']}/backup.zip")
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        response.close()
        return data

    def preview(self, data):
        return self.client.post(
            "/cases/import/preview", data={"backup": (BytesIO(data), "case.zip")}
        )

    def receipt(self, response):
        text = response.get_data(as_text=True)
        return {
            key: re.search(r'name="' + key + r'" value="([a-f0-9]+)"', text).group(1)
            for key in ["token", "sha256"]
        }

    def rewrite(self, data, change, rehash=True):
        with zipfile.ZipFile(BytesIO(data)) as archive:
            files = {name: archive.read(name) for name in archive.namelist()}
        change(files)
        if rehash:
            manifest = json.loads(files["manifest.json"])
            manifest["files"] = {
                name: dict(size=len(body), sha256=hashlib.sha256(body).hexdigest())
                for name, body in files.items()
                if name != "manifest.json"
            }
            files["manifest.json"] = json.dumps(manifest).encode()
        out = BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, body in files.items():
                archive.writestr(name, body)
        return out.getvalue()

    def test_roundtrip_preserves_everything_without_overwrite(self):
        before = app.case_path(self.case["id"]).read_bytes()
        archive = self.download()
        preview = self.preview(archive)
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertIn(b"Verified backup preview", preview.data)
        receipt = self.receipt(preview)
        result = self.client.post(
            "/cases/import/restore", data=dict(receipt, case_name="Restored fixture")
        )
        self.assertEqual(result.status_code, 302, result.data)
        new_id = result.headers["Location"].split("/")[-1]
        self.assertNotEqual(new_id, self.case["id"])
        restored = app.load_case(new_id)
        original = app.load_case(self.case["id"])
        for key in ["searches", "merge_groups", "notes", "created_at"]:
            self.assertEqual(restored[key], original[key])
        self.assertEqual(app.case_path(self.case["id"]).read_bytes(), before)
        path = case_features.EVIDENCE_DIR / new_id / (self.evidence["id"] + ".png")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), self.evidence["sha256"])
        self.assertEqual(restored["events"][-1]["kind"], "case_restored")
        self.assertEqual(self.client.get(result.headers["Location"]).status_code, 200)
        self.assertEqual(
            self.client.post(
                "/cases/import/restore", data=dict(receipt, case_name="Duplicate attempt")
            ).status_code,
            400,
        )
        with zipfile.ZipFile(BytesIO(archive)) as zipped:
            self.assertIn("report.md", zipped.namelist())

    def test_rejects_changed_archive_or_recorded_evidence(self):
        data = self.download()
        damaged = self.rewrite(
            data, lambda files: files.update({"report.md": b"changed"}), rehash=False
        )
        self.assertEqual(self.preview(damaged).status_code, 400)

        def change_evidence(files):
            buffer = BytesIO()
            Image.new("RGB", (40, 30), "black").save(buffer, "PNG")
            files["evidence/" + self.evidence["id"] + ".png"] = buffer.getvalue()

        self.assertEqual(self.preview(self.rewrite(data, change_evidence)).status_code, 400)
        self.assertEqual(list(backups.STAGING.glob("*.zip")), [])

    def test_rejects_traversal_extra_members_duplicate_names_and_symlinks(self):
        data = self.download()
        for name in [
            "../outside.txt",
            "/absolute.txt",
            "evidence/../../case.json",
            "unexpected.txt",
        ]:
            with self.subTest(name=name):
                self.assertEqual(
                    self.preview(
                        self.rewrite(data, lambda files: files.update({name: b"bad"}))
                    ).status_code,
                    400,
                )
        out = BytesIO()
        with zipfile.ZipFile(BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dest:
            for info in src.infolist():
                if info.filename == "report.md":
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                dest.writestr(info, src.read(info.filename))
        self.assertEqual(self.preview(out.getvalue()).status_code, 400)
        with zipfile.ZipFile(out := BytesIO(data), "a") as dest:
            dest.writestr("case.json", b"{}")
        self.assertEqual(self.preview(out.getvalue()).status_code, 400)

    def test_missing_evidence_and_unreferenced_evidence_rejected(self):
        data = self.download()
        name = "evidence/" + self.evidence["id"] + ".png"
        self.assertEqual(
            self.preview(self.rewrite(data, lambda files: files.pop(name))).status_code, 400
        )
        self.assertEqual(
            self.preview(
                self.rewrite(
                    data, lambda files: files.update({"evidence/" + "f" * 32 + ".png": files[name]})
                )
            ).status_code,
            400,
        )
        (case_features.EVIDENCE_DIR / self.case["id"] / (self.evidence["id"] + ".png")).unlink()
        response = self.client.get(f"/cases/{self.case['id']}/backup.zip")
        self.assertEqual(response.status_code, 409)

    def test_legacy_evidence_is_labelled_not_retroactively_hashed(self):
        case = app.load_case(self.case["id"])
        case["searches"][0]["results"][0]["findings"][0]["evidence"][0].pop("sha256")
        app.save_case(case)
        response = self.preview(self.download())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"legacy attachments", response.data)
        self.assertNotIn(
            "sha256",
            app.load_case(self.case["id"])["searches"][0]["results"][0]["findings"][0]["evidence"][
                0
            ],
        )

    def test_expired_changed_preview_and_restore_failure_leave_no_partial_case(self):
        response = self.preview(self.download())
        receipt = self.receipt(response)
        path = backups.STAGING / (receipt["token"] + ".zip")
        original_cases = set(app.CASES_DIR.glob("*.json"))
        original_evidence = set(case_features.EVIDENCE_DIR.iterdir())
        with patch.object(app, "save_case", side_effect=OSError("Simulated disk write failure")):
            result = self.client.post(
                "/cases/import/restore", data=dict(receipt, case_name="Failed restore")
            )
            self.assertEqual(result.status_code, 400)
        self.assertEqual(set(app.CASES_DIR.glob("*.json")), original_cases)
        self.assertEqual(set(case_features.EVIDENCE_DIR.iterdir()), original_evidence)
        path.write_bytes(b"changed")
        self.assertEqual(
            self.client.post(
                "/cases/import/restore", data=dict(receipt, case_name="Changed restore")
            ).status_code,
            400,
        )
        os.utime(path, (time.time() - backups.TTL - 1,) * 2)
        self.assertEqual(
            self.client.post(
                "/cases/import/restore", data=dict(receipt, case_name="Expired restore")
            ).status_code,
            400,
        )

    def test_schema_bad_urls_versions_limits_and_invalid_zip(self):
        data = self.download()

        def bad_url(files):
            case = json.loads(files["case.json"])
            case["searches"][0]["results"][0]["links"][0]["value"] = "javascript:alert(1)"
            files["case.json"] = json.dumps(case).encode()

        self.assertEqual(self.preview(self.rewrite(data, bad_url)).status_code, 400)

        def bad_type(files):
            case = json.loads(files["case.json"])
            case["searches"][0]["results"][0]["findings"] = "invalid"
            files["case.json"] = json.dumps(case).encode()

        self.assertEqual(self.preview(self.rewrite(data, bad_type)).status_code, 400)

        def bad_version(files):
            manifest = json.loads(files["manifest.json"])
            manifest["version"] = 99
            files["manifest.json"] = json.dumps(manifest).encode()

        self.assertEqual(
            self.preview(self.rewrite(data, bad_version, rehash=False)).status_code, 400
        )
        self.assertEqual(self.preview(b"not a zip").status_code, 400)
        with patch.object(backups, "MAX_TOTAL", 10):
            self.assertEqual(self.preview(data).status_code, 400)
        self.assertEqual(self.client.get("/cases/import").status_code, 200)
        self.assertIn(b"Restore a case backup", self.client.get("/cases").data)

    def test_legacy_null_source_is_preserved(self):
        case = app.load_case(self.case["id"])
        case["searches"][0]["results"][0]["findings"][0]["source"] = None
        app.save_case(case)
        response = self.preview(self.download())
        self.assertEqual(response.status_code, 200, response.data)
