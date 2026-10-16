# OSINT Menace Terminal Guide

## Full platform and web feature access

Username/Auto defaults include all candidate profile URLs from the web app.
The review screen shows the selected coverage. In Advanced options, choose
Candidate profile platforms to view the capability list and select numbers,
ranges, or `all`. Direct API checks and unverified candidate links are labeled
separately. Direct-check sources and candidate-link selections are independent.

```bash
python menace.py platforms
python menace.py platforms --json
python menace.py search example --type username
python menace.py search example --type username --mode links --profile-site reddit --profile-site youtube
python menace.py search example --type username --mode collect --platform gitlab --platform hacker-news
python menace.py links --category Username
python menace.py links --filter github --json
python menace.py links --category Username --case CASE_ID --select 1,3-5
python menace.py export CASE_ID --format html --output report.html
```

`--profile-site` uses the slugs shown by `platforms` and can be repeated. `all`
selects the full catalog. Custom forum patterns and search-engine links remain
available in links/both mode. None of the candidate-only URLs are automatically
claimed as existing profiles.

The main menu includes OSINT Links with category selection, text filtering,
pagination, and saving selected links into the active case. Source credit to
OSINT4ALL is displayed. The direct `links` command uses the same catalog and
supports JSON output and selective case saving.

Terminal users can run every web search type, inspect/filter results, save
individual findings/links, create/manage cases, edit dossiers, use the demo,
and export Word, Markdown, JSON, or HTML. CLI HTML exports embed their styles
and remove server navigation and scripts so the file works independently of
the web server. They can also be printed or saved as PDF through a browser.

