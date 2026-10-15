# OSINT Menace

**v0.1.0 – Beta: Works on My Machine Edition**

See [CHANGELOG.md](CHANGELOG.md) for this release's changes and beta scope.

**Open-Source Recon Console**

Built for Hunters, Not Browsers.

OSINT Menace is a Defensive Thinking Project.

OSINT Menace is a Python application for case-driven OSINT research, with a terminal workspace and a Dockerized web interface. Analysts can collect public-source observations, review results, save useful findings to cases, and export reports.

The tool is designed for defensive research, digital footprint review, investigation note-taking, and authorized security work. It favors passive lookups, generated source links, public records pivots, DNS/RDAP information, certificate transparency, wallet explorers, and analyst-controlled case management.

## Status

This is an early local build intended to grow into a fuller site later. The current version is useful as a local analyst console and Docker-hosted prototype.

Check the installed version with `python menace.py --version`.

## Terminal Interface

See [CLI.md](CLI.md) for the complete terminal workflow and command reference.

Terminal searches support GitHub/Bluesky/GitLab/Hacker News public profiles,
phone metadata, Bitcoin/Ethereum summaries and recent transactions, public page
text/excerpts, and structured record-source matches. Username/Auto searches default
to direct checks plus the full candidate profile-link list; other types default
to collection. Choose `--mode links`, `--mode collect`, or `--mode both` explicitly.
The CLI also provides the OSINT Links catalog and standalone HTML exports.
SEC and CourtListener require source configuration; the CLI reports missing configuration and blocked/rate-limited
requests explicitly. See the coverage and credentials table in the CLI guide.

