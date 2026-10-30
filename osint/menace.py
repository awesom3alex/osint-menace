#!/usr/bin/env python3
"""Terminal interface for OSINT Menace. No web server is started."""

import argparse
import json
import sys
from pathlib import Path

from werkzeug.exceptions import HTTPException

import app as core
import cli_workspace as workspace
import discovery
from cli_catalog import SITE_NAMES, catalog, catalog_section, platform_rows
from collectors import PLATFORMS, RECORD_SOURCES, Options
from demo import demo_case
from dossier import SECTIONS, dossier_values
from paths import DATA_ROOT
from terminal_output import Output, print_case, print_results
from version import RELEASE_NAME
from word_report import build_word_report


def export_case(case, kind, output):
    path = Path(output).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == "docx":
        with path.open("xb") as handle:
            handle.write(build_word_report(case).getvalue())
    else:
        if kind == "html":
            from bs4 import BeautifulSoup
            with core.app.test_request_context():
                state = case.get("investigation", {})
                if case.get("report_builder") is not None or state.get("assessments") or state.get("redaction", {}).get("enabled"):
                    from graph_reports import legend_ink
                    from report_builder import compose
                    html = core.render_template("report_preview.html", legend_ink=legend_ink, **compose(case))
                else:
                    html = core.render_template("report.html", case=case)
                soup = BeautifulSoup(html, "html.parser")
            for link in soup.find_all("link", rel="stylesheet"):
                filename = Path(link["href"]).name
                style = soup.new_tag("style")
                style.string = (Path(core.app.static_folder) / filename).read_text(encoding="utf-8")
                link.replace_with(style)
            for tag in soup.select(".report-actions, .report-controls, script"):
                tag.decompose()
            content = str(soup)
        else:
            content = json.dumps(case, indent=2) if kind == "json" else core.render_markdown_report(case)
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    print("Exported " + str(path))


