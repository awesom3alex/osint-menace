# OSINT Menace v0.4.0 Install Guide

This guide covers clean installs, data-preserving upgrades, operation, and troubleshooting for **OSINT Menace v0.4.0**. The production Docker service runs at **http://localhost:8088** using image `osint-menace:0.4.0` and container `osint-menace-addons`.

## Updating to a published release

The Console shows a notice when a newer stable GitHub release is published. From the original installation folder, use `python3 install.py --check` to check, or `python3 install.py --update` to stage the release and run the backed-up Docker upgrade. It preserves the existing data bind mount and resolved deployment settings. See [Release updates](UPDATES.md) for backups, active configuration paths, supported deployments, and rollback limits. Releases older than this feature need a one-time manual source update first.

## Requirements

You need:

- macOS, Linux, or Windows with WSL2.
- Docker Desktop or Docker Engine.
- Docker Compose v2.
- A terminal and Python 3 for `install.py`.
- Bash (included with macOS, Linux, and WSL2).
- A local source checkout or extracted source archive. The Python entry point uses the standard library; no host Git, Go, or addon packages are required. The Bash alternative does not require host Python.
- Internet access for Docker images, pinned addon sources, and build dependencies.
- A browser.

Global Search and the address/profile tools use the pinned packages in `requirements/requirements-discovery.txt`, installed by the Dockerfile. For local Python development, also run `pip install -r requirements/requirements-discovery.txt`. Configure `MENACE_GEOCODER_URL` in `.env` only when using an alternative/self-hosted Nominatim origin; see [Global Search](GLOBAL_SEARCH.md).

Optional for local Python development:

- Python 3.12 or newer.
- `pip`.
- A virtual environment.

## Quick Start

For terminal-only use, install the Python dependencies in a virtual environment
and run `python osint/menace.py`. No Docker service or web server is required.
See [CLI.md](CLI.md) for installation commands, the menu workflow, batch input,
case editing, and report exports.

Use a source checkout containing v0.4.0. Cloning a repository retrieves the version currently published there; a v0.4.0 Git tag or registry image is not required or assumed by these instructions.

From the project folder, run the single setup command:

```bash
cd /path/to/osint-menace
python3 install.py
```

The script fetches pinned addon sources in a temporary Docker helper, installs dependencies inside the application image, builds and starts the service, runs three bounded checks, and opens the case workspace. Docker itself must already be installed and running; the script never installs host packages or asks for `sudo`.

The same command upgrades an existing installation. It builds first, stops the old service only for a consistent backup, preserves the original data mount and configured Instagram session, and attempts to restart the previous image if replacement or validation fails. Backups are written outside the source folder in `../osint-menace-backups/`. Keep other Menace processes from writing to the same `data/` directory while setup runs.

Options:

```bash
python3 install.py --no-open  # install without opening a browser
python3 install.py --help
```

The three automatic checks cover service health/version, preservation of existing case/evidence/catalog files, and loading the case/demo screens. They do not execute external searches or the full test suite. Build failures leave the existing service running. If setup stops because a pinned addon checkout has local edits, preserve and resolve those edits before rerunning; the script does not reset them.

Open the app:

```text
http://localhost:8088
```

Check health:

```bash
curl http://localhost:8088/health
```

Expected response:

```json
{"ok":true}
```

## Using install.sh

The recommended entry point is `python3 install.py`. Its Bash helper, [`deployment/install.sh`](../deployment/install.sh), can also be run directly from the extracted project folder. Calling it through Bash also works when a downloaded ZIP does not preserve executable permissions.

| Command | Result |
| --- | --- |
| `python3 install.py` | Install or upgrade, run the three checks, and open the case workspace |
| `python3 install.py --no-open` | Install or upgrade without opening a browser; useful on a server |
| `python3 install.py --help` | Show prerequisites and options without changing anything |

### Before You Run It

- **macOS:** install and start Docker Desktop, then use Terminal.
- **Linux:** install Docker Engine with Compose v2 and give your normal user Docker access. Run setup as that user.
- **Windows:** install and start Docker Desktop with WSL2 integration, then run the command inside your WSL2 distribution. Native PowerShell and Command Prompt are not supported by this Bash script.
- Keep the source folder in a persistent location. Its `data/` directory is the production data bind mount.
- Use the same project folder when upgrading an existing installation. Keep the existing `.env` and stop other Menace processes that write to its data directory.

Docker must be installed and running before setup. The script installs application dependencies inside containers; it does not install Docker or other operating-system packages and does not require `sudo`. Optional provider credentials still need to be configured by the operator.

