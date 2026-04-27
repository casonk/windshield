# Windshield — Contributor Architecture Blueprint

## Overview

Windshield is a generic browser automation utility library built on top of Playwright's synchronous API. It was extracted from the `private-repository` repository to decouple reusable browser automation primitives from provider-specific scraping logic.

## Module Architecture

```
windshield/
├── __init__.py       Re-exports public API surface
├── _errors.py        WindshieldError base exception
├── browser.py        Chrome binary discovery, Chrome for Testing download,
│                     CDP version polling, zip extraction with permissions
├── page.py           Page interaction primitives — fill, click, type, wait,
│                     submit, read text, selector matching, frame iteration
├── debug.py          Snapshot capture (HTML + metadata JSON + PNG screenshot),
│                     Playwright event listener installation, JSONL debug logging
├── challenge.py      Cloudflare/CAPTCHA challenge page detection,
│                     wait-for-challenge-to-clear with fast-fail support
├── stealth.py        User agent rotation with JSON-persisted state,
│                     string/selector list normalization
├── http.py           urllib opener construction (with optional TLS bypass),
│                     URL fragment matching, browser location description,
│                     error text redaction
└── overlay.py        In-page manual-continue overlay (JS injection),
                      terminal prompt fallback, page guidance summarizer
```

## Data Flow

```
Downstream consumer (e.g. private-repository)
    │
    ├── windshield.browser   → Chrome binary
    ├── windshield.stealth   → User agent string
    │       ↓
    │   Playwright launch (browser context)
    │       ↓
    ├── windshield.page      → Fill/click/wait/read on pages
    ├── windshield.challenge  → Detect & wait for challenges
    ├── windshield.overlay   → Manual human-in-the-loop steps
    ├── windshield.debug     → Snapshots & event logs
    └── windshield.http      → Direct HTTP requests alongside browser
```

## Design Decisions

1. **Playwright sync_api only** — All page interaction uses Playwright's synchronous API. Async support is a future backlog item.
2. **No credential handling** — Credentials are out of scope; use `auto-pass` for KeePassXC integration.
3. **No OTP/messaging** — OTP delivery is out of scope; use `shock-relay` for Signal/IMAP polling.
4. **Provider-agnostic** — No financial institution URLs, selectors, or navigation sequences. All provider-specific logic stays in the downstream consumer.
5. **Loose Playwright coupling** — Page objects are typed as `Any` to avoid hard import dependency; Playwright is only needed at runtime.