def parser():
    root = argparse.ArgumentParser(description="OSINT Menace terminal interface")
    root.add_argument("--version", action="version", version=RELEASE_NAME)
    root.add_argument("--data-dir", type=Path, default=DATA_ROOT,
                      help="Data directory shared with the web app")
    commands = root.add_subparsers(dest="command")
    search = commands.add_parser("search", help="Run a search without a web server")
    search.add_argument("query")
    search.add_argument("--type", choices=["auto", *core.SEARCH_TYPES, "url", "records"], default="auto")
    search.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    search.add_argument("--case", help="Save results to this case ID")
    search.add_argument("--link", type=int, action="append", help="Save only numbered links; repeatable for a single target")
    search.add_argument("--finding", type=int, action="append", help="Save only numbered findings; repeatable for a single section")
    search.add_argument("--forum-pattern", default="")
    search.add_argument("--ports", default="21,22,80,443,8080")
    search.add_argument("--allow-port-scan", action="store_true")
    cases = commands.add_parser("cases", help="List saved cases")
    cases.add_argument("--json", action="store_true")
    create = commands.add_parser("create", help="Create a case")
    create.add_argument("name")
    create.add_argument("--notes", default="")
    show = commands.add_parser("show", help="Show a case")
    show.add_argument("case_id")
    dossier = commands.add_parser("dossier", help="View or update a dossier field")
    dossier.add_argument("case_id", nargs="?")
    dossier.add_argument("--fields", action="store_true")
    dossier.add_argument("--field")
    dossier.add_argument("--value")
    dossier.add_argument("--json", action="store_true", help="Print dossier fields as JSON")
    export = commands.add_parser("export", help="Export Word, Markdown, JSON, or standalone HTML")
    export.add_argument("case_id", help="Case ID or demo")
    export.add_argument("--format", choices=["docx", "md", "json", "html"], default="docx")
    export.add_argument("--output", required=True)
    export.add_argument("--status", choices=workspace.STATUSES, action="append")
    export.add_argument("--item", action="append", help="Include only these item IDs")
    items = commands.add_parser("items", help="List and filter case items")
    items.add_argument("case_id")
    items.add_argument("--filter", default="")
    items.add_argument("--json", action="store_true")
    review = commands.add_parser("review", help="Edit an item's status, notes, and tags")
    review.add_argument("case_id")
    review.add_argument("item_id")
    review.add_argument("--status", choices=workspace.STATUSES)
    review.add_argument("--notes")
    review.add_argument("--tags", help="Comma-separated tags; empty string clears")
    remove = commands.add_parser("remove", help="Remove an item from a case")
    remove.add_argument("case_id")
    remove.add_argument("item_id")
    remove.add_argument("--yes", action="store_true", help="Confirm deletion")
    update = commands.add_parser("update-case", help="Rename, annotate, archive, or restore a case")
    update.add_argument("case_id")
    update.add_argument("--name")
    update.add_argument("--notes")
    state = update.add_mutually_exclusive_group()
    state.add_argument("--archive", action="store_true")
    state.add_argument("--restore", action="store_true")
    delete = commands.add_parser("delete-case", help="Delete a case by exact-name confirmation")
    delete.add_argument("case_id")
    delete.add_argument("--confirm-name", required=True)
    batch = commands.add_parser("batch", help="Read targets from text, CSV (target column), or stdin (-)")
    batch.add_argument("input")
    batch.add_argument("--type", choices=["auto", *core.SEARCH_TYPES, "url", "records"], default="auto")
    batch.add_argument("--case")
    batch.add_argument("--json", action="store_true")
    batch.add_argument("--forum-pattern", default="")
    batch.add_argument("--ports", default="21,22,80,443,8080")
    batch.add_argument("--allow-port-scan", action="store_true")
    for command in (search, batch):
        command.add_argument("--mode", choices=("collect", "links", "both"), default=None,
                             help="Default: both for username/auto, collect for other types")
        command.add_argument("--platform", choices=PLATFORMS, action="append", help="Direct API checks (not the full candidate-link list)")
        command.add_argument("--profile-site", choices=["all", *SITE_NAMES], action="append", help="Candidate profile links; repeat or use all")
        command.add_argument("--region", default="US", help="Phone parsing region (ISO two-letter code)")
        command.add_argument("--limit", type=int, default=5, help="Maximum records or transactions returned (1-25)")
        command.add_argument("--timeout", type=int, default=10, help="Per-connection timeout in seconds (1-60)")
        command.add_argument("--text-limit", type=int, default=4000, help="Maximum page text characters (100-20000)")
        command.add_argument("--record-source", choices=RECORD_SOURCES, action="append")
        command.add_argument("--jurisdiction", choices=("US", "world"), default="US")
        command.add_argument("--wallet-source", choices=("auto", "blockstream", "blockscout"), default="auto")
        command.add_argument("--excerpt", default="", help="For URL capture, keep this exact excerpt if present in the page")
        command.add_argument("--details", action="store_true", help="Show source URLs, HTTP metadata, hashes, and technical fields")
    commands.add_parser("demo", help="Show the fictional demo dossier")
    platforms = commands.add_parser("platforms", help="List all username platforms and direct-check coverage")
    platforms.add_argument("--json", action="store_true")
    links = commands.add_parser("links", help="Browse/search the full OSINT Links catalog")
    links.add_argument("--category", default="")
    links.add_argument("--filter", default="")
    links.add_argument("--json", action="store_true")
    links.add_argument("--case")
    links.add_argument("--select", help="Save selected numbered catalog entries, such as 1,3-5")
    return root


