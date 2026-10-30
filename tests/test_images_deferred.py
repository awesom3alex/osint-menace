"""Regression checks for deferring image tools without deleting investigation data."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import workspace_store as store


class DeferredImageTests(unittest.TestCase):
    def test_image_routes_unavailable(self):
        client = app.app.test_client()
        key = "a" * 32
        for path in [
            "/images",
            "/images/" + key,
            "/images/" + key + "/files/original.png",
            "/image-reuse/" + key,
        ]:
            self.assertEqual(client.get(path).status_code, 404)
        self.assertEqual(client.post("/images").status_code, 404)
        self.assertEqual(client.post("/images/" + key + "/reuse").status_code, 404)

    def test_history_hides_but_preserves_images(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(store, "DB_PATH", Path(folder) / "history.sqlite3"),
        ):
            for key, kind, flag in [
                ("a" * 32, "image", "image_analysis"),
                ("b" * 32, "image reuse", "image_reuse"),
            ]:
                store.put(
                    key,
                    kind,
                    dict(id=key, target="Archived image", timestamp=store.now(), **{flag: True}),
                )
            store.put(
                "c" * 32,
                "console",
                dict(id="c" * 32, target="Visible search", timestamp=store.now()),
            )
            self.assertEqual([item["target"] for item in store.history()], ["Visible search"])
            for key in ["a" * 32, "b" * 32]:
                self.assertIsNotNone(store.get(key))
                self.assertEqual(app.app.test_client().get("/history/" + key).status_code, 404)

    def test_navigation_has_no_image_link(self):
        for template in [
            "index.html",
            "addons.html",
            "cases.html",
            "case.html",
            "help.html",
            "osint_links.html",
            "workspace_base.html",
        ]:
            self.assertNotIn('href="/images"', (Path("osint/templates") / template).read_text())
