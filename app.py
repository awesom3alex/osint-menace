from __future__ import annotations

from dataclasses import asdict
import datetime as dt
import ipaddress
import json
from pathlib import Path
import re
from typing import Any
import uuid

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for

import osint_tool


app = Flask(__name__)
DATA_DIR = Path("data")
CASES_DIR = DATA_DIR / "cases"
OSINT_LINKS_PATH = DATA_DIR / "catalog" / "osint_links.json"
CASES_DIR.mkdir(parents=True, exist_ok=True)


SEARCH_TYPES = {
    "email": {"label": "Email", "placeholder": "person@example.com"},
    "username": {"label": "Username", "placeholder": "handle"},
    "phone": {"label": "Phone", "placeholder": "+1 555 555 1234"},
    "name": {"label": "Full Name", "placeholder": "Jane Example"},
    "domain": {"label": "Domain", "placeholder": "example.com"},
    "ip": {"label": "IP Address", "placeholder": "93.184.216.34"},
    "wallet": {"label": "Crypto Wallet", "placeholder": "0x... or bc1..."},
}

MODULE_REGISTRY = {
    "email": {
        "name": "Email Intelligence",
        "mode": "passive",
        "checks": ["format", "Gravatar", "MX/provider", "SPF/DMARC", "search pivots"],
    },
    "username": {
        "name": "Username Recon",
        "mode": "passive",
        "checks": ["candidate profile URLs", "developer/social pivots", "search pivots"],
    },
    "phone": {
        "name": "Phone Pivots",
        "mode": "passive",
        "checks": ["format", "region guess", "public mention links"],
    },
    "name": {
        "name": "Name Pivots",
        "mode": "passive",
        "checks": ["public search pivots", "profile links", "records and filing links"],
    },
    "domain": {
        "name": "Domain Intelligence",
        "mode": "passive",
        "checks": ["DNS", "RDAP", "TLS", "CT logs", "Wayback", "reputation pivots"],
    },
    "ip": {
        "name": "IP Intelligence",
        "mode": "passive by default",
        "checks": ["PTR", "RDAP", "geo approximation", "ASN", "reputation pivots"],
    },
    "wallet": {
        "name": "Crypto Wallet Pivots",
        "mode": "passive",
        "checks": ["format", "explorer links", "ENS link"],
    },
}


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ETH_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
BTC_RE = re.compile(r"^(bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")
DOMAIN_RE = re.compile(r"^(?:[a-zA-Z0-9-]{1,63}\.)+[a-zA-Z]{2,63}$")


def section_to_dict(section: osint_tool.Section) -> dict:
    return {
        "name": section.name,
        "findings": [asdict(item) for item in section.findings],
        "links": [asdict(item) for item in section.links],
        "notes": section.notes,
    }


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def split_targets(value: str) -> list[str]:
    targets: list[str] = []
    for part in re.split(r"[\n,;]+", value):
        clean = part.strip()
        if clean:
            targets.append(clean)
    return targets[:25]


def detect_target_type(value: str) -> str:
    clean = value.strip()
    lower = clean.lower()
    if EMAIL_RE.fullmatch(clean):
        return "email"
    if ETH_RE.fullmatch(clean) or BTC_RE.fullmatch(clean):
        return "wallet"
    try:
        ipaddress.ip_address(clean)
        return "ip"
    except ValueError:
        pass
    if lower.startswith(("http://", "https://")):
        host = osint_tool.normalize_domain(lower)
        if DOMAIN_RE.fullmatch(host):
            return "domain"
    if DOMAIN_RE.fullmatch(lower):
        return "domain"
    digits = re.sub(r"\D", "", clean)
    if len(digits) >= 8 and re.fullmatch(r"[\d\s()+.-]+", clean):
        return "phone"
    if " " in clean and len(clean.split()) >= 2:
        return "name"
    return "username"


def result_summary(sections: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "targets": len(sections),
        "findings": sum(len(section.get("findings", [])) for section in sections),
        "links": sum(len(section.get("links", [])) for section in sections),
        "notes": sum(len(section.get("notes", [])) for section in sections),
    }


