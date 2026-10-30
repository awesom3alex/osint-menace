# Changelog

## 0.4.0 — 2026-10-30

**More Sources. Fewer Alibis.**

- Replaced the featured release artwork with the supplied Investigation War Room image.
- Added a quickstart guide covering a first investigation, all 19 integrated tools, built-in research features, and API/session setup.

- Corrected Tool Health startup checks to launch each new research tool's executable instead of only checking its Python interpreter. Updated release test fixtures for all 17 launchable addons and explicit optional-runtime skips.
- Set the shared application/CLI version and Docker image tag to `0.4.0` and synchronized current installation documentation. GitHub publication is separate.
- Fixed installation preservation checks to validate writable SQLite snapshots including committed WAL data while leaving the mounted source data untouched.

- Reorganized the project around a root `install.py` entry point, with application code in `osint/`, Docker/setup/update helpers in `deployment/`, dependency lists in `requirements/`, development settings in `config/`, and guides/previews in `docs/`. Existing data and private configuration remain in place; native data paths and Docker/update references follow the new layout.

- Added isolated, pinned Mail-Parser Email Evidence workflow with original `.eml` retention/hashes, claimed headers and delivery hops, inert body previews, URL Inspector actions, attachment metadata, diagnostics, stable reviewed findings, case search, and verified backup portability. Parsing remains local; no sender authentication, remote-image loading, attachment execution, or `.msg` conversion is performed.

- Integrated pinned Unfurl, waymore, Subfinder, dnstwist, and theHarvester adapters into the existing queue, History, case review, cancellation, and readable output workflows.
- Added GitHub Research tool inventory with source/license/activity disclosures and read-only ExifTool extraction from retained original evidence, including hashes and reviewed JSON/CSV export.
- Added domain and local-URL modes to Unified Search, fixed provider sets without inherited credentials, and offline public-suffix parsing. Added a future-tool roadmap for email evidence, browser capture, and Office inspection.

- Added selected cross-case identifier comparison with retained analyst decisions and stale-comparison protection.
- Added local PDF/screenshot evidence reading with page search, original-byte retention, hashes, and portable backups; Docker now includes Tesseract English.
- Added investigation questions with supporting/conflicting evidence and retained revisions.
- Added opt-in public-source schedules with changed-text review, failure/retention pausing, and restored-case activation protection.
- Added reusable, ordered research workflows with explicit tool launches and saved step progress.

- Added a combined Telephone Investigation Panel, nearby OpenStreetMap places, local international address parsing with libpostal, and exact-URL archived page history. All outputs retain provenance and require explicit selection before saving to cases.

- Added DDGS Global Search with signed query previews, web/news and tailored telephone/address/social modes, explicit engines, region/language/time/site filters, deduplicated results, saved query settings, and durable search provenance.
- Added selected-result CSV/JSON export, reviewed case saving, and idempotent review-inbox routing with retained provenance and duplicate protection.
- Added local U.S. Address Breakdown, geopy/Nominatim location candidates with attribution and public-service privacy controls, and bounded public-profile extraction with network-disabled local parsing.

- Added an analyst review inbox for case-associated source-expansion results and retained source changes, with audited accept/dismiss/link decisions.
- Added side-by-side entity comparison, typed-identifier suggestions, and retained identity assessments without automatic merging or lost conflicting fields.
- Added selected chronology export to PDF/Word and case reports, with explicit date semantics, source numbering, report exclusions, and redaction.
- Added a case health checklist for missing provenance/attachments, overdue tasks, and unsupported connections/assessments.

- Added reviewed source expansion from findings and graph objects, compatible-tool previews, and explicit History-to-case saving.
- Added retained source-page text observations with timestamps, content hashes, and selectable change comparisons.
- Added a per-case dashboard for tasks, unverified findings, unsupported connections, changed sources, and recent activity.
- Added a backup/recovery center with saved verified case ZIPs, backup freshness, download, and non-overwriting restore previews.

- Added a main-page notice for newer stable GitHub releases, with cached checks, release notes, and per-release dismissal.
- Added `update.sh` to stage published release source, preserve the existing data mount and deployment settings, and run backed-up Docker upgrades with previous-image rollback.
- Expanded installation preservation checks to cover other data files and SQLite history, with private deployment-configuration backups.

## 0.3.0 — 2026-10-28

**Now With 37% More Menace — Statistics were fabricated.**

