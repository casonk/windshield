# BACKLOG.md

Portfolio backlog for this repository. Pending items are candidates for execution —
manually or via crew-chief. Entries sourced from archility audit are tagged
`[archility:YYYY-MM-DD]`; manual entries use `[manual:YYYY-MM-DD]`.

The archility twice-weekly job populates this file automatically via `archility audit --write-backlog`.
To execute a backlog item with crew-chief: `crew-chief agent "Work on item: <item text>"`.
Mark items `[x]` when complete and move them to Done.

## Pending

- [manual:2026-08-23] Add a `## Local CI Verification` section to `AGENTS.md`.
  The repo ships CI workflows but `AGENTS.md` does not say how to reproduce
  them locally — `scripts/check_agents_md.py` in traction-control flags it.
  Include the optional-dependency install (`pip install -e ".[dev]"`), since
  bare `pip install -e .` skips the optional backends and their tests fail with
  `ModuleNotFoundError`. Template:
  `traction-control/docs/templates/AGENTS.md`.

- [manual:2026-04-26] Add Playwright stealth script injection helper
- [manual:2026-04-26] Add architecture diagrams via archility
- [manual:2026-04-26] Consider adding async Playwright (async_api) support alongside sync_api
- [manual:2026-07-23] Playwright async API support for adapter layer
- [manual:2026-07-23] CDP-based event capture for Selenium/UC backends
- [manual:2026-07-23] Integration tests with real browsers (needs CI with browser setup)
- [manual:2026-07-23] Profile manager for managing multiple Chrome profiles
- [manual:2026-07-23] Cookie/session state serialization across backends

## In Progress

## Done
