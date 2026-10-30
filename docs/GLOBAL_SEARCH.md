# Global Search and address/profile enrichment

These are v0.4.0 features. No feature starts a search just because a page is opened, and nothing is automatically added to a case.

## Global Search

Open **Search → Global Search**. Enter a name, email, username, domain, telephone number, address, or general query. Modes are All Web, News, Telephone, Address, and Social Profiles. Telephone can generate E.164, national, and international query variants; Social Profiles defaults to five social-network domains. These modes tailor indexed-web searches, not comprehensive subscriber/resident/account databases.

Expand filters to choose the engine, a paired region/language setting, SafeSearch, time window, up to five website domains, exact-phrase matching, telephone country, and 10/20/30-result limit. Web supports day/week/month/year windows; news supports day/week/month. Arbitrary date ranges and independent language/region combinations are not uniformly supported by DDGS and are not presented as guarantees. Engine filter coverage varies. Actual result URLs are also filtered to requested websites.

**Preview queries** shows the exact queries and effective filters without calling a search engine. **Run these queries** submits only that preview to the selected engine. Editing the form invalidates the preview; signed previews expire after 15 minutes or a server restart. There is no automatic fallback to another engine. At most three query variants run, with ten-second per-engine timeouts and two concurrent research requests per application worker. Production uses one worker. Queries are sent to the selected external engine, which may log/rate-limit requests.

Results preserve original input, query variants, engine, filters, retrieval time, title, snippet, URL, and any reported publication date/publisher. URLs are normalized for duplicate removal; this is not content comparison or identity resolution. Source snippets are not full-page evidence captures. Requests with errors retain their failures; partial results remain usable. Empty results do not prove absence of public information.

Filter the saved results by website and page through ten results at a time without rerunning the search. **Save query settings** creates a reusable bookmark, not a scheduled search. Saved queries can be removed; completed searches remain in History. Interrupted research requests are marked interrupted on restart.

## Selected-result actions

Select individual results or all results on the visible page, then:

- **Send selected to review inbox:** queue only those results for the chosen case. Sending the same selection twice does not duplicate inbox items.
- **Save selected as unverified findings:** explicitly add selected findings to a case while preserving provenance. Repeated saves of the same source result are rejected. Use each saved finding's existing **Add to graph** action after reviewing it.
- **Export selected JSON/CSV:** download the selected results. CSV cells are protected against spreadsheet formula interpretation. These exports contain research inputs/results, not an entire case backup.

A case context preselects a destination; it does not automatically save or queue findings. Accepted inbox results cannot later be duplicated by direct saving, and already-saved results must be linked rather than reaccepted in the inbox. Demo cases cannot receive research results. Captured data remains in local History until deliberately saved; case ZIPs preserve accepted findings and provenance but do not import the global SQLite History.

## Address Breakdown

Open **Tools → Research Tools**, select Address Breakdown, and enter the original U.S. address. `usaddress` runs locally and retains the exact original string, token labels, component grouping, and detected address type. Ambiguous/repeated labels are flagged and original tokens retained. This is parsing, not normalization, deliverability validation, property ownership, or resident identification.

## Address Location

Select Address Location, enter a public place/address (or select coordinate reverse lookup), choose output language and optional country filter, then run. Up to five candidates retain formatted address, coordinates, available bounds/components, provider, OpenStreetMap attribution, and a map link. No first candidate is automatically accepted as correct, and map/media content is not loaded automatically.

The default provider is `https://nominatim.openstreetmap.org`. Its policy prohibits personal/confidential submissions: public-service use requires explicit confirmation that the input is a public place. There is no autocomplete or bulk geocoding; requests are serialized with at least 1.1 seconds between them in the single-worker deployment. Existing results can be reviewed/exported without querying again. Downloaded candidates retain provider attribution, and coverage does not establish residency or ownership.

For confidential investigations, use an appropriate self-hosted/provider-approved Nominatim endpoint. Add an origin such as `MENACE_GEOCODER_URL=http://your-nominatim:8080` to `.env` and recreate the service with Compose. This is administrator configuration, not a user-supplied request URL. Data is sent to whichever provider is configured; running geopy itself does not make a third-party service private. No paid geocoding API is enabled automatically.

## Social Profile Details

