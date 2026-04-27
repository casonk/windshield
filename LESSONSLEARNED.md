# LESSONSLEARNED.md

Tracked durable lessons for `windshield`.
Unlike `CHATHISTORY.md`, this file should keep only reusable lessons that should change how future sessions work in this repo.

## How To Use

- Read this file after `AGENTS.md` and before `CHATHISTORY.md` when resuming work.
- Add lessons that generalize beyond a single session.
- Keep entries concise and action-oriented.
- Do not use this file for transient status updates or full session logs.

## Lessons

- Document the repository around its real execution, curation, or integration flow instead of only the top-level folder list.
- Keep local-only, private, reference-only, or generated boundaries explicit so published or runtime behavior is not confused with offline material or non-committable inputs.
- Keep tracked examples, fixtures, and `.example` templates scrubbed of real paths, usernames, hostnames, account identifiers, or other instance-specific values; real operator data belongs only in gitignored local config.
- Re-run repo-appropriate validation after changing generated artifacts, diagrams, workflows, or other CI-facing files so formatting and compatibility issues are caught before push.
- **CI optional-dep groups**: When a library uses `[project.optional-dependencies]` groups (e.g. `[http]`, `[dev]`), CI must install `pip install -e ".[dev]"` — not bare `pip install -e .` — or tests for optional backends will fail with `ModuleNotFoundError`. Keep CI install lines minimal: if `[dev]` already declares `pytest`, `ruff`, `black`, etc., don't duplicate them as separate `pip install` lines.
- **Multi-backend adapter protocols**: Use `typing.Protocol` with `@runtime_checkable` for adapter interfaces so consumers code against a single API while supporting multiple browser backends. Keep backend-specific imports lazy (inside methods/functions) so the library installs cleanly without any backend package.
- **Privacy-first backend rotation**: Order browser backends from least detectable to most detectable (undetected → HTTP → Playwright → Selenium) and only downgrade when the current backend is blocked. Define the canonical ordering as a module-level constant (`DEFAULT_ROTATION_ORDER`) rather than hardcoding in the rotation strategy constructor.
