"""Shared release identity for the terminal and web interfaces."""

from pathlib import Path

__version__ = (Path(__file__).parent / "VERSION").read_text().strip()
RELEASE_NAME = f"OSINT Menace v{__version__}"
