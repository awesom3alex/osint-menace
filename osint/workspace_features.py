"""Unified tool launches, durable history, and observed tool health."""

import copy
import re
import subprocess
import time
import uuid
from urllib.parse import urlsplit

from flask import Blueprint, abort, jsonify, render_template, request, url_for
from itsdangerous import BadSignature

import addon_presentation
import addon_tools as addons
import telephone_output
import tool_credentials as credentials
import workspace_store as store
from readable_results import field_label, structured_value

bp = Blueprint("workspace", __name__)


def finding_section(job):
    """Keep public output intact, but make top-level structured facts separately reviewable."""
    if job.get('tool') in addons.GITHUB_TOOLS:
        from github_tools import finding_section
        return finding_section(job)
    value = credentials.redact(job.get("output", ""))
    summary=telephone_output.view(dict(job,output=value))
    if summary is not None:return telephone_output.section(job,summary)
    parsed = structured_value(value)
    findings = []
    source = addons.TOOLS[job["tool"]][1]
    if parsed["structured"]:
        data = parsed["value"]
        records = data if isinstance(data, list) else [data]
        for record in records[:100]:
            if isinstance(record, dict) and any(
                str(record.get(key, "")).startswith(("http://", "https://"))
                for key in ("url", "profile_url", "link")
            ):
                findings.append(
                    dict(
                        label=str(
                            record.get("site")
                            or record.get("platform")
                            or record.get("name")
                            or "Reported profile"
                        ),
                        value=record,
                        source=source,
                    )
                )
            elif isinstance(record, dict):
                for key, val in record.items():
                    findings.append(dict(label=field_label(key), value=val, source=source))
            else:
                findings.append(dict(label="Result", value=record, source=source))
    else:
        url_lines = [line for line in value.splitlines() if re.search(r"https?://", line)]
        if url_lines:
            findings = [
                dict(label="Reported link " + str(index + 1), value=line, source=source)
                for index, line in enumerate(url_lines[:500])
            ]
            remainder = "\n".join(
                line for line in value.splitlines() if not re.search(r"https?://", line)
            )
            if remainder.strip():
                findings.append(
                    dict(
                        label="Tool messages",
                        value=remainder,
                        source=source,
                        include_in_report=False,
                    )
                )
        else:
            findings = [dict(label="Tool output", value=value, source=source)]
    for finding in findings:
        finding["collected_at"] = job["timestamp"]
        finding["collection_method"] = "Addon output: " + source
    links = []
    for link in dict.fromkeys(re.findall(r'https?://[^\s<>"\]\}]+', value)):
        links.append(dict(label=source + " source", value=link.rstrip(".,)"), source=source))
        if len(links) >= 100:
            break
    return dict(
        name=addons.TOOLS[job["tool"]][0] + ": " + job["target"],
        module_type="addon:" + job["tool"],
        module=dict(name=source, mode="analyst selected"),
        findings=findings,
        links=links,
        notes=[
            "Execution status: " + job["status"],
            "Retrieved: " + job["timestamp"],
            "Results are unverified leads. Profile matches do not establish identity.",
        ],
    )


def record(record_id):
    item = store.get(record_id)
    if item is None:
        abort(404)
    item = copy.deepcopy(item)
    if "job_ids" in item:
        item["jobs"] = [store.get(key) for key in item["job_ids"]]
        item["jobs"] = [job for job in item["jobs"] if job]
    elif "tool" in item:
        item["jobs"] = [copy.deepcopy(item)]
    else:
        item["jobs"] = []
    item["active"] = any(j["status"] in ("queued", "running") for j in item["jobs"])
    for job in item["jobs"]:
        job["output"]=credentials.redact(job.get("output",""))
        if job.get("raw_output"):job["raw_output"]=credentials.redact(job["raw_output"])
        job["telephone_view"]=telephone_output.view(job)
        job["output_view"]=addon_presentation.view(job)
        if job["tool"]=="ignorant" and job["telephone_view"]:
            job["rate_limited"]=any(row["state"]=="x" for row in job["telephone_view"]["accounts"])
        job.update(addons.progress(job))
        job["section"] = finding_section(job)
    counts = {
        state: 0
        for state in (
            "queued",
            "running",
            "cancelling",
            "completed",
            "rate-limited",
            "failed",
            "limited",
            "cancelled",
            "interrupted",
        )
    }
    for job in item["jobs"]:
        counts[job["display_state"]] = counts.get(job["display_state"], 0) + 1
    item["progress"] = dict(
        counts=counts,
        total=len(item["jobs"]),
        finished=sum(j["status"] not in ("queued", "running") for j in item["jobs"]),
    )
    return item


@bp.get("/unified")
def unified():
    return render_template("unified.html", tools=addons.catalog())


