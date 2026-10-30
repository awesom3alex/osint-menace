# Email Evidence (v0.4.0)

Open **Tools → Email Evidence**, **Case tools → Email Evidence**, or the Email Evidence card on **Research**. Choose a case and upload one original `.eml` file. The integration uses the official [SpamScope/mail-parser](https://github.com/SpamScope/mail-parser) source, pinned by commit with its Apache-2.0 license in `osint/addons/manifest.json`, and installed in a separate Python environment. It does not require credentials or paid APIs.

## What is retained

The original message bytes, original filename, SHA-256, import time, and parsed review data are stored with the case. Originals are included in JSON exports and verified case ZIP backups. Restoring a backup preserves the email evidence without running the parser or contacting services. Downloading the original verifies its hash and forces a file download rather than rendering email content in the browser.

Each case supports 20 emails, each no larger than 5 MB, within the existing 16 MB case JSON limit (including base64 overhead). Duplicate original hashes in a case are rejected. Uploads use case revision checks so concurrent edits cannot be overwritten. A failed or oversized parse does not partially save an email. Global research History remains separate from case backups; retained originals and explicitly saved findings travel with the case.

## What the analyst sees

- Claimed From, Reply-To, Return-Path, To/Cc, Date, Message-ID, Authentication-Results, Received-SPF, and DKIM-Signature values.
- Original header values, including repeated header occurrences, alongside parsed addresses.
- Parsed Received hops, reported timestamps, and IP strings present in those headers.
- Inert plain text and text extracted from HTML. HTML is never rendered, remote images are never loaded, and links are never visited during parsing.
- HTTP(S) links/resource references with an **Inspect URL locally** action using Unfurl's existing offline URL Inspector.
- Attachment filenames, content types, dispositions, decoded sizes, and decoded-payload SHA-256 hashes when available. Nested container attachments whose payload is not separately decoded are explicitly labeled instead of assigning a fabricated hash.
- Parser defects, malformed-address recovery details, warnings, and From/Reply-To/Return-Path differences.

Message dates and Received timestamps are claimed event times. Import time is collection time. **No trusted mail-server boundary is configured:** Menace does not authenticate sender identity or independently verify SPF, DKIM, or DMARC. A pasted Authentication-Results header is only a claim in the uploaded message. Address mismatches and parser defects may be legitimate and do not establish malicious intent.

## Review and case saving

Choose **Review extracted findings** to open the existing result-selection screen. Select addresses, domains, IPs, URLs, attachment metadata, or the message summary. Save selected findings, send them to the review inbox, or export selected JSON/CSV. Findings preserve the original email ID, filename, hash, collection context, and Unverified status. Existing finding-to-graph and cross-case workflows apply to suitable typed identifiers.

Reopening derived findings for the same retained original reuses its research record and stable entry IDs. It does not automatically duplicate accepted findings. Case-wide search includes parsed email text, headers, attachment names, and other retained review fields. Email originals and full body previews remain internal evidence; report redaction applies to exported reports, not these internal screens. Only explicitly saved findings are considered by existing report workflows.

## Execution and resource boundaries

The worker has no provider credentials, blocks Python socket connections, and never opens message URLs or executes attachments. No attachments are written as separate files. Parsing uses a temporary copy of the original and a maximum of two concurrent email workers. A 30-second process-group timeout stops the parser and its children. Limits include 200 MIME parts, 20 nesting levels, 1,000 headers/200,000 header characters, 100 attachments/10 MB decoded attachment data, 200 extracted URLs, and 1 MB of parsed review output. Linux workers also have an address-space limit.

Plain-text and HTML-text previews are capped at 60,000 characters each. Long previews/headers and limited URL lists are labeled; the complete original remains downloadable. Resource-limit rejections are shown without treating the message as clean or malicious.

This initial workflow supports `.eml` only. It does not install Outlook conversion extras, scan attachments for malware, extract archives, render active documents, or perform live email-account checks.

## Installation and checks

The Docker build installs the pinned package under `/opt/addons/mail-parser`; the existing `MENACE_ADDON_PREFIX` override is supported for native development. This is a case-file tool, not another domain/username addon: the general CLI search inventory remains 17 tools, and the source manifest now has 19 entries.

Focused startup check (no network queries):

```sh
python osint/addons/check.py mail-parser
```

Focused behavior checks:

```sh
python -m unittest tests.test_email_evidence -q
```

Real extraction checks skip if the isolated runtime is absent. Fixtures cover conforming MIME, repeated/folded headers, malformed-address recovery, inert HTML, attachment hashing, MIME limits, original-file integrity, case backup portability, and reviewed findings.
