# CHANGELOG.md

## [0.1.0] — 2026-04-26

### Added
- Initial extraction from `private-repository` browser automation shared modules.
- `windshield.browser` — Chrome for Testing download, discovery, CDP version helpers.
- `windshield.page` — Playwright page interaction: fill, click, type, wait, read, submit.
- `windshield.debug` — Page snapshots (HTML + JSON + PNG), runtime event capture, JSONL logging.
- `windshield.challenge` — Cloudflare/CAPTCHA challenge detection and wait-to-clear.
- `windshield.stealth` — User agent rotation with persistent state, selector/string normalization.
- `windshield.http` — HTTP opener, URL fragment matching, browser location description, error redaction.
- `windshield.overlay` — In-page manual-continue overlay and terminal prompt for human-in-the-loop steps.
- Full test suite with mock page/request/response objects.
- Traction-control governance baseline (AGENTS.md, SECURITY.md, CI, pre-commit, etc.).
