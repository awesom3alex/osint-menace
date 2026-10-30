"""Explicit addon launches with isolated executables and bounded background jobs."""

import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request

import tool_credentials as credentials
import workspace_store as store

bp = Blueprint("addons", __name__)
ROOT = Path(__file__).resolve().parent
PREFIX = Path(os.environ.get("MENACE_ADDON_PREFIX", "/opt/addons"))
TOOLS = {
    "sherlock": ("Basic Search", "Sherlock", "username", "Find public profile matches."),
    "maigret": (
        "Advanced Search",
        "Maigret",
        "username",
        "Broader username searches and profile analysis.",
    ),
    "naminter": ("WhatsMyName Search", "Naminter", "username", "Search the WhatsMyName dataset."),
    "social-analyzer": (
        "Social Profile Analysis",
        "Social Analyzer",
        "username",
        "Search and analyze public profiles.",
    ),
    "aliens_eye": (
        "Platform Scanner",
        "Aliens’ Eye",
        "username",
        "Scan platforms for username matches.",
    ),
    "toutatis": (
        "Instagram Intel",
        "Toutatis",
        "username",
        "Requires an Instagram session configured under Tools.",
    ),
    "socialscan": (
        "Account Availability",
        "Socialscan",
        "username,email",
        "Check username or email availability; availability is not proof of identity.",
    ),
    "blackbird": (
        "Account Search",
        "Blackbird",
        "username,email",
        "Search public accounts by username or email.",
    ),
    "holehe": (
        "Email Accounts",
        "Holehe",
        "email",
        "Check supported services for associated accounts.",
    ),
    "phoneinfoga": (
        "Phone Intelligence",
        "PhoneInfoga",
        "phone",
        "Phone-number intelligence; some upstream scanners need API keys.",
    ),
    "ignorant": (
        "Phone Account Check",
        "Ignorant",
        "phone",
        "Check registration on supported services; enter country calling code separately.",
    ),
    "clank": (
        "Phone Enrichment",
        "Clank",
        "phone",
        "Local phone metadata: region, carrier-of-record, and numbering information.",
    ),
}
TOOLS.update({
    'unfurl': ('URL Inspector','Unfurl','url','Decode URL fields, timestamps, and identifiers locally; remote lookups disabled.'),
    'waymore': ('Historical URL Discovery','waymore','domain','Find archived URLs using Wayback Machine and Common Crawl; URL-only mode.'),
    'subfinder': ('Passive Subdomains','Subfinder','domain','Query crt.sh and HackerTarget for subdomain leads; no active resolution.'),
    'dnstwist': ('Brand Impersonation','dnstwist','domain','Check limited look-alike permutations through DNS; no website fetches.'),
    'theharvester': ('Organization Footprint','theHarvester','domain','Search crt.sh and AlienVault OTX; no DNS resolution, crawling, or screenshots.'),
})
GITHUB_TOOLS = frozenset(('unfurl','waymore','subfinder','dnstwist','theharvester'))
EXECUTABLES = {
    "unfurl": "python",
    "waymore": "python",
    "dnstwist": "python",
    "theharvester": "python",
    "sherlock": "sherlock",
    "maigret": "maigret",
    "naminter": "naminter",
    "social-analyzer": "python",
    "aliens_eye": "aliens_eye",
    "toutatis": "toutatis",
    "socialscan": "socialscan",
    "blackbird": "python",
    "holehe": "holehe",
    "ignorant": "ignorant",
}
POOL = ThreadPoolExecutor(max_workers=2)
LOCK = threading.Lock()
JOBS = {}
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def executable(key):
    return PREFIX / (
        "bin/" + key if key in ("clank", "phoneinfoga", "subfinder") else key + "/bin/" + EXECUTABLES[key]
    )


def startup_command(key):
    """Launch the tool's help entry point, rather than its Python interpreter alone."""
    if key in GITHUB_TOOLS:
        binary = (
            PREFIX / "bin/subfinder"
            if key == "subfinder"
            else PREFIX / key / "bin" / ("theHarvester" if key == "theharvester" else key)
        )
        return [str(binary), "--help"]
    args = [str(executable(key))]
    if key in ("blackbird", "social-analyzer"):
        args.append(str(ROOT / "addons/sources" / key / (
            "blackbird.py" if key == "blackbird" else "app.py"
        )))
    return [*args, "--help"]


