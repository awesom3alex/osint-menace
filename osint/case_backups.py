"""Portable case ZIPs with verified previews and atomic, non-overwriting restore."""

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from flask import Blueprint, abort, redirect, render_template, request, send_file, url_for

import case_features
import case_workflow
from paths import DATA_ROOT

bp = Blueprint("case_backups", __name__)
STAGING = DATA_ROOT / "pending_backups"
IMPORT_LOCK = threading.Lock()
MAX_ZIP = 256_000_000
MAX_TOTAL = 512_000_000
MAX_FILE = 80_000_000
MAX_CASE = 16_000_000
TTL = 3600
MEMBER = re.compile(r"(?:case\.json|report\.md|evidence/[a-f0-9]{32}\.png)\Z")
HASH = re.compile(r"[a-f0-9]{64}\Z")


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are not allowed.")
        result[key] = value
    return result


def decode(data):
    return json.loads(
        data,
        object_pairs_hook=unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Invalid JSON number.")),
    )


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, limit=1000000):
    return isinstance(value, str) and len(value) <= limit


def validate_case(case):
    """Validate the shape consumed by case templates, reports, and merge/review helpers."""
    require(isinstance(case, dict), "Case data must be an object.")
    try:
        require(str(uuid.UUID(case["id"])) == case["id"], "Invalid case ID.")
    except (KeyError, ValueError, AttributeError, TypeError):
        raise ValueError("Invalid case ID.")
    for key in ("name", "created_at", "updated_at"):
        require(text(case.get(key), 2000), "Invalid case " + key + ".")
    require(text(case.get("notes", ""), 50000), "Invalid case notes.")
    if "investigation" in case:
        from investigation import validate as validate_investigation
        validate_investigation(case["investigation"])
    builder = case.get("report_builder")
    if builder is not None:
        require(isinstance(builder, dict), "Invalid report builder settings.")
        for key in ("order", "selected"):
            require(isinstance(builder.get(key), list) and len(builder[key]) <= 100000
                    and all(text(item, 5000) for item in builder[key]), "Invalid report content order.")
            require(len(builder[key]) == len(set(builder[key])), "Duplicate report content IDs.")
        require(set(builder["selected"]) <= set(builder["order"]), "Invalid report selection.")
        summary = builder.get("summary")
        require(isinstance(summary, dict) and all(text(summary.get(key), 20000)
                for key in ("purpose", "findings", "questions")), "Invalid executive summary.")
    from case_review import validate_review_data
    validate_review_data(case)
    from advanced_research import validate_advanced
    validate_advanced(case)
    from email_evidence import validate_email_records
    validate_email_records(case)
    from case_graphs import validate_graph

    graphs = case.get("graphs", [])
    require(isinstance(graphs, list) and len(graphs) <= 20, "Invalid case graphs.")
    graph_ids = set()
    for graph in graphs:
        validate_graph(graph)
        require(graph["id"] not in graph_ids, "Duplicate graph ID.")
        graph_ids.add(graph["id"])
    dossier = case.get("dossier", {})
    require(
        isinstance(dossier, dict) and all(text(value, 20000) for value in dossier.values()),
        "Invalid dossier fields.",
    )
    searches = case.get("searches")
    require(isinstance(searches, list) and len(searches) <= 5000, "Invalid search list.")
    refs = set()
    search_ids = set()
    evidence = {}
    count = 0
    for search in searches:
        require(isinstance(search, dict), "Invalid search record.")
        sid = search.get("id")
        require(
            text(sid, 100) and re.fullmatch(r"[a-f0-9-]{32,36}", sid) and sid not in search_ids,
            "Invalid or duplicate search ID.",
        )
        search_ids.add(sid)
        for key in ("query", "search_type", "created_at"):
            require(text(search.get(key)), "Invalid search " + key + ".")
        sections = search.get("results")
        require(isinstance(sections, list), "Invalid result sections.")
        for si, section in enumerate(sections):
            require(
                isinstance(section, dict) and text(section.get("name")), "Invalid result section."
            )
            module = section.get("module", {})
            require(
                isinstance(module, dict) and all(text(module.get(k, "")) for k in ("name", "mode")),
                "Invalid module metadata.",
            )
            for key in ("findings", "links", "notes"):
                require(isinstance(section.get(key, []), list), "Invalid section " + key + ".")
            require(all(text(note) for note in section.get("notes", [])), "Invalid section notes.")
            for link in section.get("links", []):
                require(
                    isinstance(link, dict) and text(link.get("label")) and text(link.get("value")),
                    "Invalid source link.",
                )
                case_workflow.validated_url(link["value"])
            for fi, finding in enumerate(section.get("findings", [])):
                count += 1
                require(count <= 50000, "Too many findings in this case.")
                require(
                    isinstance(finding, dict) and text(finding.get("label")), "Invalid finding."
                )
                refs.add(f"{sid}:{si}:{fi}")
                if 'research_source' in finding:
                    origin = finding['research_source']
                    require(isinstance(origin, dict) and set(origin) == {'record_id', 'entry_id'}
                            and all(isinstance(origin.get(key), str) and re.fullmatch(r'[a-f0-9]{32}', origin[key])
                                    for key in ('record_id', 'entry_id')), 'Invalid research provenance.')
                for key in (
                    "source",
                    "source_url",
                    "collected_at",
                    "collection_method",
                    "analyst_notes",
                    "reviewed_at",
                    "research_original_label",
                ):
                    require(
                        (key == "source" and finding.get(key) is None)
                        or text(finding.get(key, "")),
                        "Invalid finding " + key + ".",
                    )
                if 'finding_type' in finding:
                    from research_hub import FINDING_TYPES
                    require(finding['finding_type'] in FINDING_TYPES, 'Invalid finding type.')
                if 'tags' in finding:
                    tags=finding['tags']
                    require(isinstance(tags,list) and len(tags)<=20 and all(isinstance(tag,str) and 1<=len(tag)<=40 for tag in tags), 'Invalid finding tags.')
                if finding.get("source_url"):
                    case_workflow.validated_url(finding["source_url"])
                require(
                    finding.get("verification_status", "Unverified") in case_features.STATUSES,
                    "Invalid verification status.",
                )
                require(
                    isinstance(finding.get("include_in_report", True), bool),
                    "Invalid report selection.",
                )
                from case_research import validate_observations
                validate_observations(finding.get("observations", []))
                attached = finding.get("evidence", [])
                require(
                    isinstance(attached, list) and len(attached) <= 100, "Invalid evidence list."
                )
                for item in attached:
                    require(
                        isinstance(item, dict)
                        and text(item.get("id"), 32)
                        and re.fullmatch(r"[a-f0-9]{32}", item["id"]),
                        "Invalid evidence ID.",
                    )
                    for key in (
                        "caption",
                        "created_at",
                        "source_url",
                        "captured_at",
                        "original_filename",
                        "collection_method",
                    ):
                        require(text(item.get(key, "")), "Invalid evidence metadata.")
                    for key in ("sha256", "original_sha256"):
                        require(
                            not item.get(key)
                            or (text(item[key], 64) and HASH.fullmatch(item[key])),
                            "Invalid evidence hash.",
                        )
                    if item.get("source_url"):
                        case_workflow.validated_url(item["source_url"])
                    if item["id"] in evidence:
                        require(
                            evidence[item["id"]] == item, "Conflicting metadata for an evidence ID."
                        )
                    evidence[item["id"]] = item
        import app

        search["summary"] = app.result_summary(sections)
    groups = case.get("merge_groups", [])
    require(isinstance(groups, list), "Invalid duplicate groups.")
    used = set()
    group_ids = set()
    for group in groups:
        require(
            isinstance(group, dict)
            and text(group.get("id"))
            and group["id"] not in group_ids
            and text(group.get("created_at")),
            "Invalid duplicate group.",
        )
        members = group.get("members")
        require(
            isinstance(members, list)
            and len(members) >= 2
            and all(text(ref) and ref in refs and ref not in used for ref in members)
            and len(set(members)) == len(members),
            "Invalid merged finding references.",
        )
        used.update(members)
        group_ids.add(group["id"])
    events = case.get("events", [])
    require(isinstance(events, list) and len(events) <= 100000, "Invalid timeline.")
    for event in events:
        require(
            isinstance(event, dict)
            and all(text(event.get(k)) for k in ("kind", "timestamp", "description")),
            "Invalid timeline event.",
        )
    return evidence, count


