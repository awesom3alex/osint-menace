"""Offline, bounded extraction from one original RFC 5322 .eml message."""

import argparse
import contextlib
import hashlib
import io
import ipaddress
import json
import re
import socket
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

MAX_FILE = 5_000_000
MAX_PARTS = 200
MAX_DEPTH = 20
MAX_TEXT = 60000


class HTMLText(HTMLParser):
    """Collect inert text and URL attributes without rendering or fetching HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.urls = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "template"):
            self.hidden += 1
        if not self.hidden:
            for key, value in attrs:
                if key in ("href", "src", "action") and value:
                    self.urls.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "template") and self.hidden:
            self.hidden -= 1
        if tag in ("p", "div", "br", "li", "tr"):
            self.text.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def preflight(message):
    """Limit MIME structure before invoking upstream parsing."""
    stack = [(message, 0)]
    parts = 0
    headers = 0
    header_bytes = 0
    while stack:
        part, depth = stack.pop()
        parts += 1
        if parts > MAX_PARTS or depth > MAX_DEPTH:
            raise ValueError("Email exceeds 200 MIME parts or 20 nesting levels.")
        for key, value in part.raw_items():
            headers += 1
            header_bytes += len(key) + len(value)
        if headers > 1000 or header_bytes > 200000:
            raise ValueError("Email header count or size exceeds the review limit.")
        payload = part.get_payload()
        if isinstance(payload, list):
            stack.extend((child, depth + 1) for child in payload)


def parse(raw):
    """Return safe review data; never fetch links, authenticate senders, or write attachments."""
    if not raw or len(raw) > MAX_FILE:
        raise ValueError("Email must be nonempty and at most 5 MB.")
    if raw.startswith((b"PK\x03\x04", b"%PDF-", b"\xd0\xcf\x11\xe0")) or b"\x00" in raw[:1000]:
        raise ValueError(
            "Upload an RFC 5322 .eml message; .msg and archive files are not supported."
        )
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if not any(
        message.get(k) is not None
        for k in ("From", "To", "Subject", "Received", "Date", "Message-ID", "MIME-Version")
    ):
        raise ValueError("No recognizable email headers were found.")
    preflight(message)

    def offline(*args, **kwargs):
        raise OSError("Email evidence parsing is offline.")

    for name in ("connect", "connect_ex", "send", "sendall", "sendto"):
        setattr(socket.socket, name, offline)
    socket.create_connection = offline
    socket.getaddrinfo = offline
    logs = io.StringIO()
    with contextlib.redirect_stdout(logs), contextlib.redirect_stderr(logs):
        import mailparser

        mail = mailparser.parse_from_bytes(raw)
    headers = [dict(name=str(k)[:200], value=str(v)[:10000]) for k, v in message.raw_items()]
    warnings = []
    if any(len(str(v)) > 10000 for _, v in message.raw_items()):
        warnings.append(
            "Some displayed header values were truncated; download the original for complete values."
        )
    selected = {
        key: [str(v)[:10000] for v in message.get_all(key, [])]
        for key in (
            "From",
            "Reply-To",
            "Return-Path",
            "To",
            "Cc",
            "Date",
            "Message-ID",
            "Authentication-Results",
            "Received-SPF",
            "DKIM-Signature",
        )
    }
    addresses = []
    for field in ("from_", "reply_to", "to", "cc", "bcc", "return_path"):
        value = getattr(mail, field, None)
        if isinstance(value, list):
            for pair in value[:100]:
                if isinstance(pair, (tuple, list)) and len(pair) == 2:
                    addresses.append(
                        dict(
                            field=field, display_name=str(pair[0])[:500], address=str(pair[1])[:500]
                        )
                    )
    # Return-Path is not a mailbox-list property in all upstream versions.
    for name, address in getaddresses(selected["Return-Path"]):
        if address and not any(
            a["field"] == "return_path" and a["address"] == address for a in addresses
        ):
            addresses.append(
                dict(field="return_path", display_name=name[:500], address=address[:500])
            )
    attachments = []
    plain = []
    html = []
    attribute_urls = []
    decoded_total = 0
    stack = [message]
    while stack:
        part = stack.pop()
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        is_attachment = (
            bool(filename)
            or disposition == "attachment"
            or (not part.is_multipart() and part.get_content_maintype() != "text")
        )
        if is_attachment:
            data = part.get_payload(decode=True)
            size = len(data) if data is not None else None
            decoded_total += size or 0
            if len(attachments) >= 100 or decoded_total > 10_000_000:
                raise ValueError("Email exceeds 100 attachments or 10 MB decoded attachment data.")
            attachments.append(
                dict(
                    filename=str(filename or "Unnamed attachment")[:500],
                    content_type=part.get_content_type(),
                    disposition=disposition or "inline",
                    size=size,
                    sha256=hashlib.sha256(data).hexdigest() if data is not None else "",
                    content_id=str(part.get("Content-ID", ""))[:500],
                    note="Metadata only; not opened or executed."
                    if data is not None
                    else "Container attachment; payload not separately decoded. Original message retained.",
                )
            )
            continue
        if part.is_multipart():
            stack.extend(reversed(part.get_payload()))
            continue
        content = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        try:
            text = content.decode(charset, errors="replace")
        except LookupError:
            text = content.decode("utf-8", errors="replace")
            warnings.append("An unknown character set was decoded as UTF-8 with replacement.")
        if part.get_content_type() == "text/html":
            inert = HTMLText()
            inert.feed(text[:500000])
            html.append("".join(inert.text))
            attribute_urls.extend(inert.urls)
        elif part.get_content_type() == "text/plain":
            plain.append(text)
    plain_text = "\n".join(plain)
    html_text = "\n".join(html)
    if len(plain_text) > MAX_TEXT or len(html_text) > MAX_TEXT:
        warnings.append(
            "Body preview truncated to 60,000 characters per view; complete original retained."
        )
    urls = []
    seen = set()
    for candidate in [
        *attribute_urls,
        *re.findall(r'https?://[^\s<>"\x27]+', plain_text + "\n" + html_text),
    ]:
        value = candidate.rstrip(".,);]")[:2048]
        try:
            parsed = urlsplit(value)
            valid = (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and not parsed.username
                and not parsed.password
                and not any(ord(c) < 33 for c in value)
            )
        except ValueError:
            valid = False
        if valid and value not in seen:
            seen.add(value)
            if len(urls) < 200:
                urls.append(value)
    if len(seen) > 200:
        warnings.append("URL list limited to 200 unique HTTP(S) URLs.")
    ips = []
    for value in message.get_all("Received", []):
        candidates = re.findall(r"\[([^\]]+)\]", str(value)) + re.findall(
            r"[0-9A-Fa-f:.]+", str(value)
        )
        for candidate in candidates:
            candidate = re.sub(r"^IPv6:", "", candidate, flags=re.I)
            try:
                address = str(ipaddress.ip_address(candidate.strip(".")))
            except ValueError:
                continue
            if address not in ips and len(ips) < 100:
                ips.append(address)
    mismatch = []
    for field in ("reply_to", "return_path"):
        sender = {a["address"].casefold() for a in addresses if a["field"] == "from_"}
        other = {a["address"].casefold() for a in addresses if a["field"] == field}
        if sender and other and sender != other:
            mismatch.append(
                "From and "
                + field.replace("_", " ").title()
                + " differ. This may be legitimate; review context."
            )

    def cleaned(value):
        return json.loads(
            json.dumps(value, default=lambda v: sorted(v) if isinstance(v, set) else str(v))
        )

    defects = {
        name: cleaned(getattr(mail, name, None))
        for name in (
            "has_defects",
            "defects",
            "defects_categories",
            "address_header_defects",
            "received_header_defects",
            "date_header_defects",
            "resource_limit_defects",
        )
    }
    result = dict(
        subject=str(mail.subject or "(No subject)")[:500],
        headers=headers,
        selected_headers=selected,
        addresses=addresses[:300],
        received=cleaned(mail.received)[:100],
        plain_text=plain_text[:MAX_TEXT],
        html_text=html_text[:MAX_TEXT],
        urls=urls,
        ips=ips,
        attachments=attachments,
        defects=defects,
        date=str(mail.date or ""),
        warnings=list(dict.fromkeys(warnings + mismatch)),
        trust_note="Header values, routing hops, dates, and authentication results are claims in the uploaded message. Menace has not verified sender identity, SPF, DKIM, or DMARC.",
    )
    escaped = False

    def safe_strings(value):
        nonlocal escaped
        if isinstance(value, str):
            clean = value.encode("utf-8", errors="backslashreplace").decode("utf-8")
            escaped = escaped or clean != value
            return clean
        if isinstance(value, list):
            return [safe_strings(v) for v in value]
        if isinstance(value, dict):
            return {safe_strings(k): safe_strings(v) for k, v in value.items()}
        return value

    result = safe_strings(result)
    if escaped:
        result["warnings"].append(
            "Undecodable header bytes are shown as escaped values; complete original bytes are retained."
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file")
    args = parser.parse_args()
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
        if __import__("sys").platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
    except (ImportError, OSError, ValueError):
        pass
    try:
        path = Path(args.file)
        if path.stat().st_size > MAX_FILE:
            raise ValueError("Email exceeds 5 MB.")
        result = parse(path.read_bytes())
        serialized = json.dumps(result, ensure_ascii=False, default=str)
        if len(serialized.encode()) > 1_000_000:
            raise ValueError("Parsed email exceeds the safe review-output limit.")
        print(serialized)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                dict(
                    error=str(exc)[:500]
                    if isinstance(exc, ValueError)
                    else "Email parser failed: " + type(exc).__name__
                )
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