def execute(args):
    core.CASES_DIR = args.data_dir.expanduser().resolve() / "cases"
    if args.command == "search":
        if not args.query.strip():
            raise ValueError("Enter a target.")
        if (args.link or args.finding) and not args.case:
            raise ValueError("--link/--finding requires --case.")
        case = core.load_case(args.case) if args.case else None
        options = collector_options(args)
        results = discovery.run_search(args.type, args.query, args.forum_pattern,
                                       args.allow_port_scan, args.ports, args.mode, options)
        indices = list(range(len(workspace.candidates(results))))
        if args.link:
            if len(results) != 1:
                raise ValueError("Link selection requires a single target.")
            links = results[0].get("links", [])
            if any(number < 1 or number > len(links) for number in args.link):
                raise ValueError("Link number is outside the result list.")
            offset = len(results[0].get("findings", []))
            indices = [offset + number - 1 for number in dict.fromkeys(args.link)]
        if args.finding:
            if len(results) != 1:
                raise ValueError("--finding requires one result section. Use the interactive selector for multi-source results.")
            if any(number < 1 or number > len(results[0].get("findings", [])) for number in args.finding):
                raise ValueError("Finding number outside the result list.")
            indices = (indices if args.link else []) + [number - 1 for number in dict.fromkeys(args.finding)]
        if case is not None:
            added, skipped = workspace.save_selected(case["id"], results, indices, args.query, args.type)
            print(f"Added {added} items to {case['name']}; {skipped} duplicates skipped.", file=sys.stderr)
        if args.json:
            print(json.dumps({"results": results, "summary": core.result_summary(results)}, indent=2))
        else:
            print_results(results, details=args.details)
        if collector_failed(results):
            return 1
    elif args.command == "cases":
        cases = core.list_cases()
        if args.json:
            print(json.dumps(cases, indent=2))
        else:
            for case in cases:
                print(case["id"] + "  " + case["name"] + "  (" + str(case["search_count"]) + " items)")
            if not cases:
                print("No saved cases. Use create to start a case.")
    elif args.command == "platforms":
        if args.json:
            print(json.dumps(platform_rows(), indent=2))
        else:
            for row in platform_rows():
                Output().line(row["site"] + " / " + row["name"] + " / " + ("Direct API check + candidate link" if row["direct_check"] else "Candidate link; not automatically checked"))
    elif args.command == "links":
        data, rows = catalog(args.data_dir, args.category, args.filter)
        if args.select and not args.case:
            raise ValueError("--select requires --case.")
        if args.case:
            if not args.select:
                raise ValueError("Choose catalog entries with --select.")
            selected = workspace.select_numbers(args.select, len(rows))
            section = catalog_section(rows)
            added, skipped = workspace.save_selected(args.case, [section], selected, "OSINT Links catalog", "catalog")
            print(f"Added {added}; {skipped} duplicates skipped.", file=sys.stderr)
        if args.json:
            print(json.dumps({"source_title": data["source_title"], "source_url": data["source_url"], "links": rows}, indent=2))
        else:
            for number, row in enumerate(rows, 1):
                Output().line(f"[{number}] {row['category']} / {row['title']}")
                Output().line(row["url"], 4)
            Output().line(f"{len(rows)} links. Source credit: {data['source_title']} / {data['source_url']}")
    elif args.command == "create":
        if not args.name.strip():
            raise ValueError("Enter a case name.")
        case = core.create_case(args.name, args.notes)
        print(case["id"] + "  " + case["name"])
    elif args.command in ("show", "demo"):
        case = demo_case() if args.command == "demo" else core.load_case(args.case_id)
        print_case(case)
    elif args.command == "export":
        case = demo_case() if args.case_id == "demo" else core.load_case(args.case_id)
        case = workspace.report_case(case, args.status, args.item)
        export_case(case, args.format, args.output)
    elif args.command == "items":
        case = core.load_case(args.case_id)
        items = [item for item in case.get("searches", []) if args.filter.lower() in json.dumps(item).lower()]
        if args.json:
            print(json.dumps(items, indent=2))
        else:
            for item in items:
                print(item["id"] + " | " + item.get("review_status", "unreviewed") + " | " + item["query"])
    elif args.command == "review":
        workspace.review_item(args.case_id, args.item_id, args.status, args.notes,
                              args.tags.split(",") if args.tags is not None else None)
        print("Item updated.")
    elif args.command == "remove":
        if not args.yes:
            raise ValueError("Use --yes to confirm item removal.")
        if not core.remove_search_from_case(core.load_case(args.case_id), args.item_id):
            raise ValueError("Item not found.")
        print("Item removed.")
    elif args.command == "update-case":
        case = core.load_case(args.case_id)
        if args.name is not None:
            if not args.name.strip():
                raise ValueError("Case name cannot be empty.")
            case["name"] = args.name.strip()
        if args.notes is not None:
            case["notes"] = args.notes
        if args.archive or args.restore:
            case["archived"] = args.archive
        workspace.persist(case)
        print("Case updated.")
    elif args.command == "delete-case":
        case = core.load_case(args.case_id)
        if case.get("is_demo") or args.confirm_name != case["name"]:
            raise ValueError("Type the exact name of a saved case to confirm deletion.")
        core.case_path(args.case_id).unlink()
        print("Case deleted.")
    elif args.command == "batch":
        if args.case:
            core.load_case(args.case)
        targets = workspace.read_targets(args.input)
        results, errors, cancelled = workspace.run_targets(targets, args.type, args.forum_pattern,
                                                           args.allow_port_scan, args.ports,
                                                           args.mode or ("both" if args.type in ("auto", "username") else "collect"), collector_options(args))
        if args.case and results:
            added, skipped = workspace.save_selected(args.case, results, list(range(len(workspace.candidates(results)))),
                                                      "\n".join(targets), args.type)
            print(f"Added {added}; skipped {skipped} duplicates.", file=sys.stderr)
        if args.json:
            print(json.dumps({"results": results, "errors": errors, "cancelled": cancelled}, indent=2))
        else:
            print_results(results, details=args.details)
        if cancelled:
            return 130
        if errors or collector_failed(results):
            return 1
    elif args.command == "dossier":
        labels = dict(field for _, fields in SECTIONS for field in fields)
        if args.fields:
            for key, label in labels.items():
                print(key + ": " + label)
            return
        if not args.case_id:
            raise ValueError("Provide a case ID or --fields.")
        case = core.load_case(args.case_id)
        if args.field:
            if args.field not in labels or args.value is None:
                raise ValueError("Supply a valid --field and --value; use dossier --fields for names.")
            if len(args.value) > 20000:
                raise ValueError("Field exceeds 20,000 characters.")
            case.setdefault("dossier", {})[args.field] = args.value
            case["updated_at"] = core.utc_now()
            core.save_case(case)
            print("Dossier saved.")
        else:
            if args.json:
                print(json.dumps(dossier_values(case), indent=2))
            else:
                Output().value(dossier_values(case))


def collector_options(args):
    options = Options(platforms=tuple(args.platform or PLATFORMS), region=args.region,
                      limit=args.limit, timeout=args.timeout, text_limit=args.text_limit,
                      records_sources=tuple(args.record_source or ("wikidata",)),
                      jurisdiction=args.jurisdiction, wallet_source=args.wallet_source, excerpt=args.excerpt,
                      profile_sites=tuple(site for site in (args.profile_site or ()) if site != "all") if "all" not in (args.profile_site or ()) else ())
    options.validate()
    return options


def collector_failed(results):
    return any(isinstance(finding.get("value"), dict) and finding["value"].get("status") in
               ("error", "blocked", "rate_limited", "configuration_required", "invalid", "unsupported")
               for section in results for finding in section.get("findings", []))


def main(argv=None):
    root = parser()
    args = root.parse_args(argv)
    try:
        if args.command is None:
            root.set_defaults(data_dir=args.data_dir)
            if not sys.stdin.isatty():
                root.print_help()
                return 0
            core.CASES_DIR = args.data_dir.expanduser().resolve() / "cases"
            return workspace.Terminal(args.data_dir).run()
        return execute(args) or 0
    except (ValueError, OSError, HTTPException) as exc:
        print("Error: " + str(exc), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
