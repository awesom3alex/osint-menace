"""Shared case operations and interactive terminal workflows."""

import copy
import argparse
import csv
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

import app as core
import discovery
from collectors import Options, PLATFORMS, RECORD_SOURCES
from terminal_output import Output, candidate_summary, print_summary, print_case
from dossier import SECTIONS, dossier_values
from cli_catalog import SITE_NAMES, platform_rows, catalog, catalog_section
from version import RELEASE_NAME

STATUSES = ("unreviewed", "relevant", "verified", "rejected")


def persist(case):
    case["updated_at"] = core.utc_now()
    core.save_case(case)


def select_numbers(text, count):
    if text.strip().lower() == "all":
        return list(range(count))
    numbers = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        ends = token.split("-")
        if len(ends) > 2:
            raise ValueError("Use numbers or ranges, such as 1,3-5.")
        start, end = int(ends[0]), int(ends[-1])
        if not 1 <= start <= end <= count:
            raise ValueError("Selection is outside the displayed list.")
        numbers.update(range(start - 1, end))
    return sorted(numbers)


def candidates(results):
    items = []
    for section in results:
        for kind in ("findings", "links"):
            for entry in section.get(kind, []):
                items.append((section, kind, entry))
    return items


def fingerprint(kind, entry):
    # Preserve URL path/query distinctions; only exact stored values are duplicates.
    value = entry.get("value")
    if isinstance(value, dict) and "retrieved_at" in value and "source_url" in value:
        value = {key: data for key, data in value.items() if key != "retrieved_at"}
    return kind, json.dumps(value, sort_keys=True)


def save_selected(case_id, results, indices, query, search_type):
    case = core.load_case(case_id)
    seen = {fingerprint(kind, entry) for search in case.get("searches", [])
            for section in search.get("results", []) for kind in ("findings", "links")
            for entry in section.get(kind, [])}
    available = candidates(results)
    added = skipped = 0
    for index in indices:
        section, kind, entry = available[index]
        key = fingerprint(kind, entry)
        if key in seen:
            skipped += 1
            continue
        selected = {"name": section["name"], "module_type": section.get("module_type", search_type),
                    "findings": [], "links": [], "notes": section.get("notes", [])}
        for metadata in ("category", "retrieved_at"):
            if metadata in section:
                selected[metadata] = section[metadata]
        selected[kind] = [copy.deepcopy(entry)]
        record = core.make_search_record(search_type, query, [selected], core.result_summary([selected]))
        record.update(review_status="unreviewed", analyst_notes="", tags=[])
        case.setdefault("searches", []).append(record)
        seen.add(key)
        added += 1
    if added:
        persist(case)
    return added, skipped


def find_item(case, item_id):
    for item in case.get("searches", []):
        if item["id"] == item_id:
            return item
    raise ValueError("Item was not found in this case.")


def review_item(case_id, item_id, status=None, notes=None, tags=None):
    case = core.load_case(case_id)
    item = find_item(case, item_id)
    if status is not None:
        if status not in STATUSES:
            raise ValueError("Unknown review status.")
        item["review_status"] = status
    if notes is not None:
        item["analyst_notes"] = notes
    if tags is not None:
        item["tags"] = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
    persist(case)


def report_case(case, statuses=None, item_ids=None):
    result = copy.deepcopy(case)
    result["searches"] = [item for item in case.get("searches", [])
                          if (not statuses or item.get("review_status", "unreviewed") in statuses)
                          and (item_ids is None or item["id"] in item_ids)]
    result["summary"] = {"searches": len(result["searches"]), **{
        key: sum(item.get("summary", {}).get(key, 0) for item in result["searches"])
        for key in ("findings", "links", "notes")}}
    return result


def read_targets(filename):
    text = sys.stdin.read() if filename == "-" else Path(filename).expanduser().read_text(encoding="utf-8-sig")
    if filename != "-" and Path(filename).suffix.lower() == ".csv":
        rows = csv.DictReader(text.splitlines())
        if "target" not in (rows.fieldnames or []):
            raise ValueError("CSV requires a target column.")
        targets = [row["target"].strip() for row in rows if row.get("target", "").strip()]
    else:
        targets = [line.strip() for line in text.splitlines() if line.strip()]
    if len(targets) > 250:
        raise ValueError("Batch limit is 250 targets. Split the input into smaller files.")
    if not targets:
        raise ValueError("Input contains no targets.")
    return list(dict.fromkeys(targets))