@bp.post("/api/unified")
def launch():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a search object."), 400
    keys = data.get("tools", [])
    target, kind, country = (data.get(k, "") for k in ("target", "kind", "country"))
    if (
        not isinstance(keys, list)
        or not 1 <= len(keys) <= 12
        or not all(isinstance(k, str) for k in keys)
        or len(set(keys)) != len(keys)
    ):
        return jsonify(error="Select between 1 and 12 different compatible tools."), 400
    if not all(isinstance(v, str) for v in (target, kind, country)):
        return jsonify(error="Enter a target, type, and optional calling code as text."), 400
    commands = []
    try:
        for key in keys:
            args = addons.command(key, target, kind, country)
            if not addons.executable(key).is_file():
                raise ValueError("Selected tool is not installed: " + key)
            commands.append((key, args))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    group_id = uuid.uuid4().hex
    with addons.LOCK:
        addons.prune_jobs()
        if sum(j["status"] in ("queued", "running") for j in addons.JOBS.values()) + len(keys) > 32:
            return jsonify(error="Search queue is full. Wait for current searches to finish."), 429
        job_ids = []
        for key, args in commands:
            job_id = uuid.uuid4().hex
            job = dict(
                id=job_id,
                tool=key,
                target=target.strip(),
                kind=kind,
                created=time.time(),
                timestamp=store.now(),
                status="queued",
                output="",
                exit_code=None,
                group_id=group_id,
            )
            addons.JOBS[job_id] = job
            store.put(job_id, "addon", job)
            job_ids.append(job_id)
        store.put(
            group_id,
            "unified",
            dict(
                id=group_id,
                target=target.strip(),
                kind=kind,
                timestamp=store.now(),
                job_ids=job_ids,
            ),
        )
    for job_id, (_, args) in zip(job_ids, commands):
        addons.POOL.submit(addons.execute, job_id, args)
    return jsonify(id=group_id, url=url_for("workspace.history_detail", record_id=group_id)), 202


@bp.get("/history")
def history():
    return render_template(
        "history.html",
        records=store.history(request.args.get("q", "")),
        query=request.args.get("q", ""),
    )


@bp.get("/history/<record_id>")
def history_detail(record_id):
    from app import list_cases

    item = record(record_id)
    if item.get('record_type') in ('global_search','research_tool') and 'entries' in item:
        from flask import redirect, url_for
        return redirect(url_for('research_hub.result', record_id=record_id))
    if item.get("image_reuse") or item.get("image_analysis"):
        abort(404, "Image features are currently deferred.")
    template = (
        "history_results.html" if request.args.get("fragment") == "1" else "history_detail.html"
    )
    return render_template(template, item=item, cases=list_cases())


@bp.get("/tools")
def tools_page():
    observations = store.health()
    return render_template(
        "tools.html",
        tools=[dict(t, health=observations.get(t["id"], {}),credential_fields=credentials.fields(t["id"]),credential_token=credentials.SIGNER.dumps(t["id"])) for t in addons.catalog()],
    )


@bp.post('/tools/<tool_id>/credentials')
def save_credentials(tool_id):
    if tool_id not in credentials.SCHEMA:abort(404)
    origin=request.headers.get('Origin')
    if request.headers.get('Sec-Fetch-Site')=='cross-site' or (origin and urlsplit(origin).netloc!=request.host):abort(403)
    try:
        if credentials.SIGNER.loads(request.form.get('csrf',''),max_age=3600)!=tool_id:raise ValueError('Reload Tools before saving configuration.')
        credentials.save(tool_id,request.form)
    except BadSignature:return jsonify(error='Reload Tools before saving configuration.'),400
    except ValueError as exc:return jsonify(error=str(exc)),400
    response=jsonify(message='Configuration saved locally. New searches use it immediately; credentials have not been validated with the provider.',fields=credentials.fields(tool_id))
    response.headers['Cache-Control']='no-store'
    return response


@bp.post("/tools/<tool_id>/check")
def check(tool_id):
    # Only local CLI startup; this never queries public targets or tests credentials.
    if tool_id not in addons.TOOLS:
        abort(404)
    args = addons.startup_command(tool_id)
    try:
        import tempfile

        with tempfile.TemporaryDirectory() as work:
            result = subprocess.run(
                args, cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20
            )
        state = "passed" if result.returncode == 0 else "failed"
    except (OSError, subprocess.TimeoutExpired):
        state = "failed"
    store.update_health(tool_id, checked_at=store.now(), startup_check=state)
    return jsonify(
        message=addons.TOOLS[tool_id][1] + ": local startup " + state,
        startup_check=state,
        checked_at=store.health()[tool_id]["checked_at"],
    )


@bp.post("/api/history/<record_id>/cancel")
def cancel_search(record_id):
    item = store.get(record_id)
    if not item or not ("job_ids" in item or "tool" in item):
        abort(404)
    with addons.LOCK:
        changed = sum(addons.cancel_job(key) for key in item.get("job_ids", [record_id]))
    return jsonify(message=f"Cancellation requested for {changed} unfinished tools.")
