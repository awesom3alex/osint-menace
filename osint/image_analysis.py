"""Local face localization and image review. No recognition or identity matching."""

import re
import shutil
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file, url_for
from PIL import Image, ImageDraw, ImageFilter, ImageOps, UnidentifiedImageError

import workspace_store as store
from paths import DATA_ROOT

bp = Blueprint("images", __name__)
IMAGE_DIR = DATA_ROOT / "image_analysis"
DETECTION_LOCK = threading.BoundedSemaphore(1)
DETECTOR_PATH = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"


def detect(image):
    """Return boxes in original, orientation-corrected image coordinates."""
    sample = image.copy()
    sample.thumbnail((1600, 1600))
    gray = cv2.cvtColor(np.asarray(sample), cv2.COLOR_RGB2GRAY)
    classifier = cv2.CascadeClassifier(str(DETECTOR_PATH))
    if classifier.empty():
        raise RuntimeError("Face detector is unavailable.")
    boxes = classifier.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    sx, sy = image.width / sample.width, image.height / sample.height
    result = []
    for x, y, width, height in boxes:
        left, top = max(0, round(int(x) * sx)), max(0, round(int(y) * sy))
        right, bottom = (
            min(image.width, round((int(x) + int(width)) * sx)),
            min(image.height, round((int(y) + int(height)) * sy)),
        )
        result.append(dict(x=left, y=top, width=right - left, height=bottom - top))
    return sorted(result, key=lambda box: (box["y"], box["x"]))


def analyze(data):
    if len(data) > 10_000_000:
        raise ValueError("Choose an image of 10 MB or less.")
    try:
        image = Image.open(BytesIO(data))
        if image.format not in ("JPEG", "PNG", "WEBP") or image.width * image.height > 20_000_000:
            raise ValueError("Use PNG, JPEG, or WebP, up to 20 megapixels.")
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.info.clear()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("That file could not be read as a PNG, JPEG, or WebP image.")
    started = time.monotonic()
    boxes = detect(image)
    analysis_id = uuid.uuid4().hex
    folder = IMAGE_DIR / analysis_id
    folder.mkdir(parents=True, exist_ok=True)
    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    blurred = image.copy()
    line_width = max(2, round(max(image.size) / 350))
    for index, box in enumerate(boxes):
        x, y, w, h = (box[key] for key in ("x", "y", "width", "height"))
        rect = (x, y, x + w, y + h)
        draw.rectangle(rect, outline="#00e6c2", width=line_width)
        draw.text(
            (x + 4, max(0, y + 4)),
            str(index + 1),
            fill="white",
            stroke_width=1,
            stroke_fill="black",
        )
        # Expand blur beyond the detector box, but preserve separate exact face crops.
        padding = round(max(w, h) * 0.15)
        expanded = (
            max(0, x - padding),
            max(0, y - padding),
            min(image.width, x + w + padding),
            min(image.height, y + h + padding),
        )
        blurred.paste(
            image.crop(expanded).filter(ImageFilter.GaussianBlur(radius=max(20, max(w, h) / 5))),
            expanded,
        )
        if index < 100:
            image.crop(rect).save(folder / f"face-{index + 1}.png")
    image.save(folder / "original.png")
    annotated.save(folder / "annotated.png")
    blurred.save(folder / "blurred.png")
    result = dict(
        id=analysis_id,
        target="Image analysis",
        kind="image",
        timestamp=store.now(),
        image_analysis=True,
        width=image.width,
        height=image.height,
        faces=boxes,
        crop_count=min(len(boxes), 100),
        detector="OpenCV frontal-face Haar cascade",
        elapsed_seconds=round(time.monotonic() - started, 2),
    )
    from image_reuse import signature

    result.update(signature(image))
    store.put(analysis_id, "image", result)
    return result


def load(analysis_id):
    if not re.fullmatch(r"[a-f0-9]{32}", analysis_id):
        abort(404)
    record = store.get(analysis_id)
    if not record or not record.get("image_analysis"):
        abort(404)
    return record


