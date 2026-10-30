"""Stable application and runtime paths for source checkouts and Docker images."""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = APP_ROOT.parent if (APP_ROOT.parent / "install.py").is_file() else APP_ROOT
DATA_ROOT = PROJECT_ROOT / "data"