### What It Does

1. Confirms Docker and Compose are available and the image tag matches `VERSION`. A setup lock prevents two installers from running in the same folder.
2. Builds a small Docker helper containing Python and Git, then fetches the exact addon revisions in `osint/addons/manifest.json`. Existing modified addon checkouts are preserved and cause setup to stop for review.
3. Builds the application image while the current service remains available. Python addon environments and Go binaries are installed inside Docker.
4. For an existing container, retains its previous image and stops it briefly to take a consistent backup. A backup is also taken of any existing local `data/` during a fresh installation.
5. Starts the new image with the same `./data:/app/data` mount and configured environment, then runs the three bounded checks. The script retains an existing Instagram session when it was supplied only to the previous launch; an explicit current shell value or `.env` entry takes precedence.
6. Prints the running version, case/demo URLs, and backup folder. Unless `--no-open` was selected, it attempts to open the browser. The default URL is http://localhost:8088/cases; a customized published port is read from Docker.

The first clean build can take several minutes and requires internet access. Later runs reuse Docker's available cache. Setup uses the application code in the current checkout. To upgrade to a newer application release, update that checkout first and rerun the script; it does not update the Menace source branch automatically.

### Backups and Failure Recovery

Backups are created beside the project, outside its Docker build context:

```text
<project-parent>/osint-menace-backups/<UTC-timestamp>-<process-id>/
  data-before-install.tar.gz
  previous-image-id.txt       # existing-container upgrades only
  rollback.override.yml      # existing-container upgrades only
```

The archive contains the complete stopped-service `data/` snapshot, including cases, evidence, History, and database sidecars. It is private case data. Keep it and the retained `osint-menace:before-<timestamp>-<process-id>` image until you finish testing.

A build failure happens before the old service is stopped. If replacement or validation fails during an upgrade, the installer attempts to restart the previous application image using `rollback.override.yml`. It preserves current data rather than automatically restoring the older snapshot. If automatic rollback cannot start, the script reports that explicitly; use the manual rollback procedure below and inspect Docker logs. A failed first installation has no previous image to restart.

To manually restart the saved image, run this from the same project root with the same environment. Replace the backup folder placeholder:

```bash
backup_dir="../osint-menace-backups/YOUR_BACKUP_FOLDER"
docker compose -f docker-compose.yml -f "$backup_dir/rollback.override.yml" up -d --no-build --pull never menace
```

### Installer Troubleshooting

| Message or symptom | Action |
| --- | --- |
| Docker missing, stopped, or inaccessible | Install/start Docker and confirm your user has access, then rerun setup. On Windows, use the WSL2 terminal with Docker integration enabled. |
| Compose v2 missing | Install or enable the Docker Compose plugin, then rerun. |
| Compose image and VERSION do not match | Use the matching files from the same application release. For this release, `VERSION` is `0.4.0` and the image is `osint-menace:0.4.0`. |
| Existing container uses another data location | Run setup from the original deployment folder. The installer stops before touching that container. |
| Another setup may be running | Wait for it to finish. Remove `output/setup.lock` only after confirming no installer is active. Then rerun. |
| An addon source differs from its pinned revision | Preserve local edits and resolve the checkout mismatch. Setup does not discard changes. |
| Build or download fails | Read the Docker build error, restore internet access or resolve the reported dependency problem, then rerun. The previous service has not yet been stopped. |
| Port is already in use | Stop the conflicting service or change the host port in `docker-compose.yml`. Do not change the internal application port `8080`. |
| Service fails its startup checks | Read `docker compose -f deployment/docker-compose.yml logs --tail 80 menace` and the installer’s rollback message. Keep the backup while resolving the problem. |
| Browser does not open | Open the printed case URL manually. Browser launch is optional and does not determine installation success. |

Logs can contain sensitive investigation output; redact them before sharing.

## Docker Install

### 1. Confirm Docker Works

```bash
docker --version
docker compose -f deployment/docker-compose.yml version
```

### 2. Build And Start

Recommended setup on a clean checkout:

```bash
python3 install.py
```

For a manual build instead, host Python 3.12+ and Git are needed to fetch pinned sources:

```bash
python3 osint/addons/fetch.py
docker compose -f deployment/docker-compose.yml up --build -d
```

This builds the Python image and starts the container named:

```text
osint-menace-addons
```

The container listens internally on port `8080` and is exposed on the host at:

```text
http://localhost:8088
```

### 3. View Running Containers