def run_search(kind: str, value: str, forum_pattern: str, allow_port_scan: bool, ports_text: str) -> list[dict]:
    ports = osint_tool.parse_ports(ports_text or "21,22,80,443,8080")
    if kind == "auto":
        sections = []
        for target in split_targets(value):
            detected = detect_target_type(target)
            sections.extend(run_search(detected, target, forum_pattern, allow_port_scan, ports_text))
        return sections
    if kind == "email":
        sections = [osint_tool.email_report(value)]
    elif kind == "username":
        patterns = [forum_pattern] if forum_pattern else []
        sections = [osint_tool.username_report(value, patterns)]
    elif kind == "phone":
        sections = [osint_tool.phone_report(value)]
    elif kind == "name":
        sections = [osint_tool.name_report(value)]
    elif kind == "domain":
        sections = [osint_tool.domain_report(value)]
    elif kind == "ip":
        sections = [osint_tool.ip_report(value, allow_port_scan, ports)]
    elif kind == "wallet":
        sections = [osint_tool.crypto_report(value)]
    else:
        sections = []
    section_dicts = [section_to_dict(section) for section in sections]
    for section in section_dicts:
        section["module_type"] = kind
        section["module"] = MODULE_REGISTRY.get(kind, {"name": kind.title(), "mode": "passive"})
    return section_dicts


def case_path(case_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9-]{36}", case_id):
        abort(404)
    return CASES_DIR / f"{case_id}.json"


def load_case(case_id: str) -> dict[str, Any]:
    path = case_path(case_id)
    if not path.exists():
        abort(404)
    case_data = json.loads(path.read_text())
    case_data["summary"] = {
        "searches": len(case_data.get("searches", [])),
        "findings": sum(search.get("summary", {}).get("findings", 0) for search in case_data.get("searches", [])),
        "links": sum(search.get("summary", {}).get("links", 0) for search in case_data.get("searches", [])),
        "notes": sum(search.get("summary", {}).get("notes", 0) for search in case_data.get("searches", [])),
    }
    return case_data


def save_case(case_data: dict[str, Any]) -> None:
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    case_path(case_data["id"]).write_text(json.dumps(case_data, indent=2, sort_keys=True))


def list_cases() -> list[dict[str, Any]]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        cases.append(
            {
                "id": data.get("id"),
                "name": data.get("name", "Untitled Case"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "search_count": len(data.get("searches", [])),
            }
        )
    return cases


def create_case(name: str, notes: str = "") -> dict[str, Any]:
    now = utc_now()
    case_data = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or "Untitled Case",
        "notes": notes.strip(),
        "created_at": now,
        "updated_at": now,
        "searches": [],
    }
    save_case(case_data)
    return case_data


def append_search_to_case(case_data: dict[str, Any], search_record: dict[str, Any]) -> None:
    case_data.setdefault("searches", []).append(search_record)
    case_data["updated_at"] = utc_now()
    save_case(case_data)


def remove_search_from_case(case_data: dict[str, Any], search_id: str) -> bool:
    searches = case_data.get("searches", [])
    kept_searches = [search for search in searches if search.get("id") != search_id]
    if len(kept_searches) == len(searches):
        return False
    case_data["searches"] = kept_searches
    case_data["updated_at"] = utc_now()
    save_case(case_data)
    return True


def make_search_record(selected: str, value: str, results: list[dict[str, Any]], summary: dict[str, int]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "created_at": utc_now(),
        "search_type": selected,
        "query": value,
        "summary": summary,
        "results": results,
    }