Run OSINT Menace without starting a browser or web server:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python menace.py
```

The numbered menu supports an active case, selective saves, duplicate detection,
case/item management, review statuses, notes/tags, guided dossier editing,
batch input, and a Word/Markdown/JSON/HTML report wizard. Direct commands support the
same saved-data operations:

```bash
python menace.py search exampleuser --type username
python menace.py search example.com --type domain --json
python menace.py create "Investigation One"
python menace.py cases
python menace.py search exampleuser --type username --case CASE_ID --link 1 --link 3
python menace.py dossier --fields
python menace.py dossier CASE_ID --field summary --value "Analyst summary here"
python menace.py show CASE_ID
python menace.py export CASE_ID --format docx --output investigation.docx
python menace.py export demo --format docx --output demo.docx
```

`--case` saves the full result unless `--link` selects numbered links from a
single target. Links remain candidates until the analyst verifies them.
`--data-dir /path/to/data` before the command selects another data directory;
the default is this checkout's `data` folder. Word exports use saved dossier
fields. Existing output files are never overwritten.

Use `python menace.py --help` or `python menace.py search --help` for flags.
The original `osint_tool.py` search CLI remains available.

## Application Features

- Cyberpunk-inspired Flask web interface.
- Docker-first deployment.
- Auto-detection for mixed target lists.
- Search modules for email, username, phone, full name, domain, IP address, and crypto wallet inputs.
- Passive-first OSINT workflow.
- Per-result and per-link case capture.
- Case workspaces stored as JSON files under `data/cases`.
- Delete individual case items when a result does not fit.
- Delete an entire case with exact-name confirmation.
- Export cases as Word, JSON, Markdown, and styled HTML reports.
- Download raw search results as JSON from the results page.
- Filter generated results in the browser.
- OSINT Links page with curated public OSINT resources.
- API endpoint for future site integrations.

## Safety Model

OSINT Menace is intentionally conservative by default.

Included by default:

- Public profile URL candidates.
- Search-engine pivot links.
- Gravatar checks.
- DNS records.
- RDAP/WHOIS-style public registration data where available.
- TLS certificate inspection.
- Certificate Transparency links and subdomain pivots.
- Wayback/archive links.
- Public reputation lookup links.
- Wallet explorer links.
- ENS lookup links.
- Optional basic port scan only when explicitly enabled.

Excluded by default:

- Credential hunting.
- Password or breach account enumeration against private services.
- Dark-web scraping.
- Onion crawling.
- Evasion logic.
- Login-required automation.
- Account discovery against private messenger or family-safety apps.
- API-key-only enrichment modules.
- Automated social media scraping that would require authenticated sessions.

## Search Types

### Auto

Auto mode accepts mixed targets separated by new lines, commas, or semicolons. It detects likely target types and runs the matching modules.

Examples:

```text
person@example.com
John P. Smith
example.com
1.1.1.1
0x0000000000000000000000000000000000000000
```

### Email

Email searches include:

- Format validation.
- Gravatar hash/profile pivot.
- Domain extraction.
- MX/provider clues.
- SPF/DMARC DNS posture.
- Search-engine query links.
- Public mention pivots.

### Username

Username searches include:

- Candidate profile URLs across common platforms.
- GitHub, Reddit, YouTube, Pinterest, Tumblr, Telegram, Mastodon, Bluesky, and other public profile-style pivots.
- Search-engine pivots.
- Optional custom forum URL patterns with `{username}`.

### Phone

Phone searches include:

- Format cleanup.
- Region/country guess where possible.
- Public search query generation.
- Public mention pivots.

Signal and Life360 account discovery are intentionally not automated.

### Full Name

Full-name searches include:

- Search query generation.
- LinkedIn/public profile pivots.
- Public records search links.
- Business filing search links.

### Domain

Domain searches include:

- DNS A, AAAA, MX, NS, and TXT records.
- SPF/DMARC posture.
- RDAP public registration details where available.
- TLS certificate metadata.
- Certificate Transparency links.
- Public CT-based subdomain discovery pivots.
- Technology hints.
- Archive/Wayback pivots.
- Reputation links.

### IP Address

IP searches include:

- IP validation.
- Reverse DNS.
- RDAP/ASN organization lookup.
- Geo approximation where available.
- Public reputation links.
- Passive DNS links.
- Optional basic port scan only when the user explicitly enables authorized scanning.

### Crypto Wallet

Wallet searches include:

- Bitcoin/Ethereum format validation.
- Explorer links.
- Public transaction summary pivots.
- ENS lookup pivots.

## Cases

Cases are the working folders for an investigation. They are stored in:

```text
data/cases/
```

The case workflow supports:

- Creating a new case.
- Saving a full search to a case.
- Saving one result section to a case.
- Saving one individual link to a case.
- Selecting a case when multiple cases exist.
- Auto-saving to the only case when exactly one case exists.
- Keeping the user on the results page after adding to a case.
- Deleting individual saved items.
- Exporting the case.
- Deleting the full case.

## Reports

Use **Edit Dossier** inside a case to complete the provided background,
investigation results, methodology, open tasks, and external search notes.
The dossier follows the structure of the supplied investigation template.
Saved searches and selected links remain supporting records and are listed
in a capture log. Dossier fields are analyst-entered and are included in
HTML, Markdown, and JSON exports. Use the HTML report's Print action to
print or save a PDF through your browser. Use **Download Word** on the case,
dossier editor, or report page for an editable DOCX. Save your dossier edits
before exporting. Photo attachments are not implemented in this version.

Each case can be exported in four formats:

- `JSON`: machine-readable case data.
- `Word`: editable DOCX dossier and saved evidence.
- `Markdown`: lightweight report text.
- `HTML Report`: styled final report page with metadata, summaries, findings, links, notes, and print support.

## OSINT Links

The `/osint-links` page includes a curated set of OSINT categories and links derived from:

https://start.me/p/L1rEYQ/osint4all

Credit is shown at the bottom of the OSINT Links page. The local catalog is stored at:

```text
data/catalog/osint_links.json
```

The default catalog excludes obviously unsafe identity-generation, onion mirror, and scraped-data entries.

## API

Health check:

```bash
curl http://localhost:8088/health
```

Run a search:

```bash
curl -sS http://localhost:8088/api/search \
  -H 'Content-Type: application/json' \
  -d '{"search_type":"auto","query":"person@example.com\nexampleuser\nexample.com"}'