- Added saved graph views, inclusive relationship date filters with explicit undated handling, and persistent named milestones with automatic pre-restore snapshots.
- Added opt-in graph views, legends, relationship details, and linked evidence/screenshots to case PDF and Word reports; report exclusions also apply to linked graph content.
- Added case-local Cytoscape graphs with editable relationships, draggable and pinnable objects, photos, predefined and custom typed fields, reusable graph-local field templates, and editable legends.
- Added finding-to-graph actions, original finding links, undo/redo, PNG/JSON exports, concurrent-save conflict checks, and validated graph persistence in case backups and restores.
- Added graph search and filters, context menus, drag-to-connect handles, autosave and browser draft recovery, reversible branch/group collapse, annotations, duplicate suggestions with reviewed merging, evidence previews, relationship evidence links and dates, and a navigable mini-map.
- Simplified graph controls with action menus, folded field settings, and on-demand guidance; grouped shared navigation into Search, Investigations, Tools, and Help, and consolidated case/report exports.
- Bundled Cytoscape.js locally; documented graph workflows and limits in `docs/CASE_GRAPHS.md`.

### Report builder — 2026-10-27

- Added case-specific executive summaries with investigation purpose, key findings, and outstanding questions.
- Added report selection and ordering for findings, screenshots, notes, dossier sections, and graphs, without altering the original records.
- Added consistent numbered evidence references and a source appendix across preview, PDF, Word, and Markdown exports.
- Added a content preview, exact PDF preview, and warnings for missing summary sections, missing screenshots, and empty graph views.
- Preserved report exclusions and saved graph views; report settings persist in case backups, with conflict protection for concurrent edits.
- Validation limited to three focused checks: report integration coverage, live browser workflow, and rendered PDF/Word layout review.

### Fictional investigation demo — 2026-10-27

- Replaced the original two-record demo with the Cedar Trail Makers training investigation: six synthetic source records, fictional people and contact details, a relationship graph, two labeled synthetic captures, an executive summary, and numbered source references.
- Demonstrates supported connections, unresolved account attribution, and a ruled-out similar-name profile. All URLs use reserved example domains and phone numbers use the fictional 202-555-01xx range.
- Added read-only report preview navigation and bundled demo capture delivery. Existing demo mutation protection remains in place.
- Generated the sample investigation PDF and completed three focused checks: data/routes/read-only behavior, rendered PDF review, and the live demo/report workflow.

### Investigation workspace — 2026-10-28

- Added chronological, filterable evidence and relationship timelines with linked source records, graph connection focus, and analyst events/notes.
- Added finding and graph connection confidence assessments with reasoning, supporting findings, and numbered report citations.
- Added case tasks with due dates, source links, status tracking, overdue flags, and activity records. Tasks and analyst events can be selected in the report builder.
- Added literal-text redaction across PDF, Word, HTML, and Markdown reports, including report titles and safe download filenames. Redacted reports omit images while preserving original evidence and case records.
- Added backup validation, stale-edit protection, sample demo assessments/tasks, and native submission for investigation forms.
- Validation limited to three focused checks: integration coverage, actual PDF/Word content and layout, and live browser workflows.

### Case navigation and preparation — 2026-10-28

- Added case-wide search for evidence, identifiers, graph objects/connections, notes, confidence reasoning, and tasks, with type filters, pagination, and normalized phone-number matching.
- Added graph entity profiles combining identifiers, explicit connections, evidence, confidence assessments, and linked tasks. Profiles do not infer identity from matching names.
- Added advisory review before sharing based on selected report content and saved graph views, with links to unresolved findings, source issues, unsupported connections, missing report content, and unfinished tasks.
- Added blank, digital footprint, organization, and incident case starters. Nonblank templates create independent graphs, field definitions, tasks, and report outlines without changing existing cases.
- Grouped entity profiles, timeline/tasks, and sharing review under Case tools, with search directly accessible in the case header.
- Validation limited to three focused checks: case-tools integration coverage, live search-to-profile navigation, and live template creation/sharing review.

### Setup script

- Added `install.sh` for macOS, Linux, and WSL2 with Docker/Compose as the only host runtime prerequisites. It fetches pinned addon sources using a Docker helper, builds and starts the service, and can open the browser.
- Existing installations receive a stopped-service data backup outside the build context, a retained previous image, and automatic image rollback on upgrade failure. Three bounded checks cover health/version, original case/evidence/catalog preservation, and local screens without external OSINT searches.

### Release preparation

