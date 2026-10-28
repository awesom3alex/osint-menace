# OSINT Menace

**v0.3.0 — Now With 37% More Menace — Statistics were fabricated.**

![OSINT Menace v0.3.0 release artwork: the Menace mascot asks Steve whether it works on his computer.](docs/images/osint-menace-v0.3.0-release.jpeg)

**Open-Source Recon Console · Built for Hunters, Not Browsers.**
A Defensive Thinking Project by Alex Berta.

OSINT Menace is a local investigation workspace with a Dockerized web interface and a terminal interface. Run public-source searches, review unverified leads, save useful findings to cases, attach evidence, and export reports.

[Quick start](#quick-start) · [Features](#features) · [Included addons](#included-addons) · [CLI guide](CLI.md) · [Changelog](CHANGELOG.md)

## Features

- **Console:** searches for emails, usernames, phone numbers, names, domains, IP addresses, and crypto wallets, including mixed-input detection.
- **Addons and Unified Search:** twelve isolated tools, compatible multi-tool searches, cancellation, execution states, elapsed time, and observed rate limits.
- **Readable results:** structured JSON presented as facts, cards, and tables, with raw output available for inspection.
- **History and tool health:** reopen saved web searches without rerunning them; inspect installation, local startup checks, and observed execution outcomes.
- **Case workspaces:** analyst notes, per-finding verification states, report selection, activity timelines, and reversible duplicate consolidation that retains original findings and source assessments.
- **Evidence provenance:** screenshot attachments, source URLs, attachment times, optional capture times, SHA-256 hashes, and file-integrity checks.
- **Dossiers and reports:** guided dossier editing, editable Word reports, PDF reports, and JSON/Markdown/HTML exports. Report capabilities differ by interface; see the guides below.
- **Backup and restore:** complete case ZIPs with referenced evidence and a file manifest; verified import previews restore into a separate case without overwriting existing work.
- **Case graphs:** editable relationship maps with photos, standard and custom typed fields, reusable graph-local field templates, per-graph legends, and PNG/JSON export. Add saved findings directly to a graph. See [Case graphs](docs/CASE_GRAPHS.md).
- **Graph investigation tools:** search/filtering, autosave and browser recovery, drag-to-connect, context menus, groups and annotations, collapsible branches, duplicate review, evidence previews, and a mini-map.
- **Graph views and reporting:** save layouts and filters, explore relationship dates, preserve named milestones, and include selected graph views with legends and supporting evidence in PDF and Word reports.
- **Report builder:** executive summaries, selected and ordered content, colored legend labels, numbered evidence references, and preview before export. See [Report builder](docs/REPORT_BUILDER.md).
- **Investigation workflow:** chronological evidence/relationship timelines, confidence and reasoning with supporting sources, tasks and due dates, and text redaction for shareable reports. See [Investigation workspace](docs/INVESTIGATION_WORKSPACE.md).
- **Case navigation:** case-wide search, graph entity profiles, advisory review before sharing, and digital footprint/organization/incident starter templates. See [Case tools](docs/CASE_TOOLS.md).
- **Terminal workspace:** interactive searches, batch input, direct public-source collectors, case management, reviews/tags, dossier editing, and standalone report exports.
- **Fictional demo:** explore a read-only sample case at `/demo` without running network searches.

Image analysis and image searching are currently **disabled and deferred**.

## Quick start

### Docker web interface

Use a checkout whose `VERSION` is `0.3.0`; the commands below build locally and do not assume a published v0.3.0 image or Git tag.

Requirements: Docker Desktop or Docker Engine running with Compose v2, and Bash on macOS, Linux, or WSL2. Download/extract the source archive or clone the repository. Host Python, Git, Go, and addon packages are not required by the setup script.

From the extracted project folder:

```bash
bash install.sh
```

If you prefer Git, clone `https://github.com/awesom3alex/osint-menace.git` first and run the same command inside `osint-menace`.

Open **[http://localhost:8088](http://localhost:8088)**.

The setup script fetches pinned addons, builds and starts Docker, and performs three focused checks. Rerun it to upgrade: it backs up existing data before replacing the container and attempts to restart the previous image if installation fails. Use `bash install.sh --no-open` to skip browser launch or `bash install.sh --help` for options. See [installer instructions and troubleshooting](INSTALL.md#using-installsh) for platform requirements, backup locations, and recovery. Docker itself is a one-time prerequisite.

The first build downloads tool dependencies and can take several minutes. Each Python addon uses its own virtual environment; Go tools are compiled from pinned sources. The running image is `osint-menace:0.3.0`.

```bash
# Check the running version
curl http://localhost:8088/api/version

# Stop the web app; saved data remains in ./data
docker compose down
```

Compose listens on all host interfaces at port 8088, allowing access from another computer on a trusted local network using the host’s LAN address. **There is no built-in authentication. Do not publish this port directly to the internet.**

See [INSTALL.md](INSTALL.md) for clean setup, backed-up upgrades and rollback, the three focused installation checks, troubleshooting, and development. Existing installations should preserve the full `data/` directory and their environment configuration before replacement.

### Terminal interface

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-workspace.txt
python menace.py --version
python menace.py
```

Examples:

```bash
python menace.py search exampleuser --type username
python menace.py search example.com --type domain --json
python menace.py create "Investigation One"
python menace.py cases
python menace.py export demo --format docx --output demo.docx
```

The terminal supports direct GitHub, Bluesky, GitLab, and Hacker News profile checks; phone numbering metadata; bounded Bitcoin/Ethereum summaries; public-page capture; record-source connectors; and candidate-link generation. Candidate links are not confirmation that an account exists or belongs to a particular person.

See [CLI.md](CLI.md) for commands, provider coverage, limits, and credentials. Web addon scheduling and the web History database are separate from the terminal result workspace.

## Included addons

Tools run only when explicitly selected. Outputs are leads to review, not identity or account-ownership proof.

| Menace tool | Upstream project | Input / purpose |
| --- | --- | --- |
| Basic Search | [Sherlock](https://github.com/sherlock-project/sherlock) | Username profile checks |
| Advanced Search | [Maigret](https://github.com/soxoj/maigret) | Broader username searches |
| WhatsMyName Search | [Naminter](https://github.com/3xp0rt/naminter) | Username searches using WhatsMyName data |
| Social Profile Analysis | [Social Analyzer](https://github.com/qeeqbox/social-analyzer) | Public-profile searches and analysis |
| Platform Scanner | [Aliens’ Eye](https://github.com/arxhr007/Aliens_eye) | Username matches |
| Instagram Intel | [Toutatis](https://github.com/megadose/toutatis) | Instagram details; requires `INSTAGRAM_SESSION_ID` |
| Account Availability | [Socialscan](https://github.com/iojw/socialscan) | Username/email availability checks |
| Account Search | [Blackbird](https://github.com/p1ngul1n0/blackbird) | Username/email searches |
| Email Accounts | [Holehe](https://github.com/megadose/holehe) | Supported-service email registration checks |
| Phone Intelligence | [PhoneInfoga](https://github.com/sundowndev/phoneinfoga) | Phone intelligence; some scanners need provider keys |
| Phone Account Check | [Ignorant](https://github.com/megadose/ignorant) | Supported-service registration checks; separate calling code |
| Phone Enrichment | [Clank](https://github.com/AnshumanAtrey/clank) | Local numbering, carrier-of-record, and region metadata |

See [addons/README.md](addons/README.md) for installation details, pinned revisions, source licenses, and limits. Many tools need no paid API key for their standard operation, but services can block, change, or rate-limit results. Toutatis needs a server-side session; SEC and CourtListener terminal connectors need their own configuration. Never commit credentials to Git.

## Typical investigation

1. Create a case and record the investigation’s scope and authorization.
2. Run a Console search or select compatible tools in Addons/Unified Search.
3. Review the findings and sources, then save useful observations to the case.
4. Add verification notes and evidence. Review duplicate candidates before merging them.
5. Select findings for reports, export the desired format, and download a case backup ZIP.

The interface keeps case saves in place so you can continue working. Cancellation stops unfinished addon work and retains available output, but cannot undo requests already sent to an external service.

## Backup preview

The example below uses synthetic data.

![Verified case backup preview using sample data](docs/images/backup-preview.jpg)

From a case, choose **Download backup ZIP**. On the Cases page, choose **Restore a case backup**, inspect the verified preview, and restore as a new case.

Case backups include notes, saved findings, reviews, timeline, duplicate groups, provenance, referenced evidence, and a Markdown report snapshot. Independent global History, server credentials, and deferred image-analysis originals are not included. Other reports can be regenerated after restore. Backups are not encrypted.

## Data and privacy

| Location | Contents |
| --- | --- |
| `data/cases/` | Case JSON, dossiers, reviews, notes, timeline, and merge records |
| `data/evidence/` | Case screenshot attachments |
| `data/workspace.sqlite3` | Web search History and observed tool health |
| `data/cli_state.json` | Terminal workspace state |
| `data/pending_backups/` | Temporary import previews, expiring after one hour |
| `exports/` | Default terminal report exports |

Runtime investigation data, credentials, downloaded addon source trees, and temporary artifacts are excluded from Git. Docker persists the host’s `./data` directory. For a full application backup including History, stop the service and back up that directory consistently.

Selected tools and collectors contact their upstream services with the supplied target. Case evidence uploads are stored locally; Menace does not submit uploaded photos to image-search providers. Do not place sensitive investigation details in public issues, screenshots, or sample data.

## Limits and operating scope

- Generated URLs, tool matches, availability responses, and registration checks require independent verification.
- Phone region/carrier output describes numbering metadata, not ownership or live location.
- Network services can return partial results, false positives, errors, or rate limits. A successful process exit does not establish complete coverage.
- Web addon execution uses two workers, bounded queues, and time/output limits. Keep the single Gunicorn process configuration unless the scheduler and file locking are redesigned for multiple processes.
- Evidence hashes verify byte consistency; they do not prove that a source or screenshot is authentic. Legacy attachments may not have a historical hash.
- This is an early local-network research application. Use only for lawful, authorized work, and respect service terms and access controls.

Detailed limits and persistence behavior: [WORKSPACE_FEATURES.md](WORKSPACE_FEATURES.md).

## Development and contributions

Install development tooling with `pip install -r requirements-dev.txt`. For normal installation or upgrades, use the three focused checks in [INSTALL.md](INSTALL.md#version-and-release-checks). When changing code, select the relevant test module and review the affected workflow; do not run the complete suite or every addon automatically.

For example, case navigation changes can be checked with:

```bash
python -m unittest tests.test_case_tools -q
```

Tests use temporary case data and fixtures. External provider coverage and credentials require their own explicitly selected validation; a passing local test does not establish live-source accuracy.

Report bugs or suggest improvements through [GitHub Issues](https://github.com/awesom3alex/osint-menace/issues). Include the version, reproduction steps, and redacted error output. Contributions should preserve source attribution, readable results, bounded execution, cancellation, and case/report compatibility.

## License and credits

OSINT Menace is licensed under [Apache License 2.0](LICENSE). Integrated tools and dependencies retain their own licenses. Pinned upstream sources and their licenses are fetched separately rather than vendored into this repository. Review those licenses before redistributing a combined build. Test fixtures have source notes in [tests/fixtures/README.md](tests/fixtures/README.md).

Created by **Alex Berta · Defensive Thinking**.

- Contact: Alex@DefensiveThinking.org
- LinkedIn: [AlexanderBerta](https://www.linkedin.com/in/AlexanderBerta/)
- Support: [Buy Me a Coffee](https://buymeacoffee.com/alexberta)

Documentation: [Installation](INSTALL.md) · [Terminal guide](CLI.md) · [Workspace details](WORKSPACE_FEATURES.md) · [Addon details](addons/README.md) · [Release notes](CHANGELOG.md)
