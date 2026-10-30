"""Research-tool inventory, reviewed addon facts, and read-only retained-file metadata."""

import base64
import hashlib
import ipaddress
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

bp = Blueprint("github_tools", __name__)
CAPACITY = threading.BoundedSemaphore(2)
DESCRIPTIONS = {
    "mail-parser": (
        "Email Evidence",
        "Inspect original email headers, reported delivery hops, body text, links, and attachment metadata.",
        "Local .eml parsing; no remote images, link visits, or attachment execution.",
    ),
    "unfurl": (
        "URL Inspector",
        "Decode URL parameters, encoded values, and supported timestamps.",
        "Local only; no URL visit or remote lookup.",
    ),
    "waymore": (
        "Historical URL Discovery",
        "Discover older URLs for a domain, then review useful archive leads.",
        "Wayback Machine and Common Crawl; URLs only, no archived-body downloads.",
    ),
    "exiftool": (
        "Evidence Metadata",
        "Read metadata from an original PDF or image retained in the evidence reader.",
        "Local, read-only extraction. Metadata is reported information, not proof of authenticity.",
    ),
    "subfinder": (
        "Passive Subdomains",
        "Map an organization’s publicly reported domain footprint.",
        "crt.sh and HackerTarget; no active DNS resolution or target HTTP requests.",
    ),
    "dnstwist": (
        "Brand Impersonation",
        "Find registered look-alike domain candidates for brand review.",
        "DNS queries for hyphenation, omission, and transposition variants; four workers. No HTTP, SMTP, or screenshot requests.",
    ),
    "theharvester": (
        "Organization Footprint",
        "Gather infrastructure leads from selected organization sources.",
        "crt.sh and AlienVault OTX; no DNS resolution, crawling, or screenshots. This provider set focuses on hosts, not comprehensive email discovery.",
    ),
}


def validate_target(tool, target):
    if not isinstance(target, str) or not target or any(ord(c) < 33 for c in target):
        raise ValueError("Enter a single target without whitespace or control characters.")
    if tool == "unfurl":
        if len(target) > 2048:
            raise ValueError("URL Inspector accepts URLs up to 2,048 characters.")
        try:
            parsed = urlsplit(target)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError
            _ = parsed.port
        except ValueError:
            raise ValueError(
                "Enter an HTTP(S) URL without embedded credentials. It will be decoded locally."
            ) from None
        return target
    try:
        target = target.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise ValueError("Enter a valid public domain name.") from None
    if (
        len(target) > 253
        or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", target)
        or target.endswith((".local", ".localhost", ".internal"))
    ):
        raise ValueError("Enter a public domain name without a URL, port, path, or wildcard.")
    try:
        ipaddress.ip_address(target)
    except ValueError:
        return target
    raise ValueError("Use a domain name rather than an IP address.")


def inventory():
    import addon_tools

    manifest = json.loads((addon_tools.ROOT / "addons/manifest.json").read_text())
    output = []
    for key, (label, description, activity) in DESCRIPTIONS.items():
        executable = (
            addon_tools.PREFIX / "mail-parser/bin/python"
            if key == "mail-parser"
            else addon_tools.PREFIX / "bin/exiftool"
            if key == "exiftool"
            else addon_tools.executable(key)
        )
        output.append(
            dict(
                id=key,
                label=label,
                description=description,
                activity=activity,
                installed=executable.is_file()
                and (key != "exiftool" or bool(shutil.which("perl"))),
                **manifest[key],
            )
        )
    return output


def finding_section(job):
    import addon_tools
    import research_hub
    import tool_credentials

    raw = tool_credentials.redact(job.get("output", ""))
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = {}
    if not isinstance(payload, dict) or payload.get("menace_github_tool") != job["tool"]:
        payload = dict(
            records=[],
            error="Structured output was unavailable. Inspect the original output and execution status.",
        )
    found = []
    for row in payload.get("records", [])[:500]:
        if not isinstance(row, dict) or not isinstance(row.get("label"), str):
            continue
        value = row.get("value", "")
        details = {
            key: val for key, val in row.items() if key not in ("label", "value", "source_url")
        }
        f = research_hub.finding(
            row["label"],
            value,
            addon_tools.TOOLS[job["tool"]][1],
            row.get("source_url", ""),
            payload.get("mode", "Selected research tool"),
        )
        f["collected_at"] = job["timestamp"]
        if job.get("id"):
            f["research_source"] = dict(
                record_id=job["id"],
                entry_id=hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()[:32],
            )
        f["provider_details"] = dict(providers=payload.get("providers", []), **details)
        found.append(f)
    notes = [
        "Execution status: " + job["status"],
        DESCRIPTIONS[job["tool"]][2],
        "Outputs are unverified leads; a shared identifier or registered look-alike does not establish identity or malicious activity.",
    ]
    if payload.get("error"):
        notes.append(str(payload["error"])[:1000])
    if payload.get("rate_limited"):
        notes.append("A provider rate limit was observed; coverage is incomplete.")
    if payload.get("limited"):
        notes.append("Output was limited; coverage is incomplete.")
    return dict(
        name=DESCRIPTIONS[job["tool"]][0] + ": " + job["target"],
        module_type="addon:" + job["tool"],
        module=dict(
            name=addon_tools.TOOLS[job["tool"]][1], mode=payload.get("mode", "analyst selected")
        ),
        findings=found,
        links=[],
        notes=notes,
    )


