"""Case-local, editable investigation graphs. No external graph service required."""

import base64
import binascii
import datetime as dt
import json
import math
import re
import uuid
from io import BytesIO

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from PIL import Image

from case_features import locate

bp = Blueprint("case_graphs", __name__)
TEMPLATES = {
    "Person": ["Name", "Aliases", "Email", "Phone", "Notes"],
    "Account": ["Username", "Platform", "Profile URL", "Notes"],
    "Organization": ["Name", "Website", "Address", "Notes"],
    "Domain/IP": ["Domain or IP", "Organization", "Notes"],
    "Evidence": ["Title", "Source", "Date collected", "Notes"],
}
COLORS = ["#64b5f6", "#ba9cff", "#75d6a0", "#ffcd70", "#ff91a4"]
FIELD_TYPES = ("text", "textarea", "number", "date", "select", "checkbox", "url")


def new_graph(name):
    return dict(
        id=uuid.uuid4().hex,
        name=name,
        revision=0,
        nodes=[],
        edges=[],
        legend=[dict(type=t, color=COLORS[i], description=t) for i, t in enumerate(TEMPLATES)],
        templates={
            t: [
                dict(
                    name=n,
                    type=(
                        "textarea"
                        if n == "Notes"
                        else "date"
                        if n == "Date collected"
                        else "url"
                        if n in ("Website", "Profile URL")
                        else "text"
                    ),
                    value="",
                    options="",
                    visible=False,
                )
                for n in names
            ]
            for t, names in TEMPLATES.items()
        },
    )


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, limit=2000):
    return isinstance(value, str) and len(value) <= limit


def fields_valid(fields):
    require(isinstance(fields, list) and len(fields) <= 80, "Maximum 80 fields per object.")
    names = set()
    for f in fields:
        require(isinstance(f, dict), "Invalid field.")
        name = f.get("name")
        require(
            text(name, 100) and name.strip() and name.casefold() not in names,
            "Field names must be nonempty and unique.",
        )
        names.add(name.casefold())
        require(
            f.get("type") in FIELD_TYPES
            and text(f.get("value"), 20000)
            and text(f.get("options", ""), 2000)
            and isinstance(f.get("visible", False), bool),
            "Invalid field type or value.",
        )
        value = f["value"]
        if f["type"] == "number" and value:
            try:
                require(math.isfinite(float(value)), "Use a finite number.")
            except (ValueError, OverflowError):
                raise ValueError("Use a valid number.") from None
        if f["type"] == "checkbox":
            require(value in ("", "true", "false"), "Invalid checkbox value.")
        if f["type"] == "select" and value:
            require(value in f.get("options", "").split("|"), "Choose a listed dropdown value.")
        if f["type"] == "date" and value:
            try:
                dt.date.fromisoformat(value)
            except ValueError:
                raise ValueError("Use a valid date.") from None


def validate_graph(g):
    try:
        _validate_graph(g)
    except (TypeError, KeyError, AttributeError, OverflowError):
        raise ValueError("Invalid graph data.") from None


