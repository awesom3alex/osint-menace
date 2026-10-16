# Changelog

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
