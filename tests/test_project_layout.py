"""Relocation contracts for entry points, native data, Docker sources, and links."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

from paths import APP_ROOT, DATA_ROOT, PROJECT_ROOT

ROOT = Path(__file__).resolve().parents[1]


class ProjectLayoutTests(TestCase):
    def test_root_has_one_python_entrypoint_and_no_runtime_assets(self):
        self.assertEqual({p.name for p in ROOT.glob("*.py")}, {"install.py"})
        for name in (
            "osint/app.py",
            "osint/VERSION",
            "osint/addons/manifest.json",
            "deployment/install.sh",
            "deployment/update.sh",
            "deployment/Dockerfile",
            "deployment/docker-compose.yml",
            "requirements/requirements.txt",
            "config/ruff.toml",
        ):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertFalse((ROOT / "templates").exists())
        self.assertFalse((ROOT / "static").exists())

    def test_native_data_path_and_cli_version_from_another_directory(self):
        self.assertEqual(PROJECT_ROOT, ROOT)
        self.assertEqual(APP_ROOT, ROOT / "osint")
        self.assertEqual(DATA_ROOT, ROOT / "data")
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, str(ROOT / "osint/menace.py"), "--version"],
                cwd=folder,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn((ROOT / "osint/VERSION").read_text().strip(), result.stdout)
            help_result = subprocess.run(
                [sys.executable, str(ROOT / "install.py"), "--help"],
                cwd=folder,
                capture_output=True,
                text=True,
            )
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("--update", help_result.stdout)
            self.assertFalse((Path(folder) / "data").exists())

    def test_local_document_links_resolve(self):
        for path in [
            ROOT / "README.md",
            *(ROOT / "docs").glob("*.md"),
            ROOT / "osint/addons/README.md",
        ]:
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
                if "://" in target or target.startswith(("#", "mailto:")):
                    continue
                local = target.split("#")[0]
                if local:
                    self.assertTrue(
                        (path.parent / local).exists(), str(path.relative_to(ROOT)) + ": " + target
                    )

    def test_docker_copy_sources_and_secret_exclusions(self):
        for line in (ROOT / "deployment/Dockerfile").read_text().splitlines():
            if line.startswith("COPY ") and "--from=" not in line:
                source = line.split()[1]
                self.assertTrue((ROOT / source).exists(), source)
        ignore = (ROOT / ".dockerignore").read_text()
        for private in (
            "data/cases/",
            "data/evidence/",
            "data/private/",
            ".env",
            "data/workspace.sqlite3*",
        ):
            self.assertIn(private, ignore)
        self.assertIn("osint/addons/sources/", (ROOT / ".gitignore").read_text())
