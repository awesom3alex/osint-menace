import copy
import hashlib
import sys
import tempfile
import threading
import time
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import addon_tools as addons
import app
import case_features
import case_workflow as workflow
import workspace_features
import workspace_store as store


class InvestigationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, key, value in [
            (store, "DB_PATH", root / "history.sqlite3"),
            (app, "CASES_DIR", root / "cases"),
            (case_features, "EVIDENCE_DIR", root / "evidence"),
        ]:
            p = patch.object(obj, key, value)
            p.start()
            self.addCleanup(p.stop)
        self.client = app.app.test_client()
        self.case = app.create_case("Workflow validation")

    def add(
        self,
        source="Tool one",
        value="https://example.com/profile",
        query="sample",
        label="Profile",
    ):
        section = dict(
            name=source,
            module=dict(name=source),
            findings=[dict(label=label, value=value, source=source)],
            links=[],
            notes=[],
        )
        record = app.make_search_record("username", query, [section], app.result_summary([section]))
        app.append_search_to_case(self.case, record)
        return record

    def test_queued_cancel_never_starts_and_persists(self):
        job = dict(
            id="queued",
            tool="clank",
            target="test",
            timestamp=store.now(),
            status="queued",
            created=time.time(),
            output="",
        )
        with (
            patch.dict(addons.JOBS, {"queued": job}, clear=True),
            patch.object(addons.subprocess, "Popen") as spawn,
        ):
            self.assertEqual(self.client.post("/api/addons/jobs/queued/cancel").status_code, 200)
            addons.execute("queued", ["unused"])
            spawn.assert_not_called()
            self.assertEqual(store.get("queued")["status"], "cancelled")
            store.recover()
            self.assertEqual(store.get("queued")["status"], "cancelled")
        self.assertEqual(self.client.post("/api/addons/jobs/missing/cancel").status_code, 404)

    def test_running_cancel_stops_process_and_preserves_partial_output(self):
        job = dict(
            id="running",
            tool="clank",
            target="test",
            timestamp=store.now(),
            status="queued",
            created=time.time(),
            output="",
        )
        with patch.dict(addons.JOBS, {"running": job}, clear=True):
            thread = threading.Thread(
                target=addons.execute,
                args=(
                    "running",
                    [
                        sys.executable,
                        "-c",
                        "import time;print('partial result',flush=True);time.sleep(30)",
                    ],
                ),
            )
            thread.start()
            try:
                time.sleep(0.5)
                self.assertEqual(
                    self.client.post("/api/addons/jobs/running/cancel").status_code, 200
                )
                thread.join(4)
                self.assertFalse(thread.is_alive())
                saved = store.get("running")
                self.assertEqual(saved["status"], "cancelled")
                self.assertIn("partial result", saved["output"])
            finally:
                with addons.LOCK:
                    addons.JOBS["running"]["cancel_requested"] = True
                thread.join(5)

    def test_batch_progress_and_cancellation(self):
        with patch.object(addons.POOL, "submit"), patch.dict(addons.JOBS, {}, clear=True):
            response = self.client.post(
                "/api/unified",
                json=dict(target="+14155552671", kind="phone", tools=["clank", "phoneinfoga"]),
            )
            group = store.get(response.json["id"])
            first = group["job_ids"][0]
            addons.JOBS[first].update(
                status="completed", output="HTTP 429", rate_limited=True, finished_at=store.now()
            )
            store.put(first, "addon", addons.JOBS[first])
            item = workspace_features.record(group["id"])
            self.assertEqual(item["progress"]["finished"], 1)
            self.assertEqual(item["progress"]["counts"]["rate-limited"], 1)
            self.assertEqual(
                self.client.post("/api/history/" + group["id"] + "/cancel").status_code, 200
            )
            item = workspace_features.record(group["id"])
            self.assertFalse(item["active"])
            self.assertEqual(item["progress"]["counts"]["cancelled"], 1)
            page = self.client.get("/history/" + group["id"])
            self.assertEqual(page.status_code, 200)
            self.assertIn(b"2 of 2 tools finished", page.data)

    def test_merge_preserves_originals_all_sources_and_undo(self):
        one = self.add()
        two = self.add("Tool two", label="Different profile label")
        case = app.load_case(self.case["id"])
        original = copy.deepcopy(case["searches"])
        groups = workflow.duplicate_groups(case)
        self.assertEqual(len(groups), 1)
        endpoint = f"/cases/{case['id']}/duplicates/merge"
        response = self.client.post(endpoint, data={"key": groups[0]["key"]})
        self.assertEqual(response.status_code, 200)
        merged = app.load_case(case["id"])
        self.assertEqual(merged["searches"], original)
        view = workflow.report_case(merged)
        shown = [f for _, _, _, f in workflow.findings(view) if f.get("include_in_report", True)]
        self.assertEqual(len(shown), 1)
        self.assertEqual(
            [s["source"] for s in shown[0]["merged_sources"]], ["Tool one", "Tool two"]
        )
        self.assertIn("Tool two", app.render_markdown_report(merged))
        self.assertEqual(
            self.client.post(endpoint, data={"key": groups[0]["key"]}).status_code, 409
        )
        group_id = merged["merge_groups"][0]["id"]
        self.assertEqual(
            self.client.post(f"/cases/{case['id']}/duplicates/{group_id}/undo").status_code, 200
        )
        restored = app.load_case(case["id"])
        self.assertEqual(restored["searches"], original)
        self.assertEqual(len(workflow.duplicate_groups(restored)), 1)

    def test_no_merges_across_targets_or_different_fact_labels(self):
        self.add(value=True, label="Valid")
        self.add(value=True, label="Available")
        self.add(query="other")
        self.add(query="another")
        self.assertEqual(workflow.duplicate_groups(app.load_case(self.case["id"])), [])

    def test_provenance_hash_verification_manifest_and_timeline(self):
        search = self.add()
        case_id = self.case["id"]
        buffer = BytesIO()
        Image.new("RGB", (80, 60), "white").save(buffer, "PNG")
        data = buffer.getvalue()
        upload = f"/cases/{case_id}/evidence/{search['id']}/0/0"
        response = self.client.post(
            upload,
            data={
                "screenshot": (BytesIO(data), "sample.png"),
                "source_url": "https://example.com/source",
                "captured_at": "2026-10-16T14:30",
                "caption": "Test evidence",
            },
        )
        self.assertEqual(response.status_code, 200, response.data)
        item = response.json["evidence"]
        self.assertEqual(item["original_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(item["captured_at"], "2026-10-16T14:30:00+00:00")
        verify = f"/cases/{case_id}/evidence/{item['id']}/verify"
        self.assertTrue(self.client.post(verify).json["valid"])
        self.client.post(f"/cases/{case_id}/notes", data={"notes": "Updated context"})
        self.client.post(
            f"/cases/{case_id}/review/{search['id']}/0/0",
            data={"status": "Confirmed", "include_in_report": "on"},
        )
        case = app.load_case(case_id)
        kinds = {e["kind"] for e in workflow.timeline(case)}
        self.assertTrue(
            {
                "case_created",
                "search_saved",
                "finding_reviewed",
                "notes_updated",
                "evidence_attached",
            }
            <= kinds
        )
        manifest = self.client.get(f"/cases/{case_id}/provenance.json").json
        self.assertEqual(manifest["findings"][0]["evidence"][0]["sha256"], item["sha256"])
        html = self.client.get(f"/cases/{case_id}/report.html")
        self.assertIn(item["sha256"].encode(), html.data)
        self.assertIn(item["sha256"], app.render_markdown_report(case))
        self.assertEqual(self.client.get(f"/cases/{case_id}/report.pdf").status_code, 200)
        (case_features.EVIDENCE_DIR / case_id / (item["id"] + ".png")).write_bytes(b"changed")
        self.assertEqual(self.client.post(verify).status_code, 409)

    def test_provenance_rejects_unsafe_url_and_legacy_hash_not_fabricated(self):
        search = self.add()
        case_id = self.case["id"]
        response = self.client.post(
            f"/cases/{case_id}/evidence/{search['id']}/0/0",
            data={
                "screenshot": (BytesIO(b"anything"), "sample.png"),
                "source_url": "javascript:alert(1)",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not recorded", workflow.evidence_text({"created_at": "earlier"}))
        self.assertEqual(self.client.get(f"/cases/{case_id}").status_code, 200)

    def test_merge_combines_attachments_and_retains_original_review(self):
        first = self.add()
        second = self.add("Tool two")
        case_id = self.case["id"]
        for index, search in enumerate([first, second]):
            buffer = BytesIO()
            Image.new("RGB", (20, 20), "white" if index else "black").save(buffer, "PNG")
            buffer.seek(0)
            response = self.client.post(
                f"/cases/{case_id}/evidence/{search['id']}/0/0",
                data={"screenshot": (buffer, "sample.png")},
            )
            self.assertEqual(response.status_code, 200)
        self.client.post(
            f"/cases/{case_id}/review/{second['id']}/0/0",
            data={
                "status": "False positive",
                "analyst_notes": "Conflicting source assessment",
                "include_in_report": "on",
            },
        )
        case = app.load_case(case_id)
        candidate = workflow.duplicate_groups(case)[0]
        self.client.post(f"/cases/{case_id}/duplicates/merge", data={"key": candidate["key"]})
        merged = app.load_case(case_id)
        view = workflow.report_case(merged)
        primary = list(workflow.findings(view))[0][3]
        self.assertEqual(len(primary["evidence"]), 2)
        self.assertEqual(primary["merged_sources"][1]["verification_status"], "False positive")
        self.assertEqual(
            primary["merged_sources"][1]["analyst_notes"], "Conflicting source assessment"
        )
        original = list(workflow.findings(merged))
        self.assertEqual([len(f["evidence"]) for _, _, _, f in original], [1, 1])
        self.assertEqual(original[1][3]["verification_status"], "False positive")
