#!/usr/bin/env bash
# Update a Docker installation from a stable GitHub release, preserving its data.
set -Eeuo pipefail

main() {
  case "${1:-}" in
    --help|-h)
      printf 'Usage: python3 install.py --update [--check | --no-open]\nChecks stable GitHub releases, stages newer source, and runs the backed-up Docker installer.\nRun from your original installation folder. Requires Docker/Compose; no host Python or Git.\n'
      return ;;
    ''|--check|--no-open) ;;
    *) printf 'Unknown option. Use python3 install.py --help\n' >&2; return 2 ;;
  esac
  [[ $# -le 1 ]] || return 2
  local root helper current run active_config source_root
  root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
  cd "$root"
  export COMPOSE_FILE="${COMPOSE_FILE:-$root/deployment/docker-compose.yml}"
  command -v docker >/dev/null || { printf 'Start Docker with Compose v2 first.\n' >&2; return 1; }
  docker info >/dev/null
  docker compose version >/dev/null
  umask 077
  mkdir -p output
  [[ ! -d output/setup.lock ]] || { printf 'An installer is already active.\n' >&2; return 1; }
  mkdir output/update.lock 2>/dev/null || { printf 'An update is already active. Inspect output/update.lock if an earlier run was interrupted.\n' >&2; return 1; }
  MENACE_UPDATE_LOCK="$root/output/update.lock"
  trap 'rmdir "$MENACE_UPDATE_LOCK" 2>/dev/null || true' EXIT
  source_root="$root"
  if [[ -f output/active-update-config.txt ]]; then
    active_config="$(cat output/active-update-config.txt)"
    [[ -f "$active_config" ]] || { printf 'Saved deployment configuration is missing. Restore it before updating.\n' >&2; return 1; }
    export COMPOSE_FILE="$active_config"
    source_root="$(dirname "$active_config")/source"
  fi
  [[ ! -d "$source_root/output/setup.lock" ]] || { printf 'An installer is already active.\n' >&2; return 1; }
  current="$(docker exec osint-menace-addons cat /app/VERSION)"
  [[ "$current" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf 'Cannot read installed version.\n' >&2; return 1; }
  helper='osint-menace-source-helper:1'
  docker build -t "$helper" - < "$root/deployment/Dockerfile.setup"
  if [[ "${1:-}" == --check ]]; then
    docker run --rm --user "$(id -u):$(id -g)" -v "$root:/workspace:ro" -w /workspace "$helper" python deployment/update_release.py check "$current"
    return
  fi
  run="$(dirname "$root")/osint-menace-updates/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  mkdir -p "$run"
  printf 'Checking for a newer stable release. Existing application continues running.\n'
  docker run --rm --user "$(id -u):$(id -g)" -v "$root:/workspace:ro" -v "$run:/run" -v "$source_root:/configuration-source:ro" -w /workspace "$helper" python deployment/update_release.py stage "$current"
  [[ -f "$run/release.json" ]] || return 0
  # Resolved configuration preserves environment values, ports, and absolute binds.
  docker compose config --format json > "$run/deployment.json"
  docker run --rm --user "$(id -u):$(id -g)" -e "MENACE_RELEASE_SOURCE=$run/source" -v "$root:/workspace:ro" -v "$run:/run" -w /workspace "$helper" python deployment/update_release.py deployment
  export COMPOSE_FILE="$run/deployment.json"
  export OSINT_DATA_DIR="$(cat "$run/data-path.txt")"
  printf 'Original source remains at %s\nStaged application and private configuration: %s\n' "$root" "$run"
  if [[ "${1:-}" == --no-open ]]; then
    bash "$run/source/deployment/install.sh" --no-open
  else
    bash "$run/source/deployment/install.sh"
  fi
  # Commit the active location only after all installer checks pass.
  printf '%s\n' "$run/deployment.json" > "$root/output/active-update-config.txt.new"
  mv "$root/output/active-update-config.txt.new" "$root/output/active-update-config.txt"
  printf '\nUpdate completed. Continue running python3 install.py --update from %s for future releases.\n' "$root"
}
main "$@"
