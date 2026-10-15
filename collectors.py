"""Direct public-source collectors with bounded requests and explicit outcomes."""

from dataclasses import dataclass
import datetime as dt
from decimal import Decimal
import hashlib
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.parse
from cli_catalog import SITE_NAMES

from bs4 import BeautifulSoup
import phonenumbers
from phonenumbers import carrier, geocoder, timezone

USER_AGENT = "OSINT-Menace/1.0 (https://github.com/awesom3alex/osint-menace)"
PLATFORMS = ("github", "bluesky", "gitlab", "hacker-news")
RECORD_SOURCES = ("wikidata", "sec", "courtlistener")


@dataclass(frozen=True)
class Options:
    platforms: tuple = PLATFORMS
    region: str = "US"
    limit: int = 5
    timeout: int = 10
    text_limit: int = 4000
    records_sources: tuple = ("wikidata",)
    jurisdiction: str = "US"
    wallet_source: str = "auto"
    excerpt: str = ""
    profile_sites: tuple = ()

    def validate(self):
        if not 1 <= self.limit <= 25 or not 1 <= self.timeout <= 60 or not 100 <= self.text_limit <= 20000:
            raise ValueError("Limit must be 1-25, timeout 1-60 seconds, and text limit 100-20000.")
        if self.region.upper() not in phonenumbers.SUPPORTED_REGIONS:
            raise ValueError("Use a supported two-letter phone region, such as US or GB.")
        if not self.platforms or any(source not in PLATFORMS for source in self.platforms):
            raise ValueError("Choose direct sources from: " + ", ".join(PLATFORMS))
        if not self.records_sources or any(source not in RECORD_SOURCES for source in self.records_sources):
            raise ValueError("Unknown records source.")
        if self.wallet_source not in ("auto", "blockstream", "blockscout"):
            raise ValueError("Unknown wallet provider.")
        if self.jurisdiction not in ("US", "world"):
            raise ValueError("Jurisdiction must be US or world.")
        if len(self.excerpt) > self.text_limit:
            raise ValueError("Requested excerpt exceeds the text limit.")
        if any(site not in SITE_NAMES for site in self.profile_sites):
            raise ValueError("Unknown profile-link platform; use the platforms command for names.")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def public_address(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use a public HTTP(S) URL without embedded credentials.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Public page collection supports ports 80 and 443 only.")
    answers = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    addresses = [row[4][0] for row in answers]
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Local, private, or reserved network destinations are not supported.")
    return parsed, port, addresses[0]


def fetch(url, timeout=10, headers=None, max_bytes=2000000):
    """Resolve and pin public addresses, including each redirect; never forward auth."""
    original = urllib.parse.urlsplit(url)
    origin = (original.scheme, original.netloc.lower())
    try:
        for hop in range(4):
            parsed, port, address = public_address(url)
            connection = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout)
            sock = socket.create_connection((address, port), timeout=timeout)
            connection.sock = sock
            try:
                if parsed.scheme == "https":
                    connection.sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parsed.hostname)
                request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "identity"}
                if (parsed.scheme, parsed.netloc.lower()) == origin:
                    request_headers.update(headers or {})
                path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
                connection.request("GET", path, headers=request_headers)
                response = connection.getresponse()
                response_headers = {key.lower(): value for key, value in response.getheaders()}
                code = response.status
                if code in (301, 302, 303, 307, 308):
                    location = response_headers.get("location")
                    if not location or hop == 3:
                        return {"status": "error", "http_status": code, "url": url, "message": "Redirect limit or missing Location."}
                    destination = urllib.parse.urljoin(url, location)
                    if parsed.scheme == "https" and urllib.parse.urlsplit(destination).scheme != "https":
                        return {"status": "error", "url": url, "message": "HTTPS downgrade redirect refused."}
                    url = destination
                    continue
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    return {"status": "error", "http_status": code, "url": url, "message": "Response exceeded collection size limit."}
                status = "found" if 200 <= code < 300 else "not_found" if code == 404 else "rate_limited" if code == 429 else "blocked" if code in (401, 403) else "error"
                if code == 403 and response_headers.get("x-ratelimit-remaining") == "0":
                    status = "rate_limited"
                return {"status": status, "http_status": code, "url": url, "body": body,
                        "headers": response_headers, "message": "" if status == "found" else f"HTTP {code}"}
            finally:
                connection.close()
    except (OSError, ValueError, http.client.HTTPException) as exc:
        # Avoid echoing credential-bearing headers or request URLs in exception text.
        return {"status": "error", "url": url, "message": type(exc).__name__ + ": request could not be completed."}


