"""Whole-image duplicate/reuse matching. No face features or identity matching."""

import hashlib
import re
import shutil
import uuid
from urllib.parse import urlsplit

import cv2
import numpy as np
from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from PIL import Image

import image_analysis as images
import workspace_store as store

bp = Blueprint("image_reuse", __name__)
MAX_LIBRARY = 1000


def signature(image):
    image = image.convert("RGB")
    size = f"{image.width}x{image.height}:".encode()
    exact = hashlib.sha256(size + image.tobytes()).hexdigest()
    gray = np.asarray(
        image.convert("L").resize((32, 32), Image.Resampling.LANCZOS), dtype=np.float32
    )
    low = cv2.dct(gray)[:8, :8].flatten()[1:]
    bits = low > np.median(low)
    phash = sum(int(bit) << index for index, bit in enumerate(bits))
    return dict(pixel_sha256=exact, whole_image_phash=f"{phash:016x}", hash_version=1)


def signed(record):
    path = images.IMAGE_DIR / record["id"] / "original.png"
    if not path.is_file():
        return None
    if record.get("hash_version") == 1:
        return record
    with Image.open(path) as image:
        record.update(signature(image))
    store.put(record["id"], "image", record)
    return record


def find_matches(query, threshold=8):
    query = signed(dict(query))
    if query is None:
        raise ValueError("Original image is unavailable.")
    with store.connect() as db:
        total = db.execute(
            "SELECT count(*) FROM records WHERE type='image' AND id!=?", (query["id"],)
        ).fetchone()[0]
        rows = db.execute(
            "SELECT payload FROM records WHERE type='image' AND id!=? ORDER BY created DESC LIMIT ?",
            (query["id"], MAX_LIBRARY),
        ).fetchall()
    import json

    matches = []
    scanned = 0
    missing = 0
    for (raw,) in rows:
        record = signed(json.loads(raw))
        if not record:
            missing += 1
            continue
        scanned += 1
        exact = query["pixel_sha256"] == record["pixel_sha256"]
        distance = (
            int(query["whole_image_phash"], 16) ^ int(record["whole_image_phash"], 16)
        ).bit_count()
        # Very flat images can share the same pHash; only call them matches if pixels are identical.
        informative = int(query["whole_image_phash"], 16) not in (0, (1 << 63) - 1) and int(
            record["whole_image_phash"], 16
        ) not in (0, (1 << 63) - 1)
        if exact or (informative and distance <= threshold):
            matches.append(
                dict(
                    image_id=record["id"],
                    match_type="Identical normalized pixels" if exact else "Similar whole image",
                    distance=distance,
                    timestamp=record["timestamp"],
                    source_url=record.get("source_url", ""),
                    width=record["width"],
                    height=record["height"],
                )
            )
    matches.sort(
        key=lambda match: (match["match_type"] != "Identical normalized pixels", match["distance"])
    )
    return matches, scanned, total, missing


def source_url(value):
    value = value.strip()
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        len(value) > 2048
        or parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or any(ord(c) < 33 for c in value)
    ):
        raise ValueError("Use an HTTP or HTTPS source URL without credentials or whitespace.")
    return value


@bp.post("/images/<analysis_id>/source")
def save_source(analysis_id):
    record = images.load(analysis_id)
    try:
        record["source_url"] = source_url(request.form.get("source_url", ""))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    store.put(analysis_id, "image", record)
    return jsonify(message="Image source URL saved locally.")


@bp.post("/images/<analysis_id>/reuse")
def search(analysis_id):
    query = images.load(analysis_id)
    try:
        threshold = int(request.form.get("threshold", "8"))
        if not 0 <= threshold <= 16:
            raise ValueError("Invalid threshold")
        matches, scanned, total, missing = find_matches(query, threshold)
    except (ValueError, OSError):
        abort(400, "The image could not be searched. Use a threshold from 0 to 16.")
    run_id = uuid.uuid4().hex
    run = dict(
        id=run_id,
        target="Whole-image reuse",
        kind="image reuse",
        timestamp=store.now(),
        image_reuse=True,
        query_id=analysis_id,
        query_source_url=query.get("source_url", ""),
        matches=matches,
        scanned=scanned,
        total=total,
        missing=missing,
        threshold=threshold,
    )
    store.put(run_id, "image reuse", run)
    return redirect(url_for("image_reuse.results", run_id=run_id))


def load(run_id):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        abort(404)
    run = store.get(run_id)
    if not run or not run.get("image_reuse"):
        abort(404)
    return run


@bp.get("/image-reuse/<run_id>")
def results(run_id):
    from app import list_cases

    run = load(run_id)
    return render_template(
        "image_reuse.html", run=run, analysis=images.load(run["query_id"]), cases=list_cases()
    )


@bp.post("/image-reuse/<run_id>/case/<match_id>")
def capture(run_id, match_id):
    import app
    from case_features import EVIDENCE_DIR

    run = load(run_id)
    match = next((item for item in run["matches"] if item["image_id"] == match_id), None)
    if match is None:
        abort(404)
    with app.CASE_LOCK:
        case = app.load_case(request.form.get("case_id", ""))
        folder = EVIDENCE_DIR / case["id"]
        folder.mkdir(parents=True, exist_ok=True)
        evidence = []
        for image_id, label in [
            (run["query_id"], "Query whole image"),
            (match_id, "Matched whole image"),
        ]:
            source = images.IMAGE_DIR / image_id / "original.png"
            if not source.is_file():
                abort(404)
            key = uuid.uuid4().hex
            shutil.copyfile(source, folder / (key + ".png"))
            evidence.append(
                dict(
                    id=key, caption=label + " - whole-image reuse review", created_at=app.utc_now()
                )
            )
        links = []
        if run.get("query_source_url"):
            links.append(
                dict(
                    label="Operator-provided query source",
                    value=run["query_source_url"],
                    source="Image source metadata",
                )
            )
        if match["source_url"]:
            links.append(
                dict(
                    label="Operator-provided source page",
                    value=match["source_url"],
                    source="Image source metadata",
                )
            )
        section = dict(
            name="Whole-image reuse candidate",
            module_type="image reuse",
            module=dict(name="Whole-image hashing", mode="local library"),
            findings=[
                dict(
                    label=match["match_type"],
                    value=dict(
                        hash_distance=match["distance"],
                        matched_image_id=match_id,
                        source_url=match["source_url"] or "Not provided",
                        matched_image_saved_at=match["timestamp"],
                    ),
                    source="Local whole-image comparison",
                    evidence=evidence,
                )
            ],
            links=links,
            notes=[
                "Compared: " + run["timestamp"],
                "Similarity is a whole-image heuristic, not an identity match or calibrated probability. Review manually. Source URLs are supplied by the operator and are not independently verified.",
            ],
        )
        app.append_search_to_case(
            case,
            app.make_search_record(
                "image reuse", "Whole-image reuse", [section], app.result_summary([section])
            ),
        )
    return jsonify(message="Image reuse candidate, source link, and both images added to case.")