@bp.get("/github-tools")
def page():
    import app

    case_id = request.args.get("case_id", "")
    case = app.load_case(case_id) if case_id else None
    documents = case.get("reader_documents", []) if case else []
    return render_template(
        "github_tools.html",
        tools=inventory(),
        cases=app.list_cases(),
        case=case,
        documents=documents,
    )


@bp.post("/cases/<case_id>/reader/<document_id>/metadata")
def extract_metadata(case_id, document_id):
    import addon_tools
    import app
    import research_hub
    import workspace_store
    from case_review import require_version

    case = app.load_case(case_id)
    require_version(case)
    doc = next((d for d in case.get("reader_documents", []) if d["id"] == document_id), None)
    if not doc:
        abort(404)
    executable = addon_tools.PREFIX / "bin/exiftool"
    if not executable.is_file():
        abort(400, "ExifTool is not installed in this runtime. Build the current addon image.")
    try:
        raw = base64.b64decode(doc["original"], validate=True)
    except (ValueError, TypeError):
        abort(409, "Original document encoding is invalid.")
    if hashlib.sha256(raw).hexdigest() != doc["sha256"]:
        abort(409, "Original document failed its integrity check.")
    if not CAPACITY.acquire(blocking=False):
        abort(429, "Two metadata extractions are running; try again shortly.")
    try:
        with tempfile.TemporaryDirectory(prefix="menace-metadata-") as folder:
            source = Path(folder) / (
                "evidence.pdf" if doc["mime"] == "application/pdf" else "evidence.image"
            )
            source.write_bytes(raw)
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": folder,
                "MENACE_ADDON_PREFIX": str(addon_tools.PREFIX),
            }
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(addon_tools.ROOT / "scripts/github_worker.py"),
                    "--tool",
                    "exiftool",
                    "--file",
                    str(source),
                ],
                cwd=folder,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
            try:
                output, _ = proc.communicate(timeout=40)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.communicate()
                abort(400, "ExifTool reached its time limit; no metadata was saved.")
            if proc.returncode or len(output) > 1_000_000:
                abort(400, "ExifTool could not extract metadata within its limits.")
            if source.read_bytes() != raw:
                abort(409, "The processing copy changed unexpectedly; no metadata was saved.")
            payload = json.loads(output)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        abort(400, "Local metadata extraction failed; the original file is unchanged.")
    finally:
        CAPACITY.release()
    key = uuid.uuid4().hex
    entries = []
    for row in payload.get("records", [])[:300]:
        value = dict(
            reported_value=row["value"],
            original_filename=doc["filename"],
            original_sha256=doc["sha256"],
            document_id=doc["id"],
            finding_ref=doc.get("ref", ""),
        )
        entries.append(
            dict(
                id=uuid.uuid4().hex,
                finding=research_hub.finding(
                    row["label"],
                    value,
                    "ExifTool",
                    method="Local read-only extraction from retained original; metadata is unverified.",
                ),
            )
        )
    record = dict(
        id=key,
        record_type="research_tool",
        collector="exiftool",
        context_case_id=case_id,
        kind="document",
        target=doc["filename"],
        timestamp=workspace_store.now(),
        config=dict(
            tool="exiftool", case_id=case_id, document_id=doc["id"], original_sha256=doc["sha256"]
        ),
    )
    research_hub.finish(record, entries)
    return redirect(url_for("research_hub.result", record_id=key))


@bp.post("/api/github-tools/run")
def launch():
    import addon_tools
    import research_hub
    import workspace_store

    data = request.get_json(silent=True)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("tool"), str)
        or data["tool"] not in addon_tools.GITHUB_TOOLS
    ):
        return jsonify(error="Choose a supported GitHub research tool."), 400
    try:
        case_id = research_hub.context_case(data.get("case_id", ""))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    # Delegate validation, limits and cancellation to the existing addon queue.
    response, status = addon_tools.launch()
    if status != 202:
        return response, status
    payload = response.get_json()
    key = payload["id"]
    if case_id:
        with addon_tools.LOCK:
            saved = workspace_store.get(key)
            saved["origin_case_id"] = case_id
            if key in addon_tools.JOBS:
                addon_tools.JOBS[key]["origin_case_id"] = case_id
                workspace_store.put(key, "addon", addon_tools.JOBS[key])
            else:
                workspace_store.put(key, "addon", saved)
    return jsonify(
        id=key,
        url=url_for("workspace.history_detail", record_id=key, case_id=case_id)
        if case_id
        else url_for("workspace.history_detail", record_id=key),
    ), 202


@bp.errorhandler(HTTPException)
def api_error(error):
    if request.path.startswith("/api/"):
        return jsonify(error=error.description), error.code
    return error