def _validate_graph(g):
    require(isinstance(g, dict), "Invalid graph.")
    require(text(g.get("id"), 40) and re.fullmatch(r"[a-f0-9]{32}", g["id"]), "Invalid graph ID.")
    require(text(g.get("name"), 200) and g["name"].strip(), "Enter a graph name.")
    require(type(g.get("revision")) is int and g["revision"] >= 0, "Invalid revision.")
    legend = g.get("legend")
    require(isinstance(legend, list) and 1 <= len(legend) <= 40, "Use 1–40 object types.")
    types = set()
    for item in legend:
        require(
            isinstance(item, dict)
            and text(item.get("type"), 100)
            and item["type"].strip()
            and item["type"] not in ("__proto__", "constructor", "prototype")
            and item["type"] not in types
            and text(item.get("description"), 1000)
            and isinstance(item.get("color"), str)
            and re.fullmatch(r"#[0-9a-fA-F]{6}", item["color"]),
            "Invalid legend entry.",
        )
        types.add(item["type"])
    templates = g.get("templates")
    require(isinstance(templates, dict) and set(templates) <= types, "Invalid field templates.")
    for fields in templates.values():
        fields_valid(fields)
    nodes, edges = g.get("nodes"), g.get("edges")
    require(
        isinstance(nodes, list)
        and len(nodes) <= 1000
        and isinstance(edges, list)
        and len(edges) <= 3000,
        "Maximum 1,000 objects and 3,000 connections per graph.",
    )
    ids = set()
    groups = g.get("groups", [])
    require(isinstance(groups, list) and len(groups) <= 100, "Maximum 100 groups.")
    group_ids = set()
    for group in groups:
        require(
            isinstance(group, dict)
            and text(group.get("id"), 100)
            and re.fullmatch(r"group_[a-f0-9]{32}", group["id"])
            and group["id"] not in group_ids
            and text(group.get("label"), 200)
            and isinstance(group.get("collapsed", False), bool),
            "Invalid graph group.",
        )
        group_ids.add(group["id"])
    for node in nodes:
        require(isinstance(node, dict), "Invalid object.")
        nid = node.get("id")
        require(
            text(nid, 100) and re.fullmatch(r"[a-zA-Z0-9_-]+", nid) and nid not in ids,
            "Invalid or duplicate object ID.",
        )
        ids.add(nid)
        require(
            nid not in group_ids and node.get("group", "") in group_ids | {""},
            "Invalid object group.",
        )
        require(
            isinstance(node.get("tags", []), list)
            and len(node.get("tags", [])) <= 40
            and all(text(tag, 100) for tag in node.get("tags", [])),
            "Invalid object tags.",
        )
        require(isinstance(node.get("annotation", False), bool), "Invalid annotation.")
        validate_refs(node.get("sourceRefs", []))
        require(
            text(node.get("label"), 500) and node.get("type") in types,
            "Invalid object label or type.",
        )
        require(
            isinstance(node.get("position"), dict)
            and all(
                type(node["position"].get(k)) in (int, float)
                and math.isfinite(node["position"][k])
                and abs(node["position"][k]) < 1e7
                for k in ("x", "y")
            ),
            "Invalid object position.",
        )
        require(
            isinstance(node.get("pinned", False), bool) and text(node.get("source", "")),
            "Invalid object metadata.",
        )
        fields_valid(node.get("fields"))
        photo = node.get("photo", "")
        require(text(photo, 2_000_000), "Photo is too large. Use a smaller image.")
        if photo:
            require(
                photo.startswith("data:image/png;base64,"), "Photos must be embedded PNG images."
            )
            try:
                image = Image.open(BytesIO(base64.b64decode(photo.split(",", 1)[1], validate=True)))
                require(
                    image.format == "PNG" and image.width * image.height <= 4_000_000,
                    "Photo exceeds 4 megapixels.",
                )
                image.verify()
            except (OSError, ValueError, binascii.Error, Image.DecompressionBombError):
                raise ValueError("Invalid photo.") from None
    all_ids = set(ids)
    collapsed = g.get("collapsed", [])
    require(
        isinstance(collapsed, list)
        and len(collapsed) <= 1000
        and all(isinstance(n, str) and n in ids for n in collapsed),
        "Invalid collapsed branches.",
    )
    for edge in edges:
        require(isinstance(edge, dict), "Invalid connection.")
        eid = edge.get("id")
        require(
            text(eid, 100) and re.fullmatch(r"[a-zA-Z0-9_-]+", eid) and eid not in all_ids,
            "Invalid connection ID.",
        )
        all_ids.add(eid)
        require(eid not in group_ids, "Connection ID conflicts with a group.")
        validate_refs(edge.get("evidenceRefs", []))
        date = edge.get("date", "")
        require(text(date, 10), "Invalid relationship date.")
        if date:
            dt.date.fromisoformat(date)
        require(
            edge.get("source") in ids
            and edge.get("target") in ids
            and text(edge.get("label"), 500)
            and text(edge.get("notes", ""), 20000)
            and edge.get("status", "hypothesis") in ("hypothesis", "supported"),
            "Invalid connection endpoints or details.",
        )
    from graph_history import validate_extras

    validate_extras(g)
    require(len(json.dumps(g).encode()) <= 8_000_000, "Graph exceeds 8 MB. Reduce photo sizes.")


def validate_refs(refs):
    require(
        isinstance(refs, list)
        and len(refs) <= 100
        and all(
            isinstance(ref, str) and re.fullmatch(r"[a-f0-9-]{32,36}:\d{1,5}:\d{1,5}", ref)
            for ref in refs
        ),
        "Invalid evidence references.",
    )


def finding_choices(case):
    return [
        dict(ref=f"{s['id']}:{si}:{fi}", label=str(f.get("label", "Finding"))[:500])
        for s in case.get("searches", [])
        for si, section in enumerate(s.get("results", []))
        for fi, f in enumerate(section.get("findings", []))
    ]


@bp.get("/cases/<case_id>/graphs/evidence")
def preview_evidence(case_id):
    import app

    ref = request.args.get("ref", "")
    try:
        validate_refs([ref])
    except ValueError:
        abort(400)
    sid, si, fi = ref.split(":")
    case = app.load_case(case_id)
    finding = locate(case, sid, int(si), int(fi))
    return (
        jsonify(
            label=finding.get("label", "Finding"),
            value=finding.get("value"),
            source=finding.get("source", ""),
            notes=finding.get("analyst_notes", ""),
            status=finding.get("verification_status", "Unverified"),
            evidence=[
                dict(
                    id=e["id"],
                    caption=e.get("caption", ""),
                    url=url_for("case_features.evidence", case_id=case_id, evidence_id=e["id"]),
                )
                for e in finding.get("evidence", [])
            ],
        ),
        200,
        {"Cache-Control": "no-store"},
    )


