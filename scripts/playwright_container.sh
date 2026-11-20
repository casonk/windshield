#!/usr/bin/env bash
# Build and run the pinned Playwright server container for windshield consumers.
#   playwright_container.sh build|start|stop|status|env|run   (run = foreground, for systemd)
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="${WINDSHIELD_CONTAINER_NAME:-windshield-playwright}"
port="${WINDSHIELD_PLAYWRIGHT_PORT:-3000}"
engine="${CONTAINER_ENGINE:-podman}"
# isolated (default): own network, port published on 127.0.0.1; good for scraping the internet.
# host: shares the host network and binds 127.0.0.1, so pages served on the host's loopback
#       (UI tests against a local app) are reachable at the same URLs.
network="${WINDSHIELD_CONTAINER_NETWORK:-isolated}"
python_bin="${WINDSHIELD_PYTHON:-${repo_dir}/.venv/bin/python}"
[[ -x "${python_bin}" ]] || python_bin="$(command -v python3)"

state_dir="${WINDSHIELD_STATE_DIR:-${XDG_STATE_HOME:-${HOME}/.local/state}/windshield}/playwright"

# Node major baked into the image: $WINDSHIELD_NODE_MAJOR, else the rotation state, else config.
node_major() {
  if [[ -n "${WINDSHIELD_NODE_MAJOR:-}" ]]; then echo "${WINDSHIELD_NODE_MAJOR}"; return; fi
  for f in "${state_dir}/node-major.txt" "${repo_dir}/config/node-major.txt"; do
    [[ -f "$f" ]] && { tr -d '[:space:]' < "$f"; echo; return; }
  done
  echo 24
}

# Versions to serve: $WINDSHIELD_PLAYWRIGHT_VERSIONS, else the rotation state, $WINDSHIELD_PLAYWRIGHT_VERSIONS, else config/playwright-versions.txt,
# else the installed Python client's version. Space/comma/newline separated, e.g. "1.58.0 1.64.1".
versions() {
  local raw="${WINDSHIELD_PLAYWRIGHT_VERSIONS:-}"
  for f in "${state_dir}/versions.txt" "${repo_dir}/config/playwright-versions.txt"; do
    if [[ -z "${raw}" && -f "$f" ]]; then raw="$(grep -v '^[[:space:]]*#' "$f")"; fi
  done
  if [[ -z "${raw}" ]]; then
    raw="$("${python_bin}" -c 'from importlib.metadata import version; print(version("playwright"))')"
  fi
  echo "${raw}" | tr ', ' '\n\n' | grep -v '^$' | sort -V -u | tr '\n' ' ' | sed 's/ $//'
}

# Build revision: distinguishes a security rebuild of the same versions (rotation bumps it).
build_rev() {
  local r="${WINDSHIELD_BUILD_REV:-}"
  if [[ -z "${r}" && -f "${state_dir}/build-rev.txt" ]]; then r="$(tr -d '[:space:]' < "${state_dir}/build-rev.txt")"; fi
  [[ -n "${r}" && "${r}" != 0 ]] && echo "-r${r}" || true
}

image() { echo "localhost/windshield-playwright:v$(versions | tr ' ' '-')-node$(node_major)$(build_rev)"; }

# Drive a page through every served version, using that version's own client inside the
# container: proves the router, each server and each browser. Exit 1 on any failure.
smoke() {
  local inner="${port}"
  [[ "${network}" == isolated ]] && inner=3000
  local v minor failed=0
  for v in $("${engine}" exec "${name}" ls /opt/pw/ | grep -E '^[0-9]+\.[0-9]+\.[0-9]+'); do
    minor="${v%.*}"
    if out="$(timeout 90 "${engine}" exec -w "/opt/pw/${v}" "${name}" node -e "
const {chromium}=require('/opt/pw/${v}/node_modules/playwright');
(async()=>{const b=await chromium.connect('ws://127.0.0.1:${inner}/${minor}');
const p=await b.newPage();await p.goto('data:text/html,<title>ok</title>');
if(await p.title()!=='ok')throw new Error('wrong title');console.log('chromium '+b.version());await b.close()})()
.catch(e=>{console.error(String(e.message).split('\n')[0]);process.exit(1)})" 2>&1)"; then
      echo "ok   ${v}  ${out}"
    else
      echo "FAIL ${v}  ${out}"; failed=1
    fi
  done
  return "${failed}"
}

