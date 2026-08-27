# AGENTS.md

## Objective

Windshield is a reusable multi-backend browser automation utility library. It provides generic helpers for Chrome management, page interaction, debug snapshots, challenge detection, stealth/user-agent rotation, and HTTP utilities. Supported backends: Playwright, Selenium, undetected-chromedriver, and HTTP-only (requests + BeautifulSoup). Includes automatic backend rotation with privacy-first ordering (least detectable first) and block-aware fallback.

## Portfolio Standards

For portfolio-wide repository standards and baseline conventions, consult the control-plane repo at `./util-repos/traction-control` from the portfolio root. Start with `./util-repos/traction-control/AGENTS.md`, `./util-repos/traction-control/README.md`, and `./util-repos/traction-control/LESSONSLEARNED.md`.

## Shared Utility Repos

Available shared repos in the portfolio:

- `./util-repos/archility` — architecture diagram bootstrap and rendering
- `./util-repos/auto-pass` — KeePassXC-backed credential helpers
- `./util-repos/clockwork` — cron/systemd scheduler rendering
- `./util-repos/dyno-lab` — unified test bench, fixtures, and mocks
- `./util-repos/nordility` — NordVPN switching
- `./util-repos/shock-relay` — external messaging (Signal, Telegram, SMS)
- `./util-repos/short-circuit` — WireGuard VPN setup
- `./util-repos/snowbridge` — SMB file sharing
- `./util-repos/crew-chief` — local Ollama LLM service
- `./util-repos/wiring-harness` — Caddy, mTLS, DNS infrastructure

## Scope Boundaries

- **IN scope**: Generic browser automation utilities (provider-agnostic) — multi-backend adapters (Playwright, Selenium, undetected-chromedriver, HTTP-only), backend rotation strategy, Chrome management, page interaction, debug snapshots, challenge detection, stealth helpers
- **OUT of scope**: Credential management (use auto-pass), OTP/messaging (use shock-relay), provider-specific scraping logic, financial data parsing

## Development Rules

- Run `pre-commit run --all-files` and `pytest -q` before every push.
- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `ci:`.
- Never commit secrets, credentials, or personal data.
- Match ruff/black versions between pre-commit and CI.

## Sudo Boundary

Agents will never be able to run `sudo` commands in this environment. If a task requires elevated system changes, make the repo edits and run the validation that can be done without `sudo`, then give the user the exact command(s) to run.

Always require the user to run those commands instead of retrying `sudo`; do not claim a sudo-backed live change was applied until the user shares the result.

## Local CI Verification

CI (`.github/workflows/ci.yml`) runs the shared `install-check` and `python-ci`
workflows. Reproduce locally before pushing:

```bash
pip install -e ".[dev]"
pre-commit run --all-files
pytest -q
```

Install with the `[dev]` extra, not a bare `pip install -e .`: the browser
backends are optional extras (`playwright`, `selenium`, `undetected`), and CI's
`install-check` only proves the package installs and imports on each platform,
not that any backend works. `undetected` additionally needs `setuptools` on
Python 3.12+, since `undetected-chromedriver` still imports the removed
`distutils`.

`pre-commit` auto-fixing hooks rewrite files and exit 1 on the run that made the
change; re-run, confirm exit 0, then stage what they rewrote. Keep ruff/black
versions matched between pre-commit and CI, as the Development Rules note.

## Session Memory

- Read `LESSONSLEARNED.md` and `CHATHISTORY.md` (if present) when resuming work.
- Add reusable operational lessons to `LESSONSLEARNED.md`.
- Update `CHATHISTORY.md` after meaningful sessions.
