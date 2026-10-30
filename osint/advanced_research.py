"""Cross-case review, local document reading, questions, monitoring, and research playbooks."""

import base64
import datetime as dt
import hashlib
import io
import json
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

from case_review import require_version, save_review_case
from case_workflow import findings

bp = Blueprint("advanced", __name__)
STEPS = {
    "search": "Public-source search",
    "archive": "Archived page review",
    "identifiers": "Related identifiers",
    "review": "Review findings",
}
MAX_DOCUMENT = 5_000_000
WORK_LOCK = threading.Lock()
START_LOCK = threading.Lock()
STARTED = False


def now():
    return dt.datetime.now(dt.timezone.utc)


def typed_keys(label, value):
    """Only typed identifiers; names never establish a connection."""
    from case_review import identity_keys

    return identity_keys(dict(type=label, label=value, fields=[]))


def identifier_rows(case):
    rows = []
    for ref, _, _, f in findings(case):
        if isinstance(f.get("value"), str):
            for kind, value in typed_keys(f.get("label", ""), f["value"]):
                rows.append(
                    dict(
                        kind=kind,
                        value=value,
                        ref=ref,
                        label=f["label"],
                        url="/cases/" + case["id"] + "#finding-" + ref,
                        status=f.get("verification_status", "Unverified"),
                        source=f.get("source_url", ""),
                    )
                )
    from case_review import identity_keys

    for graph in case.get("graphs", []):
        for node in graph["nodes"]:
            if node.get("annotation"):
                continue
            for kind, value in identity_keys(node):
                rows.append(
                    dict(
                        kind=kind,
                        value=value,
                        ref="graph:" + graph["id"] + ":" + node["id"],
                        label=node["label"],
                        url=url_for(
                            "case_graphs.workspace",
                            case_id=case["id"],
                            graph=graph["id"],
                            focus=node["id"],
                        ),
                        status="Graph identifier",
                        source=node.get("source", ""),
                    )
                )
    return rows


def connection_candidates(case, others):
    own = {}
    for row in identifier_rows(case):
        own.setdefault((row["kind"], row["value"]), []).append(row)
    output = []
    for other in others:
        for right in identifier_rows(other):
            for left in own.get((right["kind"], right["value"]), []):
                key = hashlib.sha256(
                    json.dumps(
                        [other["id"], left["ref"], right["ref"], left["kind"], left["value"]]
                    ).encode()
                ).hexdigest()
                output.append(
                    dict(
                        key=key,
                        other_id=other["id"],
                        other_name=other["name"],
                        left=left,
                        right=right,
                    )
                )
                if len(output) >= 200:
                    return output
    return output


@bp.get("/cases/<case_id>/connections")
def connections(case_id):
    import app

    case = app.load_case(case_id)
    catalog = [c for c in app.list_cases() if c["id"] != case_id]
    selected = request.args.getlist("other")[:20]
    others = [app.load_case(c["id"]) for c in catalog if c["id"] in selected]
    return render_template(
        "connections.html",
        case=case,
        catalog=catalog,
        selected=selected,
        candidates=connection_candidates(case, others),
        decisions=case.get("cross_case_decisions", []),
        selected_versions={c["id"]: c["updated_at"] for c in others},
    )


@bp.post("/cases/<case_id>/connections")
def connection_decision(case_id):
    import app

    with app.CASE_LOCK:
        case = app.load_case(case_id)
        require_version(case)
        other_id = request.form.get("other_id", "")
        if other_id == case_id:
            abort(400)
        other = app.load_case(other_id)
        item = next(
            (
                i
                for i in connection_candidates(case, [other])
                if i["key"] == request.form.get("key")
            ),
            None,
        )
        decision = request.form.get("decision")
        reason = request.form.get("reason", "").strip()
        if (
            not item
            or decision not in ("linked", "dismissed", "unresolved")
            or not 1 <= len(reason) <= 5000
        ):
            abort(400, "Choose a current match, decision, and reasoning.")
        if request.form.get("other_updated_at") != other["updated_at"]:
            abort(409, "The other case changed. Compare it again before deciding.")
        records = case.setdefault("cross_case_decisions", [])
        if len(records) >= 1000:
            abort(400, "Connection decision limit reached.")
        records.append(
            dict(
                item,
                decision=decision,
                reason=reason,
                timestamp=app.utc_now(),
                other_updated_at=other["updated_at"],
            )
        )
        save_review_case(case, "cross_case_review", "Reviewed a cross-case identifier match.")
    return redirect(url_for("advanced.connections", case_id=case_id, other=other_id))


