#!/usr/bin/env python3
"""
Passive OSINT helper for emails, usernames, phones, names, domains, IPs, and
crypto wallets.

This tool is designed for lawful, authorized research. It favors public records,
public technical metadata, and generated investigation links over invasive
automation. Active checks such as port scanning require an explicit flag.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Iterable


USER_AGENT = "DT-OSINT/1.0 (+https://example.local; passive public-source research)"
TIMEOUT = 8

CONSUMER_MAIL_DOMAINS = {
    "aol.com",
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "mail.com",
    "me.com",
    "msn.com",
    "outlook.com",
    "pm.me",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
    "yandex.com",
    "zoho.com",
}

DISPOSABLE_MAIL_DOMAINS = {
    "10minutemail.com",
    "guerrillamail.com",
    "mailinator.com",
    "sharklasers.com",
    "tempmail.com",
    "throwawaymail.com",
    "yopmail.com",
}


@dataclass
class Finding:
    label: str
    value: Any
    source: str | None = None


@dataclass
class Section:
    name: str
    findings: list[Finding] = field(default_factory=list)
    links: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, label: str, value: Any, source: str | None = None) -> None:
        if value not in (None, "", [], {}):
            self.findings.append(Finding(label, value, source))

    def link(self, label: str, url: str, source: str | None = None) -> None:
        self.links.append(Finding(label, url, source))

    def note(self, text: str) -> None:
        self.notes.append(text)


def http_request(url: str, method: str = "GET", accept: str = "*/*") -> tuple[int, bytes, dict[str, str]]:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return response.status, response.read(), dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers.items())
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        return 0, str(exc).encode("utf-8", "replace"), {}


def json_get(url: str) -> Any | None:
    status, body, _ = http_request(url, accept="application/json")
    if status < 200 or status >= 300:
        return None
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None


def query_url(query: str, engine: str = "google") -> str:
    encoded = urllib.parse.quote_plus(query)
    engines = {
        "google": f"https://www.google.com/search?q={encoded}",
        "bing": f"https://www.bing.com/search?q={encoded}",
        "duckduckgo": f"https://duckduckgo.com/?q={encoded}",
    }
    return engines[engine]


def normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if "://" in domain:
        domain = urllib.parse.urlparse(domain).netloc
    return domain.strip("/")


def google_dns_records(name: str, record_type: str) -> list[str]:
    url = f"https://dns.google/resolve?name={urllib.parse.quote(name)}&type={urllib.parse.quote(record_type)}"
    data = json_get(url)
    if not isinstance(data, dict):
        return []
    return [str(answer.get("data", "")).strip('"') for answer in data.get("Answer", []) if answer.get("data")]


def infer_mail_provider(mx_records: Iterable[str]) -> str | None:
    mx_text = " ".join(mx_records).lower()
    if not mx_text:
        return None
    if "google" in mx_text or "gmail" in mx_text:
        return "Google Workspace / Gmail"
    if "outlook" in mx_text or "microsoft" in mx_text or "protection.outlook.com" in mx_text:
        return "Microsoft 365 / Outlook"
    if "protonmail" in mx_text or "proton.ch" in mx_text:
        return "Proton Mail"
    if "icloud" in mx_text or "apple" in mx_text:
        return "Apple iCloud Mail"
    if "zoho" in mx_text:
        return "Zoho Mail"
    if "yahoo" in mx_text or "yahoodns" in mx_text:
        return "Yahoo Mail"
    return next(iter(mx_records), None)


def infer_email_name(local: str) -> dict[str, Any]:
    clean = re.sub(r"\d+", "", local.split("+", 1)[0].lower())
    parts = [part for part in re.split(r"[._-]", clean) if len(part) >= 2]
    if not parts:
        return {}
    return {
        "possible_first": parts[0].title(),
        "possible_last": parts[-1].title() if len(parts) > 1 else "",
        "parts": parts,
    }


def username_permutations_from_email(email: str) -> list[str]:
    local = email.split("@", 1)[0].lower().split("+", 1)[0]
    variants = {local}
    for sep in [".", "_", "-"]:
        parts = [part for part in local.split(sep) if part]
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            variants.update(
                {
                    first,
                    last,
                    first + last,
                    last + first,
                    first[0] + last,
                    first + last[0],
                    first + "." + last,
                    first + "_" + last,
                    first[0] + "." + last,
                }
            )
    stripped = re.sub(r"\d+$", "", local)
    if stripped:
        variants.add(stripped)
    return sorted(variant for variant in variants if len(variant) >= 3)[:18]


def render(sections: list[Section], output_json: bool) -> None:
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sections": [
            {
                "name": section.name,
                "findings": [finding.__dict__ for finding in section.findings],
                "links": [finding.__dict__ for finding in section.links],
                "notes": section.notes,
            }
            for section in sections
        ],
    }
    if output_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    for section in sections:
        print(f"\n## {section.name}")
        if not section.findings and not section.links and not section.notes:
            print("- No findings.")
        for finding in section.findings:
            source = f" ({finding.source})" if finding.source else ""
            print(f"- {finding.label}: {finding.value}{source}")
        for link in section.links:
            source = f" ({link.source})" if link.source else ""
            print(f"- {link.label}: {link.value}{source}")
        for note in section.notes:
            print(f"- Note: {note}")


def email_report(email: str) -> Section:
    section = Section(f"Email: {email}")
    email = email.strip().lower()
    valid = bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email))
    section.add("Format valid", valid)
    if not valid:
        return section

    local, domain = email.rsplit("@", 1)
    section.add("Local part", local)
    section.add("Domain", domain)
    section.add("Consumer mailbox domain", domain in CONSUMER_MAIL_DOMAINS)
    section.add("Disposable mailbox domain", domain in DISPOSABLE_MAIL_DOMAINS)
    section.add("Name hints from local part", infer_email_name(local), "local inference")
    section.add("Username variants", username_permutations_from_email(email), "local inference")

    mx_records = google_dns_records(domain, "MX")
    txt_records = google_dns_records(domain, "TXT")
    spf_records = [record for record in txt_records if record.lower().startswith("v=spf1")]
    dmarc_records = google_dns_records(f"_dmarc.{domain}", "TXT")
    section.add("Mail provider hint", infer_mail_provider(mx_records), "DNS MX")
    section.add("Domain MX", mx_records[:8], "Google DNS over HTTPS")
    section.add("SPF present", bool(spf_records), "Google DNS over HTTPS")
    section.add("DMARC present", bool(dmarc_records), "Google DNS over HTTPS")

    digest = hashlib.md5(email.encode("utf-8")).hexdigest()
    gravatar_url = f"https://www.gravatar.com/avatar/{digest}?d=404"
    status, _, _ = http_request(gravatar_url, method="HEAD")
    section.add("Gravatar status", "present" if status == 200 else "not found" if status == 404 else f"unknown ({status})", "gravatar.com")
    section.link("Gravatar URL", gravatar_url)
    section.link("Gravatar profile JSON", f"https://gravatar.com/{digest}.json")
    section.link("EmailRep lookup", f"https://emailrep.io/{urllib.parse.quote(email)}")
    section.link("Have I Been Pwned", f"https://haveibeenpwned.com/account/{urllib.parse.quote(email)}")

    queries = [
        f'"{email}"',
        f'"{email}" profile',
        f'"{email}" site:github.com OR site:reddit.com OR site:linkedin.com',
        f'"{email}" "paste"',
        f'"{email}" "breach"',
        f'"{local}" "{domain}"',
    ]
    for query in queries:
        section.link(f"Search: {query}", query_url(query))
    return section


PROFILE_PATTERNS = {
    "About.me": "https://about.me/{username}",
    "Bitbucket": "https://bitbucket.org/{username}",
    "Blogspot": "https://{username}.blogspot.com/",
    "Bluesky": "https://bsky.app/profile/{username}.bsky.social",
    "Cash App": "https://cash.app/${username}",
    "CodePen": "https://codepen.io/{username}",
    "DEV Community": "https://dev.to/{username}",
    "Dribbble": "https://dribbble.com/{username}",
    "Facebook": "https://www.facebook.com/{username}",
    "Flickr": "https://www.flickr.com/people/{username}",
    "GitLab": "https://gitlab.com/{username}",
    "GitHub": "https://github.com/{username}",
    "Hacker News": "https://news.ycombinator.com/user?id={username}",
    "HackerOne": "https://hackerone.com/{username}",
    "Instagram": "https://www.instagram.com/{username}/",
    "Keybase": "https://keybase.io/{username}",
    "Mastodon social": "https://mastodon.social/@{username}",
    "Medium": "https://medium.com/@{username}",
    "Pastebin": "https://pastebin.com/u/{username}",
    "Reddit": "https://www.reddit.com/user/{username}",
    "Pinterest": "https://www.pinterest.com/{username}/",
    "Product Hunt": "https://www.producthunt.com/@{username}",
    "PyPI": "https://pypi.org/user/{username}/",
    "SoundCloud": "https://soundcloud.com/{username}",
    "Steam": "https://steamcommunity.com/id/{username}",
    "Telegram": "https://t.me/{username}",
    "TikTok": "https://www.tiktok.com/@{username}",
    "Tumblr": "https://{username}.tumblr.com/",
    "Twitch": "https://www.twitch.tv/{username}",
    "X": "https://x.com/{username}",
    "YouTube": "https://www.youtube.com/@{username}",
    "WordPress": "https://{username}.wordpress.com/",
}


def username_report(username: str, forum_patterns: Iterable[str]) -> Section:
    username = username.strip().lstrip("@")
    section = Section(f"Username: {username}")
    section.add("Format likely valid", bool(re.fullmatch(r"[A-Za-z0-9_.-]{2,64}", username)))

    for name, pattern in PROFILE_PATTERNS.items():
        section.link(name, pattern.format(username=urllib.parse.quote(username)))
    for pattern in forum_patterns:
        try:
            section.link("Configured forum pattern", pattern.format(username=urllib.parse.quote(username)))
        except KeyError:
            section.note(f"Skipped forum pattern without {{username}} placeholder: {pattern}")

    for query in [
        f'"{username}"',
        f'"{username}" "profile"',
        f'"{username}" "forum"',
        f'"{username}" "contact"',
        f'"{username}" site:github.com OR site:gitlab.com OR site:stackoverflow.com',
        f'"{username}" site:pastebin.com OR site:medium.com OR site:dev.to',
    ]:
        section.link(f"Search: {query}", query_url(query))
    section.note("Profile URLs are candidate links. A 200 response alone does not prove identity.")
    return section


def phone_report(phone: str) -> Section:
    raw = phone.strip()
    digits = re.sub(r"\D", "", raw)
    section = Section(f"Phone: {raw}")
    section.add("Digits", digits)
    section.add("E.164-like valid", bool(re.fullmatch(r"\+?[1-9]\d{7,14}", raw.replace(" ", ""))))
    if len(digits) == 10:
        section.add("Country/region guess", "North America (+1), if no explicit country code")
    elif len(digits) == 11 and digits.startswith("1"):
        section.add("Country/region guess", "North America (+1)")
    elif raw.startswith("+"):
        section.add("Country/region guess", f"International prefix present; country code starts with +{digits[:3]}")

    quoted = f'"{raw}"'
    normalized = f'"{digits}"'
    for query in [quoted, normalized, f'{quoted} "contact"', f'{quoted} "business"', f'{quoted} "public records"']:
        section.link(f"Search: {query}", query_url(query))
    section.link("Truecaller search", f"https://www.truecaller.com/search/us/{urllib.parse.quote(digits)}")
    section.link("Public web mentions", query_url(f'"{raw}" OR "{digits}"'))
    return section


def name_report(full_name: str) -> Section:
    name = " ".join(full_name.split())
    section = Section(f"Full name: {name}")
    quoted = f'"{name}"'
    for query in [
        quoted,
        f'{quoted} LinkedIn',
        f'{quoted} "profile"',
        f'{quoted} "email"',
        f'{quoted} "phone"',
        f'{quoted} "public records"',
        f'{quoted} "business filing"',
    ]:
        section.link(f"Search: {query}", query_url(query))
    section.link("LinkedIn targeted search", query_url(f'site:linkedin.com/in {quoted}'))
    section.link("OpenCorporates", f"https://opencorporates.com/officers?q={urllib.parse.quote_plus(name)}")
    section.link("SEC EDGAR full-text", f"https://www.sec.gov/edgar/search/#/q={urllib.parse.quote(name)}")
    section.link("CourtListener", f"https://www.courtlistener.com/?q={urllib.parse.quote_plus(name)}")
    return section


def try_dnspython_records(domain: str, section: Section) -> bool:
    try:
        import dns.resolver  # type: ignore
    except ImportError:
        return False

    resolver = dns.resolver.Resolver()
    resolver.lifetime = TIMEOUT
    for record_type in ["A", "AAAA", "MX", "NS", "TXT", "CAA"]:
        try:
            answers = resolver.resolve(domain, record_type)
            section.add(f"DNS {record_type}", [str(answer).strip('"') for answer in answers], "DNS")
        except Exception:
            continue
    return True


def fallback_dns(domain: str, section: Section) -> None:
    try:
        infos = socket.getaddrinfo(domain, None)
    except socket.gaierror as exc:
        section.add("DNS lookup error", str(exc))
        return
    addresses = sorted({info[4][0] for info in infos})
    section.add("Resolved addresses", addresses, "socket.getaddrinfo")


def domain_report(domain: str) -> Section:
    domain = normalize_domain(domain)
    section = Section(f"Domain: {domain}")
    if not try_dnspython_records(domain, section):
        fallback_dns(domain, section)
        section.note("Install dnspython for MX, NS, TXT, and CAA lookups: pip install dnspython")

    doh_records = {record_type: google_dns_records(domain, record_type) for record_type in ["A", "AAAA", "MX", "NS", "TXT"]}
    section.add("DNS over HTTPS", {key: value[:8] for key, value in doh_records.items() if value}, "Google DNS")
    section.add("Mail provider hint", infer_mail_provider(doh_records.get("MX", [])), "DNS MX")
    section.add("SPF present", any(record.lower().startswith("v=spf1") for record in doh_records.get("TXT", [])), "DNS TXT")
    section.add("DMARC present", bool(google_dns_records(f"_dmarc.{domain}", "TXT")), "Google DNS")

    rdap = json_get(f"https://rdap.org/domain/{urllib.parse.quote(domain)}")
    if rdap:
        section.add("RDAP handle", rdap.get("handle"), "rdap.org")
        section.add("RDAP registrar", first_entity_name(rdap), "rdap.org")
        section.add("RDAP events", summarize_events(rdap.get("events", [])), "rdap.org")

    cert = fetch_tls_certificate(domain)
    section.add("TLS certificate", cert, "live TLS")

    ct_url = f"https://crt.sh/?q=%25.{urllib.parse.quote(domain)}&output=json"
    ct_data = json_get(ct_url)
    if isinstance(ct_data, list):
        names = sorted({name.strip().lower() for row in ct_data[:500] for name in str(row.get("name_value", "")).splitlines() if name.strip()})
        section.add("Certificate transparency names", names[:50], "crt.sh")
        if len(names) > 50:
            section.note(f"CT output truncated to 50 of {len(names)} discovered names.")
    section.link("crt.sh certificate search", f"https://crt.sh/?q=%25.{urllib.parse.quote(domain)}")

    wayback = json_get(f"https://web.archive.org/cdx?url={urllib.parse.quote(domain)}/*&output=json&fl=timestamp,original,statuscode,mimetype&collapse=urlkey&limit=20")
    if isinstance(wayback, list) and len(wayback) > 1:
        section.add("Archived URL samples", wayback[1:21], "web.archive.org")
    section.link("Wayback Machine", f"https://web.archive.org/web/*/{domain}/*")
    section.link("URLScan search", f"https://urlscan.io/search/#{urllib.parse.quote('domain:' + domain)}")
    section.link("AlienVault OTX domain", f"https://otx.alienvault.com/indicator/domain/{urllib.parse.quote(domain)}")
    section.link("HackerTarget host search", f"https://api.hackertarget.com/hostsearch/?q={urllib.parse.quote(domain)}")
    section.link("SecurityTrails domain", f"https://securitytrails.com/domain/{urllib.parse.quote(domain)}/dns")
    section.link("VirusTotal domain", f"https://www.virustotal.com/gui/domain/{urllib.parse.quote(domain)}")

    tech = fingerprint_site(domain)
    section.add("Technology hints", tech, "HTTP headers/body")
    return section


def first_entity_name(rdap: dict[str, Any]) -> str | None:
    for entity in rdap.get("entities", []):
        vcard = entity.get("vcardArray", [])
        if len(vcard) != 2:
            continue
        for item in vcard[1]:
            if item and item[0] in {"fn", "org"}:
                return item[3]
    return None


def summarize_events(events: list[dict[str, Any]]) -> list[str]:
    out = []
    for event in events:
        action = event.get("eventAction")
        date = event.get("eventDate")
        if action and date:
            out.append(f"{action}: {date}")
    return out


def fetch_tls_certificate(domain: str) -> dict[str, Any] | None:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=TIMEOUT) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as tls:
                cert = tls.getpeercert()
    except Exception:
        return None
    subject = dict(x[0] for x in cert.get("subject", []))
    issuer = dict(x[0] for x in cert.get("issuer", []))
    return {
        "subject_common_name": subject.get("commonName"),
        "issuer_common_name": issuer.get("commonName"),
        "not_before": cert.get("notBefore"),
        "not_after": cert.get("notAfter"),
        "subject_alt_names": [value for key, value in cert.get("subjectAltName", []) if key == "DNS"][:25],
    }


def fingerprint_site(domain: str) -> dict[str, Any] | None:
    for scheme in ["https", "http"]:
        status, body, headers = http_request(f"{scheme}://{domain}/")
        if status:
            text = body[:200000].decode("utf-8", "ignore").lower()
            hints = []
            for marker, label in [
                ("wp-content", "WordPress"),
                ("shopify", "Shopify"),
                ("wixstatic", "Wix"),
                ("squarespace", "Squarespace"),
                ("next/static", "Next.js"),
                ("react", "React"),
                ("cloudflare", "Cloudflare"),
            ]:
                if marker in text or marker in " ".join(f"{k}: {v}" for k, v in headers.items()).lower():
                    hints.append(label)
            return {
                "url": f"{scheme}://{domain}/",
                "status": status,
                "server": headers.get("Server"),
                "powered_by": headers.get("X-Powered-By"),
                "hints": sorted(set(hints)),
            }
    return None


def ip_report(ip: str, allow_scan: bool, scan_ports: list[int]) -> Section:
    section = Section(f"IP address: {ip}")
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError as exc:
        section.add("Format valid", False)
        section.add("Error", str(exc))
        return section

    section.add("Format valid", True)
    section.add("Version", f"IPv{parsed.version}")
    section.add("Private/reserved", parsed.is_private or parsed.is_reserved)
    try:
        section.add("Reverse DNS", socket.gethostbyaddr(ip)[0], "DNS PTR")
    except socket.herror:
        section.add("Reverse DNS", "not found", "DNS PTR")

    rdap = json_get(f"https://rdap.org/ip/{urllib.parse.quote(ip)}")
    if rdap:
        section.add("RDAP name", rdap.get("name"), "rdap.org")
        section.add("RDAP handle", rdap.get("handle"), "rdap.org")
        section.add("RDAP country", rdap.get("country"), "rdap.org")
        section.add("RDAP events", summarize_events(rdap.get("events", [])), "rdap.org")

    geo = json_get(f"https://ipwho.is/{urllib.parse.quote(ip)}")
    if geo and geo.get("success", True):
        section.add(
            "Geo approximation",
            {
                "country": geo.get("country"),
                "region": geo.get("region"),
                "city": geo.get("city"),
                "latitude": geo.get("latitude"),
                "longitude": geo.get("longitude"),
            },
            "ipwho.is",
        )
        connection = geo.get("connection") or {}
        section.add(
            "ASN/org",
            {
                "asn": connection.get("asn"),
                "org": connection.get("org"),
                "isp": connection.get("isp"),
                "domain": connection.get("domain"),
            },
            "ipwho.is",
        )

    shodan_db = json_get(f"https://internetdb.shodan.io/{urllib.parse.quote(ip)}")
    if isinstance(shodan_db, dict):
        section.add(
            "Shodan InternetDB",
            {
                "ports": shodan_db.get("ports", []),
                "hostnames": shodan_db.get("hostnames", []),
                "vulns": shodan_db.get("vulns", []),
                "tags": shodan_db.get("tags", []),
                "cpes": shodan_db.get("cpes", []),
            },
            "internetdb.shodan.io",
        )

    bgp = json_get(f"https://api.bgpview.io/ip/{urllib.parse.quote(ip)}")
    if isinstance(bgp, dict) and bgp.get("status") == "ok":
        prefixes = (bgp.get("data") or {}).get("prefixes") or []
        if prefixes:
            prefix = prefixes[0]
            asn = prefix.get("asn") or {}
            section.add(
                "BGPView ASN",
                {
                    "asn": asn.get("asn"),
                    "name": asn.get("name"),
                    "description": asn.get("description"),
                    "prefix": prefix.get("prefix"),
                },
                "api.bgpview.io",
            )

    section.link("IPinfo lookup", f"https://ipinfo.io/{urllib.parse.quote(ip)}")
    section.link("Hurricane Electric BGP", f"https://bgp.he.net/ip/{urllib.parse.quote(ip)}")
    section.link("AbuseIPDB lookup", f"https://www.abuseipdb.com/check/{urllib.parse.quote(ip)}")
    section.link("AlienVault OTX IP", f"https://otx.alienvault.com/indicator/ip/{urllib.parse.quote(ip)}")
    section.link("VirusTotal lookup", f"https://www.virustotal.com/gui/ip-address/{urllib.parse.quote(ip)}")
    section.link("Shodan host page", f"https://www.shodan.io/host/{urllib.parse.quote(ip)}")
    section.link("Censys host page", f"https://search.censys.io/hosts/{urllib.parse.quote(ip)}")
    section.link("SecurityTrails passive DNS", f"https://securitytrails.com/list/ip/{urllib.parse.quote(ip)}")
    section.link("HackerTarget reverse IP", f"https://api.hackertarget.com/reverseiplookup/?q={urllib.parse.quote(ip)}")
    section.link("Pulsedive indicator", f"https://pulsedive.com/indicator/?ioc={urllib.parse.quote(ip)}")

    if allow_scan:
        section.add("Port scan", scan_ip(ip, scan_ports), "local socket connect")
    else:
        section.note("Port scan skipped. Re-run with --allow-port-scan only for systems you own or are authorized to test.")
    return section


def scan_ip(ip: str, ports: list[int]) -> dict[int, str]:
    results = {}
    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=1.5):
                results[port] = "open"
        except (socket.timeout, OSError):
            results[port] = "closed_or_filtered"
    return results


ETH_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
BTC_RE = re.compile(r"^(bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")


def crypto_report(wallet: str) -> Section:
    wallet = wallet.strip()
    section = Section(f"Crypto wallet: {wallet}")
    is_eth = bool(ETH_RE.fullmatch(wallet))
    is_btc = bool(BTC_RE.fullmatch(wallet))
    section.add("Ethereum format valid", is_eth)
    section.add("Bitcoin format plausible", is_btc)
    if is_eth:
        section.link("Etherscan", f"https://etherscan.io/address/{wallet}")
        section.link("Arkham", f"https://platform.arkhamintelligence.com/explorer/address/{wallet}")
        section.link("DeBank", f"https://debank.com/profile/{wallet}")
        section.link("ENS reverse lookup", f"https://app.ens.domains/address/{wallet}")
    if is_btc:
        section.link("Mempool.space", f"https://mempool.space/address/{wallet}")
        section.link("Blockstream", f"https://blockstream.info/address/{wallet}")
        section.link("Blockchain.com", f"https://www.blockchain.com/explorer/addresses/btc/{wallet}")
    if not is_eth and not is_btc:
        section.note("Wallet did not match common Bitcoin or Ethereum address formats.")
    section.note("Transaction summaries are best reviewed on the linked public explorers to respect rate limits and site terms.")
    return section


def parse_ports(value: str) -> list[int]:
    ports: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = [int(x) for x in part.split("-", 1)]
            ports.update(range(start, end + 1))
        else:
            ports.add(int(part))
    bad = [port for port in ports if port < 1 or port > 65535]
    if bad:
        raise argparse.ArgumentTypeError(f"Invalid port(s): {bad}")
    return sorted(ports)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Passive OSINT helper for public-source research.")
    parser.add_argument("--email", action="append", default=[], help="Email address to inspect. Can be repeated.")
    parser.add_argument("--username", action="append", default=[], help="Username/handle to inspect. Can be repeated.")
    parser.add_argument("--phone", action="append", default=[], help="Phone number to inspect. Can be repeated.")
    parser.add_argument("--name", action="append", default=[], help="Full name to inspect. Can be repeated.")
    parser.add_argument("--domain", action="append", default=[], help="Domain to inspect. Can be repeated.")
    parser.add_argument("--ip", action="append", default=[], help="IP address to inspect. Can be repeated.")
    parser.add_argument("--wallet", action="append", default=[], help="Bitcoin or Ethereum wallet to inspect. Can be repeated.")
    parser.add_argument("--forum-pattern", action="append", default=[], help="Custom forum URL containing {username}. Can be repeated.")
    parser.add_argument("--allow-port-scan", action="store_true", help="Enable basic TCP connect scan for IPs you are authorized to test.")
    parser.add_argument("--ports", type=parse_ports, default=parse_ports("21,22,25,53,80,110,143,443,445,587,993,995,3389,8080,8443"), help="Comma/range port list for --allow-port-scan.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown-like text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sections: list[Section] = []
    for value in args.email:
        sections.append(email_report(value))
    for value in args.username:
        sections.append(username_report(value, args.forum_pattern))
    for value in args.phone:
        sections.append(phone_report(value))
    for value in args.name:
        sections.append(name_report(value))
    for value in args.domain:
        sections.append(domain_report(value))
    for value in args.ip:
        sections.append(ip_report(value, args.allow_port_scan, args.ports))
    for value in args.wallet:
        sections.append(crypto_report(value))

    if not sections:
        build_parser().print_help()
        return 2
    render(sections, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