def render_markdown_report(case_data: dict[str, Any]) -> str:
    lines = [
        f"# OSINT Menace Case Report: {case_data.get('name', 'Untitled Case')}",
        "",
        "A Defensive Thinking Project.",
        "",
        f"- Case ID: {case_data.get('id')}",
        f"- Created: {case_data.get('created_at')}",
        f"- Updated: {case_data.get('updated_at')}",
        f"- Searches: {len(case_data.get('searches', []))}",
        "",
    ]
    notes = case_data.get("notes")
    if notes:
        lines.extend(["## Case Notes", "", notes, ""])
    for search in case_data.get("searches", []):
        lines.extend(
            [
                f"## Search: {search.get('query')}",
                "",
                f"- Type: {search.get('search_type')}",
                f"- Time: {search.get('created_at')}",
                f"- Findings: {search.get('summary', {}).get('findings', 0)}",
                f"- Pivots: {search.get('summary', {}).get('links', 0)}",
                "",
            ]
        )
        for section in search.get("results", []):
            lines.extend([f"### {section.get('name')}", ""])
            module = section.get("module", {})
            if module:
                lines.append(f"Module: {module.get('name')} ({module.get('mode')})")
                lines.append("")
            for finding in section.get("findings", []):
                lines.append(f"- {finding.get('label')}: {finding.get('value')}")
            for link in section.get("links", [])[:30]:
                lines.append(f"- [{link.get('label')}]({link.get('value')})")
            for note in section.get("notes", []):
                lines.append(f"- Note: {note}")
            lines.append("")
    return "\n".join(lines)


def load_osint_links() -> dict[str, Any]:
    if OSINT_LINKS_PATH.exists():
        return json.loads(OSINT_LINKS_PATH.read_text())
    return {
        "source_title": "OSINT4ALL - Start.me",
        "source_url": "https://start.me/p/L1rEYQ/osint4all",
        "categories": [],
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/help")
def help_page():
    return render_template("help.html", search_types=SEARCH_TYPES, modules=MODULE_REGISTRY)


@app.get("/osint-links")
def osint_links_page():
    catalog = load_osint_links()
    return render_template("osint_links.html", catalog=catalog)


@app.route("/cases", methods=["GET", "POST"])
def cases_page():
    if request.method == "POST":
        case_data = create_case(request.form.get("case_name", ""), request.form.get("case_notes", ""))
        return redirect(url_for("case_detail", case_id=case_data["id"]))
    return render_template("cases.html", cases=list_cases())


@app.get("/cases/<case_id>")
def case_detail(case_id: str):
    return render_template("case.html", case=load_case(case_id))


@app.post("/cases/add-result")
def add_result_to_case():
    cases = list_cases()
    case_id = request.form.get("case_id", "").strip()
    if not case_id and len(cases) == 1:
        case_id = str(cases[0]["id"])
    if not case_id:
        abort(400, "Select a case before adding this result.")

    try:
        section = json.loads(request.form.get("section_json", ""))
    except json.JSONDecodeError:
        abort(400, "Result payload could not be read.")
    if not isinstance(section, dict) or not section.get("name"):
        abort(400, "Result payload is missing a section name.")

    section.setdefault("findings", [])
    section.setdefault("links", [])
    section.setdefault("notes", [])
    section_type = section.get("module_type") or request.form.get("search_type", "result")
    source_query = request.form.get("query", "").strip() or section.get("name", "Saved Result")

    case_data = load_case(case_id)
    append_search_to_case(
        case_data,
        make_search_record(str(section_type), source_query, [section], result_summary([section])),
    )
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "message": f"Added to {case_data.get('name', 'case')}"})
    return redirect(url_for("case_detail", case_id=case_id))


@app.post("/cases/add-link")
def add_link_to_case():
    cases = list_cases()
    case_id = request.form.get("case_id", "").strip()
    if not case_id and len(cases) == 1:
        case_id = str(cases[0]["id"])
    if not case_id:
        abort(400, "Select a case before adding this link.")

    label = request.form.get("link_label", "").strip()
    value = request.form.get("link_value", "").strip()
    source_section = request.form.get("section_name", "").strip() or "Search Result"
    source_query = request.form.get("query", "").strip() or label or value
    section_type = request.form.get("search_type", "link").strip() or "link"
    if not label or not value:
        abort(400, "Link label and URL are required.")

    section = {
        "name": f"Saved Link: {label}",
        "module_type": section_type,
        "module": {
            "name": "Selected Case Link",
            "mode": "analyst selected",
        },
        "findings": [
            {
                "label": "Selected link",
                "value": label,
                "source": source_section,
            }
        ],
        "links": [
            {
                "label": label,
                "value": value,
                "source": source_section,
            }
        ],
        "notes": [f"Analyst selected this individual link from {source_section}."],
    }

    case_data = load_case(case_id)
    append_search_to_case(
        case_data,
        make_search_record(f"{section_type}:link", source_query, [section], result_summary([section])),
    )
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({"ok": True, "message": f"Added to {case_data.get('name', 'case')}"})
    return redirect(url_for("case_detail", case_id=case_id))