def run_targets(targets, kind="auto", pattern="", scan=False, ports="21,22,80,443,8080", mode="collect", options=None):
    completed, errors = [], []
    cancelled = False
    for number, target in enumerate(targets, 1):
        print(f"[{number}/{len(targets)}] Searching {target}", file=sys.stderr)
        try:
            completed.extend(discovery.run_search(kind, target, pattern, scan, ports, mode, options))
        except KeyboardInterrupt:
            cancelled = True
            print("Cancelled. Completed target results are retained.", file=sys.stderr)
            break
        except Exception as exc:
            errors.append({"target": target, "error": str(exc)})
            print(f"Source/search error: {exc}", file=sys.stderr)
    return completed, errors, cancelled


def edit_text(current):
    print("Enter text; a line containing only . finishes. /keep keeps existing text; /clear clears it; /editor opens $EDITOR.")
    first = input("text> ")
    if first == "/keep":
        return current
    if first == "/clear":
        return ""
    if first == "/editor":
        editor = shlex.split(os.environ.get("EDITOR", "vi"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.txt"
            path.write_text(current, encoding="utf-8")
            subprocess.run([*editor, str(path)], check=True)
            return path.read_text(encoding="utf-8")
    lines = []
    while first != ".":
        lines.append(first)
        first = input("text> ")
    return "\n".join(lines)


class Terminal:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.state_path = self.data_dir / "cli_state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        self.active = self.state.get("active_case")
        if self.active and not core.case_path(self.active).exists():
            self.active = None
        self.results = []
        self.query = ""
        self.kind = "auto"

    def save_state(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state["active_case"] = self.active
        self.state_path.write_text(json.dumps(self.state, indent=2))

    def choose(self, title, labels, back_label="Back"):
        output = Output()
        output.line()
        output.line(title)
        for number, label in enumerate(labels, 1):
            output.line(f"{number:>2}  {label}", 1)
        print("  0  " + back_label)
        while True:
            raw = input("> ").strip()
            if raw == "0" or not raw:
                return None
            if raw.isdigit() and 1 <= int(raw) <= len(labels):
                return int(raw) - 1
            print("Choose a displayed number, or 0 to go back.")

    def active_case(self):
        if not self.active:
            self.pick_case()
        if not self.active:
            raise ValueError("No active case selected.")
        return core.load_case(self.active)

    def pick_case(self):
        cases = [core.load_case(case["id"]) for case in core.list_cases()]
        index = self.choose("Select case", [case["name"] + (" [archived]" if case.get("archived") else "") for case in cases] + ["Create new case"])
        if index is None:
            return
        if index == len(cases):
            name = input("Case name (blank cancels): ").strip()
            if not name:
                return
            case = core.create_case(name)
        else:
            case = cases[index]
        self.active = case["id"]
        self.save_state()

    def search(self, batch=False):
        from menace import print_results
        types = [("username", "Username"), ("email", "Email"), ("phone", "Phone"),
                 ("name", "Full Name"), ("domain", "Domain"), ("ip", "IP Address"),
                 ("wallet", "Crypto Wallet"), ("url", "Public Page"),
                 ("records", "Records"), ("auto", "Auto Detect")]
        prompts = {"username": "Username / handle", "email": "Email address", "phone": "Phone number",
                   "name": "Full name", "domain": "Domain", "ip": "IP address", "wallet": "Wallet address",
                   "url": "Public page URL", "records": "Name / company / records query",
                   "auto": "Targets, separated by commas"}
        while True:
            index = self.choose("Run Search / 1. Search type", [title for _, title in types])
            if index is None:
                return
            kind, title = types[index]
            config = {**vars(Options()), **self.state.get("collector_options", {}), "excerpt": ""}
            settings = {"mode": "both" if kind in ("username", "auto") else "collect", "pattern": "", "scan": False,
                        "ports": self.state.get("ports", "21,22,80,443,8080")}
            change_type = False
            while not change_type:
                raw = input("Run Search / 2. " + ("Text/CSV input path" if batch else prompts[kind]) + " (blank goes back): ").strip()
                if not raw:
                    break
                try:
                    if batch:
                        targets = read_targets(raw)
                    else:
                        # Explicit targets remain intact (commas may occur in names and URLs).
                        targets = core.split_targets(raw) if kind == "auto" else [raw]
                    self.primary_options(kind, config)
                except (ValueError, OSError) as exc:
                    print("Input error: " + str(exc))
                    continue
                while True:
                    self.search_preview(kind, title, targets, config, settings)
                    action = self.choose("Run Search / 3. Ready", ["Run search", "Edit target", "Change search type", "Advanced options", "Select / change case"])
                    if action is None or action == 1:
                        break
                    if action == 2:
                        change_type = True
                        break
                    if action == 3:
                        self.advanced_options(kind, config, settings)
                        continue
                    if action == 4:
                        self.pick_case()
                        continue
                    try:
                        options = Options(**config)
                        options.validate()
                        if settings["scan"]:
                            core.osint_tool.parse_ports(settings["ports"])
                    except (ValueError, argparse.ArgumentTypeError) as exc:
                        print("Settings error: " + str(exc))
                        continue
                    results, errors, cancelled = run_targets(targets, kind, settings["pattern"],
                                                            settings["scan"], settings["ports"], settings["mode"], options)
                    self.results, self.query, self.kind = results, "\n".join(targets), kind
                    self.state["collector_options"] = {key: value for key, value in config.items() if key != "excerpt"}
                    self.save_state()
                    print_results(self.results)
                    print_summary(self.results, errors, cancelled)
                    self.review_results()
                    return

    def primary_options(self, kind, config):
        while kind in ("phone", "username"):
            try:
                if kind == "phone":
                    value = input("Default country [" + config["region"] + "]: ").strip()
                    candidate = {**config, "region": value.upper() or config["region"]}
                else:
                    selected = config.get("profile_sites", ())
                    Output().line("Candidate profile links: " + (", ".join(SITE_NAMES[site] for site in selected) if selected else f"all {len(SITE_NAMES)} platforms") + ". Customize coverage in Advanced options.")
                    value = input("Direct-check sources [" + ", ".join(config["platforms"]) + "] (" + ", ".join(PLATFORMS) + "): ").strip()
                    candidate = {**config, "platforms": tuple(dict.fromkeys(part.strip().lower() for part in value.split(",")))} if value else dict(config)
                Options(**candidate).validate()
                config.update(candidate)
                return
            except ValueError as exc:
                print("Input error: " + str(exc))

    def search_preview(self, kind, title, targets, config, settings):
        output = Output()
        output.line()
        output.line("Search review")
        output.field("Type", title)
        for target in targets[:5]:
            output.field("Target", target)
        if len(targets) > 5:
            output.field("Additional targets", len(targets) - 5)
        output.field("Output", {"collect": "Collected data", "links": "Research links only", "both": "Data and research links"}[settings["mode"]])
        if kind in ("username", "auto"):
            selected = config.get("profile_sites", ())
            output.field("Candidate platforms", (", ".join(SITE_NAMES[site] for site in selected) if selected else "All " + str(len(SITE_NAMES))) if settings["mode"] != "collect" else "Hidden (direct checks only)")
        if settings["mode"] != "links":
            if kind in ("username", "auto"):
                output.field("Username sources", ", ".join(config["platforms"]))
            if kind in ("name", "records", "auto"):
                output.field("Record sources", ", ".join(config["records_sources"]))
                output.field("Jurisdiction", config["jurisdiction"])
            if kind in ("phone", "auto"):
                output.field("Default country", config["region"])
            if kind in ("wallet", "auto"):
                output.field("Provider", config["wallet_source"])
            if kind in ("name", "records", "wallet", "auto"):
                output.field("Result limit", config["limit"])
            if kind in ("url", "auto"):
                output.field("Page text limit", config["text_limit"])
                if config["excerpt"]:
                    output.field("Page excerpt", config["excerpt"])
            output.field("Timeout", str(config["timeout"]) + " seconds")
        if settings["pattern"]:
            output.field("Forum pattern", settings["pattern"])
        if settings["scan"]:
            output.field("Authorized port scan", settings["ports"])
        output.field("Active case", core.load_case(self.active)["name"] if self.active else "None selected")
        output.line("Review results and select items to save after the search.", 2)

    def advanced_options(self, kind, config, settings):
        while True:
            fields = [("mode", "Output: collected data / links / both")]
            if settings["mode"] != "links":
                fields.append(("timeout", "Request timeout"))
                if kind in ("username", "auto"):
                    fields.append(("platforms", "Username sources"))
                if kind in ("phone", "auto"):
                    fields.append(("region", "Default phone country"))
                if kind in ("name", "records", "auto"):
                    fields.extend([("records_sources", "Record sources"), ("jurisdiction", "Records jurisdiction")])
                if kind in ("wallet", "auto"):
                    fields.append(("wallet_source", "Wallet provider"))
                if kind in ("name", "records", "wallet", "auto"):
                    fields.append(("limit", "Record / transaction limit"))
                if kind in ("url", "auto"):
                    fields.extend([("text_limit", "Page text limit"), ("excerpt", "Exact page excerpt")])
                if kind in ("ip", "auto"):
                    fields.append(("scan", "Authorized port scan"))
                    if settings["scan"]:
                        fields.append(("ports", "Scan ports"))
            if kind in ("username", "auto"):
                fields.append(("profile_sites", "Candidate profile platforms / coverage"))
                fields.append(("pattern", "Custom forum URL pattern"))
            index = self.choose("Advanced options", [label for _, label in fields])
            if index is None:
                return
            key = fields[index][0]
            try:
                if key == "mode":
                    choice = self.choose("Output", ["Collected data", "Research links only", "Data and research links"])
                    if choice is not None:
                        settings["mode"] = ("collect", "links", "both")[choice]
                        if settings["mode"] == "links":
                            settings["scan"] = False
                elif key == "scan":
                    settings["scan"] = input("Enable scanning for targets you are authorized to test? [y/N]: ").lower() == "y"
                elif key == "profile_sites":
                    rows = platform_rows()
                    for number, row in enumerate(rows, 1):
                        Output().line(f"[{number}] {row['name']} / " + ("Direct check available + candidate link" if row["direct_check"] else "Candidate link only"))
                    value = input("Profile links: all / numbers such as 1,3-5 (blank keeps): ").strip()
                    if value:
                        config["profile_sites"] = () if value.lower() == "all" else tuple(rows[number]["site"] for number in select_numbers(value, len(rows)))
                        if settings["mode"] == "collect":
                            settings["mode"] = "both"
                elif key in ("ports", "pattern"):
                    value = input(key.capitalize() + " [" + settings[key] + "] (blank keeps; /clear clears): ").strip()
                    if key == "ports" and value:
                        core.osint_tool.parse_ports(value)
                    if value:
                        settings[key] = "" if value == "/clear" else value
                else:
                    hints = {"platforms": ",".join(PLATFORMS), "records_sources": "wikidata,sec,courtlistener", "jurisdiction": "US/world", "wallet_source": "auto/blockstream/blockscout"}
                    current = config[key]
                    prompt = hints.get(key, key.replace("_", " "))
                    value = input(prompt + " [" + str(current) + "] (blank keeps; /clear clears): ").strip()
                    if not value:
                        continue
                    candidate = dict(config)
                    if key in ("platforms", "records_sources"):
                        candidate[key] = tuple(dict.fromkeys(part.strip().lower() for part in value.split(",")))
                    elif key in ("limit", "timeout", "text_limit"):
                        candidate[key] = int(value)
                    else:
                        candidate[key] = "" if value == "/clear" else value.upper() if key in ("region", "jurisdiction") and value.lower() != "world" else value
                    Options(**candidate).validate()
                    config.update(candidate)
            except (ValueError, argparse.ArgumentTypeError) as exc:
                print("Settings error: " + str(exc))

    def review_results(self):
        from menace import print_results
        if not self.results:
            print("Run a search first.")
            return
        while True:
            action = self.choose("Result workspace", ["View all results", "Select findings/links to save", "Export raw results as JSON", "View technical details"])
            if action is None:
                return
            if action == 0:
                print_results(self.results)
            elif action == 1:
                case = self.active_case()
                items = candidates(self.results)
                for number, (section, kind, entry) in enumerate(items, 1):
                    output = Output()
                    output.line(f"[{number}] {entry['label']}")
                    output.line(candidate_summary(entry), 4)
                indices = select_numbers(input("Select 1,3-5 / all (blank cancels): "), len(items))
                if not indices:
                    continue
                added, skipped = save_selected(case["id"], self.results, indices, self.query, self.kind)
                print(f"Added {added} items to {case['name']}; {skipped} already in case.")
            elif action == 2:
                path = Path(input("JSON output path: ").strip()).expanduser()
                with path.open("x", encoding="utf-8") as handle:
                    json.dump({"results": self.results, "summary": core.result_summary(self.results)}, handle, indent=2)
                print("Exported " + str(path))
            else:
                print_results(self.results, details=True)

    def workspace(self):
        while True:
            case = self.active_case()
            action = self.choose(case["name"], ["View case", "Review / filter items", "Rename case", "Edit case notes", "Archive / restore case", "Delete case"])
            if action is None:
                return
            if action == 0:
                print_case(case)
            elif action == 1:
                needle = input("Filter keyword, tag, status, or type (blank for all): ").lower()
                items = [item for item in case.get("searches", []) if needle in json.dumps(item).lower()]
                index = self.choose("Saved items", [item["query"][:65] + " | " + item.get("review_status", "unreviewed") for item in items])
                if index is not None:
                    self.item_menu(case, items[index])
            elif action == 2:
                name = input("New name (blank keeps current): ").strip()
                if name:
                    case["name"] = name
                    persist(case)
            elif action == 3:
                case["notes"] = edit_text(case.get("notes", ""))
                persist(case)
            elif action == 4:
                case["archived"] = not case.get("archived", False)
                persist(case)
                print("Archived." if case["archived"] else "Restored.")
            elif input("Type exact case name to delete: ") == case["name"]:
                core.case_path(case["id"]).unlink()
                self.active = None
                self.save_state()
                return
            else:
                print("Deletion cancelled.")

    def item_menu(self, case, item):
        from menace import print_results
        print_results(item.get("results", []))
        print("Notes: " + item.get("analyst_notes", ""))
        print("Tags: " + ", ".join(item.get("tags", [])))
        action = self.choose("Item actions", ["Set review status", "Edit analyst notes", "Edit tags", "Delete item"])
        if action == 0:
            index = self.choose("Status", STATUSES)
            if index is not None:
                review_item(case["id"], item["id"], status=STATUSES[index])
        elif action == 1:
            review_item(case["id"], item["id"], notes=edit_text(item.get("analyst_notes", "")))
        elif action == 2:
            review_item(case["id"], item["id"], tags=input("Comma-separated tags (blank clears): ").split(","))
        elif action == 3 and input("Delete this item? [y/N]: ").lower() == "y":
            core.remove_search_from_case(core.load_case(case["id"]), item["id"])

    def dossier(self):
        while True:
            case = self.active_case()
            values = dossier_values(case)
            filled = sum(bool(value.strip()) for value in values.values())
            index = self.choose(f"Dossier ({filled}/{len(values)} fields completed)", [title for title, _ in SECTIONS])
            if index is None:
                return
            title, fields = SECTIONS[index]
            field = self.choose(title, [label + (" [filled]" if values[key] else " [empty]") for key, label in fields])
            if field is None:
                continue
            key, label = fields[field]
            print(label + "\n" + values[key])
            value = edit_text(values[key])
            if len(value) > 20000:
                raise ValueError("Field exceeds 20,000 characters.")
            case.setdefault("dossier", {})[key] = value
            persist(case)
            print("Saved.")

    def report(self, demo=False):
        from demo import demo_case
        from menace import export_case
        case = demo_case() if demo else self.active_case()
        if not demo:
            index = self.choose("Include evidence", ["All items", "Relevant and verified", "Verified only", "Select individual items"])
            if index is None:
                return
            if index in (1, 2):
                case = report_case(case, statuses=["verified"] if index == 2 else ["relevant", "verified"])
            elif index == 3:
                items = case.get("searches", [])
                for number, item in enumerate(items, 1):
                    print(f"[{number}] {item['query']}")
                selected = select_numbers(input("Items (1,3-5 / all): "), len(items))
                case = report_case(case, item_ids=[items[number]["id"] for number in selected])
        print_case(case)
        formats = ("docx", "md", "json", "html")
        index = self.choose("Export format", formats)
        if index is None:
            return
        path = input("Output path (blank cancels): ").strip()
        if path:
            export_case(case, formats[index], path)

    def browse_catalog(self):
        while True:
            data, all_rows = catalog(self.data_dir)
            categories = [group["name"] for group in data.get("categories", [])]
            selected = self.choose("OSINT Links / category", ["All categories", *categories])
            if selected is None:
                return
            category = "" if selected == 0 else categories[selected - 1]
            query = input("Filter title, URL, or category (blank for all): ").strip()
            data, rows = catalog(self.data_dir, category, query)
            page = 0
            while True:
                start = page * 15
                for index, row in enumerate(rows[start:start + 15], start + 1):
                    Output().line(f"[{index}] {row['category']} / {row['title']}")
                    Output().line(row["url"], 4)
                Output().line(f"Page {page + 1} of {max(1, (len(rows) + 14) // 15)} / {len(rows)} links")
                Output().line("Source credit: " + data["source_title"] + " / " + data["source_url"])
                action = self.choose("Catalog actions", ["Next page", "Previous page", "Save selected links to case", "Change category / filter"])
                if action is None:
                    return
                if action == 0:
                    page = min(page + 1, max(0, (len(rows) - 1) // 15))
                elif action == 1:
                    page = max(0, page - 1)
                elif action == 2:
                    if not rows:
                        print("No matching links to save.")
                        continue
                    numbers = select_numbers(input("Link numbers (1,3-5 / all; blank cancels): "), len(rows))
                    if numbers:
                        case = self.active_case()
                        added, skipped = save_selected(case["id"], [catalog_section(rows)], numbers, "OSINT Links catalog", "catalog")
                        print(f"Added {added} links; {skipped} duplicates skipped.")
                else:
                    break

    def run(self):
        while True:
            try:
                name = core.load_case(self.active)["name"] if self.active else "None"
                action = self.choose(RELEASE_NAME + "\nActive case: " + name,
                                     ["Run search", "Review latest results", "Select / create case", "Case workspace",
                                      "Edit dossier", "Generate report", "Import targets", "Demo", "Settings", "OSINT Links catalog"], back_label="Exit")
                if action is None:
                    return 0
                if action == 0:
                    self.search()
                elif action == 1:
                    self.review_results()
                elif action == 2:
                    self.pick_case()
                elif action == 3:
                    self.workspace()
                elif action == 4:
                    self.dossier()
                elif action == 5:
                    self.report()
                elif action == 6:
                    self.search(batch=True)
                elif action == 7:
                    self.report(demo=True)
                elif action == 8:
                    print("Data directory: " + str(self.data_dir))
                    print("Editor: " + os.environ.get("EDITOR", "vi"))
                    setting = self.choose("Settings", ["Clear active case", "Set default scan ports", "Show command help"])
                    if setting == 0:
                        self.active = None
                        self.save_state()
                    elif setting == 1:
                        ports = input("Default ports (comma-separated or ranges): ").strip()
                        if ports:
                            core.osint_tool.parse_ports(ports)
                            self.state["ports"] = ports
                            self.save_state()
                    elif setting == 2:
                        from menace import parser
                        parser().print_help()
                elif action == 9:
                    self.browse_catalog()
            except (KeyboardInterrupt, EOFError):
                print("\nLeaving terminal. Saved case data is retained.")
                return 0
            except Exception as exc:
                print("Error: " + str(exc), file=sys.stderr)
