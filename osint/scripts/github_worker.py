"""Restricted adapters for pinned research tools; launched inside isolated addon runtimes."""

import argparse
import contextlib
import io
import json
import os
import re
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path(os.environ.get("MENACE_ADDON_PREFIX", "/opt/addons"))
MAX_OUTPUT = 1_000_000


def run(args):
    # All children stay in the outer addon's cancellable process group.
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(
            args, stdout=output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
        )
        deadline = time.monotonic() + 145
        limited = False
        while proc.poll() is None:
            if time.monotonic() > deadline or os.fstat(output.fileno()).st_size >= 8_000_000:
                proc.kill()
                limited = True
                break
            time.sleep(0.1)
        proc.wait()
        size = os.fstat(output.fileno()).st_size
        output.seek(0)
        text = output.read(MAX_OUTPUT).decode("utf-8", "replace")
    return proc.returncode, text, limited or size > MAX_OUTPUT


def entry(label, value, source_url="", **extra):
    return dict(label=str(label)[:200], value=value, source_url=source_url, **extra)


def unfurl(target):
    # Enforce offline behavior even if a future parser ignores remote_lookups=False.
    def offline(*args, **kwargs):
        raise OSError("Remote lookups are disabled in Menace URL Inspector.")

    socket.create_connection = offline
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    socket.getaddrinfo = offline
    socket.socket.sendto = offline
    socket.socket.send = offline
    socket.socket.sendall = offline
    logs = io.StringIO()
    with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
        from unfurl.core import Unfurl
        from unfurl.utils import strip_hover_markup

        parser = Unfurl(remote_lookups=False)
        parser.add_to_queue(data_type="url", key=None, value=target)
        parser.parse_queue()
        records = [
            entry(
                n.label or n.data_type,
                dict(
                    value=str(n.value)[:10000],
                    type=n.data_type,
                    key=n.key,
                    explanation=strip_hover_markup(n.hover or ""),
                    node_id=n.node_id,
                    parent_id=n.parent_id,
                ),
            )
            for n in list(parser.nodes.values())[:500]
        ]
    return dict(
        records=records,
        logs=logs.getvalue()[-10000:],
        limited=len(parser.nodes) > 500,
        mode="Local URL decoding; remote lookups disabled",
        providers=[],
    )


def external(tool, target):
    binary = (
        PREFIX / "bin/subfinder"
        if tool == "subfinder"
        else PREFIX / tool / "bin" / ("theHarvester" if tool == "theharvester" else tool)
    )
    configs = {
        "waymore": (
            [
                str(binary),
                "-i",
                target,
                "-mode",
                "U",
                "--providers",
                "wayback,commoncrawl",
                "-lcc",
                "1",
                "-lr",
                "2",
                "-r",
                "0",
                "--stream",
                "-oU",
                "urls.txt",
            ],
            ["Wayback Machine", "Common Crawl"],
        ),
        "subfinder": (
            [
                str(binary),
                "-d",
                target,
                "-s",
                "crtsh,hackertarget",
                "-silent",
                "-json",
                "-cs",
                "-duc",
                "-rl",
                "2",
                "-timeout",
                "10",
                "-max-time",
                "2",
                "-max-results",
                "100",
                "-rsr",
                "1000000",
            ],
            ["crt.sh", "HackerTarget"],
        ),
        "dnstwist": (
            [
                str(binary),
                "--format",
                "json",
                "--registered",
                "--threads",
                "4",
                "--fuzzers",
                "hyphenation,omission,transposition",
                target,
            ],
            ["Configured system DNS resolver"],
        ),
        "theharvester": (
            [str(binary), "-d", target, "-b", "crtsh,otx", "-l", "100", "-q", "-f", "harvest"],
            ["crt.sh", "AlienVault OTX"],
        ),
    }
    args, providers = configs[tool]
    if tool in ("waymore", "theharvester"):
        args = [
            str(PREFIX / tool / "bin/python"),
            str(ROOT / "scripts/github_upstream.py"),
            tool,
            *args[1:],
        ]
    code, output, limited = run(args)
    records = []
    if tool == "waymore":
        for line in output.splitlines():
            if line.startswith(("http://", "https://")):
                records.append(
                    entry(
                        "Archived URL candidate",
                        line[:4096],
                        "https://web.archive.org/web/*/" + quote(line, safe=":/?=&%"),
                        historical=True,
                    )
                )
    elif tool == "subfinder":
        for line in output.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("host"), str):
                records.append(
                    entry(
                        "Domain",
                        row["host"],
                        "",
                        provider_details=row.get("sources", row.get("source", [])),
                    )
                )
    elif tool == "dnstwist":
        try:
            rows = json.loads(output)
        except ValueError:
            rows = []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and row.get("domain"):
                records.append(
                    entry(
                        "Look-alike domain",
                        row,
                        assessment="Candidate only; DNS does not establish malicious intent.",
                    )
                )
    else:
        path = Path("harvest.json")
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_OUTPUT:
            rows = json.loads(path.read_text())
            for key, label in [
                ("emails", "Email"),
                ("hosts", "Domain"),
                ("ips", "IP"),
                ("people", "Reported name"),
                ("interesting_urls", "URL"),
            ]:
                for value in rows.get(key, [])[:500]:
                    records.append(entry(label, value))
    unique = []
    seen = set()
    for row in records:
        fingerprint = json.dumps(row, sort_keys=True)
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(row)
    result = dict(
        records=unique[:500],
        logs=output[-10000:],
        rate_limited=bool(
            re.search(
                r"(?:HTTP|status)[^\n]{0,20}429|rate[ -]?limited|too many requests|rate limit exceeded",
                output,
                re.I,
            )
        ),
        limited=limited or len(unique) > 500,
        mode="DNS lookups only; no HTTP content comparison"
        if tool == "dnstwist"
        else "Selected third-party sources; no target website requests",
        providers=providers,
    )
    if code:
        result["error"] = (
            "Upstream tool exited with code " + str(code) + ". Results may be incomplete."
        )
    return result, code


def metadata(path):
    executable = PREFIX / "bin/exiftool"
    code, output, limited = run([str(executable), "-json", "-G1", "-s", "-n", "--", str(path)])
    if code:
        raise ValueError("ExifTool could not read this file.")
    rows = json.loads(output)
    fields = rows[0] if rows and isinstance(rows[0], dict) else {}
    # Temporary paths and filesystem timestamps describe processing, not evidence.
    fields = {
        k: v
        for k, v in fields.items()
        if not k.startswith(("File:", "System:")) and k != "SourceFile"
    }
    return dict(
        records=[entry(k, v) for k, v in list(fields.items())[:300]],
        limited=limited or len(fields) > 300,
        mode="Local read-only metadata; original bytes unchanged",
        providers=[],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tool",
        required=True,
        choices=["unfurl", "waymore", "subfinder", "dnstwist", "theharvester", "exiftool"],
    )
    parser.add_argument("--target", default="")
    parser.add_argument("--file", default="")
    args = parser.parse_args()
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
    except (ImportError, ValueError, OSError):
        pass
    code = 0
    try:
        if args.tool == "unfurl":
            result = unfurl(args.target)
        elif args.tool == "exiftool":
            result = metadata(Path(args.file))
        else:
            result, code = external(args.tool, args.target)
    except Exception as exc:
        result = dict(records=[], error=type(exc).__name__ + ": " + str(exc)[:500], providers=[])
        code = 1
    print(json.dumps(dict(menace_github_tool=args.tool, **result), ensure_ascii=False, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
