"""Shared parsing and labels for human-facing case, console, and report values."""

import json
import re

NAMES = {
    "e164": "International number (E.164)",
    "geo": "Numbering region",
    "region": "Country / region",
    "valid": "Valid number",
    "possible": "Possible number",
    "spam": "Listed as spam",
    "operators_in_country": "Operators in country",
    "formatted": "Number formats",
    "timezones": "Time zones",
    "line_type": "Line type",
    "rfc3966": "Telephone link format",
    "mcc": "MCC",
    "mnc": "MNC",
}


def field_label(key):
    return NAMES.get(
        str(key),
        re.sub(r"([a-z])([A-Z])", r"\1 \2", str(key))
        .replace("_", " ")
        .replace("-", " ")
        .capitalize(),
    )


def display_scalar(value):
    if value is None:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value)
    return (
        text.replace("_", " ").capitalize() if re.fullmatch(r"[A-Z]+(?:_[A-Z]+)+", text) else text
    )


def structured_value(value):
    if isinstance(value, (dict, list, tuple)):
        return {"structured": True, "value": value}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, (dict, list)):
                return {"structured": True, "value": parsed}
        except (ValueError, RecursionError):
            pass
        lines = [line for line in value.splitlines() if line.strip()]
        if len(lines) > 1:
            try:
                parsed = [json.loads(line) for line in lines]
                if all(isinstance(item, (dict, list)) for item in parsed):
                    return {"structured": True, "value": parsed}
            except (ValueError, RecursionError):
                pass
    return {"structured": False, "value": value}


def readable_text(value, depth=0):
    if depth > 12:
        return "Further nested details omitted."
    value = structured_value(value)["value"]
    if isinstance(value, dict):
        return (
            "\n".join(
                f"{field_label(k)}: " + readable_text(v, depth + 1).replace("\n", "\n  ")
                for k, v in value.items()
            )
            or "No details returned."
        )
    if isinstance(value, (list, tuple)):
        return (
            "\n".join("- " + readable_text(v, depth + 1).replace("\n", "\n  ") for v in value)
            or "No results returned."
        )
    return display_scalar(value)
