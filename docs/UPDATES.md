# Release notifications and safe Docker updates

The Console checks the official `awesom3alex/osint-menace` GitHub repository for the latest published stable release. A banner appears only when its semantic version is newer than the running version. Drafts and prereleases are excluded. Checks are cached for six hours; failed checks retry after fifteen minutes. Offline or rate-limited checks leave the application usable. Dismissal hides only that release in the current browser. No case data is sent to GitHub.

From your **original installation folder**, run:

```bash
python3 install.py --check     # report installed/latest stable versions without upgrading
python3 install.py --update            # stage, back up, build, and start a newer release
python3 install.py --update --no-open  # same upgrade without opening the browser
```

Docker with Compose v2 and an internet connection are required. No host Python or Git installation is required. The updater uses the published release source archive; pushing a commit or changing `VERSION` on a branch does not trigger an update. A release must contain this updater and the shared-data installer support. There is no browser endpoint that restarts Docker, no automatic downgrade, and no scheduled background installation.

## What is preserved

New source is extracted into a private sibling folder under `../osint-menace-updates/`. The original source folder remains untouched. The current deployment's resolved settings retain environment values, published ports, and volume paths. The new image uses **the exact existing `/app/data` bind mount**, preserving cases, graph data, evidence, SQLite search history, catalog changes, pending backups, and other data stored there. Files outside that directory, such as exported reports, remain in their original locations.

Local `.env` files are copied privately to the staged installation and backed up separately. Resolved Docker settings can contain credentials; update folders and configuration backups are private, outside source/build contexts. Never publish these folders. Resolved settings are a snapshot of the active deployment; to change settings after an update, edit the active deployment configuration deliberately rather than assuming edits to the old Compose file will be used.

The existing installer builds first, keeps the previous image, stops the service for a consistent backup of the **entire data directory**, and then starts the replacement. Its three bounded checks cover service/version, original data files plus SQLite records, and local screens. Interrupted addon jobs are marked interrupted by normal startup recovery; captured results remain preserved. Do not run other writers, CLI commands, or installers against the data directory during an upgrade.

After success, `output/active-update-config.txt` in the original installation records the active private deployment configuration. Continue using `python3 install.py --update` from that original folder for later updates; the updater uses the current staged helper code. For manual administration, use the printed configuration path:

```bash
docker compose -f /absolute/path/to/deployment.json logs --tail 80 menace
```

Single-service installations with a bind-mounted data directory are supported. Multi-service deployments and non-bind data volumes stop with instructions for a manual upgrade. New releases that require additional services or deployment settings need a reviewed migration rather than blindly reusing the old deployment layout.

## Failure and rollback

Download, archive-validation, and build failures leave the running application untouched. Archive paths, links, runtime/configuration files, and extraction sizes are validated before use. The recorded SHA-256 is an audit fingerprint, not an independent signature or publisher authenticity guarantee; releases are trusted from the official repository over HTTPS.

If startup or post-upgrade checks fail, the installer attempts to restart the previous image with the preserved deployment settings. It does **not** overwrite current data automatically, because doing so could discard newer work. The installer prints the backup location containing `data-before-install.tar.gz`, `previous-image-id.txt`, `deployment.json`, and `rollback.override.yml`. Keep these files and the previous image until your own review is complete. Future destructive database migrations require an explicit restore/migration plan; an older image alone cannot reverse those migrations.

The active deployment pointer changes only after a successful installation. Do not delete the active staged source, its private configuration, or the original data directory. If interrupted, confirm no updater/installer is running before removing its lock directory. No release checks execute OSINT searches.
