"""Local graph figures and evidence summaries shared by PDF and Word exports."""

import base64
import copy
import math
import re
import textwrap
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont


def sections(case):
    lookup = {
        f"{s['id']}:{si}:{fi}": f
        for s in case.get("searches", [])
        for si, section in enumerate(s.get("results", []))
        for fi, f in enumerate(section.get("findings", []))
    }
    excluded = {ref for ref, f in lookup.items() if not f.get("include_in_report", True)}
    for group in case.get("merge_groups", []):
        members = [ref for ref in group["members"] if ref in lookup]
        if members and members[0] in excluded:
            excluded.update(members)
    output = []
    for original in case.get("graphs", []):
        settings = original.get("report", {})
        if not settings.get("include"):
            continue
        graph = copy.deepcopy(original)
        view = next((v for v in graph.get("views", []) if v["id"] == settings.get("viewId")), None)
        filters = view["filters"] if view else {}
        if not view:
            graph["collapsed"] = []
            for group in graph.get("groups", []):
                group["collapsed"] = False
        if view:
            graph["collapsed"] = view.get("collapsed", [])
            for group in graph.get("groups", []):
                group["collapsed"] = view.get("groupStates", {}).get(group["id"], False)
            for node in graph["nodes"]:
                node["position"] = view.get("positions", {}).get(node["id"], node["position"])
        hidden = set()
        for group in graph.get("groups", []):
            if group.get("collapsed"):
                hidden.update(n["id"] for n in graph["nodes"] if n.get("group") == group["id"])
        roots = set(graph.get("collapsed", []))
        for root in roots:
            seen, queue = {root}, [root]
            while queue:
                current = queue.pop()
                for edge in graph["edges"]:
                    if edge["source"] == current and edge["target"] not in seen:
                        seen.add(edge["target"])
                        queue.append(edge["target"])
                        if edge["target"] not in roots:
                            hidden.add(edge["target"])
        query = filters.get("query", "").strip().lower().lstrip("@").rstrip("/")
        nodes = []
        for node in graph["nodes"]:
            refs = set([node.get("source", "")] + node.get("sourceRefs", []))
            searchable = " ".join(
                [
                    node["label"],
                    node["type"],
                    *node.get("tags", []),
                    *[str(f[k]) for f in node["fields"] for k in ("name", "value")],
                ]
            ).lower()
            if node["id"] in hidden or refs & excluded:
                continue
            if filters.get("type") and node["type"] != filters["type"]:
                continue
            if query and query not in searchable:
                continue
            nodes.append(node)
        ids = {n["id"] for n in nodes}
        edges = []
        for edge in graph["edges"]:
            if (
                edge["source"] not in ids
                or edge["target"] not in ids
                or set(edge.get("evidenceRefs", [])) & excluded
            ):
                continue
            if filters.get("status") and edge.get("status") != filters["status"]:
                continue
            dated = bool(filters.get("from") or filters.get("to"))
            date = edge.get("date", "")
            if dated and (
                (not date and not filters.get("includeUndated", True))
                or (
                    date
                    and (
                        (filters.get("from") and date < filters["from"])
                        or (filters.get("to") and date > filters["to"])
                    )
                )
            ):
                continue
            edges.append(edge)
        if filters.get("status") or filters.get("from") or filters.get("to"):
            linked = {e[k] for e in edges for k in ("source", "target")}
            nodes = [n for n in nodes if n["id"] in linked]
        refs = set()
        for node in nodes:
            refs.update([node.get("source", ""), *node.get("sourceRefs", [])])
        for edge in edges:
            refs.update(edge.get("evidenceRefs", []))
        refs.discard("")
        evidence = []
        for ref in sorted(refs):
            finding = lookup.get(ref)
            if finding is None:
                evidence.append(
                    dict(
                        ref=ref,
                        label="Finding unavailable",
                        value="",
                        source="",
                        status="Unavailable",
                        notes="",
                    )
                )
            elif finding.get("include_in_report", True):
                from readable_results import readable_text

                evidence.append(
                    dict(
                        ref=ref,
                        label=finding.get("label", "Finding"),
                        value=readable_text(finding.get("value", "")),
                        source=finding.get("source") or "",
                        status=finding.get("verification_status", "Unverified"),
                        notes=finding.get("analyst_notes", ""),
                        attachments=finding.get("evidence", []),
                    )
                )
        graph.update(nodes=nodes, edges=edges)
        output.append(
            dict(
                graph=graph,
                view=view["name"] if view else "Full graph",
                filters=filters,
                evidence=evidence,
                image=render(graph),
            )
        )
    return output