def tool(command, timeout=30):
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise ValueError(
            "Local reader dependency missing: "
            + command[0]
            + ". Install Poppler and Tesseract, or use the Docker build."
        ) from None
    except subprocess.TimeoutExpired:
        raise ValueError(
            "Document processing reached its time limit; no document was saved."
        ) from None
    if result.returncode or len(result.stdout) > 2_000_000:
        raise ValueError("The document could not be processed within reader limits.")
    return result.stdout.decode("utf-8", errors="replace")


def ocr(path):
    return tool(["tesseract", str(path), "stdout", "-l", "eng"], 20).strip()[:60000]


def extract_document(raw, filename):
    """Local bounded extraction; retain the exact uploaded bytes and their hash."""
    from PIL import Image, UnidentifiedImageError

    pages = []
    deadline = time.monotonic() + 110
    with tempfile.TemporaryDirectory(prefix="menace-reader-") as folder:
        root = Path(folder)
        if raw.startswith(b"%PDF-"):
            mime = "application/pdf"
            path = root / "source.pdf"
            path.write_bytes(raw)
            info = tool(["pdfinfo", str(path)], 10)
            match = re.search(r"^Pages:\s+(\d+)", info, re.M)
            if not match or not 1 <= int(match[1]) <= 30:
                raise ValueError("Upload a PDF with 1 to 30 pages.")
            count = int(match[1])
            # One bounded extraction pass preserves page boundaries.
            text = tool(["pdftotext", "-enc", "UTF-8", "-layout", str(path), "-"], 30).split("\f")
            for number in range(1, count + 1):
                if time.monotonic() > deadline:
                    raise ValueError(
                        "Document processing reached its overall time limit; split the document into smaller files."
                    )
                content = text[number - 1].strip() if number <= len(text) else ""
                method = "PDF embedded text"
                if not content:
                    prefix = root / ("page-" + str(number))
                    tool(
                        [
                            "pdftoppm",
                            "-f",
                            str(number),
                            "-l",
                            str(number),
                            "-scale-to",
                            "1800",
                            "-singlefile",
                            "-png",
                            str(path),
                            str(prefix),
                        ],
                        20,
                    )
                    content = ocr(prefix.with_suffix(".png"))
                    method = "OCR (English); verify against original"
                pages.append(dict(number=number, text=content[:60000], method=method))
        else:
            try:
                image = Image.open(io.BytesIO(raw))
                if (
                    image.format not in ("PNG", "JPEG", "WEBP")
                    or image.width * image.height > 20_000_000
                ):
                    raise ValueError("Use a PNG, JPEG, or WebP image under 20 megapixels.")
                mime = Image.MIME[image.format]
                image.load()
                image.thumbnail((2400, 2400))
                path = root / "image.png"
                image.convert("RGB").save(path)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                raise ValueError("Upload a readable PDF, PNG, JPEG, or WebP.") from None
            pages = [
                dict(number=1, text=ocr(path), method="OCR (English); verify against original")
            ]
    return dict(
        id=uuid.uuid4().hex,
        filename=Path(filename).name[:255],
        mime=mime,
        original=base64.b64encode(raw).decode("ascii"),
        sha256=hashlib.sha256(raw).hexdigest(),
        pages=pages,
        created_at=now().isoformat(),
    )