def get_json(url, options, headers=None):
    response = fetch(url, options.timeout, headers)
    if response["status"] == "found":
        try:
            response["data"] = json.loads(response["body"])
        except (ValueError, UnicodeError):
            response.update(status="error", message="Source returned invalid JSON.")
    return response


def section(label, source, response, data=None, links=None):
    observation = {"status": response["status"], "retrieved_at": now(), "source_url": response.get("url", source)}
    if response.get("http_status") is not None:
        observation["http_status"] = response["http_status"]
    if response.get("message"):
        observation["message"] = response["message"]
    for header in ("retry-after", "x-ratelimit-reset"):
        if response.get("headers", {}).get(header):
            observation[header] = response["headers"][header]
    if data is not None:
        observation["data"] = data
    return {"name": label, "category": "collected_data", "module_type": "collector",
            "findings": [{"label": label, "value": observation, "source": source}],
            "links": links or [], "notes": []}


def invalid(label, message):
    return section(label, "Local validation", {"status": "invalid", "message": message})


def profiles(username, options):
    username = username.strip().lstrip("@")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,253}", username):
        return [invalid("Username", "Unsupported username format.")]
    results = []
    for provider in options.platforms:
        if provider in ("gitlab", "hacker-news"):
            results.append(extra_profile(provider, username, options))
            continue
        handle = username if "." in username else username + ".bsky.social"
        url = ("https://api.github.com/users/" + urllib.parse.quote(username, safe="") if provider == "github" else
               "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?" + urllib.parse.urlencode({"actor": handle}))
        token = os.environ.get("GITHUB_TOKEN") if provider == "github" else None
        response = get_json(url, options, {"Authorization": "Bearer " + token} if token else None)
        data = None
        links = []
        raw = response.get("data")
        if response["status"] == "found":
            required = "login" if provider == "github" else "did"
            if not isinstance(raw, dict) or not raw.get(required):
                response.update(status="error", message="Profile response did not match the expected schema.")
            else:
                keys = (("login", "name", "bio", "company", "location", "blog", "public_repos", "followers", "created_at")
                        if provider == "github" else ("did", "handle", "displayName", "description", "followersCount", "postsCount", "createdAt"))
                data = {key: raw[key] for key in keys if key in raw}
                data["identity_verified"] = False
                profile_url = ("https://github.com/" + urllib.parse.quote(raw["login"], safe="") if provider == "github" else
                               "https://bsky.app/profile/" + urllib.parse.quote(raw["did"], safe=""))
                links = [{"label": provider + " public profile (identity unverified)", "value": profile_url, "category": "candidate_profile"}]
        # Bluesky uses 400 for an unresolved actor. Other 400 responses stay errors.
        if provider == "bluesky" and response.get("http_status") == 400:
            try:
                error = json.loads(response.get("body", b"{}"))
                if error.get("error") == "ProfileNotFound":
                    response["status"] = "not_found"
            except (ValueError, AttributeError):
                pass
        result = section(provider + " profile: " + username, provider, response, data, links)
        result["notes"] = ["Account existence does not confirm association with the investigated person."]
        results.append(result)
    return results


def extra_profile(provider, username, options):
    if provider == "gitlab":
        url = "https://gitlab.com/api/v4/users?" + urllib.parse.urlencode({"username": username})
        token = os.environ.get("GITLAB_TOKEN")
        headers = {"PRIVATE-TOKEN": token} if token else None
    else:
        url = "https://hacker-news.firebaseio.com/v0/user/" + urllib.parse.quote(username, safe="") + ".json"
        headers = None
    response = get_json(url, options, headers)
    raw, data, links = response.get("data"), None, []
    if response["status"] == "found":
        if provider == "gitlab":
            if not isinstance(raw, list):
                response.update(status="error", message="Unexpected GitLab user response.")
            else:
                matches = [row for row in raw if isinstance(row, dict) and str(row.get("username", "")).casefold() == username.casefold()]
                if matches:
                    data = {key: matches[0].get(key) for key in ("id", "username", "name", "state")}
                    links = [{"label": "GitLab public profile (identity unverified)", "value": "https://gitlab.com/" + urllib.parse.quote(matches[0]["username"], safe=""), "category": "candidate_profile"}]
                else:
                    response["status"] = "no_matches"
        elif raw is None:
            response.update(status="no_matches", message="No public activity record returned; account absence is not established.")
        elif not isinstance(raw, dict) or raw.get("id") != username:
            response.update(status="error", message="Unexpected Hacker News user response.")
        else:
            data = {key: raw.get(key) for key in ("id", "karma")}
            data["username"] = raw["id"]
            data["about"] = BeautifulSoup(raw.get("about") or "", "html.parser").get_text(" ", strip=True)
            if isinstance(raw.get("created"), (int, float)):
                try:
                    data["created_at"] = dt.datetime.fromtimestamp(raw["created"], dt.timezone.utc).isoformat()
                except (ValueError, OSError, OverflowError):
                    data["created_at"] = None
            links = [{"label": "Hacker News public profile (identity unverified)", "value": "https://news.ycombinator.com/user?" + urllib.parse.urlencode({"id": username}), "category": "candidate_profile"}]
        if data is not None:
            data["identity_verified"] = False
    result = section(provider + " profile: " + username, provider, response, data, links)
    result["notes"] = ["Public profile data does not confirm identity. Hacker News only exposes users with public activity."]
    return result


