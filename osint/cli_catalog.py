"""Platform coverage and OSINT Links access for terminal users."""

import json
import re
from pathlib import Path

from osint_tool import PROFILE_PATTERNS
from paths import DATA_ROOT


def site_slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


SITE_NAMES = {site_slug(name): name for name in PROFILE_PATTERNS}


def platform_rows():
    return [{"site": slug, "name": name, "url_pattern": PROFILE_PATTERNS[name],
             "direct_check": slug in ("github", "bluesky", "gitlab", "hacker-news"), "profile_link": True}
            for slug, name in SITE_NAMES.items()]


def catalog(data_dir, category="", query=""):
    path = Path(data_dir).expanduser() / "catalog" / "osint_links.json"
    if not path.exists():
        path = DATA_ROOT / "catalog" / "osint_links.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for group in data.get("categories", []):
        if category and category.casefold() not in group["name"].casefold():
            continue
        for link in group.get("links", []):
            row = {"category": group["name"], **link}
            if query.casefold() in " ".join(str(value) for value in row.values()).casefold():
                rows.append(row)
    return data, rows


def catalog_section(rows):
    return {"name": "OSINT Links selections", "module_type": "catalog", "findings": [],
            "links": [{"label": row["title"], "value": row["url"], "source": "OSINT4ALL / " + row["category"],
                       "category": "research_link"} for row in rows], "notes": []}
