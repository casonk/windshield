#!/usr/bin/env bash
# Install a user systemd unit that keeps the Playwright server container running.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="${HOME}/.config/systemd/user"
unit_file="${unit_dir}/windshield-playwright.service"
network="${WINDSHIELD_CONTAINER_NETWORK:-isolated}"

"${repo_dir}/scripts/playwright_container.sh" build

mkdir -p "${unit_dir}"
cat > "${unit_file}" <<UNIT
[Unit]
Description=Windshield Playwright server (container)
After=network-online.target

[Service]
Environment=WINDSHIELD_CONTAINER_NETWORK=${network}
ExecStartPre=-/usr/bin/podman rm -f windshield-playwright
ExecStart=${repo_dir}/scripts/playwright_container.sh run
ExecStop=/usr/bin/podman stop -t 10 windshield-playwright
SuccessExitStatus=143
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now windshield-playwright.service
echo "Installed ${unit_file} (network: ${network})"
echo "Point consumers at it: $("${repo_dir}/scripts/playwright_container.sh" env)"