@app.post("/cases/<case_id>/items/<item_id>/delete")
def delete_case_item(case_id: str, item_id: str):
    case_data = load_case(case_id)
    if not remove_search_from_case(case_data, item_id):
        abort(404)
    return redirect(url_for("case_detail", case_id=case_id))


@app.post("/cases/<case_id>/delete")
def delete_case(case_id: str):
    case_data = load_case(case_id)
    confirmation = request.form.get("confirm_name", "").strip()
    if confirmation != case_data.get("name", ""):
        return render_template(
            "case.html",
            case=case_data,
            delete_error="Type the exact case name to delete this case.",
        ), 400
    path = case_path(case_id)
    if path.exists():
        path.unlink()
    return redirect(url_for("cases_page"))


@app.get("/cases/<case_id>/export.json")
def export_case_json(case_id: str):
    case_data = load_case(case_id)
    return jsonify(case_data)


@app.get("/cases/<case_id>/report.md")
def export_case_markdown(case_id: str):
    case_data = load_case(case_id)
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_data.get("name", "case")).strip("-").lower() or "case"
    return Response(
        render_markdown_report(case_data),
        mimetype="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}-report.md"},
    )


@app.get("/cases/<case_id>/report.html")
def export_case_html(case_id: str):
    return render_template("report.html", case=load_case(case_id))


@app.post("/api/search")
def api_search():
    payload = request.get_json(silent=True) or {}
    selected = str(payload.get("search_type", "auto"))
    value = str(payload.get("query", ""))
    forum_pattern = str(payload.get("forum_pattern", ""))
    ports_text = str(payload.get("ports", "21,22,80,443,8080"))
    allow_port_scan = bool(payload.get("allow_port_scan", False))
    if selected not in {"auto", *SEARCH_TYPES.keys()}:
        return jsonify({"error": "Unknown search_type"}), 400
    if not value.strip():
        return jsonify({"error": "Enter a value to search."}), 400
    try:
        results = run_search(selected, value.strip(), forum_pattern.strip(), allow_port_scan, ports_text.strip())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"summary": result_summary(results), "results": results})


@app.route("/", methods=["GET", "POST"])
def index():
    selected = request.form.get("search_type", "auto")
    value = request.form.get("query", "")
    case_id = request.form.get("case_id", "")
    new_case_name = request.form.get("new_case_name", "")
    forum_pattern = request.form.get("forum_pattern", "")
    ports_text = request.form.get("ports", "21,22,80,443,8080")
    allow_port_scan = request.form.get("allow_port_scan") == "on"
    results = []
    error = None
    saved_case = None

    if request.method == "POST":
        try:
            if not value.strip():
                error = "Enter a value to search."
            else:
                results = run_search(selected, value.strip(), forum_pattern.strip(), allow_port_scan, ports_text.strip())
                summary = result_summary(results)
                if new_case_name.strip():
                    saved_case = create_case(new_case_name.strip())
                    append_search_to_case(saved_case, make_search_record(selected, value.strip(), results, summary))
                elif case_id.strip():
                    saved_case = load_case(case_id.strip())
                    append_search_to_case(saved_case, make_search_record(selected, value.strip(), results, summary))
        except Exception as exc:
            error = str(exc)

    return render_template(
        "index.html",
        search_types=SEARCH_TYPES,
        modules=MODULE_REGISTRY,
        cases=list_cases(),
        selected=selected,
        value=value,
        case_id=case_id,
        new_case_name=new_case_name,
        saved_case=saved_case,
        forum_pattern=forum_pattern,
        ports=ports_text,
        allow_port_scan=allow_port_scan,
        results=results,
        summary=result_summary(results),
        error=error,
    )