@bp.route("/cases/<case_id>/reader", methods=["GET", "POST"])
def reader(case_id):
    import app

    error = None
    if request.method == "POST":
        try:
            with app.CASE_LOCK:
                case = app.load_case(case_id)
                require_version(case)
                refs = {r for r, _, _, _ in findings(case)}
                ref = request.form.get("ref", "")
                if ref and ref not in refs:
                    abort(400, "Choose an existing finding.")
                if len(case.get("reader_documents", [])) >= 20:
                    raise ValueError("Maximum 20 documents per case.")
            upload = request.files.get("document")
            if not upload:
                raise ValueError("Choose a PDF or screenshot.")
            raw = upload.read(MAX_DOCUMENT + 1)
            if not raw or len(raw) > MAX_DOCUMENT:
                raise ValueError("Documents must be nonempty and at most 5 MB.")
            if not WORK_LOCK.acquire(blocking=False):
                abort(429, "Document processing is busy. Try again shortly.")
            try:
                doc = extract_document(raw, upload.filename or "Evidence")
            finally:
                WORK_LOCK.release()
            doc["ref"] = ref
            with app.CASE_LOCK:
                case = app.load_case(case_id)
                require_version(case)
                case.setdefault("reader_documents", []).append(doc)
                save_review_case(
                    case, "document_read", "Imported a document for local text review."
                )
            return redirect(url_for("advanced.reader", case_id=case_id, document=doc["id"]))
        except ValueError as exc:
            error = str(exc)
    case = app.load_case(case_id)
    query = request.args.get("q", "").strip()[:200]
    docs = case.get("reader_documents", [])
    selected = request.args.get("document", "")
    results = []
    for doc in docs:
        for page in doc["pages"]:
            if (not selected or selected == doc["id"]) and (
                not query or query.casefold() in page["text"].casefold()
            ):
                pos = page["text"].casefold().find(query.casefold()) if query else 0
                results.append(
                    dict(
                        document=doc,
                        page=page,
                        snippet=page["text"][max(0, pos - 120) : max(0, pos - 120) + 600],
                    )
                )
    return render_template(
        "evidence_reader.html",
        case=case,
        documents=docs,
        results=results,
        query=query,
        selected=selected,
        refs=[(r, f["label"]) for r, _, _, f in findings(case)],
        error=error,
    ), 400 if error else 200


