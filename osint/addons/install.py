"""Install pinned local sources into independent virtual environments."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("MENACE_ADDON_PREFIX", "/opt/addons"))
sources = Path(os.environ.get("MENACE_ADDON_SOURCES", "/app/addons/sources"))
selected = sys.argv[1:]
for name in selected:
    if name == "exiftool":
        destination = ROOT / "exiftool"
        shutil.copytree(
            sources / name, destination, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git")
        )
        (ROOT / "bin").mkdir(parents=True, exist_ok=True)
        link = ROOT / "bin/exiftool"
        if not link.exists():
            link.symlink_to(destination / "exiftool")
        continue
    env = ROOT / name
    subprocess.run([sys.executable, "-m", "venv", str(env)], check=True)
    pip = str(env / "bin/pip")
    subprocess.run(
        [pip, "install", "--no-cache-dir", "--upgrade", "pip", "setuptools", "wheel"], check=True
    )
    if name in ("blackbird", "social-analyzer"):
        args = ["-r", str(sources / name / "requirements.txt")]
    else:
        args = [str(sources / name)]
    if name in ("unfurl", "waymore", "dnstwist", "theharvester", "mail-parser"):
        # Build from a disposable copy; source pin checks must remain clean.
        with tempfile.TemporaryDirectory(prefix="menace-addon-build-") as folder:
            package = Path(folder) / name
            shutil.copytree(sources / name, package, ignore=shutil.ignore_patterns(".git"))
            subprocess.run([pip, "install", "--no-cache-dir", str(package)], check=True)
        if name == "dnstwist":
            subprocess.run(
                [pip, "install", "dnspython>=2.6,<3", "idna>=3,<4", "tld>=0.13,<1"], check=True
            )
    else:
        subprocess.run([pip, "install", "--no-cache-dir", *args], check=True)
