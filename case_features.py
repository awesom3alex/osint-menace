"""Finding review and screenshot evidence attached to existing JSON cases."""

import datetime as dt
import hashlib
import uuid
from io import BytesIO
from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_file
from PIL import Image, UnidentifiedImageError

import case_workflow

bp = Blueprint("case_features", __name__)
EVIDENCE_DIR = Path("data/evidence")
STATUSES = ("Unverified", "Confirmed", "False positive")


def locate(case, search_id, section_index, finding_index):
    for search in case.get("searches", []):
        if search.get("id") == search_id:
            try:
                return search["results"][section_index]["findings"][finding_index]
            except (IndexError, KeyError, TypeError):
                break
    abort(404)


@bp.post("/cases/<case_id>/review/<search_id>/<int:section_index>/<int:finding_index>")
def review(case_id, search_id, section_index, finding_index):
    import app

    status = request.form.get("status", "Unverified")
    notes = request.form.get("analyst_notes", "")
    if status not in STATUSES or len(notes) > 20000:
        return jsonify(error="Choose a valid status and keep notes under 20,000 characters."), 400
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        finding = locate(case, search_id, section_index, finding_index)
        finding.update(
            verification_status=status,
            analyst_notes=notes,
            include_in_report=request.form.get("include_in_report") == "on",
            reviewed_at=app.utc_now(),
        )
        case_workflow.event(
            case,
            "finding_reviewed",
            "Reviewed " + finding.get("label", "finding") + ": " + status,
            search_id=search_id,
        )
        case["updated_at"] = app.utc_now()
        app.save_case(case)
    return jsonify(message="Finding review saved.")


@bp.post("/cases/<case_id>/notes")
def notes(case_id):
    import app

    text = request.form.get("notes", "")
    if len(text) > 50000:
        return jsonify(error="Keep case notes under 50,000 characters."), 400
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        case.update(notes=text, updated_at=app.utc_now())
        case_workflow.event(case, "notes_updated", "Case notes updated.")
        app.save_case(case)
    return jsonify(message="Case notes saved.")


@bp.post("/cases/<case_id>/evidence/<search_id>/<int:section_index>/<int:finding_index>")
def upload(case_id, search_id, section_index, finding_index):
    import app

    file = request.files.get("screenshot")
    caption = request.form.get("caption", "")[:2000]
    if not file:
        return jsonify(error="Select a PNG, JPEG, or WebP screenshot."), 400
    try:
        source_url = case_workflow.validated_url(request.form.get("source_url", ""))
        captured = request.form.get("captured_at", "").strip()
        if captured:
            parsed = dt.datetime.fromisoformat(captured)
            captured = (
                parsed.replace(tzinfo=dt.timezone.utc).isoformat()
                if parsed.tzinfo is None
                else parsed.astimezone(dt.timezone.utc).isoformat()
            )
    except ValueError as exc:
        return jsonify(error=str(exc) or "Use a valid UTC capture time."), 400
    data = file.read(10_000_001)
    if len(data) > 10_000_000:
        return jsonify(error="Screenshot must be 10 MB or smaller."), 400
    try:
        image = Image.open(BytesIO(data))
        if image.format not in ("PNG", "JPEG", "WEBP") or image.width * image.height > 20_000_000:
            raise ValueError("Unsupported image")
        image.load()
        image = image.convert("RGB")
        image.info.clear()
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
        return jsonify(error="Use a valid PNG, JPEG, or WebP image under 20 megapixels."), 400
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        if case.get("is_demo"):
            abort(403, "The demo case is read-only.")
        finding = locate(case, search_id, section_index, finding_index)
        evidence = finding.setdefault("evidence", [])
        if len(evidence) >= 10:
            return jsonify(error="Maximum 10 screenshots per finding."), 400
        evidence_id = uuid.uuid4().hex
        folder = EVIDENCE_DIR / case_id
        folder.mkdir(parents=True, exist_ok=True)
        image.save(folder / (evidence_id + ".png"), "PNG")
        path = folder / (evidence_id + ".png")
        item = dict(
            id=evidence_id,
            caption=caption,
            created_at=app.utc_now(),
            source_url=source_url,
            captured_at=captured,
            original_filename=Path(file.filename or "screenshot").name[:255],
            original_sha256=hashlib.sha256(data).hexdigest(),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            bytes=path.stat().st_size,
            collection_method="Operator screenshot upload; normalized to PNG; embedded metadata removed",
        )
        case_workflow.event(
            case,
            "evidence_attached",
            "Screenshot attached to " + finding.get("label", "finding"),
            search_id=search_id,
            evidence_id=evidence_id,
        )
        evidence.append(item)
        case["updated_at"] = app.utc_now()
        app.save_case(case)
    return jsonify(
        message="Screenshot attached.",
        evidence=dict(item, url=f"/cases/{case_id}/evidence/{evidence_id}.png"),
    )


@bp.get("/cases/<case_id>/evidence/<evidence_id>.png")
def evidence(case_id, evidence_id):
    import re

    import app

    case = app.load_case(case_id)
    if not re.fullmatch(r"[a-f0-9]{32}", evidence_id):
        abort(404)
    # A file is only served when it is referenced by this case.
    ids = {
        e.get("id")
        for s in case.get("searches", [])
        for r in s.get("results", [])
        for f in r.get("findings", [])
        for e in f.get("evidence", [])
    }
    if evidence_id not in ids:
        abort(404)
    path = EVIDENCE_DIR / case_id / (evidence_id + ".png")
    if not path.is_file():
        abort(404)
    return send_file(path.resolve(), mimetype="image/png")


@bp.post("/cases/<case_id>/evidence/<evidence_id>/verify")
def verify_evidence(case_id, evidence_id):
    import re

    import app

    if not re.fullmatch(r"[a-f0-9]{32}", evidence_id):
        abort(404)
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        item = next(
            (
                e
                for _, _, _, f in case_workflow.findings(case)
                for e in f.get("evidence", [])
                if e.get("id") == evidence_id
            ),
            None,
        )
        if item is None:
            abort(404)
        if not item.get("sha256"):
            return jsonify(error="No stored hash exists for this legacy attachment."), 409
        path = EVIDENCE_DIR / case_id / (evidence_id + ".png")
        if not path.is_file():
            return jsonify(error="The evidence file is missing."), 409
        valid = hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    if not valid:
        return jsonify(
            error="Evidence integrity check failed: file differs from its recorded SHA-256.",
            valid=False,
        ), 409
    return jsonify(message="Stored file matches its recorded SHA-256.", valid=True)
