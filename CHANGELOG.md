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
