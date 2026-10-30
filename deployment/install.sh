#!/usr/bin/env bash
# Install or upgrade this checkout without installing host Python or addon tools.
set -Eeuo pipefail

open_browser=1
case "${1:-}" in
  --no-open) open_browser=0 ;;
  --help|-h)
    cat <<'HELP'
Usage: python3 install.py [--no-open]

Requires Docker running, Docker Compose v2, and an internet connection.
Run from a local checkout or extracted source archive on macOS, Linux, or WSL2.
Fetches pinned addons, builds the app, backs up existing data, starts Docker,
runs three focused checks, and opens http://localhost:8088/cases.
Existing addon source edits are never overwritten. No host packages are installed.
HELP
    exit 0 ;;
  '') ;;
  *) printf 'Unknown option: %s\nUse --help for instructions.\n' "$1" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { printf 'Use one option at a time.\n' >&2; exit 2; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT"
export COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/deployment/docker-compose.yml}"
DATA_ROOT="${OSINT_DATA_DIR:-$ROOT/data}"
mkdir -p "$DATA_ROOT"
DATA_ROOT="$(cd -- "$DATA_ROOT" && pwd -P)"
fail() { printf '\nSetup stopped: %s\n' "$*" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || fail 'Install Docker Desktop (Mac/Windows) or Docker Engine with Compose v2 (Linux), start it, then rerun python3 install.py.'
docker info >/dev/null 2>&1 || fail 'Docker is not running or your user cannot access it. Start Docker or obtain Docker access, then rerun. Do not run this script with sudo.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose v2 is required. Install or enable the Compose plugin, then rerun.'
[[ -f osint/VERSION && -f deployment/docker-compose.yml && -f osint/addons/fetch.py ]] || fail 'Use a complete OSINT Menace source checkout.'
VERSION="$(tr -d '[:space:]' < osint/VERSION)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail 'VERSION must contain a semantic release number.'
[[ "$(docker compose config --images)" == "osint-menace:$VERSION" ]] || fail 'Compose image tag and VERSION do not match.'
mkdir -p output
[[ ! -d output/update.lock ]] || fail 'An updater is already active for this installation.'
LOCK="$ROOT/output/setup.lock"
mkdir "$LOCK" 2>/dev/null || fail 'Another setup may be running. If it was interrupted, remove output/setup.lock only after confirming no installer is active.'
HELPER='osint-menace-source-helper:1'
CONTAINER='osint-menace-addons'
backup_dir=''
restore_needed=0
old_image=''

cleanup() {
  result=$?
  trap - EXIT INT TERM
  if [[ $result -ne 0 && $restore_needed -eq 1 && -n "$old_image" ]]; then
    printf '\nInstallation did not complete; restarting the previous application image.\n' >&2
    if docker compose -f "${COMPOSE_FILE:-$ROOT/deployment/docker-compose.yml}" -f "$backup_dir/rollback.override.yml" up -d --no-build --pull never menace; then
      printf 'Previous image restarted. Data was not rolled back. Backup: %s\n' "$backup_dir" >&2
    else
      printf 'Automatic rollback could not start. Keep the backup and inspect Docker logs.\n' >&2
    fi
  fi
  rm -f "$LOCK/health.txt"
  rmdir "$LOCK" 2>/dev/null || true
  exit "$result"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
if docker inspect "$CONTAINER" >/dev/null 2>&1; then
  mount="$(docker inspect "$CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}')"
  [[ "$mount" == "$DATA_ROOT" ]] || fail 'The existing Menace container uses another data location. Run setup from its original project folder; no container was stopped.'
  project_name="$(docker inspect "$CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project"}}')"
  if [[ -n "$project_name" && "$project_name" != '<no value>' ]]; then export COMPOSE_PROJECT_NAME="$project_name"; fi
  unset project_name
  old_image="$(docker inspect "$CONTAINER" --format '{{.Image}}')"
  # Preserve a session configured only in the old launch environment. An explicit
  # current environment value or .env entry takes precedence. Never print it.
  if [[ -z "${INSTAGRAM_SESSION_ID+x}" ]] && ! { [[ -f .env ]] && grep -Eq '^[[:space:]]*(export[[:space:]]+)?INSTAGRAM_SESSION_ID[[:space:]]*=' .env; }; then
    saved_session="$(docker inspect "$CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^INSTAGRAM_SESSION_ID=//p')"
    if [[ -n "$saved_session" ]]; then export INSTAGRAM_SESSION_ID="$saved_session"; fi
    unset saved_session
  fi
fi

printf '\nInstalling OSINT Menace v%s. Addon sources and dependencies may take several minutes to download.\n' "$VERSION"
printf 'Preparing the Docker source helper; host Python and Git are not required.\n'
docker build -t "$HELPER" - < deployment/Dockerfile.setup
mkdir -p osint/addons/sources
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT:/workspace" -w /workspace "$HELPER" python osint/addons/fetch.py

# Tag the actual previous image before a same-version build can replace its tag.
if [[ -n "$old_image" ]]; then docker image tag "$old_image" "osint-menace:before-$stamp"; fi
docker compose build menace

# Never include the backup in a Docker build context or remove the existing data.
backup_dir="$(dirname "$ROOT")/osint-menace-backups/$stamp"
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
# Save resolved runtime configuration privately, separately from the data archive.
(umask 077; docker compose config --format json > "$backup_dir/deployment.json")
for config in .env .env.* docker-compose.override.yml docker-compose.override.yaml; do
  if [[ -f "$config" ]]; then (umask 077; cp "$config" "$backup_dir/$(basename "$config")"); chmod 600 "$backup_dir/$(basename "$config")"; fi
done
if [[ -n "$old_image" ]]; then
  printf '%s\n' "$old_image" > "$backup_dir/previous-image-id.txt"
  printf 'services:\n  menace:\n    image: osint-menace:before-%s\n' "$stamp" > "$backup_dir/rollback.override.yml"
  # Set rollback before stop so interruptions during a stop are recoverable.
  restore_needed=1
  docker compose stop menace
fi
printf '\nSaving data backup to %s\n' "$backup_dir"
docker run --rm -v "$DATA_ROOT:/source/data:ro" -v "$backup_dir:/backup" "$HELPER" sh -c 'umask 077; tar -czf /backup/data-before-install.tar.gz -C /source data && chown "$1:$2" /backup/data-before-install.tar.gz' sh "$(id -u)" "$(id -g)"
docker compose up -d --no-build --pull never menace

printf '\nWaiting for the application to start…\n'
healthy=0
for attempt in $(seq 1 45); do
  if docker compose exec -T menace python scripts/setup_checks.py service "$VERSION" > "$LOCK/health.txt" 2>/dev/null; then
    cat "$LOCK/health.txt"; healthy=1; break
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || fail 'The service did not become healthy. Inspect docker compose logs --tail 80 menace.'
rm -f "$LOCK/health.txt"
# Confirm protected original records before declaring the upgrade complete.
docker run --rm -v "$ROOT:/workspace:ro" -v "$DATA_ROOT:/source/data:ro" -v "$backup_dir:/backup:ro" "$HELPER" python /workspace/deployment/setup_checks.py data /backup/data-before-install.tar.gz
docker compose exec -T menace python scripts/setup_checks.py pages
host_address="$(docker compose port menace 8080)"
host_port="${host_address##*:}"
[[ "$host_port" =~ ^[0-9]+$ ]] || fail 'Docker did not report a published application port.'
URL="http://localhost:$host_port"
restore_needed=0
printf '\nOSINT Menace v%s is running at %s\nCases: %s/cases\nDemo: %s/demo\nBackup: %s\n' "$VERSION" "$URL" "$URL" "$URL" "$backup_dir"
printf 'Existing data is retained. Keep the backup and previous image until testing is complete.\n'
if [[ $open_browser -eq 1 ]]; then
  case "$(uname -s)" in
    Darwin) open "$URL/cases" || true ;;
    Linux)
      if command -v cmd.exe >/dev/null 2>&1; then cmd.exe /c start '' "$URL/cases" >/dev/null 2>&1 || true
      elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL/cases" >/dev/null 2>&1 || true
      fi ;;
  esac
fi
