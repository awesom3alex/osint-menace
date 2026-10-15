# Changelog

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