def render(graph):
    """Draw the saved arrangement without network access or a browser dependency."""
    import reportlab

    root = Path(reportlab.__file__).parent / "fonts"
    regular = str(root / "Vera.ttf")
    font = ImageFont.truetype(regular, 30)
    small = ImageFont.truetype(regular, 24)
    image = Image.new("RGB", (1800, 1100), "white")
    draw = ImageDraw.Draw(image)
    nodes = graph["nodes"]
    if not nodes:
        draw.text((80, 80), "No objects match this report view.", fill="#334155", font=font)
    else:
        xs, ys = [n["position"]["x"] for n in nodes], [n["position"]["y"] for n in nodes]
        scale = min(1400 / max(max(xs) - min(xs), 200), 650 / max(max(ys) - min(ys), 200))
        points = {
            n["id"]: (
                200 + (n["position"]["x"] - min(xs)) * scale,
                130 + (n["position"]["y"] - min(ys)) * scale,
            )
            for n in nodes
        }
        for group in graph.get("groups", []):
            positions = [points[n["id"]] for n in nodes if n.get("group") == group["id"]]
            if positions:
                xx, yy = zip(*positions)
                box = (min(xx) - 90, min(yy) - 90, max(xx) + 90, max(yy) + 130)
                draw.rounded_rectangle(box, radius=18, outline="#94a3b8", width=3)
                draw.text(
                    (box[0] + 10, box[1] - 26), group["label"][:70], font=small, fill="#475569"
                )
        for edge in graph["edges"]:
            x, y = points[edge["source"]]
            xx, yy = points[edge["target"]]
            length = math.hypot(xx - x, yy - y)
            if length:
                ux, uy = (xx - x) / length, (yy - y) / length
                start, end = (x + ux * 43, y + uy * 43), (xx - ux * 43, yy - uy * 43)
                if edge.get("status") == "hypothesis":
                    steps = max(1, int(length / 18))
                    for step in range(0, steps, 2):
                        a, b = step / steps, min((step + 1) / steps, 1)
                        draw.line(
                            (
                                start[0] + (end[0] - start[0]) * a,
                                start[1] + (end[1] - start[1]) * a,
                                start[0] + (end[0] - start[0]) * b,
                                start[1] + (end[1] - start[1]) * b,
                            ),
                            fill="#64748b",
                            width=3,
                        )
                else:
                    draw.line((*start, *end), fill="#64748b", width=3)
                draw.polygon(
                    [
                        end,
                        (end[0] - ux * 18 - uy * 8, end[1] - uy * 18 + ux * 8),
                        (end[0] - ux * 18 + uy * 8, end[1] - uy * 18 - ux * 8),
                    ],
                    fill="#64748b",
                )
            else:
                draw.arc((x - 75, y - 105, x + 75, y + 25), 180, 530, fill="#64748b", width=3)
            label = "\n".join(textwrap.wrap(edge["label"], 24))
            at = ((x + xx) / 2, (y + yy) / 2 - 32)
            box = draw.multiline_textbbox(at, label, font=small, anchor="mm", align="center")
            draw.rectangle(box, fill="white")
            draw.multiline_text(at, label, font=small, fill="#334155", anchor="mm", align="center")
        colors = {t["type"]: t["color"] for t in graph["legend"]}
        for node in nodes:
            x, y = points[node["id"]]
            if node.get("annotation"):
                draw.rounded_rectangle(
                    (x - 100, y - 40, x + 100, y + 40),
                    radius=10,
                    fill="#fff1ae",
                    outline="#c7a951",
                    width=2,
                )
            else:
                draw.ellipse(
                    (x - 42, y - 42, x + 42, y + 42),
                    fill=colors[node["type"]],
                    outline="#334155",
                    width=2,
                )
                if node.get("photo"):
                    photo = (
                        Image.open(BytesIO(base64.b64decode(node["photo"].split(",", 1)[1])))
                        .convert("RGB")
                        .resize((80, 80))
                    )
                    mask = Image.new("L", (80, 80))
                    ImageDraw.Draw(mask).ellipse((0, 0, 79, 79), fill=255)
                    image.paste(photo, (int(x - 40), int(y - 40)), mask)
            lines = [
                node["label"],
                *[f["name"] + ": " + f["value"] for f in node["fields"] if f.get("visible")],
            ]
            label = "\n".join(textwrap.wrap(" | ".join(lines), 24)[:6])
            draw.multiline_text(
                (x, y + 55), label, font=font, fill="#0f172a", anchor="ma", align="center"
            )
    bounds = ImageChops.difference(image, Image.new("RGB", image.size, "white")).getbbox()
    if bounds:
        left, top, right, bottom = bounds
        image = image.crop(
            (
                max(0, left - 40),
                max(0, top - 40),
                min(image.width, right + 40),
                min(image.height, bottom + 40),
            )
        )
    out = BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def summary_lines(section):
    graph = section["graph"]
    lines = [
        f"View: {section['view']} | {len(graph['nodes'])} objects | {len(graph['edges'])} connections",
        "Legend: solid arrow = supported; dashed arrow = hypothesis. Relationship labels are analyst assessments.",
    ]
    f = section["filters"]
    if f.get("from") or f.get("to"):
        lines.append(
            f"Dates: {f.get('from') or 'any'} to {f.get('to') or 'any'}; undated relationships {'included' if f.get('includeUndated', True) else 'excluded'}."
        )
    lines.extend(f"{t['type']}: {t['description']}" for t in graph["legend"])
    lines.extend(
        f"{e['label']} [{e.get('status', 'hypothesis')}]"
        + (f" | Date: {e['date']}" if e.get("date") else "")
        + (f" | Notes: {e['notes']}" if e.get("notes") else "")
        for e in graph["edges"]
    )
    for node in graph["nodes"]:
        lines.append(f"Object: {node['label']} [{node['type']}]")
        lines.extend(f"{f['name']}: {f['value']}" for f in node["fields"] if f.get("value"))
    for e in section["evidence"]:
        lines.append(
            f"Evidence: {e['label']} [{e['status']}] | Source: {e['source']} | Reference: {e['ref']}"
        )
        lines.append(e["value"])
        if e["notes"]:
            lines.append("Analyst notes: " + e["notes"])
    return lines