@bp.get("/cases/<case_id>/reader/<document_id>/original")
def original(case_id, document_id):
    import app

    doc = next(
        (d for d in app.load_case(case_id).get("reader_documents", []) if d["id"] == document_id),
        None,
    )
    if not doc:
        abort(404)
    raw = base64.b64decode(doc["original"], validate=True)
    if hashlib.sha256(raw).hexdigest() != doc["sha256"]:
        abort(409, "Original document failed its integrity check.")
    response = send_file(
        io.BytesIO(raw),
        mimetype=doc["mime"],
        download_name=doc["filename"],
        as_attachment=request.args.get("download") == "1",
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "sandbox"
    return response


@bp.route("/cases/<case_id>/questions", methods=["GET", "POST"])
def questions(case_id):
    import app

    if request.method == "POST":
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            require_version(case)
            records = case.setdefault("research_questions", [])
            key = request.form.get("id", "")
            item = next((q for q in records if q["id"] == key), None)
            if key and not item:
                abort(404)
            if not key:
                if len(records) >= 100:
                    abort(400, "Maximum 100 questions per case.")
                item = dict(id=uuid.uuid4().hex, history=[])
                records.append(item)
            title = request.form.get("title", "").strip()
            status = request.form.get("status", "Open")
            refs = {r for r, _, _, _ in findings(case)}
            supporting = request.form.getlist("supporting")
            conflicting = request.form.getlist("conflicting")
            if (
                not 1 <= len(title) <= 500
                or status not in ("Open", "Investigating", "Answered")
                or not set(supporting + conflicting) <= refs
                or set(supporting) & set(conflicting)
            ):
                abort(
                    400,
                    "Use a title, valid status, and distinct supporting and conflicting findings.",
                )
            fields = {
                name: request.form.get(name, "").strip()
                for name in ("answer", "unanswered", "next_steps")
            }
            if any(len(v) > 5000 for v in fields.values()) or len(item["history"]) >= 100:
                abort(400, "Question text or revision limit reached.")
            if status == "Answered" and not fields["answer"]:
                abort(400, "Record your answer before marking the question answered.")
            snapshot = dict(
                title=title,
                status=status,
                supporting=supporting,
                conflicting=conflicting,
                **fields,
                timestamp=app.utc_now(),
            )
            item.update(snapshot)
            item["history"].append(snapshot)
            save_review_case(case, "question_updated", "Updated an investigation question.")
        return redirect(url_for("advanced.questions", case_id=case_id))
    case = app.load_case(case_id)
    return render_template(
        "research_questions.html",
        case=case,
        questions=case.get("research_questions", []),
        refs=[(r, f["label"]) for r, _, _, f in findings(case)],
    )


def monitor_tick():
    """Run due, explicitly enabled monitors. Network fetches never hold the case lock."""
    import app
    import case_research
    from demo import DEMO_ID

    for meta in app.list_cases():
        if meta["id"] == DEMO_ID:
            continue
        case = app.load_case(meta["id"])
        if case.get("is_demo"):
            continue
        # Restored backups must be explicitly re-enabled before sending requests.
        for monitor in case.get("source_monitors", [])[:50]:
            if (
                not monitor["enabled"]
                or monitor.get("owner_case_id") != case["id"]
                or dt.datetime.fromisoformat(monitor["next_run"]) > now()
            ):
                continue
            ref = monitor["ref"]
            url = monitor["url"]
            token = monitor["id"]
            source = next((f for r, _, _, f in findings(case) if r == ref), None)
            if not source or source.get("source_url") != url:
                with app.CASE_LOCK:
                    current = app.load_case(case["id"])
                    item = next(
                        (m for m in current.get("source_monitors", []) if m["id"] == token), None
                    )
                    if item:
                        item.update(
                            enabled=False,
                            error="Source changed or was removed; review before re-enabling.",
                        )
                        current["updated_at"] = app.utc_now()
                        app.save_case(current)
                continue
            try:
                if not case_research.CAPTURE_LOCK.acquire(blocking=False):
                    continue
                try:
                    snapshot = case_research.fetch_public_page(url)
                finally:
                    case_research.CAPTURE_LOCK.release()
                failure = ""
            except Exception as exc:
                # Provider failures must not kill future schedules.
                failure = str(exc)[:500]
                snapshot = None
            with app.CASE_LOCK:
                current = app.load_case(case["id"])
                item = next(
                    (m for m in current.get("source_monitors", []) if m["id"] == token), None
                )
                if (
                    not item
                    or not item["enabled"]
                    or item["url"] != url
                    or item["next_run"] != monitor["next_run"]
                ):
                    continue
                finding = next((f for r, _, _, f in findings(current) if r == ref), None)
                if not finding or finding.get("source_url") != url:
                    item.update(
                        enabled=False,
                        error="Source changed or was removed; review before re-enabling.",
                    )
                elif failure:
                    item.update(error=failure, failures=item.get("failures", 0) + 1)
                    if item["failures"] >= 3:
                        item["enabled"] = False
                else:
                    observations = finding.setdefault("observations", [])
                    changed = not observations or observations[-1]["sha256"] != snapshot["sha256"]
                    if changed and len(observations) >= 25:
                        item.update(
                            enabled=False,
                            error="Observation retention limit reached; review the source.",
                        )
                    else:
                        if changed:
                            snapshot.update(id=uuid.uuid4().hex, timestamp=app.utc_now())
                            observations.append(snapshot)
                        item.update(
                            error="",
                            failures=0,
                            outcome="Changed; review inbox"
                            if changed and len(observations) > 1
                            else "Baseline saved"
                            if changed
                            else "Unchanged",
                        )
                item["last_run"] = app.utc_now()
                item["next_run"] = (now() + dt.timedelta(hours=item["hours"])).isoformat()
                from case_backups import MAX_CASE, encode

                current["updated_at"] = app.utc_now()
                if len(encode(current)) > MAX_CASE:
                    # Drop only this unsaved observation and pause rather than retrying
                    # the same due network request every scheduler pass.
                    if snapshot and finding:
                        retained = finding.get("observations", [])
                        if retained and retained[-1].get("id") == snapshot.get("id"):
                            retained.pop()
                    item.update(
                        enabled=False,
                        error="Case storage limit reached; review before re-enabling.",
                        outcome="Paused: storage limit",
                    )
                app.save_case(current)


def scheduler_loop():
    import fcntl

    import app

    app.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with (app.DATA_DIR / "source-monitor.lock").open("a") as stream:
        # A replacement worker waits for the old worker during graceful reload.
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                threading.Event().wait(5)
        while True:
            try:
                monitor_tick()
            except Exception:
                app.app.logger.exception("Source monitor pass failed")
            threading.Event().wait(30)


def start_scheduler():
    global STARTED
    with START_LOCK:
        if not STARTED:
            STARTED = True
            threading.Thread(target=scheduler_loop, name="source-monitors", daemon=True).start()


@bp.route("/cases/<case_id>/monitors", methods=["GET", "POST"])
def monitors(case_id):
    import app

    if request.method == "POST":
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            require_version(case)
            records = case.setdefault("source_monitors", [])
            key = request.form.get("id", "")
            item = next((m for m in records if m["id"] == key), None)
            if key:
                if not item:
                    abort(404)
                if request.form.get("action") == "pause":
                    item["enabled"] = False
                else:
                    finding = next((f for r, _, _, f in findings(case) if r == item["ref"]), None)
                    if not finding or not finding.get("source_url"):
                        abort(400, "Source no longer exists.")
                    item.update(
                        enabled=True,
                        owner_case_id=case_id,
                        url=finding["source_url"],
                        next_run=now().isoformat(),
                        failures=0,
                        error="",
                    )
            else:
                ref = request.form.get("ref", "")
                hours = request.form.get("hours", 24, type=int)
                finding = next((f for r, _, _, f in findings(case) if r == ref), None)
                if (
                    not finding
                    or not finding.get("source_url")
                    or hours not in (1, 6, 24, 168)
                    or len(records) >= 50
                ):
                    abort(400, "Choose a source and a supported schedule; maximum 50 monitors.")
                if any(m["ref"] == ref for m in records):
                    abort(409, "A monitor already exists for this source.")
                from case_workflow import validated_url

                try:
                    validated_url(finding["source_url"])
                except ValueError as exc:
                    abort(400, str(exc))
                records.append(
                    dict(
                        id=uuid.uuid4().hex,
                        ref=ref,
                        url=finding["source_url"],
                        hours=hours,
                        enabled=True,
                        owner_case_id=case_id,
                        next_run=now().isoformat(),
                        last_run="",
                        error="",
                        outcome="Pending first check",
                        failures=0,
                    )
                )
            save_review_case(
                case, "monitor_updated", "Updated a public-source monitoring schedule."
            )
        return redirect(url_for("advanced.monitors", case_id=case_id))
    case = app.load_case(case_id)
    return render_template(
        "source_monitors.html",
        case=case,
        monitors=case.get("source_monitors", []),
        refs=[(r, f["label"]) for r, _, _, f in findings(case) if f.get("source_url")],
    )


@bp.route("/cases/<case_id>/workflows", methods=["GET", "POST"])
def workflows(case_id):
    import app

    if request.method == "POST":
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            require_version(case)
            records = case.setdefault("research_workflows", [])
            action = request.form.get("action", "create")
            if action in ("complete", "reopen"):
                item = next((w for w in records if w["id"] == request.form.get("id")), None)
                if not item:
                    abort(404)
                index = request.form.get("index", type=int)
                if index is None or not 0 <= index < len(item["steps"]):
                    abort(400)
                note = request.form.get("note", "").strip()
                if len(note) > 5000:
                    abort(400)
                item["steps"][index].update(
                    done=action == "complete", note=note, timestamp=app.utc_now()
                )
            else:
                title = request.form.get("title", "").strip()
                target = request.form.get("target", "").strip()
                kind = request.form.get("kind", "domain")
                selected = request.form.getlist("steps")
                if (
                    not 1 <= len(title) <= 200
                    or not 1 <= len(target) <= 254
                    or kind not in ("domain", "email", "username", "phone", "ip")
                    or not selected
                    or len(set(selected)) != len(selected)
                    or not set(selected) <= set(STEPS)
                    or len(records) >= 50
                ):
                    abort(
                        400,
                        "Choose a title, identifier type, target, and research steps; maximum 50 workflows.",
                    )
                order = request.form.get("order", ",".join(STEPS)).split(",")
                if len(order) != 4 or set(order) != set(STEPS):
                    abort(400, "Provide each step once in the order field.")
                records.append(
                    dict(
                        id=uuid.uuid4().hex,
                        title=title,
                        target=target,
                        kind=kind,
                        created_at=app.utc_now(),
                        steps=[
                            dict(kind=k, done=False, note="", timestamp="")
                            for k in order
                            if k in selected
                        ],
                    )
                )
            save_review_case(case, "workflow_updated", "Updated a saved research workflow.")
        return redirect(url_for("advanced.workflows", case_id=case_id))
    case = app.load_case(case_id)
    return render_template(
        "research_workflows.html",
        case=case,
        workflows=case.get("research_workflows", []),
        steps=STEPS,
    )


@bp.get("/cases/<case_id>/workflows/<workflow_id>/<int:index>/open")
def open_step(case_id, workflow_id, index):
    import app

    case = app.load_case(case_id)
    item = next((w for w in case.get("research_workflows", []) if w["id"] == workflow_id), None)
    if not item or not 0 <= index < len(item["steps"]):
        abort(404)
    kind = item["steps"][index]["kind"]
    if kind == "search":
        return redirect(
            url_for(
                "case_research.expand", case_id=case_id, target=item["target"], kind=item["kind"]
            )
        )
    if kind == "archive":
        return redirect(
            url_for(
                "research_hub.tools",
                case_id=case_id,
                tool="archive_history",
                original=(
                    "https://" + item["target"] if item["kind"] == "domain" else item["target"]
                ),
            )
        )
    if kind == "identifiers":
        return redirect(
            url_for("advanced.related_identifiers", case_id=case_id, workflow_id=workflow_id)
        )
    return redirect(url_for("case_review.inbox", case_id=case_id))


def validate_advanced(case):
    """Validate imported state, including retained original bytes, before any UI consumes it."""

    def require(ok):
        if not ok:
            raise ValueError("Invalid advanced research data.")

    def text(value, limit=5000):
        return isinstance(value, str) and len(value) <= limit

    def collection(name, limit):
        values = case.get(name, [])
        require(isinstance(values, list) and len(values) <= limit)
        require(
            all(
                isinstance(v, dict)
                and isinstance(v.get("id"), str)
                and re.fullmatch(r"[a-f0-9]{32}", v["id"])
                for v in values
            )
        )
        require(len({v["id"] for v in values}) == len(values))
        return values

    for doc in collection("reader_documents", 20):
        require(
            text(doc.get("filename"), 255)
            and doc.get("mime") in ("application/pdf", "image/png", "image/jpeg", "image/webp")
        )
        require(
            text(doc.get("original"), 6_666_668)
            and text(doc.get("ref", ""))
            and text(doc.get("created_at"))
        )
        try:
            raw = base64.b64decode(doc["original"], validate=True)
        except (ValueError, TypeError):
            raise ValueError("Invalid document original encoding.") from None
        require(
            0 < len(raw) <= MAX_DOCUMENT and hashlib.sha256(raw).hexdigest() == doc.get("sha256")
        )
        if doc["mime"] == "application/pdf":
            require(raw.startswith(b"%PDF-"))
        else:
            from PIL import Image

            with Image.open(io.BytesIO(raw)) as image:
                require(
                    Image.MIME.get(image.format) == doc["mime"]
                    and image.width * image.height <= 20_000_000
                )
                image.verify()
        pages = doc.get("pages")
        require(isinstance(pages, list) and 1 <= len(pages) <= 30)
        for n, page in enumerate(pages, 1):
            require(
                isinstance(page, dict)
                and page.get("number") == n
                and text(page.get("text"), 60000)
                and text(page.get("method"), 200)
            )
    for item in collection("research_questions", 100):
        require(isinstance(item.get("history"), list) and len(item["history"]) <= 100)
        for row in [item, *item["history"]]:
            require(
                isinstance(row, dict) and row.get("status") in ("Open", "Investigating", "Answered")
            )
            require(
                all(
                    text(row.get(k), 5000)
                    for k in ("title", "answer", "unanswered", "next_steps", "timestamp")
                )
            )
            for key in ("supporting", "conflicting"):
                require(
                    isinstance(row.get(key), list)
                    and len(row[key]) <= 5000
                    and all(text(r) for r in row[key])
                )
    for item in collection("source_monitors", 50):
        require(
            all(
                text(item.get(k))
                for k in ("ref", "url", "owner_case_id", "next_run", "last_run", "error", "outcome")
            )
        )
        require(
            type(item.get("enabled")) is bool
            and item.get("hours") in (1, 6, 24, 168)
            and type(item.get("failures")) is int
            and item["failures"] >= 0
        )
        require(dt.datetime.fromisoformat(item["next_run"]).tzinfo is not None)
        from case_workflow import validated_url

        validated_url(item["url"])
    for item in collection("research_workflows", 50):
        require(
            all(text(item.get(k), 500) for k in ("title", "target", "created_at"))
            and item.get("kind") in ("domain", "email", "username", "phone", "ip")
        )
        steps = item.get("steps")
        require(isinstance(steps, list) and 1 <= len(steps) <= 4)
        require(
            all(
                isinstance(s, dict)
                and s.get("kind") in STEPS
                and type(s.get("done")) is bool
                and text(s.get("note"))
                and text(s.get("timestamp"))
                for s in steps
            )
        )
        require(len({s["kind"] for s in steps}) == len(steps))
    decisions = case.get("cross_case_decisions", [])
    require(isinstance(decisions, list) and len(decisions) <= 1000)
    for item in decisions:
        require(
            isinstance(item, dict) and item.get("decision") in ("linked", "dismissed", "unresolved")
        )
        require(
            all(
                text(item.get(k))
                for k in (
                    "key",
                    "other_id",
                    "other_name",
                    "reason",
                    "timestamp",
                    "other_updated_at",
                )
            )
        )
        for side in ("left", "right"):
            row = item.get(side)
            require(
                isinstance(row, dict)
                and all(
                    text(row.get(k))
                    for k in ("kind", "value", "ref", "label", "url", "status", "source")
                )
            )
            require(
                row["kind"] in ("email", "phone", "username", "domain")
                and row["url"].startswith("/cases/")
            )


@bp.get("/cases/<case_id>/workflows/<workflow_id>/identifiers")
def related_identifiers(case_id, workflow_id):
    import app

    case = app.load_case(case_id)
    workflow = next((w for w in case.get("research_workflows", []) if w["id"] == workflow_id), None)
    if not workflow:
        abort(404)
    return render_template(
        "workflow_identifiers.html", case=case, workflow=workflow, identifiers=identifier_rows(case)
    )