@bp.route("/images", methods=["GET", "POST"])
def page():
    if request.method == "POST":
        file = request.files.get("image")
        if not file:
            return render_template("images.html", error="Select an image to analyze."), 400
        if not DETECTION_LOCK.acquire(blocking=False):
            return render_template(
                "images.html", error="Another image is being analyzed. Please try again shortly."
            ), 429
        try:
            result = analyze(file.read(10_000_001))
        except ValueError as exc:
            return render_template("images.html", error=str(exc)), 400
        except RuntimeError:
            return render_template(
                "images.html",
                error="The local face detector is unavailable. Check the application installation.",
            ), 503
        finally:
            DETECTION_LOCK.release()
        return redirect(url_for("images.result", analysis_id=result["id"]))
    return render_template("images.html")


@bp.get("/images/<analysis_id>")
def result(analysis_id):
    from app import list_cases

    return render_template("images.html", analysis=load(analysis_id), cases=list_cases())


@bp.get("/images/<analysis_id>/files/<filename>")
def image_file(analysis_id, filename):
    analysis = load(analysis_id)
    permitted = {"original.png", "annotated.png", "blurred.png"} | {
        f"face-{i + 1}.png" for i in range(analysis["crop_count"])
    }
    if filename not in permitted:
        abort(404)
    path = IMAGE_DIR / analysis_id / filename
    if not path.is_file():
        abort(404)
    response = send_file(path.resolve(), mimetype="image/png")
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.post("/images/<analysis_id>/case")
def save_to_case(analysis_id):
    import app
    from case_features import EVIDENCE_DIR

    analysis = load(analysis_id)
    variant = request.form.get("variant", "annotated")
    crops = request.form.get("include_crops") == "on"
    if variant not in ("original", "annotated", "blurred"):
        return jsonify(error="Select original, annotated, or blurred output."), 400
    if variant == "blurred" and crops:
        return jsonify(
            error="Unblurred face crops cannot be included with a blurred report image."
        ), 400
    caption = request.form.get("caption", "")[:2000]
    with app.CASE_LOCK:
        case = app.load_case(request.form.get("case_id", ""))
        folder = EVIDENCE_DIR / case["id"]
        folder.mkdir(parents=True, exist_ok=True)

        def evidence(filename, label):
            source = IMAGE_DIR / analysis_id / filename
            if not source.is_file():
                abort(404)
            key = uuid.uuid4().hex
            shutil.copyfile(source, folder / (key + ".png"))
            return dict(id=key, caption=label, created_at=app.utc_now())

        findings = [
            dict(
                label="Face detection summary",
                value=dict(
                    detected_faces=len(analysis["faces"]),
                    image_width=analysis["width"],
                    image_height=analysis["height"],
                    detector=analysis["detector"],
                    image_variant=variant,
                ),
                source=analysis["detector"],
                evidence=[
                    evidence(
                        variant + ".png",
                        caption or variant.title() + " image - local face detection",
                    )
                ],
            )
        ]
        for index, box in enumerate(analysis["faces"]):
            finding = dict(
                label=f"Detected face {index + 1}", value=box, source=analysis["detector"]
            )
            if crops and index < analysis["crop_count"]:
                finding["evidence"] = [
                    evidence(
                        f"face-{index + 1}.png",
                        f"Detected face {index + 1} crop. Identity not inferred.",
                    )
                ]
            findings.append(finding)
        section = dict(
            name="Image face detection",
            module_type="image",
            module=dict(name=analysis["detector"], mode="local detection only"),
            findings=findings,
            links=[],
            notes=[
                "Analyzed: " + analysis["timestamp"],
                "Detections may be missed or incorrect. Review the whole image before sharing. No identities or personal attributes are inferred.",
                "Original image and other variants remain in local search history.",
            ],
        )
        app.append_search_to_case(
            case,
            app.make_search_record(
                "image", "Image analysis", [section], app.result_summary([section])
            ),
        )
    return jsonify(message="Image analysis and selected evidence added to " + case["name"] + ".")
