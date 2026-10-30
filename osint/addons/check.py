"""Check selected CLI startup without querying public targets."""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addon_tools import PREFIX, TOOLS, startup_command

selected = sys.argv[1:] or list(TOOLS)
failed = []
for key in selected:
    if key == "mail-parser":
        args = [str(PREFIX / "mail-parser/bin/mail-parser"), "--help"]
    elif key == "exiftool":
        args = [str(PREFIX / "bin/exiftool"), "-ver"]
    elif key in TOOLS:
        args = startup_command(key)
    else:
        raise SystemExit("Unknown tool: " + key)
    with tempfile.TemporaryDirectory() as work:
        try:
            import os

            env = dict(os.environ, HOME=work, XDG_CONFIG_HOME=work)
            result = subprocess.run(
                args, cwd=work, env=env, capture_output=True, text=True, timeout=45
            )
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
