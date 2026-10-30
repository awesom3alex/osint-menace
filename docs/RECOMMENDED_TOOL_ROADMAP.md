# Further tool recommendations

Browsertrix and oletools below remain proposals. Mail-Parser is now implemented; see [Email Evidence](EMAIL_EVIDENCE.md). The first six recommended tools are implemented in [GitHub research tools](GITHUB_RESEARCH_TOOLS.md). New tools should add a distinct investigation capability, retain source attribution, and fit the existing review/backup flow.

## Implemented: mail-parser — local email evidence

Source: [SpamScope/mail-parser](https://github.com/SpamScope/mail-parser). Its documented features include headers, Received chains, timestamps, MIME bodies, attachments, and parsing defects; it is Apache-2.0 licensed. Outlook .msg support has an additional system dependency.

Implemented Menace workflow: upload an .eml original, preserve bytes/hash, inspect claimed From/Reply-To/Return-Path and Received hops, extract URLs into URL Inspector, and route selected addresses/domains/IPs to case review. Present header claims separately from trusted delivery-system observations; do not equate header parsing or copied Authentication-Results with independent sender authentication. Disable remote image loading and never open attachments automatically. Start with .eml, bounded MIME expansion and attachment counts, then consider .msg.

Why useful: expands incident and phishing investigations with a new evidence type and reuses the new URL/file analysis tools.

## 2. Browsertrix Crawler — richer web evidence

Source: [webrecorder/browsertrix-crawler](https://github.com/webrecorder/browsertrix-crawler). It provides browser-based crawling in a dedicated Docker container and is AGPLv3-or-later licensed.

Proposed Menace workflow: explicitly capture one public page using a bounded browser job, retain rendered output and a portable web archive, attach a hash/collection time/final URL, then review it beside the current plain-text source observations. Start with one page, no login, no cross-site crawl, public-address/redirect controls, strict resource caps, and a separate worker. Do not expose the Docker socket through the web app. Large web archives need storage/backup support before activation.

Why useful: JavaScript-rendered pages and preservation of what an analyst actually reviewed exceed the current text-only source capture.

## 3. oletools — Office evidence inspection

Source: [decalage2/oletools](https://github.com/decalage2/oletools). The documented tools inspect Office/OLE/OpenXML structures, metadata, VBA macros, embedded objects, and DDE links. Its package uses a BSD-style license with additional third-party notices.

Proposed Menace workflow: accept original Office documents into a bounded document-inspection worker, report metadata and embedded links, flag reported macros/objects, and route selected indicators to review. Parsing would remain read-only; Menace would not execute macros, render active documents, or launch extracted objects. Add decompression limits, file-format validation, and retention rules first.

Why useful: complements ExifTool with structural evidence and suspicious-document investigation.

## Integration order

With Mail-Parser implemented, I would add Browsertrix for public-page preservation, then oletools when Office evidence is needed. Keep these as separate, opt-in capabilities. Existing username tools already overlap heavily; another broad username scanner has lower marginal value than these additions.