Enter a known public HTTP(S) profile URL. The existing public fetcher validates DNS destinations, pins connections, and revalidates redirects; private/reserved addresses and credentials are refused. No login, browser cookies, URL mutation, private API activation, or access-control bypass is used. A response is limited to 1 MB; local parsing runs in a subprocess with a twelve-second limit and network calls disabled. Inference postprocessors that invent email/username associations are excluded. Avatar/media URLs are retained only as text, not downloaded automatically.

The original URL, final fetched URL, page-content SHA-256, collection time, extractor output, and limitations remain available for review. Platform coverage varies; blocked/script-only/unsupported pages produce an explicit failure rather than a fabricated profile. No AI fallback is enabled.

## Packages and operation

Reviewed direct versions are pinned in `requirements/requirements-discovery.txt`: DDGS 9.16.1, usaddress 0.5.16, geopy 2.5.0, and socid-extractor 0.1.1. Docker installs these in the application runtime; existing addon virtual environments remain separate. Python development also needs `pip install -r requirements/requirements-discovery.txt`. Upstream package licenses and provider/data terms still apply.

Implementation references: [DDGS](https://github.com/deedy5/ddgs), [usaddress](https://github.com/datamade/usaddress), [geopy](https://github.com/geopy/geopy), [socid-extractor](https://github.com/soxoj/socid-extractor), and [Nominatim public-service policy](https://operations.osmfoundation.org/policies/nominatim/).

## Telephone Investigation Panel

Research Tools now includes a combined telephone panel. Local libphonenumber metadata always runs; PhoneInfoga and public web mentions are separate opt-in sources. Enter a two-letter default number region. The exact original, E.164 form, possible/valid numbering-plan status, region, number type, original carrier allocation, and time zones are retained. Neither validity nor geographic allocation identifies the subscriber or current location.

PhoneInfoga runs with a 30-second limit, isolated working directory and environment, with only explicitly configured PhoneInfoga credentials from Tools, without unrelated API keys or `.env` files. Its upstream output and search links remain unverified. Optional web mentions use DDGS with up to three number formats and an explicit selected engine. Individual provider failures do not discard successful metadata/results. Selected findings can be saved, exported, or sent to the review inbox.

## Nearby Places

Use **Find nearby mapped places** on an address-location candidate, or select Nearby Places and enter latitude, longitude. Choose a radius of 100/250/500/1,000 metres and amenities, shops/businesses, or tourism/landmarks. Explicit confirmation is required before coordinates are sent to `https://overpass-api.de/api/interpreter`. Queries use a 12-second provider budget and bounded public fetch; no account or API key is required.

Up to 100 provider features are requested and the nearest 50 returned features are displayed with tags, approximate straight-line distance, coordinates or geometry centre, OpenStreetMap source link, and attribution. The result cap is disclosed; it is not an exhaustive nearest-neighbour search. Proximity does not establish a relationship. No resident, property-owner, or live-location information is inferred. Existing selection, case review, graph actions and exports apply.

## International Address Breakdown

Libpostal runs locally in a bounded subprocess with its model data included in the Docker image. Input is limited to 500 characters, preserving the exact original. Components remain an ordered list so repeated labels are retained. Up to ten normalized suggestions are shown separately and never overwrite the input. Parsing is not address verification.

`scripts/install_libpostal.sh` pins upstream source revision `25099c506612b34b23b1bfe286ca6321fcf06f35` and Python bindings `postal==1.1.11`; model artifacts are downloaded by that upstream revision's build tooling. Models substantially increase the Docker image and first build's downloads. Docker builds run the installer automatically. Native development needs libpostal and its models before installing `postal==1.1.11`; existing U.S. parsing does not depend on it. Model initialization happens per request with a 45-second wall limit and bounded worker memory/CPU. No address is transmitted by this tool.

## Archived Page History

Enter a public page/profile URL, optionally restrict dates, and explicitly authorize sending the URL to the Internet Archive. Lookup uses the exact URL, successful captures, content-digest collapse, and a 50-record cap. The date window is inclusive. Results are ordered newest first within the provider's returned slice; narrow the window when the cap is reached. The underlying read uses the public CDX index and `waybackpy` snapshot representation with bounded fetch, avoiding library retries and automatic archive creation.

Every result retains the original input, archived original, UTC capture date, archive link, MIME type, digest, provider and filters. A capture date is not a publication date. Captured content opens only when selected; no page is fetched, published, or newly archived automatically. Availability and social-platform archive coverage vary. Results are reviewed before adding to a case.

Additional pinned packages: `overpy==0.7`, `waybackpy==3.0.6`. No new paid API providers or credentials are enabled.

### Quick Add To Case

Each result card has **Add To Case** at the top right. Choose the destination case in the toolbar; this button saves only that card, even if other results are selected. Select several checkboxes and use **Add Selected To Case (count)** to save a batch from the current page. Existing results are skipped and repeated complete saves are refused. Findings retain source provenance and start as unverified. The destination toolbar stays visible while scrolling on desktop, with a normal flowing layout on small screens.

Add To Case and batch case saves complete in place: the current results page, filter and scroll position stay open, and a confirmation names the destination case. Saved card buttons show Added To Case for that destination during the current visit. Saved selections are cleared; other selections remain. Failures appear on the same page. Without JavaScript, a successful submission returns to the current results page and filter rather than opening the case.

### Persistent status and review preview

Saved status is read from the destination case, including findings accepted through the inbox, rather than relying on a temporary browser flag. Switching cases refreshes that status; the destination is remembered for this results page in the current browser session. A removed finding becomes available again when status is refreshed. Status requests are not cached. Case saves retain server-side duplicate protection.

Add To Case opens a review dialog for the unsaved selected results. Each title, analyst note, comma-separated tag list, and finding type can be adjusted before confirmation; cancelling does not save anything. Up to 20 tags of 40 characters each, notes up to 20,000 characters, and titles up to 1,000 characters are supported. Saved originals keep their original content, source URL, collection time and research provenance; the original label is retained separately when edited. Type and tags appear in case findings and reports and survive case backups. Confirmation saves in place and clears only saved selections. Existing saved findings are not silently overwritten.


## Unified telephone output and tool credentials

Unified PhoneInfoga output separates skipped/not-configured providers, returned facts, and labeled search shortcuts. Ignorant output becomes a table of reported registration signals; rate-limited platforms are marked not checked. Banners, progress bars and debug logs remain available in collapsed raw output. Case saves use the structured summary rather than banner/donation text. Generated search links and registration signals remain unverified. Explicit country calling codes normalize PhoneInfoga and Clank input to international format, preventing a local number prefix from being mistaken for a different country's calling code.

Open **Tools → Tool Health → API and session configuration** to configure PhoneInfoga's optional Numverify/APILayer key or legacy Google Custom Search key and search engine ID, Toutatis's required Instagram session, and Blackbird's optional Instagram session. Each field includes **API Information**. Other current addon modes do not require credentials; Clank stays in local mode. Google Custom Search JSON API is closed to new customers and existing customers must transition by January 1, 2027; see the linked Google documentation. Provider plans, quotas and access policies apply. Saving does not make a provider request or validate a credential, and tool startup checks only run help commands.

Values are written atomically to `data/private/tool-credentials.json` with directory mode 0700 and file mode 0600. They are not encrypted at rest. The directory is excluded from Git and Docker build contexts; the existing data bind mount preserves settings across container replacements. Case exports/history do not contain this credential file. Installation-level backups of the data directory must be protected as sensitive backups. The configuration page never echoes a saved value; blank fields retain values and removal clears only the local override. Server environment values remain active when a local override is removed. Configuration writes require a short-lived signed form token and reject cross-site browser submissions. Anyone able to access this installation can change its configuration.

New searches read credentials immediately. Child environments receive only the matching tool's known credentials; keys are not put in job records or added to case exports, and raw/URL-encoded secret values are redacted before output is stored. Changing credentials does not alter an already-running provider request. No credentials are tested automatically and no paid provider is enabled until a user supplies its credentials and runs the tool.


## Consistent addon presentation

Unified Search, saved History, and the individual Addons results view share the OSINT Menace output presentation. Structured JSON uses labeled facts and nested result groups; recognized text uses reported-signal tables and clickable public-link cards. Unrecognized lines remain accessible in collapsed raw output. Credits, donation text, progress bars and routine startup noise are omitted from the normal result view. A reported link or availability signal never establishes identity. Older plain-text Socialscan results cannot reliably recover color-only status; new runs use a bounded JSON result file and retain the original CLI log separately.

Local startup status on Tools is separate from provider availability. The grouped audit checks all 12 installed addon help commands, renders representative output for every tool, and reviews credentials for the enabled modes. It does not validate live platform responses or API subscriptions.
