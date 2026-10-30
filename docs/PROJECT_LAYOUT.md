# Project layout

The top level contains the main `install.py` entry point, a short README, the project license, and organized folders. Application code is under `osint/`. The reorganization does not relocate existing `data/`, `output/`, `.env`, or private settings.

```text
osint-menace/
├── install.py
├── README.md
├── LICENSE
├── osint/
│   ├── app.py
│   ├── menace.py
│   ├── VERSION
│   ├── paths.py
│   ├── addons/
│   ├── scripts/
│   ├── static/
│   └── templates/
├── deployment/
├── requirements/
├── config/
├── docs/
│   ├── images/
│   ├── releases/
│   ├── QUICKSTART.md
│   └── previews/
├── tests/
├── data/
├── output/
└── tmp/
```

## Entry points

From the project folder:

```sh
python3 install.py                 # Install/upgrade this source checkout
python3 install.py --no-open       # Same, without opening the browser
python3 install.py --check         # Check stable GitHub releases
python3 install.py --update        # Stage and install a newer stable release
python3 osint/menace.py --version  # Terminal version
python3 osint/menace.py            # Terminal workspace
```

The installer also works when invoked by absolute path from another directory. It explicitly selects its own project folder and deployment configuration. Windows users should run it within WSL2. Bash-only entry points remain available at `deployment/install.sh` and `deployment/update.sh`.

Docker commands use the explicit Compose file:

```sh
docker compose -f deployment/docker-compose.yml config
docker compose -f deployment/docker-compose.yml logs --tail 80 menace
docker compose -f deployment/docker-compose.yml down
```

The build context remains the project root; the Dockerfile is `deployment/Dockerfile`. Inside the image the application still runs in `/app`, and the existing data bind mount remains `/app/data`. Installer upgrades preserve the existing Compose project label when present, so reorganizing source files does not intentionally create a second application deployment.

## Native development

Use Python 3.12 and an isolated environment, then install the applicable dependency files from `requirements/`. Run from the project root so generated output has a predictable location. For example:

```sh
python -m pip install -r requirements/requirements.txt -r requirements/requirements-workspace.txt
python osint/app.py
python -m unittest tests.test_case_tools -q
```

For Gunicorn without Docker, keep the project as the working directory and add the source path explicitly:

```sh
gunicorn --pythonpath osint --config osint/gunicorn.conf.py app:app
```

`osint/paths.py` anchors native runtime data to the project `data/` folder; it uses `/app/data` inside Docker. Running a source entry point from `osint/` does not create a replacement investigation directory there. Addon workers remain alongside the application under `osint/scripts/`, with pinned source trees under `osint/addons/sources/`. These downloaded trees remain excluded from Git.

Development lint configuration is at `config/ruff.toml`:

```sh
ruff check --config config/ruff.toml install.py osint deployment tests
```

Tests bootstrap the application source path through `tests/__init__.py`. If selecting the full suite intentionally, use `python -m unittest discover -s tests -t .`; normal validation should still select focused modules.

## Existing installations and scripts

Old source commands such as `./install.sh`, `./update.sh`, and root-level `menace.py` have moved to the entry points above. Existing external scripts that invoke those filenames need their paths updated. An older installed updater may not recognize a release with this reorganized layout; use the new source's `install.py` for that migration. When installing from a separate source copy, preserve the original data bind with `OSINT_DATA_DIR=/absolute/path/to/original/data python3 /path/to/new/source/install.py`. The installer verifies the existing container's data mount before stopping it.

The updater now builds deployment configuration with an explicit Dockerfile path. It retains resolved ports, environment settings, existing absolute data binds, private configuration backups, and interrupted-update protection. Runtime originals and credentials must remain outside the build context's included files; the root `.dockerignore` continues to exclude them.
