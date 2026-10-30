"""Case-local original email evidence and analyst-reviewed derived findings."""

import base64
import hashlib
import io
import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

bp = Blueprint("email_evidence", __name__)
CAPACITY = threading.BoundedSemaphore(2)
MAX_FILE = 5_000_000
MAX_EMAILS = 20


def runtime():
    import addon_tools

    return addon_tools.PREFIX / "mail-parser/bin/python"


def parse_original(raw):
    """Run the pinned parser in a time-limited, offline child process."""
    if not runtime().is_file():
        raise ValueError(
            "Mail-Parser is not installed in this runtime. Rebuild the current Docker image."
        )
    if not CAPACITY.acquire(blocking=False):
        abort(429, "Two email parses are running; try again shortly.")
    try:
        with tempfile.TemporaryDirectory(prefix="menace-email-") as folder:
            path = Path(folder) / "original.eml"
            path.write_bytes(raw)
            script = Path(__file__).parent / "scripts/mail_evidence_worker.py"
            env = dict(
                PATH=os.environ.get("PATH", ""),
                HOME=folder,
                PYTHONIOENCODING="utf-8",
                PYTHONDONTWRITEBYTECODE="1",
            )
            with tempfile.TemporaryFile() as out:
                proc = subprocess.Popen(
                    [str(runtime()), str(script), str(path)],
                    cwd=folder,
                    env=env,
                    stdout=out,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    raise ValueError(
                        "Email parsing reached its 30-second limit; no email was saved."
                    ) from None
                if os.fstat(out.fileno()).st_size > 1_000_000:
                    raise ValueError("Email review output exceeds its size limit.")
                out.seek(0)
                try:
                    parsed = json.load(out)
                except ValueError:
                    raise ValueError("Email parser did not return readable output.") from None
                if proc.returncode or not isinstance(parsed, dict) or parsed.get("error"):
                    raise ValueError(
                        str(parsed.get("error", "Email parsing failed; no email was saved."))
                        if isinstance(parsed, dict)
                        else "Invalid email parser output."
                    )
                return parsed
    finally:
        CAPACITY.release()


def locate(case, email_id):
    item = next((e for e in case.get("email_evidence", []) if e["id"] == email_id), None)
    if not item:
        abort(404)
    return item


@bp.get("/email-evidence")
def overview():
    import app

    return render_template(
        "email_evidence.html",
        case=None,
        cases=app.list_cases(),
        installed=runtime().is_file(),
        emails=[],
    )


@bp.route("/cases/<case_id>/email-evidence", methods=["GET", "POST"])
def workspace(case_id):
    import app
    from case_review import require_version, save_review_case

    error = None
    if request.method == "POST":
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            require_version(case)
            if len(case.get("email_evidence", [])) >= MAX_EMAILS:
                abort(400, "Maximum 20 original emails per case.")
        upload = request.files.get("email")
        if not upload or not (upload.filename or "").lower().endswith(".eml"):
            abort(
                400, "Choose one .eml file. Outlook .msg files are not supported in this workflow."
            )
        raw = upload.read(MAX_FILE + 1)
        if not raw or len(raw) > MAX_FILE:
            abort(400, "Email must be nonempty and at most 5 MB.")
        try:
            digest = hashlib.sha256(raw).hexdigest()
            if any(e["sha256"] == digest for e in case.get("email_evidence", [])):
                abort(409, "This original email is already retained in the case.")
            parsed = parse_original(raw)
            item = dict(
                id=uuid.uuid4().hex,
                filename=Path(upload.filename).name[:255],
                created_at=app.utc_now(),
                sha256=digest,
                original=base64.b64encode(raw).decode("ascii"),
                parsed=parsed,
            )
            with app.CASE_LOCK:
                case = app.load_case(case_id)
                require_version(case)
                if any(e["sha256"] == digest for e in case.get("email_evidence", [])):
                    abort(409, "Email already retained.")
                case.setdefault("email_evidence", []).append(item)
                save_review_case(
                    case, "email_imported", "Imported original email evidence for local review."
                )
            return redirect(url_for("email_evidence.detail", case_id=case_id, email_id=item["id"]))
        except ValueError as exc:
            error = str(exc)
    case = app.load_case(case_id)
    return render_template(
        "email_evidence.html",
        case=case,
        cases=app.list_cases(),
        installed=runtime().is_file(),
        emails=case.get("email_evidence", []),
        error=error,
    ), 400 if error else 200


@bp.get("/cases/<case_id>/email-evidence/<email_id>")
def detail(case_id, email_id):
    import app

    case = app.load_case(case_id)
    item = locate(case, email_id)
    return render_template("email_evidence_detail.html", case=case, item=item, mail=item["parsed"])


@bp.get("/cases/<case_id>/email-evidence/<email_id>/original")
def original(case_id, email_id):
    import app

    item = locate(app.load_case(case_id), email_id)
    try:
        raw = base64.b64decode(item["original"], validate=True)
    except ValueError:
        abort(409, "Original email encoding is invalid.")
    if hashlib.sha256(raw).hexdigest() != item["sha256"]:
        abort(409, "Original email failed its integrity check.")
    response = send_file(
        io.BytesIO(raw),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=item["filename"],
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def derived_entries(item):
    """Create candidates with original provenance, without interpreting header trust."""
    import research_hub

    output = []
    seen = set()
    mail = item["parsed"]

    def add(label, value, context):
        fingerprint = json.dumps([label, value, context], sort_keys=True)
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        f = research_hub.finding(
            label,
            value,
            "Mail-Parser",
            method="Local extraction from retained .eml; "
            + context
            + ". Header claims are unverified.",
        )
        f["collected_at"] = item["created_at"]
        f["email_provenance"] = dict(
            email_id=item["id"],
            original_filename=item["filename"],
            original_sha256=item["sha256"],
            context=context,
        )
        output.append(dict(id=hashlib.sha256(fingerprint.encode()).hexdigest()[:32], finding=f))

    for address in mail["addresses"]:
        field_label = {"from_": "From", "reply_to": "Reply-To", "return_path": "Return-Path"}.get(
            address["field"], address["field"].title()
        )
        context = "Claimed " + field_label + " address"
        if address["display_name"]:
            context += "; display name: " + address["display_name"]
        add(
            "Email",
            address["address"],
            context,
        )
        if "@" in address["address"]:
            add("Domain", address["address"].rsplit("@", 1)[1], "Domain in a claimed email address")
    for url in mail["urls"]:
        add("URL", url, "Link or resource reference present in message content; not visited")
        host = urlsplit(url).hostname
        if host:
            add("Domain", host, "Hostname in an extracted URL; not visited")
    for ip in mail["ips"]:
        add("IP", ip, "Address present in a Received header; source and trust not established")
    for attachment in mail["attachments"]:
        add(
            "Attachment metadata",
            attachment,
            "Attachment listed in retained original; not opened or executed",
        )
    add(
        "Email message summary",
        dict(
            subject=mail["subject"],
            reported_date=mail["date"],
            headers=mail["selected_headers"],
            warnings=mail["warnings"],
            defects=mail["defects"],
        ),
        mail["trust_note"],
    )
    return output[:500]


@bp.post("/cases/<case_id>/email-evidence/<email_id>/review")
def review(case_id, email_id):
    import app
    import research_hub
    import workspace_store
    from case_review import require_version

    case = app.load_case(case_id)
    require_version(case)
    item = locate(case, email_id)
    # Reopening the same retained original reuses the same result IDs and saves.
    key = hashlib.sha256(("mail-parser:" + case_id + ":" + email_id).encode()).hexdigest()[:32]
    if workspace_store.get(key) is None:
        record = dict(
            id=key,
            record_type="research_tool",
            collector="mail-parser",
            target=item["filename"],
            kind="email evidence",
            timestamp=item["created_at"],
            context_case_id=case_id,
            settings=dict(email_id=email_id, original_sha256=item["sha256"]),
        )
        research_hub.finish(record, derived_entries(item))
    return redirect(url_for("research_hub.result", record_id=key))


def validate_email_records(case):
    """Validate portable originals and the shapes consumed by email evidence pages."""

    def require(ok):
        if not ok:
            raise ValueError("Invalid email evidence data.")

    def text(value, limit=10000):
        return isinstance(value, str) and len(value) <= limit

    items = case.get("email_evidence", [])
    require(isinstance(items, list) and len(items) <= MAX_EMAILS)
    ids = set()
    hashes = set()
    for item in items:
        require(
            isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and re.fullmatch(r"[a-f0-9]{32}", item["id"])
            and item["id"] not in ids
        )
        ids.add(item["id"])
        require(
            text(item.get("filename"), 255)
            and item["filename"].lower().endswith(".eml")
            and text(item.get("created_at"), 100)
        )
        require(text(item.get("original"), 6_666_668))
        try:
            raw = base64.b64decode(item["original"], validate=True)
        except (ValueError, TypeError):
            raise ValueError("Invalid email original encoding.") from None
        require(
            0 < len(raw) <= MAX_FILE
            and hashlib.sha256(raw).hexdigest() == item.get("sha256")
            and item["sha256"] not in hashes
        )
        hashes.add(item["sha256"])
        mail = item.get("parsed")
        require(
            isinstance(mail, dict)
            and len(json.dumps(mail, ensure_ascii=False).encode()) <= 1_000_000
        )
        require(
            all(
                text(mail.get(k), 60000 if k in ("plain_text", "html_text") else 10000)
                for k in ("subject", "plain_text", "html_text", "date", "trust_note")
            )
        )
        for key, limit in [
            ("headers", 1000),
            ("addresses", 300),
            ("received", 100),
            ("urls", 200),
            ("ips", 100),
            ("attachments", 100),
            ("warnings", 200),
        ]:
            require(isinstance(mail.get(key), list) and len(mail[key]) <= limit)
        require(
            isinstance(mail.get("selected_headers"), dict) and isinstance(mail.get("defects"), dict)
        )
        require(
            all(
                text(k, 200) and isinstance(v, list) and all(text(x) for x in v)
                for k, v in mail["selected_headers"].items()
            )
        )
        require(
            all(
                isinstance(h, dict) and text(h.get("name"), 200) and text(h.get("value"))
                for h in mail["headers"]
            )
        )
        require(
            all(
                isinstance(a, dict)
                and all(text(a.get(k), 500) for k in ("field", "display_name", "address"))
                for a in mail["addresses"]
            )
        )
        require(all(isinstance(h, dict) for h in mail["received"]))
        require(all(text(w) for w in mail["warnings"]) and all(text(ip, 100) for ip in mail["ips"]))
        for url in mail["urls"]:
            require(text(url, 2048))
            try:
                p = urlsplit(url)
                require(
                    p.scheme in ("http", "https")
                    and bool(p.hostname)
                    and not p.username
                    and not p.password
                )
            except ValueError:
                raise ValueError("Invalid extracted email URL.") from None
        for a in mail["attachments"]:
            require(
                isinstance(a, dict)
                and all(
                    text(a.get(k), 1000)
                    for k in ("filename", "content_type", "disposition", "content_id", "note")
                )
            )
            require(
                a.get("size") is None or type(a["size"]) is int and 0 <= a["size"] <= 10_000_000
            )
            require(
                isinstance(a.get("sha256"), str)
                and (a["sha256"] == "" or re.fullmatch(r"[a-f0-9]{64}", a["sha256"]))
            )
