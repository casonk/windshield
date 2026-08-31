# BACKLOG.md

Portfolio backlog for this repository. Pending items are candidates for execution —
manually or via crew-chief. Entries sourced from archility audit are tagged
`[archility:YYYY-MM-DD]`; manual entries use `[manual:YYYY-MM-DD]`.

The archility twice-weekly job populates this file automatically via `archility audit --write-backlog`.
To execute a backlog item with crew-chief: `crew-chief agent "Work on item: <item text>"`.
Mark items `[x]` when complete and move them to Done.

## Pending

- [manual:2026-04-26] Consider adding async Playwright (async_api) support alongside sync_api
- [manual:2026-07-23] Playwright async API support for adapter layer
- [manual:2026-07-23] CDP-based event capture for Selenium/UC backends
- [manual:2026-07-23] Integration tests with real browsers (needs CI with browser setup)
- [manual:2026-07-23] Profile manager for managing multiple Chrome profiles
- [manual:2026-07-23] Cookie/session state serialization across backends

## In Progress

## Done

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