def prune_jobs():
    finished = sorted(
        (key for key, job in JOBS.items() if job["status"] not in ("queued", "running")),
        key=lambda key: JOBS[key].get("created", 0),
        reverse=True,
    )
    for key in finished[80:]:
        del JOBS[key]


def catalog():
    manifest = json.loads((ROOT / "addons/manifest.json").read_text())
    return [
        dict(
            id=k,
            label=v[0],
            upstream=v[1],
            types=v[2].split(","),
            description=v[3],
            installed=executable(k).is_file(),
            configured=k != "toutatis" or bool(credentials.values(k).get("INSTAGRAM_SESSION_ID")),
            **manifest[k],
        )
        for k, v in TOOLS.items()
    ]


def command(key, target, kind, country=""):
    if key not in TOOLS or kind not in TOOLS[key][2].split(","):
        raise ValueError("Choose a supported tool and target type.")
    target = target.strip()
    if (
        not target
        or len(target) > (2048 if key == "unfurl" else 254)
        or target.startswith("-")
        or any(c.isspace() or ord(c) < 32 for c in target)
    ):
        raise ValueError("Enter one target without spaces, control characters, or leading dashes.")
    if key in GITHUB_TOOLS:
        from github_tools import validate_target
        target = validate_target(key, target)
        runtime = executable(key) if key != 'subfinder' else Path(__import__('sys').executable)
        return [str(runtime), str(ROOT/'scripts/github_worker.py'), '--tool', key, '--target', target]
    if kind == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", target):
        raise ValueError("Enter a valid email address.")
    if kind == "phone" and not re.fullmatch(r"\+?[0-9]{7,15}", target):
        raise ValueError("Use 7–15 digits with an optional leading +, without spaces.")
    if kind == "username" and not re.fullmatch(r"[\w.@+\-]{1,100}", target):
        raise ValueError(
            "Enter a username of up to 100 letters, digits, dots, underscores, +, @ or hyphens."
        )
    if kind == 'phone' and key != 'ignorant' and country:
        import phonenumbers
        if not re.fullmatch(r'[1-9][0-9]{0,2}',country):raise ValueError('Enter a country calling code, such as 1 or 44.')
        try:
            region=phonenumbers.region_code_for_country_code(int(country))
            parsed=phonenumbers.parse(target,region if region not in ('ZZ','001') else None)
            if not phonenumbers.is_possible_number(parsed) or parsed.country_code!=int(country):raise ValueError('Phone number does not match the chosen calling code. Use international + format.')
            target=phonenumbers.format_number(parsed,phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:raise ValueError('Use international + format for this number.') from None
    args = {
        "sherlock": [target, "--print-found", "--no-color"],
        "maigret": [target, "--no-color", "--no-progressbar", "--top-sites", "500"],
        "naminter": ["--username", target, "--no-color"],
        "social-analyzer": [
            str(ROOT / "addons/sources/social-analyzer/app.py"),
            "--username",
            target,
            "--top",
            "100",
        ],
        "aliens_eye": [target, "--profile", "quick", "--no-nsfw", "--json-stdout"],
        "socialscan": [target, "--json", "socialscan-results.json"],
        "blackbird": [str(ROOT / "addons/sources/blackbird/blackbird.py"), "--" + kind, target],
        "holehe": [target, "--no-color", "--no-clear"],
        "phoneinfoga": ["scan", "-n", target],
        "clank": ["--json", "--local", target],
    }
    if key == "ignorant":
        if not re.fullmatch(r"[1-9][0-9]{0,2}", country):
            raise ValueError("Enter a country calling code, such as 1 or 44.")
        if target.startswith("+"):
            if not target[1:].startswith(country):
                raise ValueError("Country calling code does not match the number.")
            target = target[1 + len(country) :]
        args[key] = [country, target, "--no-color", "--no-clear"]
    if key == "toutatis":
        session = credentials.values(key).get("INSTAGRAM_SESSION_ID")
        if not session:
            raise ValueError("Configure an Instagram session under Tools.")
        args[key] = ["-u", target, "-s", session]
    return [str(executable(key)), *args[key]]


def observed_rate_limit(message):
    from readable_results import structured_value

    message="\n".join(line for line in message.splitlines() if not ('[+] Phone number used' in line and '[-] Phone number not used' in line))
    if re.search(r'^\s*\[x\]\s*[a-zA-Z0-9.-]+\s*$',message,re.M):return True
    parsed = structured_value(message)

    def walk(value, depth=0):
        if depth > 12:
            return False
        if isinstance(value, dict):
            for key, item in value.items():
                if (
                    str(key).lower().replace("_", "") in ("ratelimit", "ratelimited")
                    and item is True
                ):
                    return True
                if str(key).lower() in ("status", "status_code", "code") and item in (429, "429"):
                    return True
                if walk(item, depth + 1):
                    return True
        elif isinstance(value, list):
            return any(walk(item, depth + 1) for item in value)
        return False

    return (
        walk(parsed["value"])
        if parsed["structured"]
        else bool(
            re.search(
                r"\b429\b|too many requests|rate[ -]?limit(?:ed| exceeded| reached|ing)",
                message,
                re.I,
            )
        )
    )


def execute(job_id, args):
    with LOCK:
        if job_id not in JOBS or JOBS[job_id].get("status") == "cancelled":
            return
        JOBS[job_id].update(status="running", started_at=store.now(), started=time.time())
        if JOBS[job_id].get("id"):
            store.put(job_id, "addon", JOBS[job_id])
    status, message, code = "failed", "", None
    raw_message=None
    try:
        with (
            tempfile.TemporaryDirectory(prefix="menace-addon-") as work,
            tempfile.TemporaryFile() as output,
        ):
            if JOBS[job_id]["tool"] == "blackbird":
                for directory in ("data", "assets"):
                    source = ROOT / "addons/sources/blackbird" / directory
                    if source.is_dir():
                        shutil.copytree(source, Path(work) / directory)
            env = credentials.environment(JOBS[job_id]["tool"])
            secret_values = list(credentials.values(JOBS[job_id]["tool"]).values())
            if JOBS[job_id]["tool"]=="toutatis" and "-s" in args:secret_values.append(args[args.index("-s")+1])
            if JOBS[job_id]['tool'] in GITHUB_TOOLS:
                env = {k:v for k,v in env.items() if k in ('PATH','LANG','LC_ALL','SSL_CERT_FILE','SSL_CERT_DIR','SYSTEMROOT')}
                env['MENACE_ADDON_PREFIX'] = str(PREFIX)
                env['XDG_CONFIG_HOME'] = str(Path(work)/'config')
                env['UNFURL_REMOTE_LOOKUPS'] = 'false'
            env.update(HOME=work, NO_COLOR="1", TERM="dumb", PYTHONUNBUFFERED="1")
            # Each child is a separate process group so timeouts stop its children too.
            proc = subprocess.Popen(
                args,
                cwd=work,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + 180
            while proc.poll() is None:
                with LOCK:
                    cancelled = JOBS[job_id].get("cancel_requested", False)
                if (
                    cancelled
                    or time.monotonic() > deadline
                    or os.fstat(output.fileno()).st_size > 8_000_000
                ):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    status = "cancelled" if cancelled else "limited"
                    break
                time.sleep(0.2)
            else:
                status = "completed" if proc.returncode == 0 else "failed"
            code = proc.returncode
            output.seek(0)
            message = ANSI.sub("", output.read(1_000_000).decode("utf-8", "replace"))
            message = credentials.redact(message,secret_values)
            if JOBS[job_id]['tool']=='socialscan' and status=='completed':
                machine=Path(work)/'socialscan-results.json'
                if machine.is_file() and not machine.is_symlink() and machine.stat().st_size<=1_000_000:
                    try:
                        parsed=json.loads(machine.read_text())
                        if isinstance(parsed,(dict,list)):
                            raw_message=message
                            message=credentials.redact(json.dumps(parsed,ensure_ascii=False),secret_values)
                    except (ValueError,OSError):pass
            if JOBS[job_id]['tool'] in GITHUB_TOOLS:
                try:
                    structured = json.loads(message)
                    if structured.get('limited') and status != 'cancelled': status = 'limited'
                except (ValueError, AttributeError): pass
            if status == "cancelled":
                message += "\nCancelled by operator. Results may be incomplete."
            if status == "limited":
                message += "\nStopped at the 180-second or output limit. Results may be incomplete."
    except Exception as exc:
        message = f"Unable to run addon: {type(exc).__name__}"
    with LOCK:
        JOBS[job_id].update(
            status=status, output=message, exit_code=code, rate_limited=observed_rate_limit(message)
        )
        if raw_message is not None:JOBS[job_id]["raw_output"]=raw_message
        if JOBS[job_id].get("id"):
            JOBS[job_id]["finished_at"] = store.now()
            store.put(job_id, "addon", JOBS[job_id])
            rate_limited = observed_rate_limit(message)
            fields = dict(
                last_run=store.now(),
                last_status=status,
                exit_code=code,
                rate_limit_observed=rate_limited,
            )
            if status == "completed":
                fields["last_success"] = store.now()
            store.update_health(JOBS[job_id]["tool"], **fields)


@bp.get("/addons")
def page():
    from app import list_cases

    return render_template("addons.html", tools=catalog(), cases=list_cases())


@bp.get("/api/addons")
def inventory():
    return jsonify(catalog())


@bp.post("/api/addons/run")
def launch():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="Send a JSON object."), 400
    try:
        key = payload.get("tool", "")
        if not isinstance(key, str) or key not in TOOLS:
            raise ValueError("Select a tool.")
        target, kind, country = (payload.get(k, "") for k in ("target", "kind", "country"))
        if not all(isinstance(v, str) for v in (target, kind, country)):
            raise ValueError("Target, type and country must be text.")
        args = command(key, target, kind, country)
        if not executable(key).is_file():
            raise ValueError(
                "Addon is not installed in this runtime. Build the addon Docker image."
            )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    with LOCK:
        prune_jobs()
        for old in list(JOBS):
            if time.time() - JOBS[old]["created"] > 3600 and JOBS[old]["status"] not in (
                "queued",
                "running",
            ):
                del JOBS[old]
        if (
            sum(j["status"] in ("queued", "running") for j in JOBS.values()) >= 2
            or len(JOBS) >= 100
        ):
            return jsonify(
                error="Addon capacity reached. Wait for current searches to finish."
            ), 429
        job_id = uuid.uuid4().hex
        JOBS[job_id] = dict(
            id=job_id,
            tool=key,
            target=target,
            kind=kind,
            created=time.time(),
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            status="queued",
            output="",
            exit_code=None,
        )
    store.put(job_id, "addon", JOBS[job_id])
    POOL.submit(execute, job_id, args)
    return jsonify(id=job_id), 202


@bp.get("/api/addons/jobs/<job_id>")
def job(job_id):
    with LOCK:
        result = dict(JOBS[job_id]) if job_id in JOBS else store.get(job_id)
    if result is None:
        abort(404)
    from workspace_features import finding_section

    result["output"]=credentials.redact(result.get("output",""))
    if result.get("raw_output"):result["raw_output"]=credentials.redact(result["raw_output"])
    result.update(progress(result))
    result["section"] = finding_section(result)
    return jsonify(result)


def progress(job):
    end = time.time()
    if job.get("finished_at"):
        try:
            end = dt.datetime.fromisoformat(job["finished_at"]).timestamp()
        except ValueError:
            pass
    elapsed = max(0, round(end - job.get("started", job.get("created", end))))
    state = (
        "cancelling"
        if job.get("cancel_requested") and job["status"] == "running"
        else "rate-limited"
        if job.get("rate_limited") and job["status"] in ("completed", "failed")
        else job["status"]
    )
    return dict(elapsed_seconds=elapsed, display_state=state)


def cancel_job(job_id):
    """Caller holds LOCK. Queued jobs never spawn; running workers stop their process group."""
    job = JOBS.get(job_id)
    if job is None:
        saved = store.get(job_id)
        if not saved or "tool" not in saved:
            abort(404)
        return False
    if job["status"] not in ("queued", "running"):
        return False
    job["cancel_requested"] = True
    if job["status"] == "queued":
        job.update(status="cancelled", finished_at=store.now(), output="Cancelled before starting.")
    store.put(job_id, "addon", job)
    return True


@bp.post("/api/addons/jobs/<job_id>/cancel")
def cancel(job_id):
    with LOCK:
        changed = cancel_job(job_id)
    return jsonify(message="Cancellation requested." if changed else "Search has already finished.")
