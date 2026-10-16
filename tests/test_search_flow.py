import contextlib
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import app
import cli_workspace as workspace


class SearchFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = app.CASES_DIR
        app.CASES_DIR = Path(self.temp.name) / "cases"
        self.terminal = workspace.Terminal(self.temp.name)
        self.results = [{"name": "Test result", "findings": [], "links": [], "notes": []}]

    def tearDown(self):
        app.CASES_DIR = self.original
        self.temp.cleanup()

    def search(self, answers, batch=False):
        output = StringIO()
        with patch("builtins.input", side_effect=answers) as inputs, patch.object(workspace, "run_targets", return_value=(self.results, [], False)) as run, patch.object(self.terminal, "review_results"), contextlib.redirect_stdout(output):
            self.terminal.search(batch=batch)
        return run, output.getvalue(), inputs

    def test_phone_type_then_target_then_country(self):
        run, text, inputs = self.search(["3", "+12025550147", "", "1"])
        self.assertIn("Default country", inputs.call_args_list[2].args[0])
        self.assertEqual(run.call_args.args[0], ["+12025550147"])
        self.assertEqual(run.call_args.args[1], "phone")
        self.assertEqual(run.call_args.args[-1].region, "US")
        self.assertIn("Search review", text)
        self.assertNotIn("Forum URL", text)

    def test_username_sources(self):
        run, text, _ = self.search(["1", "octocat", "github", "1"])
        self.assertEqual(run.call_args.args[-1].platforms, ("github",))
        self.assertIn("Username sources: github", text)

    def test_back_preserves_previous_search(self):
        self.terminal.results, self.terminal.query, self.terminal.kind = ["old"], "old query", "phone"
        run, _, _ = self.search(["1", "octocat", "", "0", "", "0"])
        run.assert_not_called()
        self.assertEqual(self.terminal.results, ["old"])
        self.assertEqual(self.terminal.query, "old query")
        self.assertEqual(self.terminal.kind, "phone")

    def test_advanced_timeout_and_invalid_input_stays_in_menu(self):
        run, text, _ = self.search(["3", "+12025550147", "", "4", "2", "bad", "2", "5", "0", "1"])
        self.assertIn("Settings error", text)
        self.assertEqual(run.call_args.args[-1].timeout, 5)

    def test_explicit_url_keeps_commas(self):
        url = "https://example.com/?values=a,b"
        run, _, _ = self.search(["8", url, "1"])
        self.assertEqual(run.call_args.args[0], [url])

    def test_authorized_scan_is_opt_in_and_not_persisted(self):
        run, _, _ = self.search(["6", "192.0.2.1", "4", "3", "y", "4", "22,443", "0", "1"])
        self.assertTrue(run.call_args.args[3])
        self.assertEqual(run.call_args.args[4], "22,443")
        self.assertNotIn("scan", self.terminal.state)

    def test_batch_selects_type_before_file(self):
        path = Path(self.temp.name) / "targets.txt"
        path.write_text("one\ntwo\n")
        run, _, inputs = self.search(["1", str(path), "", "1"], batch=True)
        self.assertIn("Text/CSV input path", inputs.call_args_list[1].args[0])
        self.assertEqual(run.call_args.args[0], ["one", "two"])

    def test_records_advanced_source(self):
        run, text, _ = self.search(["9", "Example company", "4", "3", "sec", "0", "1"])
        self.assertEqual(run.call_args.args[-1].records_sources, ("sec",))
        self.assertIn("Record sources: sec", text)


if __name__ == "__main__":
    unittest.main()
