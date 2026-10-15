"""CLI search orchestration and result classification."""

import urllib.parse

import app as core
from collectors import Options, collect, now
from cli_catalog import SITE_NAMES

COLLECT_TYPES = ("username", "phone", "wallet", "url", "name", "records")


def classify_links(section):
    for link in section.get("links", []):
        host = urllib.parse.urlsplit(link.get("value", "")).hostname or ""
        link["category"] = ("search_link" if host in ("www.google.com", "www.bing.com", "duckduckgo.com") else
                            "candidate_profile" if section.get("module_type") == "username" else "research_link")


def run_search(kind, query, pattern="", scan=False, ports="21,22,80,443,8080", mode=None, options=None):
    options = options or Options()
    mode = mode or ("both" if kind in ("username", "auto") else "collect")
    options.validate()
    if mode not in ("collect", "links", "both"):
        raise ValueError("Mode must be collect, links, or both.")
    if kind == "auto":
        results = []
        for target in core.split_targets(query):
            detected = "url" if target.lower().startswith(("https://", "http://")) else core.detect_target_type(target)
            results.extend(run_search(detected, target, pattern, scan, ports, mode, options))
        return results
    if kind in COLLECT_TYPES:
        results = collect(kind, query, options) if mode != "links" else []
        if mode in ("links", "both"):
            if kind in ("records", "url"):
                links = [{"label": "Public page", "value": query, "category": "research_link"}] if kind == "url" else []
                if links:
                    results.append({"name": "Research links: " + query, "module_type": kind, "findings": [], "links": links, "notes": []})
            else:
                legacy = core.run_search(kind, query, pattern, False, ports)
                for section in legacy:
                    section["findings"] = []
                    classify_links(section)
                    if kind == "username" and options.profile_sites:
                        names = {SITE_NAMES[site] for site in options.profile_sites}
                        section["links"] = [link for link in section["links"]
                                            if link["category"] != "candidate_profile" or link["label"] in names
                                            or link["label"] == "Configured forum pattern"]
                    results.append(section)
        return results
    # Email, domain and IP already have direct checks. Link-only mode never
    # invokes these collectors; it yields only a search pivot.
    if mode == "links":
        return [{"name": "Search links: " + query, "module_type": kind, "findings": [], "notes": [],
                 "links": [{"label": "Search: " + query, "value": core.osint_tool.query_url(query), "category": "search_link"}]}]
    previous_timeout = core.osint_tool.TIMEOUT
    try:
        core.osint_tool.TIMEOUT = options.timeout
        results = core.run_search(kind, query, pattern, scan, ports)
    finally:
        core.osint_tool.TIMEOUT = previous_timeout
    for section in results:
        section["category"] = "collected_data"
        section["retrieved_at"] = now()
        classify_links(section)
        if mode == "collect":
            section["links"] = []
    return results
