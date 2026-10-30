# OSINT Menace v0.4.0 Quickstart

**More Sources. Fewer Alibis.**

A practical guide to getting started, choosing tools, and understanding API requirements. Prepared October 30, 2026, for the modes integrated into this version of Menace.

## 1. Install and open Menace

You need Docker Desktop (or Docker Engine with Compose v2), Python 3 for the installer, Bash, an internet connection, and a browser. Windows users should run the installer through WSL2. Use a source folder containing v0.4.0.

Start Docker, open a terminal in the project folder, and run:

```sh
cd /path/to/osint-menace
python3 install.py
```

The installer downloads the pinned tools, builds the application, starts it, and checks application health, existing-data preservation, and key pages. The first build can take time because it downloads tool dependencies and international address models. It does not install the addon packages onto your computer's Python environment.

Open **[http://localhost:8088](http://localhost:8088)**. Open **Help** and confirm the version reads **OSINT Menace v0.4.0**. To install without automatically opening a browser, use `python3 install.py --no-open`.

Menace has no built-in login. The supplied Docker configuration exposes port 8088 on the host's network interfaces; use a trusted network and appropriate host access controls.

## 2. Your first investigation

1. **Explore the demo:** open **Help → Demo** to see a fictional case without changing it.
2. **Create a case:** open **Investigations → Cases**, create a case, and record its purpose and starting identifiers.
3. **Choose an entry point:** use **Search → Console** for one identifier, **Search → Global Search** for web/news research, or a tool from the tables below for a specific task.
4. **Review before saving:** inspect the source, collection time, tool status, and actual result. Select relevant findings and add them to the case, or send supported results to its review inbox. Selecting a case context does not by itself save every result.
5. **Build the case:** add notes, questions, tasks, evidence, and graph connections. Treat account matches and extracted claims as leads until corroborated.
6. **Share and back up:** use the case's report/export actions for sharing, and **Investigations → Backup and recovery** for a verified case ZIP. Download a copy to separate storage.

A simple first exercise is to search a public username, review a candidate profile, save one supported observation, add a source note, and export a case report. A generated profile link is a place to look, not confirmation that an account exists or belongs to a particular person.

## 3. API access: the short answer

**Most Menace tools do not require you to obtain an API key.** This does not mean they all work offline: many contact public websites or public APIs, which may block requests, change their behavior, or impose quotas.

- **Local / no key:** processing happens locally after installation.
- **Online / no key:** the selected identifier or query is sent to external services, but no operator credential is required in this Menace mode.
- **Optional credentials:** basic operation is available without keys; configured providers or enrichment may need them.
- **Required credential:** that particular connector cannot run without the specified token/session.

These tables describe Menace's configured integrations. Upstream tools may support additional providers, keys, AI features, or scanning modes that Menace does not expose. A tool being installed or passing its startup check does not confirm that every external source currently works.

## 4. Account, email, and telephone addons

Open **Tools → Addons**. Names in the first column are the labels shown in Menace; the upstream project follows in parentheses.

| Tool | What it does | API / account requirement |
| --- | --- | --- |
| Basic Search (Sherlock) | Checks supported sites for a supplied username and returns candidate public profiles. | **Online / no key** for the integrated mode. |
| Advanced Search (Maigret) | Broader username searches and profile analysis. | **Online / no key.** Optional upstream AI features are not enabled. |
| WhatsMyName Search (Naminter) | Searches username patterns using the WhatsMyName dataset. | **Online / no key.** |
| Social Profile Analysis (Social Analyzer) | Searches supported platforms for public profiles matching a username. | **Online / no key** in the integrated mode. |
| Platform Scanner (Aliens’ Eye) | Checks supported platforms for username matches. | **Online / no key** in the integrated mode. |
| Instagram Intel (Toutatis) | Retrieves Instagram account information available through an authenticated session. Returned fields depend on platform access. | **Required Instagram session ID** (`INSTAGRAM_SESSION_ID`). This is a login session, not an API key. It can expire. |
| Account Availability (Socialscan) | Checks supported services for username/email availability signals. | **Online / no key.** Availability is not identity verification. |
| Account Search (Blackbird) | Searches supported services by username or email. | **Online / no key** for public search. An Instagram session is **optional** for enrichment; AI features are not enabled. |
| Email Accounts (Holehe) | Checks supported services for account-registration signals associated with an email address. | **Online / no key** in the integrated mode. Signals may be incomplete or blocked. |
| Phone Intelligence (PhoneInfoga) | Combines number parsing and available scanners/search leads. | **Optional credentials.** Local parsing needs none; some provider scanners need keys and otherwise skip. |
| Phone Account Check (Ignorant) | Checks supported services for phone-registration signals. Enter the country calling code separately. | **Online / no key** in the integrated mode. |
| Phone Enrichment (Clank) | Returns local numbering metadata, including region and original carrier allocation. | **Local / no key.** Menace uses its local mode, not paid-provider enrichment. |

Phone metadata does not identify the subscriber, establish current ownership, or show live location. Carrier allocation may be outdated after a number is ported.

## 5. Domain, URL, and retained-evidence tools

Open **Tools → Research** for these tools. Evidence Metadata uses an original document retained through the case's **Evidence reader**. Email Evidence is also available directly under **Tools**.

| Tool | What it does | API / account requirement |
| --- | --- | --- |
| URL Inspector (Unfurl) | Breaks an HTTP(S) URL into components and decodes supported parameters, identifiers, and embedded timestamps. It does not visit the URL. | **Local / no key.** Remote lookups are disabled. |
| Historical URL Discovery (waymore) | Finds historical URLs for a domain through Wayback Machine and Common Crawl. Menace uses URL-only mode. | **Online / no key** for these selected sources. It does not download archived page bodies in this mode. |
| Passive Subdomains (Subfinder) | Finds subdomain leads through crt.sh and HackerTarget. Menace does not actively resolve the returned hosts in this mode. | **Online / no key** for the selected sources. Other upstream Subfinder providers may require keys. |
| Brand Impersonation (dnstwist) | Generates a limited set of look-alike domain variants and checks DNS. | **Online / no key.** A registered variant alone does not establish impersonation or malicious activity. No website comparison or SMTP probing runs. |
| Organization Footprint (theHarvester) | Collects infrastructure leads through crt.sh and AlienVault OTX. | **Online / no key** for the selected sources. Menace does not enable the full upstream provider set or promise comprehensive email discovery. |
| Evidence Metadata (ExifTool) | Reads metadata from a retained original PDF/image, such as author, software, dates, camera details, or GPS fields when present. | **Local / no key.** Metadata may be absent or edited. |
| Email Evidence (Mail-Parser) | Parses an uploaded `.eml`: headers, delivery hops, inert body text, links, attachment metadata/hashes, and parser warnings. Retains the original message and its hash. | **Local / no key or email login.** Does not connect to a mailbox, execute attachments, load remote images, or independently verify SPF/DKIM/DMARC. |

**Email workflow:** choose a case, upload one original `.eml` (up to 5 MB), inspect the parsed message, then choose **Review extracted findings**. Select only the findings you want to save, send to review, or export. Use **Inspect URL locally** on a message link to decode it without visiting it. Outlook `.msg` conversion and direct mailbox import are not included.

**Metadata workflow:** upload the original PDF/image through **Evidence reader**, then use its metadata action. Earlier normalized screenshot attachments may have had embedded metadata removed, so use the original file when metadata matters.

## 6. Built-in research and search tools

| Tool / source | What it does | API / account requirement |
| --- | --- | --- |
| Global Search (DDGS) | Searches the selected web/news engine with query previews and filters; retains queries and result provenance. | **Online / no operator key** in the exposed modes. Search engines may block or rate-limit requests. Snippets are not full-page evidence. |
| Console / Unified Search | Routes supported identifiers to collectors and research links. Unified Search combines selected compatible sources. | Depends on the selected source; most need no key. See the connector table below. |
| Address Breakdown (usaddress) | Parses U.S. address text into labeled components. | **Local / no key.** Does not verify deliverability, residents, or ownership. |
| International Address Breakdown (libpostal) | Parses international address text and offers normalized suggestions while preserving the input. | **Local / no key** after model installation. Does not verify an address. |
| Address Location (geopy / Nominatim) | Returns location candidates for an address or reverse-geocodes coordinates. | **Online / no key** with the default public Nominatim service. The UI requires public-place confirmation. Use a suitable administrator-configured endpoint for confidential data. |
| Nearby Places (OpenStreetMap Overpass) | Finds mapped amenities, businesses, or landmarks near supplied coordinates. | **Online / no key** with the configured public service. Proximity does not establish a relationship. |
| Social Profile Details (socid-extractor) | Fetches a supplied public profile page and extracts available fields locally. | **Online / no key or login.** No JavaScript browser rendering; unsupported or blocked pages may fail. |
| Telephone Investigation Panel | Combines offline number metadata with optional PhoneInfoga and web-mention searches. | **Local / no key** for metadata; selected online sources contact services. PhoneInfoga can use operator-configured provider credentials. |
| Archived Page History | Lists existing Internet Archive captures of one exact public URL. | **Online / no key.** Does not create an archived snapshot. |
| Evidence reader / OCR | Retains original supported PDFs/images and provides text reading, page search, and supported OCR. | **Local / no key.** OCR accuracy varies; check the original. |
| Source changes / source monitoring | Captures public page text and compares observations; optional schedules repeat checks while the production app runs. | **Online / no key or login.** Does not render a browser, run page scripts, or authenticate to sites. |
| OSINT Links | A searchable directory of external research destinations. | **No key to browse the directory.** Linked sites have their own account, access, and pricing requirements. |

Some Console domain/IP collection makes direct DNS, TLS, or HTTP requests. A tool needing no API key does not imply that every operation is offline or purely passive.

### Console connector credentials

| Connector | Coverage in Menace | Credential requirement |
| --- | --- | --- |
| GitHub | Public user/profile metadata. | No key required; **optional `GITHUB_TOKEN`** for authenticated quota. |
| GitLab | Public exact-username matches. | No key required; **optional `GITLAB_TOKEN`**. |
| Bluesky / Hacker News | Public user/profile metadata where available. | **No key** in the integrated mode. |
| Email, domain, and IP lookups | Format/DNS checks, public records and related research leads depending on the selected collector. | **No operator key** for built-in modes. An external research link does not mean Menace has called that site's API. |
| Bitcoin / Ethereum | Selected public mainnet address statistics and a bounded transaction sample through Blockstream / Blockscout. | **No key** for the exposed connectors. Not a complete cross-chain or token investigation. |
| Wikidata | Structured name/entity candidates. | **No key.** Candidates are not identity verification. |
| SEC company lookup | U.S. company name/ticker/CIK matches from the company ticker dataset. | **No API key**, but **`SEC_USER_AGENT` is required** with organization/name and contact email. This is an identifying request header. |
| CourtListener | Indexed U.S. court-opinion search. | **Required `COURTLISTENER_TOKEN`** in Menace. Not a complete court-record search. |

Cases, graphs, investigation questions, comparisons, workflows, review decisions, reports, and backups do not require a separate third-party API key.

## 7. Configure credentials only when needed

### PhoneInfoga, Toutatis, and Blackbird

Open **Help → Tool Health**, find the tool, and expand **API and session configuration**.

| Setting | Used by | Purpose |
| --- | --- | --- |
| `INSTAGRAM_SESSION_ID` | Toutatis; optionally Blackbird | Authenticated Instagram access. Treat a session value like a password. |
| `NUMVERIFY_API_KEY` | PhoneInfoga | Optional APILayer number-verification provider. Provider plans and quotas apply. |
| `GOOGLE_API_KEY` + `GOOGLECSE_CX` | PhoneInfoga | Optional Google Custom Search scanner; both settings are needed. Check current provider eligibility before arranging access. |

Save credentials on the relevant tool card. Stored values are not redisplayed. Blank fields retain existing values; removing a local value can leave an administrator-supplied environment value active. These settings are stored locally with restricted file permissions, without encryption, and are excluded from case exports. Back up the installation's private configuration securely.

PhoneInfoga uses its available scanners and skips those requiring missing credentials; its [scanner documentation](https://sundowndev.github.io/phoneinfoga/getting-started/scanners/) explains the provider distinctions. Toutatis's [upstream usage](https://github.com/megadose/toutatis#usage) requires a session argument.

### GitHub, GitLab, SEC, and CourtListener

These connector settings use the application process environment; they are not fields on the Tool Health credential cards. Obtain a CourtListener token from your [account profile](https://www.courtlistener.com/profile/api-token/). Menace adds the authentication header itself; supply the token value only. See the [CourtListener authentication documentation](https://wiki.free.law/c/courtlistener/help/api/rest/v4/rest-api-v47) and [SEC developer resources](https://www.sec.gov/about/developer-resources).

For Docker, an administrator must explicitly pass the desired variables into the `menace` service. Merely putting an arbitrary variable in `.env` does **not** pass it into the container. For example, add only the settings you need to the existing `environment:` list in `deployment/docker-compose.yml`:

```yaml
      - GITHUB_TOKEN
      - GITLAB_TOKEN
      - SEC_USER_AGENT
      - COURTLISTENER_TOKEN
```

Set their real values in your installation's private root `.env` file or launching shell. A `SEC_USER_AGENT` value should identify the operator, for example `Example Research Team contact@example.org`. Recreate the service from the project folder to apply environment changes:

```sh
docker compose -f deployment/docker-compose.yml up -d --force-recreate
```

For a native Python runtime, set the variables in the shell that launches Menace. Keep real values out of case notes, shared commands, screenshots, and source control. Optional API providers may have their own charges; using Menace does not provision provider accounts.

## 8. Common questions

**A tool says Ready or Installed but finds nothing.** That confirms local availability, not current platform coverage. Review History for a block, rate limit, unsupported input, expired session, or missing provider configuration. An empty result does not prove absence.

**Where is my research?** History keeps run output. Case findings are the records you explicitly saved or accepted. A case ZIP includes its retained evidence and accepted findings, but not unrelated global History or operator credentials.

**Can I use my usual browser?** Yes. Open Menace in your preferred browser. An embedded research browser and Capture to Case browser extension are not included in v0.4.0.

**How do I protect my work?** Create verified backups through **Investigations → Backup and recovery** and download them to separate storage. Keep the root `data/` folder and private deployment configuration when moving an installation. Report exports are for sharing; use case ZIPs for restoration.

**How do I stop or restart Menace?** Run from the project folder:

```sh
docker compose -f deployment/docker-compose.yml stop
docker compose -f deployment/docker-compose.yml start
```

**How do I update?** Run `python3 install.py` from an updated source checkout. For a newer published stable GitHub release, use `python3 install.py --check` and `python3 install.py --update`. A local version number does not imply a release has been published.

## Further reading

[Installation and troubleshooting](INSTALL.md) · [Terminal guide](CLI.md) · [Research integrations](GITHUB_RESEARCH_TOOLS.md) · [Email Evidence](EMAIL_EVIDENCE.md) · [Global Search and research tools](GLOBAL_SEARCH.md) · [Advanced case features](ADVANCED_RESEARCH.md) · [Backup and review workflows](RESEARCH_WORKSPACE.md)
