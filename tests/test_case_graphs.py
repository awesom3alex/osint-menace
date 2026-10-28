"""Graph persistence, conflict handling, and backup trust boundary tests."""

import base64
import copy
import re
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app
import case_backups
from demo import DEMO_ID


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for obj, key, value in [
            (app, "CASES_DIR", root / "cases"),
            (case_backups, "STAGING", root / "staging"),
        ]:
            patcher = patch.object(obj, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = app.app.test_client()
        self.case = app.create_case("Graph fixture", "")
        self.base = f"/cases/{self.case['id']}/graphs"
        response = self.client.post(self.base, data={"name": "People"})
        self.assertEqual(response.status_code, 302)
        self.graph = app.load_case(self.case["id"])["graphs"][0]

    def put(self, graph):
        return self.client.put(self.base + "/" + self.graph["id"], json=graph)

    def populated(self):
        graph = copy.deepcopy(self.graph)
        photo = BytesIO()
        Image.new("RGB", (10, 10), "red").save(photo, "PNG")
        graph["nodes"] = [
            dict(
                id="person",
                type="Person",
                label="Alice",
                position={"x": 123, "y": -57},
                pinned=True,
                source="",
                photo="data:image/png;base64," + base64.b64encode(photo.getvalue()).decode(),
                fields=[
                    dict(
                        name="Custom date",
                        type="date",
                        value="2026-10-27",
                        options="",
                        visible=True,
                    )
                ],
            )
        ]
        graph["nodes"].append(dict(graph["nodes"][0], id="second", label="Bob", photo=""))
        graph["edges"] = [
            dict(
                id="relationship",
                source="person",
                target="second",
                label="Associated with",
                status="hypothesis",
                notes="Unverified",
            )
        ]
        graph["legend"][0]["description"] = "People in this investigation"
        return graph

    def test_save_custom_fields_photo_positions_and_reject_stale_tab(self):
        graph = self.populated()
        response = self.put(graph)
        self.assertEqual(response.status_code, 200, response.data)
        saved = app.load_case(self.case["id"])["graphs"][0]
        graph["revision"] = response.json["revision"]
        self.assertEqual(saved, graph)
        self.assertEqual(self.put(self.graph).status_code, 409)
        self.assertEqual(app.load_case(self.case["id"])["graphs"][0], saved)
        self.assertEqual(self.client.get(self.base).status_code, 200)

    def test_invalid_graphs_leave_saved_data_unchanged(self):
        original = app.case_path(self.case["id"]).read_bytes()
        for mutate in [
            lambda g: g["edges"][0].update(target="missing"),
            lambda g: g["nodes"][0].update(photo="https://example.com/tracker.png"),
            lambda g: g["nodes"][0].update(photo="data:image/png;base64,not-an-image"),
            lambda g: g["nodes"][0].update(type=[]),
            lambda g: g["nodes"][0]["fields"][0].update(value="not-a-date"),
            lambda g: g["nodes"][0]["fields"].append(dict(g["nodes"][0]["fields"][0])),
            lambda g: g["legend"][0].update(color="url(javascript:alert(1))"),
            lambda g: g["nodes"][0]["position"].update(x=float("inf")),
        ]:
            graph = self.populated()
            mutate(graph)
            with self.subTest(graph=graph):
                self.assertEqual(self.put(graph).status_code, 400)
                self.assertEqual(app.case_path(self.case["id"]).read_bytes(), original)

    def test_finding_add_preserves_source_and_deduplicates(self):
        section = dict(
            name="Fixture",
            findings=[dict(label="Account", value="alice", source="Fixture")],
            links=[],
            notes=[],
        )
        search = app.make_search_record(
            "username", "alice", [section], app.result_summary([section])
        )
        app.append_search_to_case(self.case, search)
        url = self.base + f"/add/{search['id']}/0/0"
        for _ in range(2):
            self.assertEqual(
                self.client.post(url, data={"graph_id": self.graph["id"]}).status_code, 302
            )
        graph = app.load_case(self.case["id"])["graphs"][0]
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(graph["nodes"][0]["source"], f"{search['id']}:0:0")
        self.assertIn(b"Add to graph", self.client.get(f"/cases/{self.case['id']}").data)

    def test_backup_restore_retains_graph_and_embedded_photo(self):
        graph = self.populated()
        gid = "group_" + "c" * 32
        graph.update(groups=[dict(id=gid, label="People", collapsed=True)], collapsed=["person"])
        graph["nodes"][0].update(group=gid, tags=["review"], annotation=True)
        graph["edges"][0].update(date="2026-10-27", evidenceRefs=["d" * 32 + ":0:0"])
        self.assertEqual(self.put(graph).status_code, 200)
        archive = self.client.get(f"/cases/{self.case['id']}/backup.zip")
        self.assertEqual(archive.status_code, 200, archive.data)
        preview = self.client.post(
            "/cases/import/preview", data={"backup": (BytesIO(archive.data), "graph.zip")}
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        receipt = {
            key: re.search(r'name="' + key + r'" value="([a-f0-9]+)"', preview.text).group(1)
            for key in ("token", "sha256")
        }
        restored = self.client.post(
            "/cases/import/restore", data=dict(receipt, case_name="Restored graph")
        )
        self.assertEqual(restored.status_code, 302, restored.data)
        case_id = restored.headers["Location"].split("/")[-1]
        self.assertEqual(app.load_case(case_id)["graphs"], app.load_case(self.case["id"])["graphs"])

    def test_backup_validator_rejects_malformed_graph(self):
        case = app.load_case(self.case["id"])
        case["graphs"][0]["nodes"] = [dict(id="bad")]
        with self.assertRaises(ValueError):
            case_backups.validate_case(case)

    def test_demo_and_missing_cases(self):
        self.assertEqual(self.client.post(f"/cases/{DEMO_ID}/graphs").status_code, 403)
        self.assertEqual(
            self.client.put(
                f"/cases/{DEMO_ID}/graphs/{self.graph['id']}", json=self.graph
            ).status_code,
            403,
        )
        self.assertEqual(self.client.post(self.base + "/add/missing/0/0").status_code, 404)

    def test_groups_annotations_relationship_evidence_roundtrip(self):
        graph = self.populated()
        gid = "group_" + "a" * 32
        ref = "b" * 32 + ":0:0"
        graph.update(groups=[dict(id=gid, label="Accounts", collapsed=True)], collapsed=["person"])
        graph["nodes"][0].update(group=gid, tags=["priority"], sourceRefs=[ref], annotation=True)
        graph["edges"][0].update(evidenceRefs=[ref], date="2026-10-27")
        response = self.put(graph)
        self.assertEqual(response.status_code, 200, response.data)
        saved = app.load_case(self.case["id"])
        case_backups.validate_case(saved)
        self.assertEqual(saved["graphs"][0]["groups"], graph["groups"])
        self.assertEqual(saved["graphs"][0]["edges"], graph["edges"])
        self.assertEqual(saved["graphs"][0]["nodes"], graph["nodes"])

    def test_reject_invalid_groups_references_tags_and_dates(self):
        for modify in [
            lambda g: g.update(groups=[dict(id="person", label="Invalid")]),
            lambda g: g.update(collapsed=["missing"]),
            lambda g: g["nodes"][0].update(group="missing"),
            lambda g: g["nodes"][0].update(tags="not a list"),
            lambda g: g["edges"][0].update(evidenceRefs=["../../other-case"]),
            lambda g: g["edges"][0].update(date="2026-99-99"),
        ]:
            graph = self.populated()
            modify(graph)
            self.assertEqual(self.put(graph).status_code, 400)

    def test_evidence_preview_is_case_scoped_and_handles_missing_findings(self):
        section = dict(
            name="Fixture",
            findings=[
                dict(
                    label="Source account",
                    value={"username": "demo"},
                    source="Fixture",
                    analyst_notes="Review this",
                )
            ],
            links=[],
            notes=[],
        )
        search = app.make_search_record(
            "username", "demo", [section], app.result_summary([section])
        )
        app.append_search_to_case(self.case, search)
        ref = f"{search['id']}:0:0"
        response = self.client.get(self.base + "/evidence", query_string={"ref": ref})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["value"], {"username": "demo"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        other = app.create_case("Other case", "")
        self.assertEqual(
            self.client.get(
                f"/cases/{other['id']}/graphs/evidence", query_string={"ref": ref}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(self.base + "/evidence", query_string={"ref": "bad"}).status_code, 400
        )
        self.assertEqual(
            self.client.get(
                self.base + "/evidence", query_string={"ref": f"{search['id']}:999:0"}
            ).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
