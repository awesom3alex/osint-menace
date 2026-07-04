# OSINT Menace Install Guide

This guide explains how to install, run, update, and troubleshoot OSINT Menace locally with Docker.

## Requirements

You need:

- macOS, Linux, or Windows with WSL2.
- Docker Desktop or Docker Engine.
- Docker Compose v2.
- A terminal.
- A browser.

Optional for local Python development:

- Python 3.12 or newer.
- `pip`.
- A virtual environment.

## Quick Start

From the project folder:

```bash
cd /path/to/osint-menace
docker compose up --build -d
```

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

## Docker Install

### 1. Confirm Docker Works

```bash
docker --version
docker compose version
```

### 2. Build And Start

```bash
docker compose up --build -d
```

This builds the Python image and starts the container named:

```text
menace-osint
```

The container listens internally on port `8080` and is exposed on the host at:

```text
http://localhost:8088
```

### 3. View Running Containers

```bash
docker ps
```

You should see `menace-osint` running.

### 4. View Logs

```bash
docker logs --tail 100 menace-osint
```

### 5. Stop The App

```bash
docker compose down
```

### 6. Restart The App

```bash
docker compose up -d
```

### 7. Rebuild After Code Changes

Source files are copied into the Docker image. After changing Python, templates, CSS, or docs that should be inside the container, rebuild:

```bash
docker compose up --build -d
```

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

Because `data/` is mounted, cases survive container rebuilds and restarts.

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
docker compose up -d
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

- Delete individual saved items with `Delete Item`.
- Export JSON, Markdown, or HTML report.
- Delete the entire case from the Danger Zone.

### Reports

Report routes:

```text
/cases/<case_id>/export.json
/cases/<case_id>/report.md
/cases/<case_id>/report.html
```

The HTML report is styled for browser viewing and printing.

## API Usage

Search API:

```bash
curl -sS http://localhost:8088/api/search \
  -H 'Content-Type: application/json' \
  -d '{"search_type":"username","query":"exampleuser"}'
```

Auto mode:

```bash
curl -sS http://localhost:8088/api/search \
  -H 'Content-Type: application/json' \
  -d '{"search_type":"auto","query":"person@example.com\nexampleuser\nexample.com"}'
```

Health:

```bash
curl http://localhost:8088/health
```

## Local Python Development

Docker is the recommended runtime, but you can run the app locally for development.

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run Flask locally:

```bash
flask --app app run --host 0.0.0.0 --port 8088 --debug
```

Open:

```text
http://localhost:8088
```

Compile-check Python:

```bash
python3 -m py_compile app.py osint_tool.py
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
docker logs --tail 100 menace-osint
```

Check health from inside the container:

```bash
docker exec menace-osint python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=10).read().decode())"
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
docker compose up -d
```

### Changes Are Not Showing Up

Rebuild the image:

```bash
docker compose up --build -d
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

Rebuild:

```bash
docker compose up --build -d
```

Stop:

```bash
docker compose down
```

Logs:

```bash
docker logs --tail 100 menace-osint
```

Shell into container:

```bash
docker exec -it menace-osint /bin/sh
```

Health from host:

```bash
curl http://localhost:8088/health
```

Health from container:

```bash
docker exec menace-osint python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=10).read().decode())"
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
docker compose down
```

Remove the image if desired:

```bash
docker image rm osint-menace:latest
```

Remove saved case data only if you are sure:

```bash
rm -rf data/cases
```

That last command deletes saved investigations. Back up anything important first.
