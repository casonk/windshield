# Windshield

Reusable Playwright browser automation utilities — Chrome management, page interaction, debugging, challenge detection, and stealth helpers.

Extracted from provider-specific browser automation code to provide a generic, testable foundation for any Playwright-based scraping or automation workflow.

## Prerequisites

- Python 3.10+
- [Playwright](https://playwright.dev/python/) (sync API) — required at runtime for page interaction
- Chrome or Chromium — discovered automatically or downloaded via Chrome for Testing

## Installation

```bash
pip install git+https://github.com/casonk/windshield.git
```

For development:

```bash
git clone https://github.com/casonk/windshield.git
cd windshield
./bootstrap.sh --all --pre-commit
```

`bootstrap.sh` creates `.venv`, installs the package in editable mode, and then
reports which optional browser backends actually resolved — worth knowing,
because **every backend here is an optional extra**. `./bootstrap.sh` on its own
installs `.[dev]`, which gives you the test tooling and no way to drive a page:

```
  [ ] playwright                 page interaction (the primary backend)
  [ ] selenium                   selenium driver support
  [x] requests                   windshield.http
```

Pick what you need:

| Command | Installs |
| --- | --- |
| `./bootstrap.sh` | `.[dev]` — tests and linting only |
| `./bootstrap.sh --all` | every backend, plus dev |
| `./bootstrap.sh --extras playwright` | just the primary backend |
| `./bootstrap.sh --extras playwright,http` | pick your own set |

Playwright's browser binaries are a separate download; the script tells you when
that step is needed:

```bash
.venv/bin/playwright install chromium
```

<details>
<summary>Why not <code>pip install -e ".[dev]"</code> directly?</summary>

Since [PEP 668](https://peps.python.org/pep-0668/), Debian, Ubuntu, Arch and
openSUSE mark the system Python as externally managed, and pip refuses to
install into it:

```
error: externally-managed-environment
```

Fedora still allows it, which is why the old instruction worked on some
machines and not others. Installing into a virtualenv is correct on all of
them, and on macOS and Windows too.

</details>

## Modules

| Module | Purpose |
|---|---|
| `windshield.browser` | Chrome for Testing download/discovery, CDP version helpers |
| `windshield.page` | Page interaction: fill, click, type, wait, submit, read |
| `windshield.debug` | Page snapshots (HTML + JSON + PNG), runtime event capture |
| `windshield.challenge` | Cloudflare/CAPTCHA challenge detection and waiting |
| `windshield.stealth` | User agent rotation with persistent state |
| `windshield.http` | HTTP opener, URL matching, browser location, error redaction |
| `windshield.overlay` | In-page manual-continue overlay for human-in-the-loop steps |

### Playwright initialization scripts

For an opt-in, generic Playwright fingerprint adjustment, install the bundled
initialization scripts on a context **before** creating its first page. They run
before page JavaScript on every document in that context. Provider-specific
scripts remain the caller's responsibility and can replace the bundled tuple.

```python
from windshield import install_playwright_stealth_scripts

context = browser.new_context()
install_playwright_stealth_scripts(context)
page = context.new_page()
```

### Async Playwright adapter

The default adapter API remains synchronous so Selenium, undetected Chrome, and
HTTP consumers keep one common contract. Async applications can opt into the
parallel Playwright-only API without changing those callers:

```python
from windshield import create_async_playwright_page

page = await create_async_playwright_page(raw=existing_async_page)
await page.goto("https://example.com")
title = await page.title()
await page.close()
```

Pass an async Playwright `Page` through `raw` when the application owns the
browser lifecycle. Without `raw`, the helper starts Playwright and creates a
page using the supplied launch options.

### Selenium and undetected Chrome CDP events

Chrome-backed Selenium and undetected-chromedriver sessions can expose network
and console events through the performance log. Enable that log when creating
the driver, register normal page event handlers, and drain it from your own
polling loop. This helper deliberately does not start a background thread.

```python
page.on("response", events.append)
page.on("console", events.append)
page.drain_cdp_events()
```

### Named Chrome profiles

Use a dedicated user-data directory for each automation identity instead of
sharing an interactive browser profile. The manager only creates and lists
directories beneath the root you provide; it never imports, changes, or deletes
an existing Chrome profile.

```python
from windshield import ProfileManager, create_page

profiles = ProfileManager("~/.local/share/windshield/profiles")
work_profile = profiles.create("work")
page = create_page("undetected", profile_dir=work_profile)
```

### Cookie-session exchange

Session exchange is explicit and in-memory: it gives the caller a
JSON-serializable cookie snapshot but never writes it to disk. Cookies are
bearer credentials; persist the snapshot only in an appropriate secure store.

```python
from windshield import export_session_state, import_session_state

state = export_session_state(source_page)
import_session_state(target_page, state)
```

Selenium can add cookies only for the currently open domain. Navigate to each
domain before importing multi-domain snapshots there.

### Real-browser integration check

The dedicated Browser Integration workflow installs Chromium and drives only an
inline document through the synchronous Playwright adapter. Run it locally when
changing adapter behavior:

```bash
pip install -e ".[dev,playwright]"
python -m playwright install chromium
pytest -q tests/test_browser_integration.py
```

## Quick Start

```python
from windshield.browser import discover_chrome_binary, download_chrome_for_testing
from windshield.page import fill_first_visible, click_first_visible, wait_for_any_selector
from windshield.debug import capture_page_snapshot

# Find or download Chrome
chrome_path = discover_chrome_binary() or download_chrome_for_testing()

# Interact with a Playwright page
fill_first_visible(page, ["#username", "input[name='user']"], "myuser", "username")
click_first_visible(page, ["button[type='submit']", "#login-btn"], "submit")

# Wait for navigation
wait_for_any_selector(page, [".dashboard", "#main-content"], timeout_ms=10000,
                      state="visible", field_name="post_login")

# Debug snapshot
capture_page_snapshot(page, Path("./snapshots"), "post-login")
```

## Multi-Backend Support

Windshield supports 4 browser automation backends that can be swapped transparently:

| Backend | Package | Best For | Anti-Detection |
|---------|---------|----------|----------------|
| `playwright` | `playwright` | Default, most ergonomic | No |
| `undetected` | `undetected-chromedriver` | Scraping, live profiles | Yes |
| `selenium` | `selenium` | Fallback, legacy compat | No |
| `http` | `requests` + `beautifulsoup4` | Static pages, APIs | N/A |

### Quick Start

```python
from windshield import create_page, BackendType

# Wrap an existing Playwright page
page = create_page("playwright", raw=existing_page)

# Create an undetected Chrome browser with a live user profile
page = create_page("undetected", profile_dir="/path/to/chrome/profile")

# Use HTTP-only mode for static pages
page = create_page("http", html="<html>...</html>")

# All windshield functions work with any adapter
from windshield import fill_first_visible, click_first_visible
fill_first_visible(page, ["input#username"], "user@example.com", "username")
click_first_visible(page, ["button[type=submit]"], "submit")
```

### Backend Rotation

Automatically rotate between backends when one gets blocked:

```python
from windshield import RotationStrategy, BackendType

strategy = RotationStrategy(
    backends=[BackendType.UNDETECTED, BackendType.PLAYWRIGHT, BackendType.SELENIUM],
    cooldown_seconds=300,
)

# Get the next available backend
backend, page = strategy.create_page(profile_dir="/path/to/profile")

# If blocked, report it and try the next backend
strategy.report_block(backend, reason="CAPTCHA detected")
backend, page = strategy.create_page()

# On success, clear block history
strategy.report_success(backend)
```

### Optional Dependencies

Install only the backends you need:

```bash
pip install playwright           # Playwright backend
pip install selenium             # Selenium backend
pip install undetected-chromedriver  # Undetected Chrome backend
pip install requests beautifulsoup4  # HTTP-only backend
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