def checked_zip(path):
    """Never extract arbitrary archive paths. Bound every read before decompression."""
    require(Path(path).stat().st_size <= MAX_ZIP, "Backup ZIP exceeds 256 MB.")
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [info.filename for info in entries]
        require(
            len(entries) <= 2003 and len(set(names)) == len(names),
            "Too many or duplicate ZIP members.",
        )
        require(
            "manifest.json" in names and "case.json" in names,
            "Missing backup manifest or case data.",
        )
        total = 0
        files = {}
        for info in entries:
            require(
                info.filename == "manifest.json" or MEMBER.fullmatch(info.filename),
                "Unexpected or unsafe ZIP path.",
            )
            mode = stat.S_IFMT(info.external_attr >> 16)
            require(
                mode in (0, stat.S_IFREG)
                and not info.flag_bits & 1
                and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                "Unsupported ZIP member type or encryption.",
            )
            cap = MAX_CASE if info.filename.endswith(".json") else MAX_FILE
            total += info.file_size
            require(
                info.file_size <= cap and total <= MAX_TOTAL,
                "Backup expands beyond the supported size limit.",
            )
            with archive.open(info) as stream:
                data = stream.read(cap + 1)
            require(len(data) == info.file_size and len(data) <= cap, "Invalid ZIP member size.")
            files[info.filename] = data
    manifest = decode(files.pop("manifest.json"))
    require(
        isinstance(manifest, dict)
        and manifest.get("format") == "osint-menace-case"
        and manifest.get("version") == 1,
        "Unsupported backup format or version.",
    )
    indexed = manifest.get("files")
    require(
        isinstance(indexed, dict) and set(indexed) == set(files),
        "Backup manifest does not match the files.",
    )
    for name, data in files.items():
        entry = indexed[name]
        require(
            isinstance(entry, dict)
            and entry.get("size") == len(data)
            and entry.get("sha256") == digest(data),
            "Backup hash mismatch: " + name,
        )
    case = decode(files["case.json"])
    evidence, count = validate_case(case)
    require(manifest.get("case_id") == case["id"], "Manifest case ID does not match.")
    require(
        {name for name in files if name.startswith("evidence/")}
        == {f"evidence/{key}.png" for key in evidence},
        "Missing or unreferenced evidence files.",
    )
    legacy = 0
    from PIL import Image

    for key, item in evidence.items():
        data = files[f"evidence/{key}.png"]
        if item.get("sha256"):
            require(item["sha256"] == digest(data), "Recorded evidence hash mismatch: " + key)
        else:
            legacy += 1
        # Decode locally to confirm attachments can be safely used in reports.
        try:
            with Image.open(BytesIO(data)) as image:
                require(
                    image.format == "PNG" and image.width * image.height <= 20_000_000,
                    "Invalid evidence PNG.",
                )
                image.verify()
        except (OSError, SyntaxError, Image.DecompressionBombError):
            raise ValueError("An evidence PNG could not be verified.")
    return (
        case,
        files,
        dict(
            searches=len(case["searches"]),
            findings=count,
            evidence=len(evidence),
            legacy=legacy,
            bytes=total,
        ),
    )


