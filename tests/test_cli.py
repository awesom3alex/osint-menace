import contextlib
from io import StringIO
from pathlib import Path
import tempfile
import unittest

import app
import menace


class CLITests(unittest.TestCase):
    def test_case_search_dossier_and_word(self):
        original = app.CASES_DIR
        try:
            with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(StringIO()):
                prefix = ["--data-dir", folder]
                self.assertEqual(menace.main(prefix + ["create", "CLI example"]), 0)
                case_id = app.list_cases()[0]["id"]
                self.assertEqual(menace.main(prefix + ["search", "exampleuser", "--type", "username", "--mode", "links",
                                                       "--case", case_id, "--link", "1"]), 0)
                saved = app.load_case(case_id)
                self.assertEqual(len(saved["searches"][0]["results"][0]["links"]), 1)
                self.assertEqual(menace.main(prefix + ["dossier", case_id, "--field", "summary", "--value", "CLI summary"]), 0)
                self.assertEqual(app.load_case(case_id)["dossier"]["summary"], "CLI summary")
                output = str(Path(folder) / "reports" / "report.docx")
                self.assertEqual(menace.main(prefix + ["export", case_id, "--output", output]), 0)
                self.assertTrue(Path(output).read_bytes().startswith(b"PK"))
                with contextlib.redirect_stderr(StringIO()):
                    self.assertEqual(menace.main(prefix + ["export", case_id, "--output", output]), 1)
        finally:
            app.CASES_DIR = original


if __name__ == "__main__":
    unittest.main()
