"""Install pinned local sources into independent virtual environments."""

import subprocess
import sys
from pathlib import Path

ROOT = Path("/opt/addons")
sources = Path("/app/addons/sources")
selected = sys.argv[1:]
for name in selected:
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
    subprocess.run([pip, "install", "--no-cache-dir", *args], check=True)
