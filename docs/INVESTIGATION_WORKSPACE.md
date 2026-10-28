# Investigation workspace

Open a case and choose **Investigation workspace**. The read-only demo includes sample events, confidence reviews, and tasks.

## Timeline

The timeline combines recorded case activity, evidence collection, screenshot capture or attachment, dated graph connections, and analyst-created events. Events appear from earliest to latest. Filter by type or UTC date range. Source links open the finding; relationship links select the corresponding graph connection. Add an analyst event with its event time in UTC, a note, and an optional link to a finding or connection.

## Confidence

Record Not assessed, Low, Medium, or High confidence for a finding or graph connection. An assessed level requires written reasoning. Attach any supporting case findings. Confidence supplements the existing verification status and hypothesis/supported labels; it does not change either automatically. Report exports include confidence, reasoning, and numbered supporting citations for selected items, respecting existing source exclusions.

## Tasks

Create a question or next step with details, an optional due date, and an optional link to evidence or a graph connection. Track Open, In progress, and Complete. Overdue flags use the UTC calendar date. Task changes are recorded in case activity. Tasks and analyst timeline events are available as optional report items; they are not included automatically.

## Report redaction

Enable redaction and enter literal text to replace, one entry per line. Matching is case insensitive. Include alternate spellings, usernames, and phone formats separately. PDF, Word, Markdown, and HTML report content replace matches with `[REDACTED]`; titles and download filenames are also handled. Reports omit all graph figures, photos, and screenshots while redaction is enabled, because text replacement cannot reliably remove identifiers from image pixels. Redacted graph descriptions, object details, and relationships remain available.

Review the report preview and exact PDF before sharing. This feature redacts the specified strings; it does not discover identifiers or guarantee anonymity. Original records, the investigation workspace, JSON exports, and backups retain original data. Turning redaction off restores the original report content.

All changes are saved under `investigation` in the case JSON. Backups preserve and validate these settings. Saving against an older case timestamp is rejected to prevent overwriting newer changes. Demo modifications remain blocked.