def legend_ink(color):
    """Choose legible text over the exact legend background color."""
    rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    luminance = sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))
    return "#000000" if luminance > 0.179 else "#ffffff"


def report_details(section):
    """Reader-facing sections shared by PDF and Word exports."""
    graph = section["graph"]
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    yield "Connections", [
        (f"{labels.get(e['source'], 'Unknown')} to {labels.get(e['target'], 'Unknown')}",
         e["label"] + " (" + e.get("status", "hypothesis") + ")"
         + ("\nDate: " + e["date"] if e.get("date") else "")
         + ("\nAnalyst notes: " + e["notes"] if e.get("notes") else ""))
        for e in graph["edges"]
    ]
    yield "Object details", [
        (n["label"] + " (" + n["type"] + ")",
         "\n".join(f"{f['name']}: {f['value']}" for f in n["fields"] if f.get("value"))
         or "No additional details recorded.") for n in graph["nodes"]
    ]
    yield "Linked evidence", [
        (e["label"] + " (" + e["status"] + ")",
         "Source: " + e["source"] + "\n" + e["value"]
         + ("\nAnalyst notes: " + e["notes"] if e["notes"] else "")
         + "\nEvidence reference: " + e["ref"]) for e in section["evidence"]
    ]


def attachments(section, case_id):
    import case_features

    seen = set()
    for evidence in section["evidence"]:
        for item in evidence.get("attachments", []):
            eid = item.get("id", "")
            if not isinstance(eid, str) or not re.fullmatch(r"[a-f0-9]{32}", eid) or eid in seen:
                continue
            seen.add(eid)
            path = case_features.EVIDENCE_DIR / case_id / (eid + ".png")
            if path.is_file():
                yield path, item.get("caption", "Supporting screenshot")
