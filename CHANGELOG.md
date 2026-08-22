# CHANGELOG.md

## [0.2.0] — Unreleased

### Fixed
- The `undetected` and `all` extras were unusable on Python 3.12+.
  `undetected-chromedriver` 3.5.5 imports `distutils`, removed from the stdlib
  in PEP 632, so the extra installed cleanly and then raised
  `ModuleNotFoundError: No module named 'distutils'` on first import. Both
  extras now pull `setuptools` on 3.12+, which restores the shim.

### Added
- `bootstrap.sh` — creates a virtualenv, installs editable, and reports which
  optional browser backends resolved. The README previously documented a bare
  `pip install -e ".[dev]"`, which PEP 668 causes current Debian, Ubuntu, Arch
  and openSUSE to refuse, and which installs no browser backend at all.
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
