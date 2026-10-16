import contextlib
import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import app
import cli_workspace as workspace
import menace


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_dir = app.CASES_DIR
        app.CASES_DIR = Path(self.temp.name) / "cases"
        self.case = app.create_case("Training")
        self.results = [{"name": "Username: training", "findings": [
            {"label": "Handle", "value": "training", "source": "Input"}],
            "links": [{"label": "Profile", "value": "https://example.com/profile"}], "notes": []}]

    def tearDown(self):
        app.CASES_DIR = self.old_dir
        self.temp.cleanup()

    def test_selection_duplicates_and_review_exports(self):
        self.assertEqual(workspace.select_numbers("1,2-2", 2), [0, 1])
        with self.assertRaises(ValueError):
            workspace.select_numbers("0", 2)
        self.assertEqual(workspace.save_selected(self.case["id"], self.results, [1], "training", "username"), (1, 0))
        self.assertEqual(workspace.save_selected(self.case["id"], self.results, [1], "training", "username"), (0, 1))
        case = app.load_case(self.case["id"])
        item = case["searches"][0]
        self.assertEqual(item["results"][0]["findings"], [])
        workspace.review_item(case["id"], item["id"], "verified", "Corroborated source", ["demo", "demo"])
        case = app.load_case(case["id"])
        self.assertEqual(case["searches"][0]["tags"], ["demo"])
        self.assertEqual(len(workspace.report_case(case, ["relevant"])["searches"]), 0)
        report = workspace.report_case(case, ["verified"])
        self.assertEqual(report["summary"]["links"], 1)
        self.assertIn("Corroborated source", app.render_markdown_report(report))
        self.assertEqual(len(app.load_case(case["id"])["searches"]), 1)

    def test_batch_cancel_preserves_completed_results(self):
        with patch.object(workspace.discovery, "run_search", side_effect=[self.results, KeyboardInterrupt]), contextlib.redirect_stderr(StringIO()):
            results, errors, cancelled = workspace.run_targets(["one", "two"])
        self.assertTrue(cancelled)
        self.assertEqual(results, self.results)
        self.assertEqual(errors, [])

    def test_input_csv_and_stdin(self):
        path = Path(self.temp.name) / "targets.csv"
        path.write_text("target,notes\nexample.com,a\nexample.com,b\nexample.org,c\n")
        self.assertEqual(workspace.read_targets(str(path)), ["example.com", "example.org"])
        with patch("sys.stdin", StringIO("one\ntwo\n")):
            self.assertEqual(workspace.read_targets("-"), ["one", "two"])

    def test_terminal_selection_survives_restart(self):
        terminal = workspace.Terminal(self.temp.name)
        with patch("builtins.input", side_effect=["1"]), contextlib.redirect_stdout(StringIO()):
            terminal.pick_case()
        self.assertEqual(workspace.Terminal(self.temp.name).active, self.case["id"])
        with patch("builtins.input", side_effect=["0"]), contextlib.redirect_stdout(StringIO()):
            self.assertEqual(terminal.run(), 0)

    def test_cli_review_and_confirmed_deletion(self):
        workspace.save_selected(self.case["id"], self.results, [1], "training", "username")
        item = app.load_case(self.case["id"])["searches"][0]
        prefix = ["--data-dir", self.temp.name]
        with contextlib.redirect_stdout(StringIO()), contextlib.redirect_stderr(StringIO()):
            self.assertEqual(menace.main(prefix + ["review", self.case["id"], item["id"], "--status", "relevant"]), 0)
            self.assertEqual(menace.main(prefix + ["remove", self.case["id"], item["id"]]), 1)
            self.assertEqual(menace.main(prefix + ["remove", self.case["id"], item["id"], "--yes"]), 0)
        self.assertEqual(app.load_case(self.case["id"])["searches"], [])

    def test_interactive_selection_and_report_wizard(self):
        terminal = workspace.Terminal(self.temp.name)
        terminal.active = self.case["id"]
        terminal.results = self.results
        terminal.query = "training"
        with patch("builtins.input", side_effect=["2", "2", "0"]), contextlib.redirect_stdout(StringIO()):
            terminal.review_results()
        saved = app.load_case(self.case["id"])
        self.assertEqual(len(saved["searches"]), 1)
        self.assertEqual(len(saved["searches"][0]["results"][0]["links"]), 1)
        path = Path(self.temp.name) / "wizard.json"
        with patch("builtins.input", side_effect=["1", "3", str(path)]), contextlib.redirect_stdout(StringIO()):
            terminal.report()
        self.assertEqual(len(json.loads(path.read_text())["searches"]), 1)

    def test_batch_json_stdout_and_error_exit(self):
        path = Path(self.temp.name) / "input.txt"
        path.write_text("one\ntwo\n")
        output = StringIO()
        with patch.object(workspace.discovery, "run_search", side_effect=[self.results, ValueError("Unavailable")]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(StringIO()):
            code = menace.main(["--data-dir", self.temp.name, "batch", str(path), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["errors"][0]["target"], "two")


if __name__ == "__main__":
    unittest.main()