```bash
docker ps
```

You should see `osint-menace-addons` running.

### 4. View Logs

```bash
docker logs --tail 100 osint-menace-addons
```

### 5. Stop The App

```bash
docker compose -f deployment/docker-compose.yml down
```

### 6. Restart The App

```bash
docker compose -f deployment/docker-compose.yml up -d
```

### 7. Rebuild After Code Changes

Source files are copied into the Docker image. After changing Python, templates, CSS, or docs that should be inside the container, rebuild:

```bash
docker compose -f deployment/docker-compose.yml up --build -d
```

## Upgrade an Existing Installation to v0.4.0

Recommended: rerun `python3 install.py` from the same project folder. Keep the same `.env` file and data directory. The script creates `data-before-install.tar.gz`, `previous-image-id.txt`, and `rollback.override.yml` in the backup folder printed at completion. It attempts image rollback automatically on failure; it does not restore an older data snapshot over newer work.

### Manual Upgrade Alternative

Keep the existing `data/` directory and the same environment or `.env` file used by the current deployment. If `INSTAGRAM_SESSION_ID` is configured, retain it without placing its value in commands, screenshots, or release notes. Existing cases do not require a destructive migration.

First update your source checkout through your normal Git or release-download workflow. Preserve any local changes. Confirm `VERSION` contains `0.4.0` and Compose selects `osint-menace:0.4.0`. Do not assume a remote branch, tag, or image has been published simply because the local version was bumped.

From the project root, build before stopping the service:

```bash
cat VERSION
python3 osint/addons/fetch.py
docker compose -f deployment/docker-compose.yml build menace
```

Create a backup outside the Docker build context, record the running image, stop the service, then archive its complete data directory. Stop any other Menace process that writes to the same directory before taking this backup.

```bash
set -e
backup_dir="../osint-menace-backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
printf 'Backup folder: %s\n' "$backup_dir"
docker inspect osint-menace-addons --format '{{.Image}}' > "$backup_dir/previous-image-id.txt"
cp docker-compose.yml "$backup_dir/compose-at-upgrade.yml"
docker compose -f deployment/docker-compose.yml stop menace
tar -czf "$backup_dir/data-before-v0.4.0.tar.gz" data
docker compose -f deployment/docker-compose.yml up -d --no-build --pull never menace
```

Keep the printed date folder and previous image until you have finished testing. The backup contains original case information and search history; store it privately. If archiving fails, do not continue with replacement. Restart the previous container with `docker start osint-menace-addons` while resolving the backup problem.

The complete data backup includes cases, evidence, the History database and any SQLite sidecars, the OSINT Links catalog, and other persisted workspace files. Do not copy an active SQLite database or discard its `-wal`/`-shm` files. Case ZIP backups are useful for individual investigations but do not replace this full-service backup.

### Roll Back the Application Image

A routine image rollback keeps the current data. Set `backup_dir` to the actual folder created above; do not paste the example unchanged.

```bash
backup_dir="../osint-menace-backups/YOUR_BACKUP_FOLDER"
previous_image="$(cat "$backup_dir/previous-image-id.txt")"
docker image tag "$previous_image" osint-menace:rollback
cat > "$backup_dir/rollback.override.yml" <<'YAML'
services:
  menace:
    image: osint-menace:rollback
YAML
docker compose -f docker-compose.yml -f "$backup_dir/rollback.override.yml" up -d --no-build --pull never menace
```

Run this from the original project root with the same environment configuration. The base Compose file keeps `./data:/app/data` and the production port mapping. Keep a separate copy of newer data before any data restore; restoring the archived snapshot would discard later work. An older application may not expose newer graph or report features even when their records remain on disk.

### Production upgrades

Use `python3 install.py` from the v0.4.0 source checkout to build and start the complete production image. The installer preserves existing data, retains the previous image for rollback, and records the backup location in its output. Local deployment logs and backups are not included in a clean Git checkout.

Production uses port 8088. A development server on another port does not establish which version is running in Docker; use the version check below to confirm the deployed service.

## Version and Release Checks

The setup script performs three automatic checks and reports their results. For a manually managed install, use these **three focused checks** instead; there is no need to repeat them after a successful scripted setup. Extensive automated suites and every-addon startup checks are not required for normal operation.

1. **Service and version:** confirm the container is running, health returns `{"ok":true}`, and the version API returns `0.4.0`.

   ```bash
   docker compose -f deployment/docker-compose.yml ps menace
   curl --fail http://localhost:8088/health
   curl --fail http://localhost:8088/api/version
   ```

   Expected version response:

   ```json
   {"application":"OSINT Menace","version":"0.4.0"}
   ```

