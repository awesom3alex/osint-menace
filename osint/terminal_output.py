"""Human-readable rendering shared by both command-line entry points."""

import datetime as dt
import re
import shutil
import textwrap

LABELS = {
    "e164": "E.164 format", "international": "International format",
    "possible": "Possible number", "valid": "Valid number", "region": "Country code",
    "country_calling_code": "Calling code", "number_type": "Number type",
    "region_description": "Numbering region", "original_carrier": "Original carrier",
    "time_zones": "Time zones", "identity_verified": "Identity verified",
    "login": "Username", "displayName": "Display name", "public_repos": "Public repositories",
    "followersCount": "Followers", "postsCount": "Posts", "createdAt": "Created",
    "created_at": "Created", "balance_eth": "Balance (ETH)", "balance_wei": "Balance (wei)",
    "confirmed_btc": "Confirmed balance (BTC)", "confirmed_satoshis": "Confirmed balance (satoshis)",
    "pending_delta_satoshis": "Pending change (satoshis)", "confirmed_transaction_count": "Confirmed transactions",
    "txid": "Transaction ID", "hash": "Transaction hash", "block_time": "Block time (Unix seconds)",
    "body_sha256": "Response SHA-256", "text": "Page text", "text_truncated": "Text truncated",
    "analyst_selected_excerpt": "Selected excerpt", "cik_str": "SEC CIK", "caseName": "Case name",
    "dateFiled": "Filed", "absolute_url": "Record path", "concepturi": "Record URL",
    "ens_domain_name": "ENS name", "is_contract": "Contract account",
}
TECHNICAL = {"analysis_mode", "metadata_version", "body_sha256", "bytes", "content_type", "balance_wei", "confirmed_satoshis"}
ENUMS = {"fixed_line_or_mobile": "Fixed line or mobile", "fixed_line": "Fixed line", "mobile": "Mobile",
         "offline_metadata": "Offline metadata", "unknown": "Unknown", "closed_or_filtered": "Closed or filtered"}
STATUSES = {"found": "Found", "not_found": "Not found", "no_matches": "No matches", "rate_limited": "Rate limited",
            "configuration_required": "Configuration needed", "blocked": "Blocked", "error": "Error",
            "invalid": "Invalid input", "unsupported": "Unsupported"}


def clean(value):
    # Source content must not execute terminal control/escape sequences.
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", str(value))
    return "".join(char for char in text if char in "\n\t" or (ord(char) >= 32 and not 127 <= ord(char) <= 159))


def label(key):
    if str(key).upper() in ("A", "AAAA", "MX", "NS", "TXT", "CAA", "PTR"):
        return str(key).upper()
    return LABELS.get(key, str(key).replace("_", " ").capitalize())


def scalar(value):
    if value is None or value == "":
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str):
        return ENUMS.get(value, value)
    return str(value)


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError, AttributeError):
        return scalar(value)


