# Installed addon integration

From a source checkout or extracted archive, run the setup script. Docker must already be running; host Python and Git are not required:

```sh
python3 install.py
```

Open http://localhost:8088/addons. All nineteen sources are pinned by commit in
`manifest.json`, with their original licenses in `sources/<tool>/`. Downloaded
sources are excluded from Git but included in the Docker build. The fetch script
refuses to replace changed sources. Python tools use separate virtual environments
under `/opt/addons`; PhoneInfoga and Clank are compiled from the pinned Go sources.
Social Analyzer runs its source CLI because its source checkout does not contain
the package directory declared in its upstream setup.py. PhoneInfoga is CLI-only;
its separate upstream browser interface is not part of this integration.

The Addons page runs one selected target in a background job and captures raw
stdout/stderr, status, and timestamp. Results can be saved to existing cases and
then exported with the existing report workflow. Tool output remains unverified;
registration and profile matches do not establish identity. Clank uses `--local`
for numbering metadata, not live location. Maigret is limited to its top 500
sites; Social Analyzer to its top 100; Aliens' Eye uses its quick profile.

Each run has an isolated temporary working directory, a 180-second time limit,
an 8 MB output stop threshold, and a 1 MB displayed-output cap. Two searches may
run at once. Jobs stay in memory for at most an hour (removed on later launches),
with a maximum of 100 retained jobs; restarting the server clears them. Save useful
output to a case before restarting. The container uses one Gunicorn worker with
four threads because the job registry is in memory.

## Optional configuration

Toutatis requires an Instagram session from an account the operator controls.
Set `INSTAGRAM_SESSION_ID` in an untracked `.env` beside docker-compose.yml, then
run `docker compose -f deployment/docker-compose.yml up -d --force-recreate`. Menace does not accept sessions in its
web form or save them in cases. The upstream CLI receives the session as a process
argument, so restrict host/container access. Do not commit or share `.env`.

PhoneInfoga scanners that require provider API keys remain limited without them.
The default Clank integration uses its local mode; its authenticated providers,
Telegram, WhatsApp, permutation generation, and interactive menu are not exposed.
Some upstream registration checks may be broken or rate limited by their providers;
a successful tool exit does not guarantee coverage or accurate results.

The app binds to `0.0.0.0:8088` for access from other computers on the same
trusted local network. Open `http://<host-LAN-IP>:8088/addons` from the other
computer. The app has no user authentication; do not forward this port to the
public internet. Preserve upstream license notices if distributing the
image; licenses vary by project (including AGPL/GPL components). Dependencies are
resolved at build time; source commits are pinned but all transitive packages
are not yet locked.

## Validation

OSINT Menace v0.4.0 retains the existing pinned addon inventory. Use the three focused installation checks in [INSTALL.md](../../docs/INSTALL.md#version-and-release-checks) after an upgrade. Select an individual tool's startup check only when it is relevant; do not run every addon automatically. Local startup checks use `--help` and do not establish external platform coverage or verify credentials.

For addon code changes, choose the targeted fixture tests for the affected tool. Runtime results may still be incomplete, rate limited, or inaccurate even when installation succeeds.

## GitHub research expansion

Five new launchable tools bring the addon CLI inventory to seventeen: Unfurl, waymore, Subfinder, dnstwist, and theHarvester. The eighteenth source, ExifTool, is exposed through retained-document metadata rather than arbitrary filesystem targets. See [GitHub research tools](../../docs/GITHUB_RESEARCH_TOOLS.md) for exact modes, provider disclosures, version compatibility, installation, and verification.

The earlier dnstwist/Subfinder proposals are now implemented. Historical URL discovery uses waymore rather than adding another overlapping waybackurls CLI. Active httpx probing remains deferred. [Further recommendations](../../docs/RECOMMENDED_TOOL_ROADMAP.md) cover Browsertrix Crawler and oletools; these remain proposals. Mail-Parser is now installed as [Email Evidence](../../docs/EMAIL_EVIDENCE.md), a retained-case-file workflow.