- Replaced the earlier announcement artwork with the supplied Steve image and featured it in the README for v0.3.0.
- Fixed terminal HTML exports to respect saved report composition and redaction, synchronized graph/report inclusion with concurrent-edit protection, and retained merged-source provenance while honoring report exclusions.

### Documentation

- Updated the install guide and current workspace/addon documentation for v0.3.0, including clean builds, stopped-service data backups, rollback, current case/report tools, production versus development ports, and three focused installation checks.

## 0.2.0 — 2026-10-16

### Added

- Twelve isolated GitHub addons with explicit tool selection and bounded background execution.
- Unified multi-tool searches, durable History, tool health observations, cancellation, elapsed time, and execution-state progress.
- Readable JSON results throughout the investigation workspace.
- Finding review states, analyst notes, report selection, screenshot evidence, source URLs, collection times, SHA-256 hashes, and integrity checks.
- Case timelines and reversible duplicate consolidation that preserves original results, source assessments, and attachments.
- PDF reports and richer HTML/Markdown exports.
- Case ZIP backups with file manifests, verified import previews, size/path/schema checks, and restore to a separate case without overwriting existing work.
- A shared Console-first menu, themed form fields, compact headers, and a top-right Passive Mode indicator.
- A runtime version sourced from `VERSION`, displayed in navigation and available at `/api/version`; release Docker image `osint-menace:0.2.0`.

### Maintenance

- Preserved the existing terminal workspace, public-source collectors, demo, dossier editing, and Word exports while integrating the web investigation workspace.

- Simplified application registration and shared navigation data.
- Formatted and checked first-party Python workspace code; removed unused imports.
- Separated save confirmation from optional case-panel refresh, so a display-refresh failure does not falsely report that a saved change failed.
- Excluded local preview screenshots and runtime investigation data from source control/build context.

### Scope and compatibility

- Image analysis and image reuse remain deferred and disabled. Previously saved image files and case evidence are retained.
- Existing case data remains compatible, including legacy findings without a source name and evidence without a historical file hash.
- Backup format remains version 1; the application version is recorded separately.
- Case ZIPs include attached evidence, notes, reviews, merges, timeline, and a Markdown report snapshot. Independent global History and server credentials are not included.
- Deployment remains a single Gunicorn worker with four threads and a trusted local-network interface. No new authentication or remote publication is part of this release.

## v0.1.0 – Beta: Works on My Machine Edition

Released October 14, 2026. This is a beta prerelease.

### Terminal workspace

- Interactive search wizard: select a type, enter a target, review settings, and run.
- Active cases, selective saves, duplicate detection, notes, tags, review states,
  item deletion, case renaming, archiving, and exact-name case deletion.
- Guided dossier editing, demo case, batch input, and source/limit controls.
- Readable output with optional technical details and machine-readable JSON.
- All 32 candidate username platforms, clearly distinguished from direct checks.
- Direct GitHub, Bluesky, GitLab, and Hacker News profile collectors.
- Phone metadata, Bitcoin/Ethereum summaries and transaction samples, public-page
  text/excerpts, and Wikidata/SEC/CourtListener source connectors.
- OSINT Links catalog browsing, filtering, pagination, and selective case saving.

### Reporting and web interface

- Dossier editing based on the supplied investigation-report structure.
- Editable Word reports and Markdown, JSON, and styled HTML exports.
- CLI HTML exports embed styles and work without a running web server.
- Fictional demo case with completed dossier and sample evidence.
- Updated navigation and a Demo option in the web interface.

### Maintenance and verification

- Tests grouped under `tests/`; 47 automated tests passed for this release.
- Local cases, CLI state, report exports, and credentials are excluded from Git.
- Updated README, installation instructions, and complete CLI guide.
- Live read-only collector checks succeeded during development for GitHub,
  Bluesky, GitLab, Hacker News, public-page capture, Bitcoin, Ethereum, and Wikidata.

### Beta scope

- Most username platforms provide candidate links only; account existence and
  identity association are not implied by a generated URL.
- SEC requires `SEC_USER_AGENT`; CourtListener requires `COURTLISTENER_TOKEN`.
  These connectors were tested with fixtures, not live configured credentials.
- Network sources can block, rate-limit, or change their responses.
- Phone output is numbering-plan metadata, not ownership or live location.
- Wallet transactions are bounded samples; cases use local JSON file storage.
- Unsaved result workspaces are not restored after exiting the CLI.
- Attachments, independent ENS resolution, and exhaustive records coverage are
  not included. Review the CLI guide for each provider's scope.
