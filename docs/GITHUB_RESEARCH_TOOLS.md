# GitHub research tools (v0.4.0)

Open **Tools → Research**, or a case's **Case tools → Research**. The original six additions have pinned sources and license metadata in `osint/addons/manifest.json`. Five use the existing cancellable addon queue; ExifTool reads retained evidence documents. Existing cases, reports, graphs, and the original twelve addons remain available.

Mail-Parser is now also available through the **Email Evidence** card and case menus; see [Email Evidence](EMAIL_EVIDENCE.md) for the original-message workflow.

## Included tools and uses

| Menace tool | Upstream | Current exposed mode | Practical use |
| --- | --- | --- | --- |
| URL Inspector | [Unfurl](https://github.com/RyanDFIR/unfurl) | Local HTTP(S) URL decoding with remote lookups disabled and Python socket connections blocked | Decode parameters, encoded values, and supported embedded timestamps; review the explanation for each derived field. |
| Historical URL Discovery | [waymore](https://github.com/xnl-h4ck3r/waymore) | Wayback Machine and Common Crawl, URL-only mode; one Common Crawl collection and bounded source requests | Find older company contact pages, discontinued paths, and historical document links. A historical URL is not a live page or proof of an archived capture's contents. |
| Evidence Metadata | [ExifTool](https://github.com/exiftool/exiftool) | Read-only extraction from an original PDF/image retained by Evidence reader | Review reported author/software fields, document dates, and embedded camera/GPS information when present. Metadata may be absent, stale, or edited. |
| Passive Subdomains | [Subfinder](https://github.com/projectdiscovery/subfinder) | Explicit crt.sh and HackerTarget sources; no active resolution; update checks disabled | Discover infrastructure leads for organization research, then add selected hosts to cases and graphs. Source lists are retained with reported results. |
| Brand Impersonation | [dnstwist](https://github.com/elceef/dnstwist) | Registered permutations using hyphenation, omission, and transposition with four DNS workers | Review look-alike domains. A registration/DNS answer does not establish phishing or malicious intent. No web-content comparison, SMTP probing, or screenshots run. |
| Organization Footprint | [theHarvester](https://github.com/laramies/theHarvester) | Explicit crt.sh and AlienVault OTX sources, limit 100, quiet mode, no DNS resolution/brute force, crawling, API scanning, screenshots, or Shodan | Gather additional passive infrastructure leads. These selected providers emphasize hosts; this mode does not promise comprehensive email or people discovery. |

The six sources have varying licenses: Unfurl/dnstwist Apache-2.0, waymore/Subfinder MIT, ExifTool under Perl's Artistic/GPL alternatives, and theHarvester's package metadata declares GPLv2. Preserve upstream notices. Current theHarvester development requires Python 3.14; the integration pins release 4.10.0 for the existing Python 3.12 runtime. Subfinder pins release v2.17.0. Other exact source revisions are recorded in the manifest. Python tools remain isolated from Menace and from one another. Transitive dependencies are resolved during installation and are not fully locked.

## Review workflow

1. Choose a case context and read the activity description on the tool's card.
2. Enter one URL or public domain and explicitly launch the selected tool. Simply visiting a page never starts a search.
3. Results open in History with progress, execution status, diagnostics, and cancellation. Case-associated addon results also appear in that case's review inbox after completion. Saving findings or accepting them in the inbox remains explicit. Decoded facts carry stable provenance IDs so duplicate inbox acceptance can be detected.
4. Review useful findings, save them, and use existing finding-to-graph actions. Original provider messages remain available separately from the readable result cards.

The URL Inspector accepts up to 2,048 characters and does not follow the supplied URL. Domain modes accept a domain without a path, port, wildcard, IP address, or command-line options. International domains are normalized to IDNA. The selected network modes disclose their named providers and do not load saved operator keys, user proxies, or inherited provider configuration. Python public-suffix parsing uses its bundled snapshot without an automatic list download.

Jobs retain the existing two-worker queue, process-group cancellation, 180-second outer time limit, bounded output, and durable History. Adapter subprocesses also use a shorter time limit and file/output caps. Structured results are capped at 500 records. Partial, failed, rate-limited, or empty results require inspection; startup success is not proof of live provider coverage. External requests already sent cannot be undone by cancellation. These subprocess controls do not constitute an operating-system network sandbox.

## Original-file metadata

Upload an original PDF/PNG/JPEG/WebP in **Evidence reader**, then follow its ExifTool link or select that case on Research. Each retained document has a **Read retained original metadata** action. The original's SHA-256 is checked before processing. ExifTool reads a temporary copy; the copy is checked afterwards, and the retained original is never passed to a write operation. Filesystem dates/paths belonging to temporary processing are excluded.

Results go to the existing research-results selection screen. Select fields for case saving, review-inbox routing, or JSON/CSV export. Each finding retains its original filename, original SHA-256, document ID, and optional finding reference. Extracted metadata is not automatically saved as case evidence; reviewed saved findings and original documents travel with the existing case ZIP backup. Global History is separate from case backups.

Existing normalized screenshot attachments have their embedded metadata removed by the older screenshot uploader. To inspect original metadata, upload the original file through Evidence reader. Metadata extraction does not add reverse-image search or remote image-analysis services.

## Installation and verification

Normal installation uses `python3 install.py`: it restores pinned sources and builds Docker. The image builds Subfinder alongside the existing Go tools, installs four isolated Python tool environments, and installs the pinned Perl ExifTool tree. The addon catalog now contains 17 launchable CLIs; ExifTool is the eighteenth source and is exposed through the retained-document workflow.

For native development, set `MENACE_ADDON_PREFIX` to a dedicated directory before starting the app; its default remains `/opt/addons`. `osint/addons/install.py` also accepts `MENACE_ADDON_SOURCES` to locate the pinned source tree. Install the selected Python tools and ExifTool using Python 3.12; build Subfinder with its required Go toolchain into `<prefix>/bin/subfinder`. No credentials are needed for the currently exposed provider sets.

Targeted startup checks (no target queries):

```sh
python osint/addons/check.py unfurl waymore exiftool subfinder dnstwist theharvester
```

Focused behavior checks:

```sh
python -m unittest tests.test_github_tools -q
```

The real Unfurl/ExifTool integration tests skip when those runtimes are absent. Provider parsing, source selection, review behavior, and validation use offline fixtures. No broad live reconnaissance is part of these tests.
