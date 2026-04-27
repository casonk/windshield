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
pip install -e ".[dev]"
pre-commit install
```

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