```

Supported `search_type` values:

```text
auto
email
username
phone
name
domain
ip
wallet
```

## Project Layout

```text
.
├── menace.py               # Main CLI entry point and direct commands
├── cli_workspace.py        # Interactive search and case workflows
├── cli_catalog.py          # Platform coverage and OSINT Links catalog
├── collectors.py           # Direct public-source collectors
├── discovery.py            # Search modes and result classification
├── terminal_output.py      # Readable terminal output
├── app.py                  # Flask routes, case management, reports, API
├── osint_tool.py           # Shared search helpers and original CLI
├── dossier.py              # Dossier fields and Markdown sections
├── word_report.py          # Word report generation
├── demo.py                 # Fictional demo case
├── Dockerfile              # Python/Gunicorn container
├── docker-compose.yml      # Local service definition
├── requirements.txt        # Python dependencies
├── INSTALL.md              # Installation and operations guide
├── CLI.md                  # Terminal workflow and command reference
├── README.md               # Product and developer overview
├── data/
│   ├── cases/              # Saved case JSON files
│   └── catalog/            # OSINT Links catalog
├── exports/                # Local report exports, excluded from Git
├── tests/                  # Automated CLI, collector, and report tests
├── reference_scripts/      # Optional local reference notes/archives
├── static/
│   └── styles.css          # Cyberpunk UI styling
└── templates/              # Flask/Jinja HTML templates
```

## Development Checks

From the project root, with the dependencies installed:

```bash
python -m unittest discover -s tests -v
git diff --check
```

Tests use temporary case directories and mocked network responses. Live provider
availability is separate from this test suite. Save local reports under
`exports/`, for example:

```bash
python menace.py export demo --format docx --output exports/demo.docx
```

Saved cases, CLI state, credentials, and local exports are excluded from Git.
The `data/catalog` resource catalog remains part of the application.

## GitHub Sources That Inspired This Application

The following GitHub projects were reviewed as reference material for workflow ideas, target categories, UI/reporting concepts, defensive boundaries, or passive pivot patterns. OSINT Menace does not present these credits inside run results, but they are documented here for attribution and project history.

| Project | GitHub Source | What It Informed |
| --- | --- | --- |
| AVTrack | https://github.com/marie-jeannesotho844/AVTrack | Report/export thinking and investigation-result workflow ideas from a tracking-oriented tool. |
| E4GL30S1NT | https://github.com/C0MPL3XDEV/E4GL30S1NT | Modular OSINT CLI structure, username reconnaissance, email discovery, phone lookup, DNS/WHOIS-style pivots, and direct subcommand organization. |
| IG-Detective | https://github.com/shredzwho/IG-Detective | Investigation management, reporting concepts, and the decision to avoid auth-walled social automation in the default app. |
| LeakRecon | https://github.com/Webfooted-cupule499/LeakRecon | Leak/threat-intel workflow ideas, crypto tracker concepts, reporting structure, and safety boundaries around dark-web and credential modules. |
| OSINT-Profiler | https://github.com/Despairing-australiancrawl83/OSINT-Profiler | Multi-target profiling ideas for emails, phone numbers, usernames, and saved investigative reports. |
| OSINT Tool For TG / TeleOSINT | https://github.com/Flintgliboom/OSINT-Tool-For-TG | Telegram-related OSINT category awareness and the decision to keep private/API-gated account discovery out of the default workflow. |
| VENOM | https://github.com/ghostport-sudo/venom | Email, username, phone, domain, web UI, export/report, and passive module organization ideas. |
| CloudCheck | https://github.com/blacklanternsecurity/cloudcheck | Cloud/CDN/provider-awareness concepts for domain/IP enrichment and technology hints. |
| cloudgaze | https://github.com/Roentgenographic-skyline37/cloudgaze | Dashboard/product UI ideas, filtering concepts, and report/export interaction patterns. |
| Tookie OSINT | https://github.com/Alfredredbird/tookie-osint | Username discovery, profile URL coverage, internationalized OSINT-tool presentation, and platform-list thinking. |

The local `reference_scripts/` folder also contains duplicate E4GL30S1NT archive material. Treat the table above as the deduplicated source list.

## Legal And Ethical Use

Use OSINT Menace only for lawful, defensive, and authorized research. Do not use it to harass people, bypass privacy controls, scrape private services, enumerate accounts where terms prohibit it, or scan systems without permission.

The app generates public pivots and performs passive checks by default. If you enable the authorized port scan option, you are responsible for ensuring that you own or have permission to test the target.

## License Notes

Local development used archived reference projects under `reference_scripts/`, but the public GitHub package keeps that folder lightweight and ignores third-party zip archives by default. Those upstream projects have their own licenses and authors. Review each upstream license before redistributing, copying, or incorporating code from those projects.

OSINT Menace itself should maintain clear separation between:

- Original application code.
- Curated public links.
- Locally archived third-party reference material.
- Future modules that may require separate licensing, API keys, or permission gates.

## See Also

- [INSTALL.md](INSTALL.md) for setup, Docker commands, troubleshooting, and local development.

## Created by Alex Berta
- Alex Berta
- Alex@DefensiveThinking.org 
- Linkedin: /in/AlexanderBerta
- Buy Me A Coffee - https://buymeacoffee.com/alexberta
