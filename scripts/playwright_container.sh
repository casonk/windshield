#!/usr/bin/env bash
# Build and run the pinned Playwright server container for windshield consumers.
#   playwright_container.sh build|start|stop|status|env|run   (run = foreground, for systemd)
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="${WINDSHIELD_CONTAINER_NAME:-windshield-playwright}"
port="${WINDSHIELD_PLAYWRIGHT_PORT:-3000}"
engine="${CONTAINER_ENGINE:-podman}"
python_bin="${WINDSHIELD_PYTHON:-${repo_dir}/.venv/bin/python}"
[[ -x "${python_bin}" ]] || python_bin="$(command -v python3)"

version() {
  if [[ -n "${PLAYWRIGHT_VERSION:-}" ]]; then echo "${PLAYWRIGHT_VERSION}"; return; fi
  "${python_bin}" -c 'from importlib.metadata import version; print(version("playwright"))'
}

image() { echo "localhost/windshield-playwright:$(version)"; }

run_args() {
  # Loopback-only publish; no host mounts, no secrets. --ipc=host avoids Chromium
  # shared-memory crashes; --init reaps zombie browser processes.
  echo --rm --init --ipc=host --name "${name}" -p "127.0.0.1:${port}:3000" "$(image)"
}

case "${1:-}" in
  build)
    v="$(version)"
    "${engine}" build --build-arg "PLAYWRIGHT_VERSION=${v}" -t "$(image)" \
      -f "${repo_dir}/deploy/container/Containerfile" "${repo_dir}/deploy/container"
    ;;
  start)
    "${engine}" container exists "${name}" 2>/dev/null && { echo "already running"; exit 0; }
    # shellcheck disable=SC2046
    "${engine}" run -d $(run_args) >/dev/null
    echo "started ${name} on ws://127.0.0.1:${port}"
    ;;
  run)
    # shellcheck disable=SC2046
    exec "${engine}" run $(run_args)
    ;;
  stop)
    "${engine}" stop "${name}" >/dev/null 2>&1 && echo "stopped ${name}" || echo "not running"
    ;;
  status)
    if "${engine}" container exists "${name}" 2>/dev/null; then
      echo "running: ${name} ($(image)) on ws://127.0.0.1:${port}"
    else
      echo "not running (image: $(image))"; exit 1
    fi
    ;;
  env)
    echo "export WINDSHIELD_PLAYWRIGHT_WS=ws://127.0.0.1:${port}/"
    ;;
  *)
    echo "usage: $0 build|start|run|stop|status|env" >&2; exit 2
    ;;
esac
