"""Test bootstrap for the application source directory."""
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1] / 'osint'
sys.path.insert(0, str(APP_ROOT))