def archive_case(case):
    """Export all referenced evidence, including findings excluded from reports."""
    evidence, _ = validate_case(case)
    files = {"case.json": encode(case)}
    import app

    files["report.md"] = app.render_markdown_report(case).encode("utf-8")
    for key, item in evidence.items():
        path = case_features.EVIDENCE_DIR / case["id"] / (key + ".png")
        require(
            path.is_file(),
            "Evidence file is missing: " + key + ". Restore it before backing up this case.",
        )
        require(path.stat().st_size <= MAX_FILE, "An evidence file exceeds the backup size limit.")
        data = path.read_bytes()
        require(
            not item.get("sha256") or item["sha256"] == digest(data),
            "Evidence integrity check failed: " + key,
        )
        files[f"evidence/{key}.png"] = data
    require(
        len(files) <= 2002
        and len(files["case.json"]) <= MAX_CASE
        and sum(map(len, files.values())) <= MAX_TOTAL,
        "Case exceeds supported backup limits.",
    )
    manifest = dict(
        format="osint-menace-case",
        version=1,
        application_version=app.APP_VERSION,
        case_id=case["id"],
        created_at=app.utc_now(),
        files={name: dict(size=len(data), sha256=digest(data)) for name, data in files.items()},
    )
    output = tempfile.SpooledTemporaryFile(max_size=8_000_000)
    try:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", encode(manifest))
            for name, data in files.items():
                archive.writestr(name, data)
        require(output.tell() <= MAX_ZIP, "Compressed backup exceeds 256 MB.")
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise


def cleanup_staging():
    STAGING.mkdir(parents=True, exist_ok=True)
    for path in STAGING.glob("*.zip"):
        if (
            re.fullmatch(r"[a-f0-9]{32}\.zip", path.name)
            and time.time() - path.stat().st_mtime > TTL
        ):
            path.unlink()