Additional API references: [GitLab users](https://docs.gitlab.com/api/users/) and
[Hacker News API](https://github.com/HackerNews/API).

## Direct collection

Normal terminal output uses labeled fields, readable statuses, wrapped text,
and numbered records rather than JSON dictionaries. Empty fields appear as
`Not available`; zero balances and false values remain visible. Source and check
time are shown with results. Add `--details` to `search` or `batch` for source
URLs, HTTP metadata, response hashes, and technical fields. The interactive
result menu offers the same technical view. `--json` retains the machine-readable
format and is unaffected by presentation settings. The original `osint_tool.py`
also uses the shared readable renderer for its text output.

Username and Auto Detect searches default to `--mode both`, exposing direct
checks plus the full candidate-link coverage of the web interface. Other types
default to `--mode collect`. Use `--mode collect` for direct observations only,
`--mode links` for request-free research links, or `--mode both` for both.

```bash
python menace.py search octocat --type username --platform github
python menace.py search bsky.app --type username --platform bluesky --json
python menace.py search '+442083661177' --type phone --region GB
python menace.py search https://example.com --type url --text-limit 4000
python menace.py search https://example.com --type url --excerpt 'Example Domain'
python menace.py search WALLET_ADDRESS --type wallet --wallet-source auto --limit 5
python menace.py search 'Ada Lovelace' --type name --record-source wikidata
python menace.py search 'Apple' --type records --record-source sec --jurisdiction US
python menace.py search 'example query' --type records --record-source courtlistener --jurisdiction US
python menace.py batch targets.txt --mode collect --timeout 10 --json
```

The menu exposes `url` and `records` search types, output mode, and customizable
collector settings. Source selection, default phone region, timeout, result
limits, and page text/excerpt controls persist between menu sessions. Direct
commands use their own explicit/default options. Repeat `--platform` or
`--record-source` to select multiple sources.

New collectors return source URLs, retrieval times, and explicit statuses:
`found`, `not_found`, `no_matches`, `blocked`, `rate_limited`, `error`, `invalid`,
`unsupported`, or `configuration_required`. Rate-limit headers are included when
the provider supplies them. No automatic retries or block bypasses are used.
Failures return exit code 1, while a completed lookup with no matches succeeds.
Existing domain/IP/email checks keep their legacy observations and source labels;
their older helpers do not yet provide the same per-request status detail.

### Source coverage and credentials

- GitHub: public profile metadata. Optional `GITHUB_TOKEN` increases the available
  authenticated quota. Profiles remain identity-unverified candidates.
- Bluesky: public profile metadata, resolving a full handle or adding
  `.bsky.social` to a short username.
- GitLab: exact username matches from the public users API. Optional
  `GITLAB_TOKEN` is used only for this provider if configured.
- Hacker News: public user metadata. A missing API activity record is reported
  as no match, not proof that an account does not exist.
- Other platforms remain candidate URL links in links/both mode and are not
  claimed as checked. Run `python menace.py platforms` for complete coverage.
- Phone: offline libphonenumber validation, formatting, region, type, original
  carrier allocation, and time zones. This does not establish ownership,
  assignment, live location, or current carrier after portability.
- Bitcoin: Blockstream mainnet address statistics, confirmed balance, pending
  delta, and a bounded recent transaction sample.
- Ethereum: Blockscout mainnet native ETH balance and recent transactions.
  ENS names are included only if returned by the provider. Token balances,
  cross-chain histories, and independent ENS resolution are not implemented.
- Wikidata: structured label/description candidates from a public knowledge base,
  not official identity or registry verification.
- SEC: company name/ticker/CIK matches from the US company ticker dataset,
  not searches for people or all business registrations. Set `SEC_USER_AGENT`
  to an organization/name and contact email as required by the source.
- CourtListener: indexed US court opinions with case names, courts, filing dates,
  snippets, and references. Set `COURTLISTENER_TOKEN`. This is not a complete
  court-record search. Jurisdiction is `US` for SEC and CourtListener;
  `world` is supported only for the Wikidata connector.

Set credentials through the environment, not command arguments. They are not
written to case files or CLI state. Requests do not send credentials to a
different origin after redirects.

### Page evidence and limits

Public page collection accepts public HTTP(S) destinations on ports 80/443,
checks every redirect destination, and pins the validated public IP for the
connection. Private/local networks and credential-bearing URLs are rejected.
The response limit is 2 MB; JavaScript is not executed. HTML/plain-text content
is supported, not PDF/image extraction.

Captured findings contain title, extracted text, final source URL, retrieval
timestamp, content type, and SHA-256 of the response body. The full raw body is
not stored. `--excerpt` keeps only an exact match from the extracted text;
an absent excerpt produces `no_matches`, never invented evidence. Select the
capture through the menu or use `--case CASE_ID --finding 1` for a single-section
result. Exports preserve this evidence as structured findings.

`--limit` bounds returned records/transactions (1-25), `--timeout` sets a socket
timeout (1-60 seconds), and `--text-limit` bounds saved page text (100-20000
characters). A timeout is not a total batch deadline. Some APIs return a fixed
page size upstream; the collector trims the displayed sample and does not
exhaustively paginate.

Implementation references: [GitHub users](https://docs.github.com/en/rest/users/users),
[Bluesky profiles](https://docs.bsky.app/docs/api/app-bsky-actor-get-profile),
[Blockstream Esplora](https://github.com/Blockstream/esplora/blob/master/API.md),
[Blockscout API](https://github.com/blockscout/blockscout-api-v2-swagger),
[Wikibase API](https://www.mediawiki.org/wiki/Wikibase/API),
[SEC developer resources](https://www.sec.gov/about/developer-resources), and
[CourtListener search](https://wiki.free.law/c/courtlistener/help/api/rest/v4/search).

The terminal interface runs without a browser or web server and shares the
case/dossier format with the web app. Run commands from the project folder.

## Install and launch

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python menace.py
```

On Windows, activate with `.venv\Scripts\activate`.

The menu opens when standard input is a terminal. Without a command and with
piped input, the program prints help. Use `batch -` to process piped targets.

## Interactive workflow

Run Search now follows **Search type -> Target -> Review -> Run**. Select a
friendly type name first; Phone asks for the number and default country,
Username asks for the handle and sources, and other types ask for their relevant
target. Explicit targets remain intact, including commas in names and URLs;
use Auto Detect or file import for multiple targets.

The review screen shows the target, output mode, relevant source settings, and
active case. Choose Run search, Edit target, Change search type, Advanced options,
or Select/change case. Username/Auto default to direct checks plus candidate links;
other types default to collection. Output mode, timeouts,
record limits, excerpts, custom forums, and scanning are under Advanced options.
Only options relevant to the search type are shown. Scanning starts off for
every search and requires an explicit selection to enable it.

Back at the review screen returns to target entry. Blank target input returns
to the type picker; Back there returns to the main menu. Invalid menu choices
are retried in place. Cancelling setup preserves your previous result workspace.
File import uses the same flow, with search type selected before the input file.

1. Select or create a case. The active case selection persists between sessions.
2. Run a search or import targets from a text/CSV file.
3. Review numbered findings and links. Select `1,3-5` or `all` to save them.
4. Open the case workspace to review items, add notes/tags, change status,
   remove an item, rename/edit the case, or archive/restore it.
5. Complete the dossier by section. Filled/empty indicators show progress.
6. Generate a report: include all items, relevant/verified items, verified
   items only, or individually selected items. Preview and export Word,
   Markdown, or JSON.

Each menu has `0` or blank input to go back. At the main menu this exits.
An interrupted search retains results for completed targets in the current
session so they can be reviewed and saved. Unsaved results are not retained
after exiting the program.

Save selections create one case item per finding/link. Exact duplicate values
within the same item type are skipped. Existing saved bundles are also checked.
Links with different paths, query strings, or trailing slashes remain distinct.

Review states are `unreviewed`, `relevant`, `verified`, and `rejected`.
Setting verified is an analyst decision; the program does not verify identity.

Archive is a reversible case metadata flag, not file deletion. Archived cases
remain selectable in the CLI and visible in the web app. Review controls and
archive editing are currently exposed through the CLI.

## Notes and dossier editing

For multiline text, finish with a line containing only `.`. `/keep` retains
the existing value; `/clear` clears it. `/editor` opens the editor configured
in `$EDITOR`, falling back to `vi`. Each dossier field is saved after editing.

## Direct commands

```bash
python menace.py --help
python menace.py search --help
python menace.py search exampleuser --type username
python menace.py search example.com --type domain --json
python menace.py create "Training Investigation" --notes "Scope and context"
python menace.py cases --json
python menace.py show CASE_ID
python menace.py search exampleuser --type username --case CASE_ID --link 1 --link 3
python menace.py items CASE_ID --filter unreviewed
python menace.py review CASE_ID ITEM_ID --status relevant --tags "profile,follow-up" --notes "Review notes"
python menace.py remove CASE_ID ITEM_ID --yes
python menace.py update-case CASE_ID --name "Updated name" --notes "Updated context"
python menace.py update-case CASE_ID --archive
python menace.py update-case CASE_ID --restore
python menace.py delete-case CASE_ID --confirm-name "Updated name"
python menace.py dossier --fields
python menace.py dossier CASE_ID --field summary --value "Analyst summary"
python menace.py export CASE_ID --format docx --status verified --output report.docx
python menace.py export CASE_ID --format md --item ITEM_ID --output report.md
python menace.py export demo --format docx --output demo.docx
```

Repeat `--status` or `--item` to include several values. Export filters affect
saved evidence only; the saved dossier narrative remains included. Review the
preview before sharing. Output files are created exclusively and never overwritten.

## Batch searches

```bash
python menace.py batch targets.txt --json
python menace.py batch targets.csv --case CASE_ID
cat targets.txt | python menace.py batch - --json
```

Text input uses one target per line. CSV requires a `target` header. Inputs are
deduplicated, with at most 250 nonempty input rows per batch. Targets run
sequentially. Progress/errors go to stderr so JSON stdout can be redirected.
Exit codes: `0` success, `1` failed command or batch target, `2` invalid command
arguments, `130` cancelled batch. Completed batch results still appear in output
and are saved if `--case` was supplied. Individual checks retain their module
timeouts; cancellation preserves completed targets, not a half-finished target.

## Advanced options

`search` and `batch` accept `--forum-pattern`, `--ports`, and
`--allow-port-scan`. Scanning is off by default; the menu asks explicitly when
running IP/Auto searches. The settings menu persists a default port list for
interactive searches; direct commands use their explicit/default arguments.

```bash
python menace.py --data-dir /path/to/data cases
python menace.py search exampleuser --type username --forum-pattern 'https://example.com/u/{username}'
```

The data directory defaults to this checkout's `data` directory. CLI state is
stored in `data/cli_state.json` and excluded from Git. Saved cases stay in
`data/cases`. Choose the same directory in the CLI and web runtime to share cases.
