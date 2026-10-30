"""Non-destructive duplicate groups, case activity, and collection provenance."""

import copy
import hashlib
import json
import uuid
from urllib.parse import urlsplit, urlunsplit

from flask import Blueprint, abort, jsonify, request

bp = Blueprint("case_workflow", __name__)


def event(case, kind, description, **details):
    import app

    case.setdefault("events", []).append(
        dict(
            id=uuid.uuid4().hex,
            timestamp=app.utc_now(),
            kind=kind,
            description=description,
            **details,
        )
    )


def findings(case):
    for search in case.get("searches", []):
        for si, section in enumerate(search.get("results", [])):
            for fi, finding in enumerate(section.get("findings", [])):
                yield f"{search['id']}:{si}:{fi}", search, section, finding


def canonical(value):
    if isinstance(value, str):
        value = value.strip()
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and not any(c.isspace() for c in value)
            ):
                return urlunsplit(
                    (
                        parsed.scheme.lower(),
                        parsed.netloc.lower(),
                        parsed.path or "/",
                        parsed.query,
                        "",
                    )
                )
        except ValueError:
            pass
    return value


def fingerprint(search, finding):
    value = canonical(finding.get("value"))
    # Full URL values can have different tool labels. Other facts must have the same label.
    is_url = (
        isinstance(value, str)
        and value.startswith(("http://", "https://"))
        and not any(c.isspace() for c in value)
    )
    label = "" if is_url else str(finding.get("label", "")).strip().casefold()
    raw = json.dumps(
        [search.get("query", "").strip(), label, value], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def duplicate_groups(case):
    used = {ref for group in case.get("merge_groups", []) for ref in group["members"]}
    groups = {}
    for ref, search, section, finding in findings(case):
        if ref in used:
            continue
        key = fingerprint(search, finding)
        groups.setdefault(key, []).append(
            dict(
                ref=ref,
                value=finding.get("value"),
                label=finding.get("label", "Finding"),
                source=finding.get("source")
                or section.get("module", {}).get("name", "OSINT Menace"),
                query=search.get("query", ""),
                created_at=search.get("created_at", ""),
            )
        )
    return [dict(key=key, members=members) for key, members in groups.items() if len(members) > 1]


def timeline(case):
    events = list(case.get("events", []))
    seen = {e.get("search_id") for e in events if e["kind"] == "search_saved"}
    if not any(e["kind"] == "case_created" for e in events):
        events.append(
            dict(
                timestamp=case.get("created_at", ""),
                kind="case_created",
                description="Case created (existing record)",
            )
        )
    for search in case.get("searches", []):
        if search["id"] not in seen:
            events.append(
                dict(
                    timestamp=search.get("created_at", ""),
                    kind="search_saved",
                    description="Saved search: " + search.get("query", ""),
                    search_id=search["id"],
                )
            )
    return sorted(events, key=lambda e: e.get("timestamp", ""), reverse=True)


def report_case(case):
    """Render merged findings once; all originals remain intact in the JSON case."""
    result = copy.deepcopy(case)
    lookup = {ref: (search, section, finding) for ref, search, section, finding in findings(result)}
    for group in result.get("merge_groups", []):
        members = [lookup[ref] for ref in group["members"] if ref in lookup]
        if len(members) < 2:
            continue
        primary = members[0][2]
        primary["merged_sources"] = []
        evidence_ids = {e["id"] for e in primary.get("evidence", [])}
        for index, (search, section, finding) in enumerate(members):
            primary["merged_sources"].append(
                dict(
                    source=finding.get("source")
                    or section.get("module", {}).get("name", "OSINT Menace"),
                    collected_at=finding.get("collected_at") or search.get("created_at", ""),
                    source_url=finding.get("source_url", ""),
                    verification_status=finding.get("verification_status", "Unverified"),
                    analyst_notes=finding.get("analyst_notes", ""),
                )
            )
            if index:
                # Report selection on the representative controls the consolidated result.
                finding["include_in_report"] = False
                for evidence in finding.get("evidence", []):
                    if evidence["id"] not in evidence_ids:
                        primary.setdefault("evidence", []).append(copy.deepcopy(evidence))
                        evidence_ids.add(evidence["id"])
    return result


@bp.post("/cases/<case_id>/duplicates/merge")
def merge(case_id):
    import app

    with app.CASE_LOCK:
        case = app.load_case(case_id)
        candidate = next(
            (g for g in duplicate_groups(case) if g["key"] == request.form.get("key")), None
        )
        if candidate is None:
            return jsonify(
                error="This duplicate group changed. Refresh the case to review it."
            ), 409
        group = dict(
            id=uuid.uuid4().hex,
            members=[m["ref"] for m in candidate["members"]],
            created_at=app.utc_now(),
        )
        case.setdefault("merge_groups", []).append(group)
        event(
            case,
            "duplicates_merged",
            f"Merged {len(group['members'])} duplicate findings for reports; originals retained.",
            group_id=group["id"],
        )
        case["updated_at"] = app.utc_now()
        app.save_case(case)
    return jsonify(
        message="Duplicates merged. Originals and sources retained.",
        refresh_case=True,
        changed_refs=group["members"],
    )


@bp.post("/cases/<case_id>/duplicates/<group_id>/undo")
def undo(case_id, group_id):
    import app

    with app.CASE_LOCK:
        case = app.load_case(case_id)
        groups = case.get("merge_groups", [])
        group = next((g for g in groups if g["id"] == group_id), None)
        if group is None:
            abort(404)
        case["merge_groups"] = [g for g in groups if g["id"] != group_id]
        event(
            case,
            "merge_undone",
            "Duplicate merge undone; separate findings restored.",
            group_id=group_id,
        )
        case["updated_at"] = app.utc_now()
        app.save_case(case)
    return jsonify(message="Merge undone.", refresh_case=True, changed_refs=group["members"])


def validated_url(value):
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        if (
            len(value) > 2048
            or parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or any(ord(c) < 33 for c in value)
        ):
            raise ValueError()
    except ValueError:
        raise ValueError("Use an HTTP or HTTPS source URL without credentials or whitespace.")
    return value


def enrich(search):
    for _, _, section, finding in findings(dict(searches=[search])):
        finding.setdefault("collected_at", search["created_at"])
        if finding.get("source_url"):
            try:
                finding["source_url"] = validated_url(finding["source_url"])
            except (ValueError, AttributeError):
                finding.pop("source_url", None)
        finding.setdefault("collection_method", "Saved tool result")
        value = finding.get("value")
        if isinstance(value, dict):
            value = next(
                (
                    value.get(k)
                    for k in ("url", "profile_url", "link")
                    if isinstance(value.get(k), str)
                ),
                None,
            )
        if isinstance(value, str):
            try:
                finding.setdefault("source_url", validated_url(value))
            except ValueError:
                pass


def evidence_text(item):
    parts = ["Attached (UTC): " + item.get("created_at", "Not recorded")]
    for field, label in [
        ("source_url", "Source page"),
        ("captured_at", "Operator capture time (UTC)"),
        ("original_filename", "Uploaded filename"),
        ("original_sha256", "Uploaded file SHA-256"),
        ("sha256", "Stored PNG SHA-256"),
    ]:
        if item.get(field):
            parts.append(label + ": " + str(item[field]))
    if not item.get("sha256"):
        parts.append("File hash not recorded for this legacy attachment.")
    return "\n".join(parts)


@bp.get("/cases/<case_id>/provenance.json")
def manifest(case_id):
    import app

    with app.CASE_LOCK:
        case = app.load_case(case_id)
    return jsonify(
        case_id=case_id,
        generated_at=app.utc_now(),
        findings=[
            dict(
                reference=ref,
                label=finding.get("label"),
                source=finding.get("source")
                or section.get("module", {}).get("name", "OSINT Menace"),
                source_url=finding.get("source_url", ""),
                collected_at=finding.get("collected_at") or search.get("created_at"),
                collection_method=finding.get("collection_method", "Legacy case capture"),
                evidence=finding.get("evidence", []),
            )
            for ref, search, section, finding in findings(case)
        ],
    )


def merge_view(case):
    lookup = {ref: (search, section, finding) for ref, search, section, finding in findings(case)}
    groups = []
    references = {}
    for group in case.get("merge_groups", []):
        members = [lookup[ref] for ref in group["members"] if ref in lookup]
        if not members:
            continue
        groups.append(
            dict(
                group,
                representative=members[0][2],
                sources=[
                    f.get("source") or section.get("module", {}).get("name", "OSINT Menace")
                    for _, section, f in members
                ],
            )
        )
        for index, ref in enumerate(group["members"]):
            references[ref] = dict(id=group["id"], primary=index == 0)
    return groups, references
