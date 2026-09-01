# BACKLOG.md

Portfolio backlog for this repository. Pending items are candidates for execution —
manually or via crew-chief. Entries sourced from archility audit are tagged
`[archility:YYYY-MM-DD]`; manual entries use `[manual:YYYY-MM-DD]`.

The archility twice-weekly job populates this file automatically via `archility audit --write-backlog`.
To execute a backlog item with crew-chief: `crew-chief agent "Work on item: <item text>"`.
Mark items `[x]` when complete and move them to Done.

## Pending


## In Progress

## Done

- [x] [manual:2026-07-23] Add integration tests with real browsers. Added a
  dedicated Chromium CI job and an inline-document Playwright adapter smoke
  test that skips in ordinary environments without browser provisioning.
  [manual:2026-09-01]

- [x] [manual:2026-07-23] Add cookie/session state serialization across
  backends. Added explicit in-memory, JSON-serializable cookie exchange for
  Playwright, Selenium/undetected Chrome, and HTTP without automatic storage.
  [manual:2026-09-01]

- [x] [manual:2026-07-23] Add a profile manager for multiple Chrome profiles.
  Added validated named-directory creation, discovery, and existence checks for
  isolated user-data directories without touching existing Chrome data.
  [manual:2026-09-01]

- [x] [manual:2026-07-23] Add CDP-based event capture for Selenium/UC
  backends. Added an explicit, pull-based performance-log drain that
  normalizes Chrome CDP network and console events and dispatches registered
  handlers without requiring background threads. [manual:2026-09-01]

- [x] [manual:2026-04-26] Add async Playwright (`async_api`) support alongside
  the sync API. Consolidated the duplicate adapter-layer item: added parallel
  awaitable page/locator protocols, wrappers, a Playwright-only constructor,
  and mock-backed coverage without changing the synchronous multi-backend
  contract. [manual:2026-08-31]

- [x] [manual:2026-04-26] Add architecture diagrams via archility. Completed
  through the checked-in PlantUML and Draw.io sources, PNG/SVG renders, and
  supplemental import/class/tooling diagrams (f9e65fd, a737eb6, 6e0c57e,
  aec4d00).

- [x] [manual:2026-04-26] Add Playwright stealth script injection helper.
  Added `install_playwright_stealth_scripts` with mock-backed context/page
  tests and explicit opt-in usage documentation. [manual:2026-08-31]

- [x] [manual:2026-08-23] Add a `## Local CI Verification` section to
  `AGENTS.md`. Completed in 0f46a5d (`docs: add a Local CI Verification section
  to AGENTS.md`, #7).
