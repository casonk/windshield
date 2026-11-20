# BACKLOG.md

Portfolio backlog for this repository. Pending items are candidates for execution —
manually or via crew-chief. Entries sourced from archility audit are tagged
`[archility:YYYY-MM-DD]`; manual entries use `[manual:YYYY-MM-DD]`.

The archility twice-weekly job populates this file automatically via `archility audit --write-backlog`.
To execute a backlog item with crew-chief: `crew-chief agent "Work on item: <item text>"`.
Mark items `[x]` when complete and move them to Done.

## Pending

- [ ] [codecov:2026-11-18] **Raise patch coverage on PR #32: 96.1539% patched, 3 changed lines have no test coverage.** Files: src/windshield/remote.py (2 missing, 97.29%), src/windshield/adapters/_factory.py (1 missing, 75%). Add tests for the uncovered lines. (codecov-pr:32, https://github.com/casonk/windshield/pull/32#issuecomment-6974887060)
- [ ] [codecov:2026-11-19] **Raise patch coverage on PR #38: 66.6667% patched, 3 changed lines have no test coverage.** Files: src/windshield/remote.py (3 missing, 66.66%). Add tests for the uncovered lines. (codecov-pr:38, https://github.com/casonk/windshield/pull/38#issuecomment-7013079732)
- [ ] [codecov:2026-11-19] **Raise patch coverage on PR #40: 85.514% patched, 31 changed lines have no test coverage.** Files: src/windshield/container_rotation.py (31 missing, 85.51%). Add tests for the uncovered lines. (codecov-pr:40, https://github.com/casonk/windshield/pull/40#issuecomment-7014522455)
- [ ] [codecov:2026-11-20] **Raise patch coverage on PR #42: 82.2785% patched, 14 changed lines have no test coverage.** Files: src/windshield/container_rotation.py (9 missing, 62.5%), src/windshield/notify.py (5 missing, 90.9%). Add tests for the uncovered lines. (codecov-pr:42, https://github.com/casonk/windshield/pull/42#issuecomment-7027085660)
- [ ] [codecov:2026-11-20] **Raise patch coverage on PR #47: 73.3945% patched, 29 changed lines have no test coverage.** Files: src/windshield/consumer_matrix.py (29 missing, 71.84%). Add tests for the uncovered lines. (codecov-pr:47, https://github.com/casonk/windshield/pull/47#issuecomment-7041899037)
- [ ] [manual:2026-10-15] **Ask GitHub Support to purge pre-rewrite commits** — this
  repository's published history was rewritten (most recently on 2026-10-15,
  to remove per-commit AI attribution trailers). GitHub keeps serving the old
  commits to anyone with a hash, and through the read-only `refs/pull/*` refs
  of earlier pull requests, until Support garbage-collects them. The request
  is filed once for the whole portfolio from traction-control's backlog; mark
  this done when an old hash returns 404 here. Never push an old clone's
  history back.


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