def phone(number, options):
    try:
        parsed = phonenumbers.parse(number, options.region.upper())
    except phonenumbers.NumberParseException:
        return [invalid("Phone analysis", "Could not parse the phone number for the selected region.")]
    valid = phonenumbers.is_valid_number(parsed)
    types = {value: name.lower() for name, value in vars(phonenumbers.PhoneNumberType).items() if name.isupper() and isinstance(value, int)}
    data = {"e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
            "analysis_mode": "offline_metadata", "metadata_version": phonenumbers.__version__,
            "international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            "possible": phonenumbers.is_possible_number(parsed), "valid": valid,
            "region": phonenumbers.region_code_for_number(parsed), "country_calling_code": parsed.country_code,
            "number_type": types.get(phonenumbers.number_type(parsed), "unknown"),
            "region_description": geocoder.description_for_number(parsed, "en"),
            "original_carrier": carrier.name_for_number(parsed, "en"),
            "time_zones": list(timezone.time_zones_for_number(parsed))}
    result = section("Phone analysis: " + number, "libphonenumber metadata (offline)",
                     {"status": "found" if valid else "invalid", "url": "https://github.com/daviddrysdale/python-phonenumbers"}, data)
    result["notes"] = ["Validation describes numbering-plan metadata, not assignment or account ownership. Region is not a live location. Carrier allocation can be outdated after number portability."]
    return [result]


def wallet(address, options):
    is_eth = bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", address))
    is_btc = bool(re.fullmatch(r"(?:bc1[ac-hj-np-z02-9]{11,71}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})", address))
    if not is_eth and not is_btc:
        return [invalid("Wallet", "Input does not match supported Ethereum or Bitcoin address formats.")]
    provider = options.wallet_source if options.wallet_source != "auto" else ("blockscout" if is_eth else "blockstream")
    if (is_eth and provider != "blockscout") or (is_btc and provider != "blockstream"):
        return [invalid("Wallet", "The selected provider does not support this address chain.")]
    base = ("https://eth.blockscout.com/api/v2/addresses/" if is_eth else "https://blockstream.info/api/address/") + address
    response = get_json(base, options)
    data = None
    raw = response.get("data")
    if response["status"] == "found":
        try:
            if is_eth:
                wei = int(raw["coin_balance"])
                data = {"chain": "Ethereum mainnet", "balance_wei": str(wei), "balance_eth": str(Decimal(wei) / Decimal(10**18)),
                        "is_contract": raw.get("is_contract"), "ens_domain_name": raw.get("ens_domain_name")}
            else:
                confirmed, pending = raw["chain_stats"], raw["mempool_stats"]
                balance = int(confirmed["funded_txo_sum"]) - int(confirmed["spent_txo_sum"])
                delta = int(pending["funded_txo_sum"]) - int(pending["spent_txo_sum"])
                data = {"chain": "Bitcoin mainnet", "confirmed_satoshis": balance, "confirmed_btc": str(Decimal(balance) / Decimal(10**8)),
                        "pending_delta_satoshis": delta, "confirmed_transaction_count": confirmed["tx_count"]}
        except (KeyError, TypeError, ValueError):
            response.update(status="error", message="Wallet data missing required fields; balance unavailable.")
    results = [section(provider + " wallet summary", provider, response, data)]
    if response["status"] != "found":
        return results
    tx_response = get_json(base + ("/transactions" if is_eth else "/txs"), options)
    transactions = None
    if tx_response["status"] == "found":
        raw = tx_response.get("data")
        items = raw.get("items") if is_eth and isinstance(raw, dict) else raw
        if not isinstance(items, list):
            tx_response.update(status="error", message="Transaction response did not match the expected schema.")
        else:
            keys = ("hash", "timestamp", "block_number", "from", "to", "value", "status") if is_eth else ("txid", "status", "fee", "size")
            transactions = [{key: row.get(key) for key in keys} for row in items[:options.limit] if isinstance(row, dict)]
    results.append(section(provider + " recent transactions", provider, tx_response, transactions))
    for result in results:
        result["notes"] = ["Provider snapshot; returned transactions are a bounded sample, not a complete account history. Wallet ownership is not established."]
    return results