2. **Browser and existing data:** open http://localhost:8088/cases, confirm existing cases are present, and open the fictional demo at http://localhost:8088/demo. The Help menu displays `OSINT Menace v0.4.0`.
3. **One representative workflow:** create a disposable test case from a starter template, open its graph and timeline/tasks, then save and preview a report. Use the demo to inspect populated entity profiles and sharing-review items without running live searches. Download a PDF if report export is part of your intended use.

The demo remains read-only. Use a newly created test case to exercise editing. These checks establish a working installation; they do not establish the accuracy or availability of external OSINT providers.

For code changes, install `requirements/requirements-dev.txt` and choose the relevant targeted tests rather than automatically running the full test suite. Feature behavior and operating limits are documented in [WORKSPACE_FEATURES.md](WORKSPACE_FEATURES.md) and [CHANGELOG.md](CHANGELOG.md).

## Data Persistence

The compose file mounts local data into the container:

```yaml
volumes:
  - ./data:/app/data
```

Saved cases live on the host at:

```text
data/cases/
```

The OSINT Links catalog lives at:

```text
data/catalog/osint_links.json
```

Because `data/` is mounted, cases and supporting workspace data survive container rebuilds and restarts. Graphs, saved graph views/milestones, report composition, timeline notes, confidence reviews, tasks, and redaction settings are stored in each case JSON. History is stored in `data/workspace.sqlite3`; attached screenshots live in `data/evidence/`. Preserve the entire directory when upgrading.

## Ports

Default port mapping:

```text
host 8088 -> container 8080
```

To change the host port, edit `docker-compose.yml`:

```yaml
ports:
  - "8090:8080"
```

Then rebuild or restart:

```bash
docker compose -f deployment/docker-compose.yml up -d
```

Open:

```text
http://localhost:8090
```

## Using The App

### Console

Use the Console page for searches. Choose a search type or use `Auto` for mixed input.

### Cases

Use the Cases page to create case workspaces.

After running a search:

- Click `Add To Case` to save a whole result section.
- Click `Add Link` to save only one useful link.
- If there is one case, OSINT Menace selects it automatically.
- If there are multiple cases, choose the destination case.
- The results page stays open and shows an inline success message.

Inside a case:

- Use **Search case** to find saved names, usernames, emails, phone numbers, notes, evidence, graph objects, and tasks. Search includes findings excluded from reports.
- Open **Case tools → Entity profiles** for an object's identifiers, connections, linked evidence, confidence assessments, and related tasks. Matching names do not automatically merge identities.
- Open **Case tools → Timeline and tasks** to filter chronological events, add analyst notes, record confidence and reasoning, and track next steps with due dates.
- Use **Case graphs** to create editable maps with custom fields, photos, legends, filters, saved views, and named milestones. Select which view appears in a report.
- Choose **Export & backup → Build report** to write the executive summary, select and order content, and preview the exact PDF layout.
- Use **Review before sharing** from Case tools or report preview to review unresolved findings, unsupported connections, missing sources, report gaps, and unfinished tasks. These are advisory prompts, not export blockers.
- Configure **Report redaction** in the investigation workspace. It replaces specified text and omits all images while enabled. Original case data, JSON exports, backups, and internal review pages retain original identifiers.
- Download a complete case backup ZIP before transferring an investigation. Restoring a ZIP creates a separate case.

On the Cases page, choose **Blank case**, **Digital footprint review**, **Organization research**, or **Incident research** when creating a case. Nonblank starters add an empty graph with relevant fields, three tasks, and a report outline. They do not fabricate evidence or conclusions, and cannot overwrite an existing case.

### Reports

Report and preparation routes:

```text
/cases/<case_id>/report-builder
/cases/<case_id>/report-preview
/cases/<case_id>/report-preview.pdf
/cases/<case_id>/sharing-review
/cases/<case_id>/report.pdf
/cases/<case_id>/report.docx
/cases/<case_id>/report.md
/cases/<case_id>/report.html
/cases/<case_id>/export.json
```

PDF and Word reports include colored legend labels, graph context, numbered evidence references, and a source appendix. Saved builder settings control content order and selection across PDF, Word, Markdown, and HTML. New case content is left unselected after the first builder save. Graph sources can appear in the appendix when their graph is selected; existing report exclusions are respected.