@bp.before_app_request
def upload_limit():
    if request.endpoint == "case_backups.preview":
        request.max_content_length = MAX_ZIP + 1_000_000


@bp.get("/cases/<case_id>/backup.zip")
def download(case_id):
    import app

    try:
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            output = archive_case(case)
    except (ValueError, OSError) as exc:
        return render_template("backup_import.html", error=str(exc)), 409
    name = re.sub(r"[^A-Za-z0-9_.-]+", "-", case["name"]).strip("-")[:100] or "case"
    response = send_file(
        output, mimetype="application/zip", as_attachment=True, download_name=name + "-backup.zip"
    )
    response.headers["Cache-Control"] = "no-store"
    response.call_on_close(output.close)
    return response


@bp.get("/cases/import")
def page():
    return render_template("backup_import.html")


@bp.post("/cases/import/preview")
def preview():
    token = uuid.uuid4().hex
    path = STAGING / (token + ".zip")
    try:
        with IMPORT_LOCK:
            cleanup_staging()
            require(
                len(list(STAGING.glob("*.zip"))) < 4,
                "Four previews are pending. Finish an import or wait for previews to expire after one hour.",
            )
            file = request.files.get("backup")
            require(file is not None, "Choose a Menace case backup ZIP.")
            with path.open("xb") as target:
                size = 0
                while chunk := file.stream.read(1024 * 1024):
                    size += len(chunk)
                    require(size <= MAX_ZIP, "Backup ZIP exceeds 256 MB.")
                    target.write(chunk)
            case, _, counts = checked_zip(path)
            with path.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
        return render_template(
            "backup_import.html", preview=case, counts=counts, token=token, sha=sha
        )
    except (
        ValueError,
        OSError,
        zipfile.BadZipFile,
        RuntimeError,
        RecursionError,
        KeyError,
        TypeError,
    ) as exc:
        path.unlink(missing_ok=True)
        return render_template(
            "backup_import.html", error="Backup could not be verified: " + str(exc)
        ), 400


@bp.post("/cases/import/restore")
def restore():
    import app

    token = request.form.get("token", "")
    if not re.fullmatch(r"[a-f0-9]{32}", token):
        abort(404)
    path = STAGING / (token + ".zip")
    try:
        with IMPORT_LOCK:
            require(
                path.is_file() and time.time() - path.stat().st_mtime <= TTL,
                "This preview expired or was already imported. Upload the ZIP again.",
            )
            with path.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
            require(
                sha == request.form.get("sha256"), "The previewed backup changed. Upload it again."
            )
            case, files, _ = checked_zip(path)
            old_id = case["id"]
            name = request.form.get("case_name", "").strip()
            require(0 < len(name) <= 500, "Enter a restored case name of up to 500 characters.")
            with app.CASE_LOCK:
                new_id = str(uuid.uuid4())
                while (
                    app.case_path(new_id).exists() or (case_features.EVIDENCE_DIR / new_id).exists()
                ):
                    new_id = str(uuid.uuid4())
                case.update(
                    id=new_id,
                    name=name,
                    updated_at=app.utc_now(),
                    restored_from=dict(
                        case_id=old_id, backup_sha256=sha, restored_at=app.utc_now()
                    ),
                )
                case_workflow.event(
                    case,
                    "case_restored",
                    "Restored from a verified backup as a new case.",
                    original_case_id=old_id,
                    backup_sha256=sha,
                )
                case_features.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
                destination = case_features.EVIDENCE_DIR / new_id
                try:
                    with tempfile.TemporaryDirectory(
                        dir=case_features.EVIDENCE_DIR, prefix=".restore-"
                    ) as folder:
                        for member, data in files.items():
                            if member.startswith("evidence/"):
                                (Path(folder) / member.split("/")[1]).write_bytes(data)
                        os.rename(folder, destination)
                    app.save_case(case)
                except Exception:
                    shutil.rmtree(destination, ignore_errors=True)
                    raise
            path.unlink()
        return redirect(url_for("case_detail", case_id=new_id))
    except (
        ValueError,
        OSError,
        zipfile.BadZipFile,
        RuntimeError,
        RecursionError,
        KeyError,
        TypeError,
    ) as exc:
        return render_template(
            "backup_import.html", error="Restore did not complete: " + str(exc)
        ), 400


@bp.after_app_request
def prevent_backup_cache(response):
    if request.endpoint and request.endpoint.startswith("case_backups."):
        response.headers["Cache-Control"] = "no-store"
    return response
