#!/usr/bin/env python3
"""Main installer and updater entry point for OSINT Menace."""

import argparse
import shutil
import subprocess
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Install or upgrade OSINT Menace using Docker. No Python packages are required on the host."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--update",
        action="store_true",
        help="check for a newer stable release and run the backed-up updater",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="check for a newer stable release without installing it",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="do not launch the browser after installation or update",
    )
    args = parser.parse_args(argv)
    if args.check and args.no_open:
        parser.error("--check does not open a browser; use it without --no-open")
    root = Path(__file__).resolve().parent
    bash = shutil.which("bash")
    if not bash:
        parser.exit(1, "Bash is required. On Windows, run this installer inside WSL2.\n")
    script = root / "deployment" / ("update.sh" if args.update or args.check else "install.sh")
    if not script.is_file() or not (root / "osint/VERSION").is_file():
        parser.exit(1, "Use a complete OSINT Menace project folder.\n")
    options = ["--check"] if args.check else ["--no-open"] if args.no_open else []
    try:
        result = subprocess.run([bash, str(script), *options], cwd=root)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
