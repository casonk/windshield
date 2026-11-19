#!/usr/bin/env bash
# Install the weekly rotation timer (new Playwright minors and Node LTS, verified before promotion)
# through Clockwork, the portfolio's scheduler.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
clockwork_dir="${CLOCKWORK_DIR:-${repo_dir}/../clockwork}"
manifest="${clockwork_dir}/examples/windshield/playwright-rotate.toml"

if [[ ! -f "${manifest}" ]]; then
  echo "error: Clockwork manifest not found: ${manifest}" >&2
  exit 1
fi

(cd "${clockwork_dir}" && python3 -m clockwork install --manifest "${manifest}" --target systemd-user)
systemctl --user daemon-reload
systemctl --user enable --now windshield-playwright-rotate.timer
echo "Installed. Next run:"
systemctl --user list-timers windshield-playwright-rotate.timer --no-pager | head -3
echo "Preview a rotation without changing anything:"
echo "  PYTHONPATH=${repo_dir}/src python3 -m windshield.container_rotation --dry-run"
