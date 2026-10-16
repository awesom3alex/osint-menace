import contextlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import app
import cli_catalog
import cli_workspace
import collectors
import discovery
import menace


class ParityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = app.CASES_DIR
        app.CASES_DIR = Path(self.temp.name) / "cases"
        self.case = app.create_case("Parity case")

    def tearDown(self):
        app.CASES_DIR = self.old
        self.temp.cleanup()

    def test_full_username_links_available_by_default(self):
        with patch.object(discovery, "collect", return_value=[]):
            results = discovery.run_search("username", "example")
        names = {link["label"] for section in results for link in section["links"]}
        self.assertTrue(set(app.osint_tool.PROFILE_PATTERNS).issubset(names))
        self.assertIn("Reddit", names)
        self.assertIn("YouTube", names)

    def test_specific_profile_links_and_custom_forum(self):
        results = discovery.run_search("username", "example", "https://example.com/u/{username}", mode="links",
                                       options=collectors.Options(profile_sites=("reddit", "youtube")))
        names = {link["label"] for section in results for link in section["links"] if link["category"] == "candidate_profile"}
        self.assertEqual(names, {"Reddit", "YouTube", "Configured forum pattern"})

    def test_new_direct_sources_and_null_activity(self):
        with patch.object(collectors, "get_json", return_value={"status": "found", "data": [{"username": "example", "id": 1}]}):
            result = collectors.collect("username", "example", collectors.Options(platforms=("gitlab",)))[0]
        self.assertEqual(result["findings"][0]["value"]["status"], "found")
        with patch.object(collectors, "get_json", return_value={"status": "found", "data": None}):
            result = collectors.collect("username", "example", collectors.Options(platforms=("hacker-news",)))[0]
        self.assertEqual(result["findings"][0]["value"]["status"], "no_matches")

    def test_catalog_direct_command_and_selected_save(self):
        output = StringIO()
        args = ["--data-dir", self.temp.name, "links", "--category", "Username", "--json"]
        with contextlib.redirect_stdout(output):
            self.assertEqual(menace.main(args), 0)
        data = json.loads(output.getvalue())
        self.assertTrue(data["links"])
        self.assertIn("start.me", data["source_url"])
        with contextlib.redirect_stdout(StringIO()), contextlib.redirect_stderr(StringIO()):
            self.assertEqual(menace.main(args + ["--case", self.case["id"], "--select", "1"]), 0)
        self.assertEqual(len(app.load_case(self.case["id"])["searches"]), 1)

    def test_standalone_html_export(self):
        path = Path(self.temp.name) / "report.html"
        with contextlib.redirect_stdout(StringIO()):
            menace.export_case(app.load_case(self.case["id"]), "html", str(path))
        text = path.read_text()
        self.assertIn("<style>", text)
        self.assertNotIn("<script", text)
        self.assertNotIn("/static/", text)
        self.assertIn("Parity case", text)

    def test_catalog_menu_saves_without_browser(self):
        terminal = cli_workspace.Terminal(self.temp.name)
        terminal.active = self.case["id"]
        with patch("builtins.input", side_effect=["1", "", "3", "1", "0"]), contextlib.redirect_stdout(StringIO()):
            terminal.browse_catalog()
        self.assertEqual(len(app.load_case(self.case["id"])["searches"]), 1)

    def test_profile_coverage_menu(self):
        terminal = cli_workspace.Terminal(self.temp.name)
        config = vars(collectors.Options()).copy()
        settings = {"mode": "links", "pattern": "", "scan": False, "ports": "80"}
        # Links-only options are output, profile platforms, custom forum.
        with patch("builtins.input", side_effect=["2", "1,2", "0"]), contextlib.redirect_stdout(StringIO()):
            terminal.advanced_options("username", config, settings)
        self.assertEqual(len(config["profile_sites"]), 2)
        self.assertEqual(len(cli_catalog.platform_rows()), len(app.osint_tool.PROFILE_PATTERNS))


if __name__ == "__main__":
    unittest.main()
