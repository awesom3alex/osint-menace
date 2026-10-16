"""Check CLI startup without querying a public target."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addon_tools import ROOT, TOOLS, executable

failed = []
for key in TOOLS:
    args = [str(executable(key))]
    if key == "social-analyzer":
        args.append(str(ROOT / "addons/sources/social-analyzer/app.py"))
    if key == "blackbird":
        args.append(str(ROOT / "addons/sources/blackbird/blackbird.py"))
    args.append("--help")
    with tempfile.TemporaryDirectory() as work:
        try:
            result = subprocess.run(args, cwd=work, capture_output=True, text=True, timeout=45)
            passed = result.returncode == 0
            print(f"{key}: {'PASS' if passed else 'FAIL'} (exit {result.returncode})", flush=True)
            if not passed:
                print((result.stdout + result.stderr)[-2500:])
                failed.append(key)
        except Exception as exc:
            print(f"{key}: FAIL ({exc})", flush=True)
            failed.append(key)
if failed:
    raise SystemExit("CLI startup failed: " + ", ".join(failed))
