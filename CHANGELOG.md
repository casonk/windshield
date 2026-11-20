# CHANGELOG.md

## [0.2.0] — Unreleased

### Fixed
- Rotation now tests a client matrix and keeps consumers current. `python -m windshield.client_matrix` installs the Python client of each of the last 3-5 served versions (`WINDSHIELD_MATRIX_SIZE`, default 5) into cached venvs and drives the container with it; `scripts/playwright_container.sh verify` runs it against the candidate before anything is promoted (`WINDSHIELD_VERIFY_CLIENTS=0` skips). After a promotion, and on every weekly run, `windshield.client_bump` moves the interpreters listed in `~/.config/windshield/consumers.txt` up to the newest served version, smoke-tests them, restores the previous version if that fails, and alerts. Clients are chosen by minor (`playwright==1.65.*`) because PyPI patch numbers differ from npm's.
- The rotation timer installer renders the Clockwork manifest with this checkout's real path, so it works when the repo is not under `~/git`.
- Playwright rotation now alerts through shock-relay (Signal, Telegram, Gmail): once per failed plan, on rollback, when a Node bump is rejected, when version checks fail twice running, and when a rotation is promoted. Recipients come from `WINDSHIELD_NOTIFY_<CHANNEL>_TARGET` (see `~/.config/windshield/notify.env`).
- Manual-step guidance (`sanitize_manual_guidance_text`) now drops control and invisible format characters. The text comes from the page being driven and is printed to the operator's terminal and shown in the overlay, so an escape sequence in a heading or button label (title changes, clipboard writes, screen clears) could previously reach the terminal.
- The `undetected` and `all` extras were unusable on Python 3.12+.
  `undetected-chromedriver` 3.5.5 imports `distutils`, removed from the stdlib
  in PEP 632, so the extra installed cleanly and then raised
  `ModuleNotFoundError: No module named 'distutils'` on first import. Both
  extras now pull `setuptools` on 3.12+, which restores the shim.

### Changed
- Playwright container rotation: `windshield.container_rotation` (weekly Clockwork timer, `scripts/install_playwright_rotation.sh`) rotates new Playwright minors in and drops the oldest beyond five, and tracks the Node LTS. Candidates are built and verified end to end (`playwright_container.sh verify`) before promotion, with rollback if the restarted service is unhealthy, memory of rejected plans, and a Node bump that cannot block new Playwright versions. Node is now an explicit pin copied into the image; image tags carry it (`...-node24`). New `smoke` and `verify` commands in `scripts/playwright_container.sh`.
- The Playwright container serves several versions at once (`config/playwright-versions.txt`, one server per version behind one port routed by URL path). Clients set `WINDSHIELD_PLAYWRIGHT_WS=ws://127.0.0.1:3000/{version}`; `{version}` becomes the installed client's major.minor. The image builds on the oldest version's base because the newest base ships Node 26, under which older Playwright releases hang extracting browser archives; browser installs now time out and retry instead of hanging.
- Playwright service unit treats the container's SIGTERM exit (143) as a clean stop, so `systemctl --user stop` no longer leaves the unit in `failed`.
- Playwright container: `WINDSHIELD_CONTAINER_NETWORK=host` mode (shares the host network, server bound to `127.0.0.1`) so UI tests can reach pages served on the host's loopback; the service installer records the mode in the unit.
- Playwright container image now bakes in the pinned `playwright` package (offline start, verified with `--network=none`). `playwright_container.sh start` waits until the server is listening, and `windshield.remote` retries transient connect errors (`ECONNRESET`/`ECONNREFUSED`) up to 5 times; version mismatches are not retried.

### Added
- Containerised Playwright server: `windshield.remote` (`launch_or_connect`, `WINDSHIELD_PLAYWRIGHT_WS`), used automatically by `create_page("playwright")` and `create_async_playwright_page()`; `deploy/container/Containerfile`, `scripts/playwright_container.sh` and `scripts/install_playwright_service.sh`. Loopback-only by default, falls back to a local browser unless `WINDSHIELD_PLAYWRIGHT_STRICT=1`.
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
- Initial extraction of browser-automation shared modules from a private
  consumer repository.
- `windshield.browser` — Chrome for Testing download, discovery, CDP version helpers.
- `windshield.page` — Playwright page interaction: fill, click, type, wait, read, submit.
- `windshield.debug` — Page snapshots (HTML + JSON + PNG), runtime event capture, JSONL logging.
- `windshield.challenge` — Cloudflare/CAPTCHA challenge detection and wait-to-clear.
- `windshield.stealth` — User agent rotation with persistent state, selector/string normalization.
- `windshield.http` — HTTP opener, URL fragment matching, browser location description, error redaction.
- `windshield.overlay` — In-page manual-continue overlay and terminal prompt for human-in-the-loop steps.
- Full test suite with mock page/request/response objects.
- Traction-control governance baseline (AGENTS.md, SECURITY.md, CI, pre-commit, etc.).
