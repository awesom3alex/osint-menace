# Investigation workspace — v0.4.0

Current release: **v0.4.0**. Production runs at **http://localhost:8088** using `osint-menace:0.4.0`. The Console and Addons remain available alongside these workspace destinations:

- `/unified`: one username, email, or telephone target with multiple selected compatible tools. Two workers execute tools; up to 32 jobs may be queued/running. Each tool keeps its 180-second and output limits. Unsupported tools, missing installations, and missing Toutatis sessions are rejected before any part of a batch starts.
- `/history`: successful Console/API searches and every addon/unified launch are stored under `data/workspace.sqlite3`. Reopen a search without rerunning tools. The list shows up to 200 matching searches; older records remain in the database. History recording was introduced in v0.2.0 and does not reconstruct earlier unsaved searches. Search history stores captured output but not command arguments or credentials. Tool output is redacted for the configured Instagram session. SQLite files are local and mounted with `data/`.
- `/tools`: installation and session presence, local CLI startup checks, last run/outcome, last successful exit, and observed rate-limit messages. Credentials are not validated. A successful exit is not proof of platform coverage or accuracy. Local startup checks run `--help` and do not query targets.
- Case findings now support Unverified / Confirmed / False positive, notes, and report inclusion. New addon captures split structured top-level facts and reported text URLs into separately reviewable findings. Original tool output stays in History. Existing saved case values are preserved. Saving a review or adding a result stays in place.
- Each finding accepts up to ten PNG/JPEG/WebP screenshots, up to 10 MB and 20 megapixels each. Images are decoded and re-encoded as PNG in `data/evidence/<case-id>/`; metadata is stripped. Source URL/caption and attachment time are retained. Screenshots are operator-provided evidence, not automatic webpage captures.
- Download PDF from a case. The PDF includes selected findings, source attribution/URLs, retrieval and review timestamps, verification status, notes, and screenshots with page numbers. HTML and Markdown exports respect report selection and include review context. JSON exports retain the full original case. The legacy PDF path limits large finding values to a clearly marked 40,000-character excerpt. Saved report-builder compositions use the shared ordered report path. JSON exports retain original captured values.

## Setup

