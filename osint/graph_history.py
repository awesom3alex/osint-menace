"""Validated graph views and bounded, case-local milestone snapshots."""

import copy
import datetime as dt
import math
import re
import uuid

from flask import abort, jsonify, request


def check(value, message):
    if not value:
        raise ValueError(message)


def point(value):
    return isinstance(value, dict) and all(
        type(value.get(k)) in (int, float) and math.isfinite(value[k]) and abs(value[k]) < 1e7
        for k in ("x", "y")
    )


def validate_filters(filters):
    check(isinstance(filters, dict), "Invalid view filters.")
    for key, limit in [("query", 2000), ("type", 100), ("status", 20)]:
        check(
            isinstance(filters.get(key, ""), str) and len(filters.get(key, "")) <= limit,
            "Invalid view filter.",
        )
    check(
        filters.get("status", "") in ("", "hypothesis", "supported"), "Invalid relationship filter."
    )
    for key in ("from", "to"):
        value = filters.get(key, "")
        check(isinstance(value, str) and (not value or len(value) == 10), "Invalid timeline date.")
        if value:
            dt.date.fromisoformat(value)
    check(
        not filters.get("from") or not filters.get("to") or filters["from"] <= filters["to"],
        "Start date must be before the end date.",
    )
    check(isinstance(filters.get("includeUndated", True), bool), "Invalid undated filter.")


def validate_extras(graph):
    from case_graphs import validate_graph

    views = graph.get("views", [])
    check(isinstance(views, list) and len(views) <= 30, "Maximum 30 saved views.")
    ids = set()
    for view in views:
        check(
            isinstance(view, dict)
            and isinstance(view.get("id"), str)
            and re.fullmatch(r"[a-f0-9]{32}", view["id"])
            and view["id"] not in ids,
            "Invalid or duplicate view ID.",
        )
        ids.add(view["id"])
        check(
            isinstance(view.get("name"), str) and 0 < len(view["name"].strip()) <= 100,
            "Enter a view name of up to 100 characters.",
        )
        validate_filters(view.get("filters"))
        check(
            type(view.get("zoom")) in (int, float)
            and math.isfinite(view["zoom"])
            and 0.1 <= view["zoom"] <= 3
            and point(view.get("pan")),
            "Invalid saved viewport.",
        )
        positions = view.get("positions", {})
        check(
            isinstance(positions, dict)
            and len(positions) <= 1000
            and all(
                re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", k) and point(v) for k, v in positions.items()
            ),
            "Invalid saved positions.",
        )
        collapsed = view.get("collapsed", [])
        check(
            isinstance(collapsed, list)
            and len(collapsed) <= 1000
            and all(
                isinstance(n, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", n) for n in collapsed
            ),
            "Invalid saved branches.",
        )
        groups = view.get("groupStates", {})
        check(
            isinstance(groups, dict)
            and len(groups) <= 100
            and all(
                re.fullmatch(r"group_[a-f0-9]{32}", k) and isinstance(v, bool)
                for k, v in groups.items()
            ),
            "Invalid saved groups.",
        )
    report = graph.get("report", {})
    check(
        isinstance(report, dict)
        and isinstance(report.get("include", False), bool)
        and isinstance(report.get("viewId", ""), str)
        and report.get("viewId", "") in ids | {""},
        "Invalid report view selection.",
    )
    snapshots = graph.get("snapshots", [])
    check(isinstance(snapshots, list) and len(snapshots) <= 10, "Maximum 10 snapshots per graph.")
    seen = set()
    for snapshot in snapshots:
        check(
            isinstance(snapshot, dict)
            and isinstance(snapshot.get("id"), str)
            and re.fullmatch(r"[a-f0-9]{32}", snapshot["id"])
            and snapshot["id"] not in seen,
            "Invalid snapshot ID.",
        )
        seen.add(snapshot["id"])
        check(
            isinstance(snapshot.get("name"), str) and 0 < len(snapshot["name"].strip()) <= 150,
            "Invalid snapshot name.",
        )
        check(
            isinstance(snapshot.get("created_at"), str) and len(snapshot["created_at"]) <= 100,
            "Invalid snapshot time.",
        )
        dt.datetime.fromisoformat(snapshot["created_at"])
        data = snapshot.get("data")
        check(
            isinstance(data, dict) and not any(k in data for k in ("snapshots", "id", "revision")),
            "Nested snapshot data is not supported.",
        )
        validate_graph(dict(data, id=graph["id"], revision=0))


def milestone(graph, name):
    import app

    return dict(
        id=uuid.uuid4().hex,
        name=name,
        created_at=app.utc_now(),
        data={
            k: copy.deepcopy(v)
            for k, v in graph.items()
            if k not in ("snapshots", "id", "revision")
        },
    )


def register(bp):
    @bp.route("/cases/<case_id>/graphs/<graph_id>/snapshots", methods=["POST"])
    @bp.route("/cases/<case_id>/graphs/<graph_id>/snapshots/<snapshot_id>", methods=["DELETE"])
    @bp.route(
        "/cases/<case_id>/graphs/<graph_id>/snapshots/<snapshot_id>/restore", methods=["POST"]
    )
    def snapshots(case_id, graph_id, snapshot_id=None):
        import app
        from case_graphs import save_graph_case, validate_graph

        payload = request.get_json() or {}
        if not isinstance(payload, dict):
            return jsonify(error="Invalid snapshot request."), 400
        with app.CASE_LOCK:
            case = app.load_case(case_id)
            graph = next((g for g in case.get("graphs", []) if g["id"] == graph_id), None)
            if graph is None:
                abort(404)
            if payload.get("revision") != graph["revision"]:
                return jsonify(error="The graph changed. Reload before managing snapshots."), 409
            saved = graph.setdefault("snapshots", [])
            chosen = next((s for s in saved if s["id"] == snapshot_id), None)
            if snapshot_id and chosen is None:
                abort(404)
            try:
                if request.method == "DELETE":
                    saved.remove(chosen)
                elif snapshot_id:
                    check(
                        len(saved) < 10,
                        "Remove a snapshot to leave room for the automatic pre-restore milestone.",
                    )
                    before = milestone(graph, ("Before restoring " + chosen["name"])[:150])
                    restored = copy.deepcopy(chosen["data"])
                    graph = dict(
                        restored,
                        id=graph_id,
                        revision=graph["revision"],
                        snapshots=saved + [before],
                    )
                    index = next(i for i, g in enumerate(case["graphs"]) if g["id"] == graph_id)
                    case["graphs"][index] = graph
                else:
                    name = payload.get("name", "")
                    check(
                        isinstance(name, str) and 0 < len(name.strip()) <= 150,
                        "Enter a snapshot name.",
                    )
                    check(
                        len(saved) < 10,
                        "Maximum 10 snapshots per graph. Remove one to create another.",
                    )
                    saved.append(milestone(graph, name.strip()))
                graph["revision"] += 1
                validate_graph(graph)
                save_graph_case(case)
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
        return jsonify(graph=graph)
