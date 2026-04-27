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

## Session Memory

- Read `LESSONSLEARNED.md` and `CHATHISTORY.md` (if present) when resuming work.
- Add reusable operational lessons to `LESSONSLEARNED.md`.
- Update `CHATHISTORY.md` after meaningful sessions.