def page(url, options):
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password:
            return [invalid("Public page", "Embedded URL credentials are not supported.")]
    except ValueError:
        return [invalid("Public page", "Malformed URL.")]
    response = fetch(url, options.timeout, {"Accept": "text/html, text/plain;q=0.9"})
    data = None
    if response["status"] == "found":
        content_type = response["headers"].get("content-type", "").lower()
        if not any(value in content_type for value in ("text/html", "application/xhtml+xml", "text/plain")):
            response.update(status="unsupported", message="Only HTML and plain-text pages are supported.")
        else:
            body = response["body"]
            if "html" in content_type:
                soup = BeautifulSoup(body, "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                for tag in soup(["script", "style", "noscript", "template", "svg"]):
                    tag.decompose()
                text = soup.get_text(" ", strip=True)
            else:
                title, text = "", body.decode("utf-8", "replace")
            text = " ".join(text.split())
            data = {"title": title, "text": text[:options.text_limit], "text_truncated": len(text) > options.text_limit,
                    "body_sha256": hashlib.sha256(body).hexdigest(), "content_type": content_type, "bytes": len(body)}
            if options.excerpt:
                excerpt = " ".join(options.excerpt.split())
                if excerpt not in text:
                    response.update(status="no_matches", message="The exact excerpt was not found in the extracted page text.")
                    data = None
                else:
                    data.update(text=excerpt, text_truncated=False, analyst_selected_excerpt=True)
    result = section("Public page: " + url, "Public HTTP page", response, data)
    result["notes"] = ["Text capture only; JavaScript is not executed. Hash identifies the retrieved response body, which is not stored in full."]
    return [result]


def records(query, options):
    results = []
    for provider in options.records_sources:
        if provider in ("sec", "courtlistener") and options.jurisdiction != "US":
            results.append(invalid(provider, "This connector supports US records only; choose --jurisdiction US."))
            continue
        headers = None
        if provider == "sec":
            agent = os.environ.get("SEC_USER_AGENT", "")
            if not agent:
                results.append(section("SEC company matches", "SEC", {"status": "configuration_required", "message": "Set SEC_USER_AGENT to your organization and contact email."}))
                continue
            url = "https://www.sec.gov/files/company_tickers.json"
            headers = {"User-Agent": agent}
        elif provider == "courtlistener":
            token = os.environ.get("COURTLISTENER_TOKEN")
            if not token:
                results.append(section("CourtListener matches", "CourtListener", {"status": "configuration_required", "message": "Set COURTLISTENER_TOKEN for this source."}))
                continue
            url = "https://www.courtlistener.com/api/rest/v4/search/?" + urllib.parse.urlencode({"q": query, "type": "o"})
            headers = {"Authorization": "Token " + token}
        else:
            url = "https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": query, "language": "en", "format": "json", "limit": options.limit})
        response = get_json(url, options, headers)
        data = None
        if response["status"] == "found":
            try:
                raw = response["data"]
                if provider == "sec":
                    if not isinstance(raw, dict) or not all(isinstance(row, dict) and "title" in row for row in raw.values()):
                        raise ValueError("Invalid SEC schema")
                    data = [row for row in raw.values() if query.lower() in row["title"].lower() or query.upper() == row.get("ticker")][:options.limit]
                elif provider == "courtlistener":
                    data = [{key: row.get(key) for key in ("caseName", "court", "dateFiled", "absolute_url", "snippet")}
                            for row in raw["results"][:options.limit]]
                else:
                    data = [{key: row.get(key) for key in ("id", "label", "description", "concepturi")} for row in raw["search"][:options.limit]]
                if not data:
                    response["status"] = "no_matches"
            except (KeyError, TypeError, AttributeError, ValueError):
                response.update(status="error", message="Records response did not match the expected schema.")
        result = section(provider + " matches: " + query, provider, response, data)
        result["notes"] = ["Name matches are candidates, not identity confirmation. SEC covers company names/tickers, not individual people. Wikidata is a public knowledge base, not an official records registry. CourtListener searches indexed opinions, not all court records."]
        results.append(result)
    return results


def collect(kind, value, options=None):
    options = options or Options()
    options.validate()
    value = value.strip()
    if not value:
        raise ValueError("Enter a collection target.")
    functions = {"username": profiles, "phone": phone, "wallet": wallet, "url": page, "name": records, "records": records}
    if kind not in functions:
        raise ValueError("Unsupported direct collector type.")
    return functions[kind](value, options)