class Output:
    def __init__(self, details=False, width=None):
        self.details = details
        self.width = max(24, min(width or shutil.get_terminal_size((88, 24)).columns, 110))

    def line(self, text="", indent=0):
        prefix = " " * min(indent, self.width // 3)
        for paragraph in clean(text).splitlines() or [""]:
            lines = textwrap.wrap(paragraph.expandtabs(4), width=self.width,
                                  initial_indent=prefix, subsequent_indent=prefix,
                                  break_long_words=True, break_on_hyphens=False)
            print("\n".join(lines) if lines else "")

    def field(self, name, value, indent=2):
        self.line(name + ": " + clean(scalar(value)), indent)

    def value(self, value, indent=4):
        if isinstance(value, dict):
            if not value:
                self.line("No details returned.", indent)
            for key, item in value.items():
                if key in TECHNICAL and not self.details:
                    continue
                if key in ("from", "to") and isinstance(item, dict) and item.get("hash") and not self.details:
                    self.field(key.capitalize() + " address", item["hash"], indent)
                    continue
                if isinstance(item, (dict, list)):
                    if isinstance(item, list) and all(not isinstance(element, (dict, list)) for element in item):
                        self.field(label(key), ", ".join(scalar(element) for element in item) or "Not available", indent)
                    else:
                        self.line(label(key) + ":", indent)
                        self.value(item, indent + 2)
                else:
                    name = "Transaction value (wei)" if key == "value" and "hash" in value and "block_number" in value else label(key)
                    if key in ("timestamp", "createdAt", "created_at", "updated_at") and isinstance(item, str):
                        item = timestamp(item)
                    self.field(name, "+" + str(item) if key == "country_calling_code" else item, indent)
        elif isinstance(value, list):
            if not value:
                self.line("No records returned.", indent)
            for number, item in enumerate(value, 1):
                if isinstance(item, (dict, list)):
                    self.line("Record " + str(number), indent)
                    self.value(item, indent + 2)
                    self.line()
                else:
                    self.line("- " + scalar(item), indent)
        else:
            self.line(scalar(value), indent)

    def finding(self, finding, number):
        value = finding.get("value")
        self.line("Finding " + str(number) + " / " + finding.get("label", "Result"), 2)
        if isinstance(value, dict) and "status" in value and "retrieved_at" in value:
            status = STATUSES.get(value["status"], value["status"])
            data = value.get("data")
            if isinstance(data, dict) and data.get("analysis_mode") == "offline_metadata" and value["status"] == "found":
                status = "Valid number format"
            self.field("Status", status, 4)
            if value.get("message"):
                self.field("Details", value["message"], 4)
            if data is not None:
                self.value(data)
            source = finding.get("source")
            if source:
                self.field("Source", source, 4)
            self.field("Checked", timestamp(value["retrieved_at"]), 4)
            if self.details:
                for key in ("source_url", "http_status", "retry-after", "x-ratelimit-reset"):
                    if key in value:
                        self.field(label(key), value[key], 4)
        else:
            self.value(value)
            if finding.get("source"):
                self.field("Source", finding["source"], 4)
        self.line()


def print_results(results, details=False, width=None):
    output = Output(details, width)
    for section in results:
        output.line()
        output.line(section.get("name", "Results"))
        output.line("-" * output.width)
        for number, finding in enumerate(section.get("findings", []), 1):
            output.finding(finding, number)
        for number, link in enumerate(section.get("links", []), 1):
            category = {"candidate_profile": "Candidate profile", "search_link": "Search link", "research_link": "Research link"}.get(link.get("category"), "Research link")
            output.line(f"Link {number} / {category} / {link.get('label', 'Source')}", 2)
            output.line(link.get("value", ""), 4)
        if section.get("notes"):
            output.line("Notes", 2)
            for note in dict.fromkeys(section["notes"]):
                output.line("- " + note, 4)
        if not any(section.get(key) for key in ("findings", "links", "notes")):
            output.line("No findings.", 2)


def candidate_summary(entry):
    value = entry.get("value")
    if isinstance(value, dict) and "status" in value:
        data = value.get("data")
        if isinstance(data, dict):
            primary = next((data[key] for key in ("international", "login", "handle", "title", "balance_eth", "confirmed_btc") if data.get(key)), None)
        elif isinstance(data, list):
            primary = str(len(data)) + " records"
        else:
            primary = None
        return STATUSES.get(value["status"], value["status"]) + (" / " + str(primary) if primary else "")
    if isinstance(value, dict):
        return str(len(value)) + " detail fields"
    if isinstance(value, list):
        return str(len(value)) + " values"
    return clean(scalar(value))


def print_summary(results, errors=(), cancelled=False):
    statuses = [finding["value"]["status"] for section in results for finding in section.get("findings", [])
                if isinstance(finding.get("value"), dict) and "status" in finding["value"]]
    problems = sum(status in ("error", "blocked", "rate_limited", "configuration_required", "invalid", "unsupported") for status in statuses) + len(errors)
    text = f"Completed: {len(results)} result groups | Issues: {problems}"
    if cancelled:
        text += " | Cancelled; completed results retained"
    Output().line(text)


def print_case(case):
    from dossier import SECTIONS, dossier_values
    output = Output()
    output.line(case["name"])
    output.field("Case ID", case["id"])
    output.field("Case notes", case.get("notes"))
    values = dossier_values(case)
    for title, fields in SECTIONS:
        if any(values[key] for key, _ in fields):
            output.line()
            output.line(title)
            for key, name in fields:
                if values[key]:
                    output.field(name, values[key])
    for record in case.get("searches", []):
        output.line()
        output.field("Saved item", record["id"])
        output.field("Review", record.get("review_status", "unreviewed"))
        if record.get("analyst_notes"):
            output.field("Analyst notes", record["analyst_notes"])
        if record.get("tags"):
            output.field("Tags", ", ".join(record["tags"]))
        print_results(record.get("results", []))