@bp.get("/cases/<case_id>/graphs")
def workspace(case_id):
    import app

    case = app.load_case(case_id)
    return render_template("graphs.html", case=case, finding_choices=finding_choices(case))


def save_graph_case(case):
    """Keep graphs within the existing case-backup JSON size limit."""
    import app
    from case_backups import MAX_CASE, encode

    builder = case.get("report_builder")
    if builder is not None:
        selected = [key for key in builder["selected"] if not key.startswith("graph:")]
        for graph in case.get("graphs", []):
            key = "graph:" + graph["id"]
            if key not in builder["order"]:
                builder["order"].append(key)
            if graph.get("report", {}).get("include"):
                selected.append(key)
        builder["selected"] = selected
    require(
        len(encode(case)) <= MAX_CASE, "Case exceeds the backup size limit. Reduce graph photos."
    )
    case["updated_at"] = app.utc_now()
    app.save_case(case)


@bp.post("/cases/<case_id>/graphs")
def create(case_id):
    import app

    name = request.form.get("name", "Investigation graph").strip()[:200]
    if not name:
        abort(400, "Enter a graph name.")
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        graphs = case.setdefault("graphs", [])
        if len(graphs) >= 20:
            abort(400, "Maximum 20 graphs per case.")
        graph = new_graph(name)
        graphs.append(graph)
        try:
            save_graph_case(case)
        except ValueError as exc:
            abort(400, str(exc))
    return redirect(url_for("case_graphs.workspace", case_id=case_id, graph=graph["id"]))


@bp.put("/cases/<case_id>/graphs/<graph_id>")
def save(case_id, graph_id):
    import app

    graph = request.get_json()
    try:
        validate_graph(graph)
    except (ValueError, TypeError, KeyError) as exc:
        return jsonify(error=str(exc)), 400
    if graph["id"] != graph_id:
        abort(400)
    with app.CASE_LOCK:
        case = app.load_case(case_id)
        old = next((g for g in case.get("graphs", []) if g["id"] == graph_id), None)
        if old is None:
            abort(404)
        if old["revision"] != graph["revision"]:
            return jsonify(
                error="This graph changed in another tab. Export your JSON before reloading."
            ), 409
        if graph.get("snapshots", []) != old.get("snapshots", []):
            return jsonify(error="Use snapshot controls to manage saved milestones."), 400
        graph["revision"] += 1
        case["graphs"][case["graphs"].index(old)] = graph
        try:
            save_graph_case(case)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
    return jsonify(revision=graph["revision"])


@bp.post("/cases/<case_id>/graphs/add/<search_id>/<int:si>/<int:fi>")
def add_finding(case_id, search_id, si, fi):
    import app

    with app.CASE_LOCK:
        case = app.load_case(case_id)
        finding = locate(case, search_id, si, fi)
        graphs = case.setdefault("graphs", [])
        gid = request.form.get("graph_id", "")
        graph = next((g for g in graphs if g["id"] == gid), None)
        if graph is None:
            if gid:
                abort(404)
            if len(graphs) >= 20:
                abort(400)
            graph = new_graph("Investigation graph")
            graphs.append(graph)
        source = f"{search_id}:{si}:{fi}"
        if not any(
            n.get("source") == source or source in n.get("sourceRefs", []) for n in graph["nodes"]
        ):
            fields = [dict(f) for f in graph["templates"].get("Evidence", [])]
            original_name = "Original finding"
            suffix = 2
            while any(f["name"].casefold() == original_name.casefold() for f in fields):
                original_name = f"Original finding {suffix}"
                suffix += 1
            fields.append(
                dict(
                    name=original_name,
                    type="textarea",
                    value=json.dumps(finding.get("value"), ensure_ascii=False)[:20000],
                    options="",
                    visible=False,
                )
            )
            graph["nodes"].append(
                dict(
                    id=uuid.uuid4().hex,
                    label=str(finding.get("label", "Finding"))[:500],
                    type="Evidence",
                    position=dict(x=100 + len(graph["nodes"]) * 20, y=100),
                    pinned=False,
                    source=source,
                    photo="",
                    fields=fields,
                )
            )
            try:
                validate_graph(graph)
            except ValueError as exc:
                abort(400, str(exc))
            graph["revision"] += 1
            try:
                save_graph_case(case)
            except ValueError as exc:
                abort(400, str(exc))
    return redirect(url_for("case_graphs.workspace", case_id=case_id, graph=graph["id"]))


from graph_history import register

register(bp)
