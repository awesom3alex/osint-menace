# Research and recovery tools (v0.4.0)

## Expand sources

Open **Case tools → Expand sources**, use a finding's **Expand sources** link, or select a graph object and choose **Expand sources for this object**. Recorded emails, phone numbers, domains, IP addresses, and explicitly labeled usernames are suggested. Edit the identifier and choose its type before running anything.

Use the public-source Console or select compatible installed addon tools. Configuration and availability are shown before launch; nothing runs merely by viewing the preview. Source expansion uses the existing search collectors and bounded addon queue. It never enables port scanning. Platform checks may generate requests visible to external services; results remain unverified leads. Results open in History with the originating case preselected. Review them and explicitly click **Add to case**, then use the existing finding-to-graph action if needed. Nothing is silently added to a case or graph.

## Source changes

On a case finding, choose **Source changes**. Findings need a recorded source URL. **Capture current public page** fetches public HTML/plain text, removes scripts/styles, normalizes whitespace, and saves a timestamped text observation with its final URL and SHA-256. The original finding and screenshots are unchanged. The first capture establishes a baseline; subsequent captures can be compared using earlier/later selectors. Added and removed lines have both textual markers and color highlights. Comparisons display up to 600 lines; complete retained text is available below.

Captures are on demand, not scheduled. They do not log into sites, run page scripts, render screenshots, bypass access controls, or treat changes as confirmed investigative conclusions. Each redirect must resolve to public addresses; connections are pinned to validated DNS answers. Standard web ports only, four requests maximum, eight-second socket timeouts, 1 MB response limit, and 60,000 readable characters. Dynamic content can create noisy differences. Up to 25 observations per finding are retained without automatic deletion; case backup limits still apply. Captures are included in case JSON and verified ZIP backups, but are not automatically added to narrative reports.

## Investigation dashboard

Open **Case tools → Dashboard** for unfinished and overdue tasks, unverified findings, hypothetical connections or connections missing evidence links, and sources whose latest two observations differ. Counts cover the entire case, including findings excluded from reports. Lists show up to 30 items with links back to the relevant record; recent case activity is displayed below. This is an internal review workspace, not a shareable/redacted report.

## Backup and recovery center

Open **Investigations → Backup and recovery**, or **Case tools → Backups**. Each case shows its last successful saved backup and whether the case changed afterwards. **Back up now** saves a verified case ZIP on this host under `data/backups/<case-id>/`. It includes the case, source observations, and all referenced screenshots, even for findings excluded from reports. SHA-256 and the existing manifest/image validation are checked before a saved ZIP is offered for download or restore preview.

**Preview restore** uses the existing verified-import workflow. Review the preview before the final restore; restoration creates a new case and never overwrites the original. Uploaded case ZIPs use the same workflow. Up to 20 backups are retained per case; none are automatically deleted. Corrupt archives are rejected.

Download copies to separate storage: host-local backups do not protect against disk failure. Case ZIPs do not contain global search history, runtime credentials, or Docker settings. The installer/updater's stopped-service backup separately preserves the entire `data/` directory (including saved case backups and SQLite history), with private configuration backups. Saved backup files are excluded from Git and Docker build contexts. Demo mutation protection applies to every new action.

## Review inbox

Case tools → Review inbox lists pending findings from source-expansion searches explicitly associated with the case, plus retained changes between consecutive source observations. It does not assign unrelated global history to a case. Results from queued tools appear after they finish. Each action requires the current case revision and records a timestamped audit decision:

- **Accept:** save one search finding as unverified, or mark a source change reviewed. Original search results and observations remain intact.
- **Dismiss:** remove the item from pending review while retaining the decision and source.
- **Link:** associate the item with an existing finding, with optional reasoning, without changing that finding's value or verification status. Linked reviews appear beside the finding.

The Reviewed tab retains decisions; double submission cannot duplicate accepted evidence. Search-history records remain in SQLite; decision metadata is part of the case and its ZIP backup. A restored case has its observations and review decisions, but unrelated global History is not imported by a case ZIP.

## Entity resolution

Case tools → Resolve entities compares two graph objects side by side, including recorded photos, all fields, conflicting values, and source references. Typed email/phone/username/domain matches generate suggestions; a shared name alone never does. Suggestions are not identity claims. You can compare manually even without a matching identifier.

Record **same entity**, **different entities**, or **related, identity unresolved**, with required reasoning. Both objects and their original fields/photos are retained. Each assessment preserves comparison snapshots and photo fingerprints, and later assessments do not erase earlier ones. A decision does not merge objects or turn an unsupported graph relationship into a confirmed fact. The existing explicit graph merge controls remain separate. Identifier suggestions are capped at 100; filter the object picker to locate objects beyond its first 500 matches.

## Export investigation chronology

Case tools → Export chronology lets you select individual evidence collection, screenshot capture/attachment, relationship-date, and analyst-event entries. Save the selection before downloading PDF or Word. Optionally include the selected chronology in the regular case report, where it participates in report ordering and source numbering.

Dates identify **event time**, **collection time**, **capture time**, or **attachment time** rather than treating them as interchangeable. Analyst-supplied times are labeled as such; relationship hypotheses keep their status. Excluded findings and relationships linked to excluded sources are omitted. Exports reuse report redaction and source numbering. Internal case-activity logs are not automatically included. Undated records need dates before they can appear. Free-text analyst notes still require human review before sharing.

## Case health checklist

Case tools → Case health lists missing source URLs, missing screenshot files, overdue tasks, connections without valid evidence links, and medium/high confidence assessments without valid supporting findings. Links return to the relevant review/edit screen. Local derivations should be explained rather than assigned invented source URLs. The checklist covers the whole case, including findings excluded from reports, and does not change records or certify correctness. It checks attachment existence; use the existing Verify file integrity action for content hashes. External URL availability is not checked automatically.