wait_listening() {
  for _ in $(seq 1 120); do
    "${engine}" logs "${name}" 2>&1 | grep -q "Listening on" && return 0
    sleep 0.5
  done
  echo "server did not start" >&2; "${engine}" logs "${name}" 2>&1 | tail -5 >&2; return 1
}

run_args() {
  # Loopback-only publish; no host mounts, no secrets. --ipc=host avoids Chromium
  # shared-memory crashes; --init reaps zombie browser processes.
  case "${network}" in
    isolated)
      echo --rm --init --ipc=host --name "${name}" -p "127.0.0.1:${port}:3000" "$(image)" ;;
    host)
      echo --rm --init --ipc=host --name "${name}" --network=host \
        -e PLAYWRIGHT_HOST=127.0.0.1 -e "PLAYWRIGHT_PORT=${port}" "$(image)" ;;
    *) echo "WINDSHIELD_CONTAINER_NETWORK must be isolated or host" >&2; exit 2 ;;
  esac
}

case "${1:-}" in
  build)
    all="$(versions)"
    oldest="${all%% *}"   # oldest base image => Node 24; see the Containerfile
    "${engine}" build --pull=newer --build-arg "PLAYWRIGHT_BASE=${oldest}" \
      --build-arg "PLAYWRIGHT_VERSIONS=${all}" --build-arg "NODE_MAJOR=$(node_major)" -t "$(image)" \
      -f "${repo_dir}/deploy/container/Containerfile" "${repo_dir}/deploy/container"
    ;;
  start)
    "${engine}" container exists "${name}" 2>/dev/null && { echo "already running"; exit 0; }
    # shellcheck disable=SC2046
    "${engine}" run -d $(run_args) >/dev/null
    # The published port accepts TCP before the server inside is listening.
    wait_listening || true
    echo "started ${name} on ws://127.0.0.1:${port}"
    ;;
  run)
    # shellcheck disable=SC2046
    exec "${engine}" run $(run_args)
    ;;
  smoke)
    smoke
    ;;
  verify)
    # Start a throwaway candidate (isolated network, own name and port), smoke it, remove it.
    name="${name}-candidate"; port="${WINDSHIELD_VERIFY_PORT:-3900}"; network=isolated
    "${engine}" rm -f "${name}" >/dev/null 2>&1 || true
    # shellcheck disable=SC2046
    "${engine}" run -d $(run_args) >/dev/null
    rc=0
    wait_listening && smoke || rc=1
    # Also drive the server with each recent version's *Python* client (what consumers use).
    if [[ "${rc}" == 0 && "${WINDSHIELD_VERIFY_CLIENTS:-1}" != 0 ]]; then
      PYTHONPATH="${repo_dir}/src" "${python_bin}" -m windshield.client_matrix \
        --endpoint "ws://127.0.0.1:${port}" --versions "$(versions)" || rc=1
    fi
    "${engine}" rm -f "${name}" >/dev/null 2>&1 || true
    exit "${rc}"
    ;;
  stop)
    "${engine}" stop "${name}" >/dev/null 2>&1 && echo "stopped ${name}" || echo "not running"
    ;;
  status)
    if "${engine}" container exists "${name}" 2>/dev/null; then
      echo "running: ${name} ($("${engine}" inspect "${name}" --format "{{.ImageName}}")) on ws://127.0.0.1:${port}/{version}  [versions: $(versions)]"
    else
      echo "not running (image: $(image))"; exit 1
    fi
    ;;
  env)
    echo "export WINDSHIELD_PLAYWRIGHT_WS=ws://127.0.0.1:${port}/{version}"
    ;;
  *)
    echo "usage: $0 build|start|run|smoke|verify|stop|status|env" >&2; exit 2
    ;;
esac
