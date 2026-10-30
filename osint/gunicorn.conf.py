"""Load the source directory and start opted-in source checks in the ready worker."""

import sys
from pathlib import Path

# Works in both /app inside Docker and the source checkout's osint/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def post_worker_init(worker):
    from advanced_research import start_scheduler

    start_scheduler()