The HTML preview is for content review; its embedded PDF shows exact PDF pagination. Word pagination can differ by editor. Redaction uses case-insensitive literal matches; enter alternate spellings, usernames, and phone formats separately. It does not automatically discover identifying information. Review the final export before sharing.

Detailed guides: [Case graphs](CASE_GRAPHS.md), [Report builder](REPORT_BUILDER.md), [Investigation workspace](INVESTIGATION_WORKSPACE.md), and [Search, profiles, review, and templates](CASE_TOOLS.md).

## Local Python Development

Docker is the production runtime. For development, use a separate source checkout and data directory so a development process cannot write to production data. The development port below is 8097; it is not the production service on 8088.

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements/requirements.txt -r requirements/requirements-workspace.txt
```

Run Flask locally:

```bash
flask --app app run --host 127.0.0.1 --port 8097 --debug
```

Open:

```text
http://localhost:8097
```

Compile-check Python:

```bash
python3 -m py_compile osint/app.py osint/osint_tool.py
```

## Updating OSINT Links

The OSINT Links catalog is stored in:

```text
data/catalog/osint_links.json
```

If this file is regenerated later, keep the page attribution to:

```text
https://start.me/p/L1rEYQ/osint4all
```

The app expects catalog data shaped like:

```json
{
  "source_title": "OSINT4ALL - Start.me",
  "source_url": "https://start.me/p/L1rEYQ/osint4all",
  "categories": [
    {
      "name": "Username",
      "links": [
        {
          "title": "Example Tool",
          "url": "https://example.com"
        }
      ]
    }
  ]
}
```

## Troubleshooting

### The App Does Not Open

Check that the container is running:

```bash
docker ps
```

Check logs:

```bash
docker logs --tail 100 osint-menace-addons
```

Check health from inside the container:

```bash
docker exec osint-menace-addons python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=10).read().decode())"
```

### Port 8088 Is Already In Use

Edit `docker-compose.yml` and change:

```yaml
ports:
  - "8088:8080"
```

to another host port, such as:

```yaml
ports:
  - "8090:8080"
```

Restart:

```bash
docker compose -f deployment/docker-compose.yml up -d
```

### Changes Are Not Showing Up

Rebuild the image:

```bash
docker compose -f deployment/docker-compose.yml up --build -d
```

Then refresh the browser.

### Cases Are Missing

Check the local cases folder:

```bash
ls -la data/cases
```

The Docker volume should mount `./data` to `/app/data`. If the compose file was changed, verify the volume still exists.

### DNS Or Public Lookups Fail

Some modules rely on public DNS, RDAP, TLS, or HTTP endpoints. Failures can happen because of:

- No network connection.
- DNS resolver issues.
- Rate limiting.
- Temporary source outage.
- The target not having the expected public records.

Review the result notes before treating missing data as meaningful.

### Authorized Port Scan Does Not Run

Port scanning is disabled unless the checkbox is selected in the UI. Only enable it for systems you own or have explicit permission to test.

## Maintenance Commands

For normal installation or upgrades, run `python3 install.py`. The manual command below only rebuilds and starts; it does not create a backup. Use the backed-up procedure above when managing an upgrade manually.

```bash
docker compose -f deployment/docker-compose.yml up --build -d
```

Stop:

```bash
docker compose -f deployment/docker-compose.yml down
```

Logs:

```bash
docker logs --tail 100 osint-menace-addons
```

Shell into container:

```bash
docker exec -it osint-menace-addons /bin/sh
```

Health from host:

```bash
curl http://localhost:8088/health
```

Health from container:

```bash
docker exec osint-menace-addons python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=10).read().decode())"
```

## Security Notes

- Keep case data private.
- Treat reports as sensitive investigative material.
- Do not commit real case files to a public repository.
- Review third-party source licenses before redistributing archived reference projects.
- Keep high-risk modules behind explicit permission gates if they are added later.

## Uninstall

Stop and remove the container:

```bash
docker compose -f deployment/docker-compose.yml down
```

Remove the image if desired:

```bash
docker image rm osint-menace:0.4.0
```

Keep `data/` after uninstalling if you want to retain investigations and history. Removing the container or image does not delete this bind-mounted directory. Delete saved data only as a separate, deliberate action after verifying a backup.

Research Tools includes the Telephone Investigation Panel, Nearby Places (OpenStreetMap/Overpass), International Address Breakdown (libpostal), and Archived Page History. Docker builds install the international parser and its large model downloads automatically; allow additional disk space and initial build time. See [research tool documentation](GLOBAL_SEARCH.md) for provider disclosure, limits and review workflows.