Run `python3 install.py` from the source folder with Docker and Compose v2 already available. The installer fetches pinned addon sources, builds the application, backs up existing data, starts the service, and runs three bounded checks. `--no-open` skips browser launch; `--help` prints usage. See [installer instructions](INSTALL.md#using-installsh) for supported platforms, upgrade behavior, backups, and recovery.

## Persistence and operation

`start.sh` marks unfinished stored addon jobs as interrupted on a container restart. Jobs do not automatically rerun. All history is stored locally until deliberately removed; back up the complete `data/` directory while the service is stopped to capture cases, history, and evidence consistently. Existing cases are not migrated destructively. Case writes are serialized and replaced atomically in the single-worker deployment. Do not increase Gunicorn worker count without replacing the in-memory scheduler and case lock with cross-process coordination.

The service retains the existing local-network binding at port 8088. User authentication was not part of this update. Treat the local network as trusted; do not expose the port publicly.

## Validation

Use the three focused installation checks in [INSTALL.md](INSTALL.md#version-and-release-checks): service/version, browser and existing data, and one representative workflow. Routine upgrades do not require a full automated suite or all-addon smoke run. For development, choose the targeted tests for the behavior being changed; fixtures use temporary databases, cases, and screenshots.

Runtime workspace dependencies are in `requirements/requirements-workspace.txt`; the Dockerfile installs them after the isolated addon layers. Production uses a single Gunicorn worker with four threads. A stopped-service backup of all `data/` is the recommended upgrade snapshot.

## v0.4.0 case and report capabilities

| Destination | Behavior | Guide |
| --- | --- | --- |
| Case graphs | Editable objects, custom fields, photos, legends, search, filters, saved views, and milestones | [Graphs](CASE_GRAPHS.md) |
| Report builder and preview | Executive summary, content selection/order, numbered evidence, colored legend labels, PDF/Word/HTML/Markdown exports | [Reports](REPORT_BUILDER.md) |
| Investigation workspace | Chronological events, analyst notes, confidence/reasoning with sources, task status and due dates, report redaction | [Workflow](INVESTIGATION_WORKSPACE.md) |
| Search case and entity profiles | Search saved case content and view explicitly linked identifiers, evidence, connections, confidence, and tasks | [Case tools](CASE_TOOLS.md) |
| Review before sharing | Advisory review of selected report content, source gaps, unresolved findings/connections, and unfinished tasks | [Case tools](CASE_TOOLS.md) |
| New case templates | Blank, digital footprint, organization, and incident starters with independent fields, graph, tasks, and report outline | [Case tools](CASE_TOOLS.md) |

Graphs, report settings, timeline notes, confidence assessments, tasks, and redaction settings remain in case JSON and survive case backup/restore. Search and profiles use original case content; finding exclusions affect reports, not internal investigation access. Profiles do not automatically equate people or accounts that share a name.

Redaction replaces specified literal text and omits all graph figures, photos, and screenshots while enabled. It does not anonymize JSON, backups, entity profiles, or internal sharing-review pages. Review exports before sharing. The demo at `/demo` contains fictional people, reserved example domains, synthetic captures, and sample tasks/assessments; modifications to it remain blocked.

## Image features deferred

Image analysis and whole-image reuse have been removed from the active interface at the user's request. Their blueprints are not registered, so upload, analysis, image file serving, and reuse endpoints are unavailable. Their History entries are hidden without deleting the records. The source modules remain dormant for possible future research.

Saved originals and variants in `data/image_analysis/` and existing case evidence are preserved. Normal screenshot evidence, case review, and report exports remain available. No reverse-image provider or API integration is active.

## Investigation workflow

- Addons and Unified Search expose cancellation for queued and running tools. Queued jobs never start after cancellation; running process groups are stopped, and available output is retained as incomplete. Cancellation is not an undo of requests already sent by an upstream tool.
- Saved-search pages show finished tool counts, queued/running/cancelling/completed/failed/cancelled/interrupted states, observed rate limits, timestamps and elapsed seconds. Progress counts tools rather than estimating platform coverage. Addon output includes cancellation and a link to its saved search.
- Case timelines record creation, captures, reviews, case-note edits, evidence attachments, merges, undo, and saved-search removal. Existing cases derive known creation/search events without inventing earlier edit history.
- Duplicate candidates require the same target and matching values, plus matching labels for non-URL facts. URL comparison normalizes scheme/host and removes fragments while retaining paths and query strings. Review and merge explicitly; undo is available. Original JSON findings remain intact. Reports show the representative once, all contributing sources/reviews, and combined attachments; its report checkbox controls selection. New captures can be consolidated by undoing an existing group and reviewing again.
- New evidence uploads record original upload SHA-256, normalized PNG SHA-256 and byte count, source URL, upload filename, automatic attachment time, and optional operator-supplied UTC capture time. Embedded metadata is removed. Integrity checks compare current stored bytes with the recorded stored hash. Legacy attachments have no asserted hash. Hashes establish byte consistency, not source authenticity.
- Cases expose a provenance JSON manifest. HTML, Markdown and PDF reports include provenance and merged-source details.

## Case backup and restore

Each case offers **Download backup ZIP**, containing complete case JSON, all referenced PNG evidence (including excluded findings), a Markdown report snapshot, and a versioned manifest with sizes and SHA-256 hashes. Missing evidence or recorded hash mismatches prevent an incomplete export. Legacy evidence keeps its original metadata; manifest hashes describe the backup bytes and do not retroactively establish collection integrity.

**Cases → Restore a case backup** accepts a ZIP and verifies the manifest, recorded evidence hashes, file paths, PNG validity, and case/merge schemas. The preview shows counts and legacy hash limitations. Restoring always assigns a new case ID and evidence folder, preserves search IDs and merge references, and records the originating case/archive hash in the timeline. The original case is never overwritten. Files are written into a staging folder and the case becomes visible only after evidence has been placed successfully. Reusing a consumed preview is rejected.

Limits: 256 MB compressed, 512 MB expanded, 80 MB per evidence file, 16 MB case JSON, and 2,000 unique evidence files. Four pending previews are allowed, each expiring after one hour; expired uploads are removed on the next preview. Temporary uploads live in `data/pending_backups/`, excluded from Git and Docker build context. Backup routes require Flask 3.1 or newer for their larger per-request upload allowance; ordinary upload limits remain unchanged. Case ZIPs exclude independent search History, credentials, and deferred image-analysis originals. Other report formats are regenerated after restore. Backups are not encrypted.
