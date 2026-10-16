"""Restore exactly the reviewed upstream revisions before a clean Docker build."""

import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
for name, info in json.loads((root / "manifest.json").read_text()).items():
    dest = root / "sources" / name
    if dest.exists():
        actual = subprocess.check_output(
            ["git", "-C", str(dest), "rev-parse", "HEAD"], text=True
        ).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(dest), "status", "--porcelain"], text=True
        ).strip()
        if actual != info["revision"] or dirty:
            raise SystemExit(
                f"{name}: source differs from manifest; preserve local work and resolve before building"
            )
        continue
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(dest)], check=True)
    subprocess.run(
        ["git", "-C", str(dest), "remote", "add", "origin", info["repository"]], check=True
    )
    subprocess.run(
        ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", info["revision"]], check=True
    )
    subprocess.run(["git", "-C", str(dest), "checkout", "--detach", "FETCH_HEAD"], check=True)
    print(f"{name}: {info['revision']}")
