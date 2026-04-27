# CHANGELOG.md

## [0.2.0] — Unreleased

### Added
- Multi-backend adapter layer (`windshield.adapters`)
  - `PlaywrightPageAdapter` — thin wrapper for Playwright sync pages
  - `SeleniumPageAdapter` — Selenium WebDriver with stale-element retry
  - `UndetectedChromePageAdapter` — anti-detection via undetected-chromedriver
  - `HttpPageAdapter` — requests + BeautifulSoup for static pages
- `create_page()` factory function for backend-agnostic browser creation
- `RotationStrategy` for automatic backend fallback on detection/blocking
- `BackendType` enum, `PageAdapter`/`LocatorAdapter` protocols
- `UnsupportedOperationError` for operations unsupported by a backend
- Optional dependency groups in pyproject.toml

## [0.1.0] — 2026-04-26

### Added
- Initial extraction from `personal-finance` browser automation shared modules.
- `windshield.browser` — Chrome for Testing download, discovery, CDP version helpers.
- `windshield.page` — Playwright page interaction: fill, click, type, wait, read, submit.
- `windshield.debug` — Page snapshots (HTML + JSON + PNG), runtime event capture, JSONL logging.
- `windshield.challenge` — Cloudflare/CAPTCHA challenge detection and wait-to-clear.
- `windshield.stealth` — User agent rotation with persistent state, selector/string normalization.
- `windshield.http` — HTTP opener, URL fragment matching, browser location description, error redaction.
- `windshield.overlay` — In-page manual-continue overlay and terminal prompt for human-in-the-loop steps.
- Full test suite with mock page/request/response objects.
- Traction-control governance baseline (AGENTS.md, SECURITY.md, CI, pre-commit, etc.).
