"""Opt-in Playwright initialization scripts and user-agent rotation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_STEALTH_USER_AGENTS = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
)

# These scripts are intentionally small, dependency-free overrides for browser
# automation fingerprints. Install them on a BrowserContext before its first
# page is created so Playwright evaluates them before every document script.
DEFAULT_PLAYWRIGHT_STEALTH_SCRIPTS = (
    """
    (() => {
      const define = (object, property, getter) => {
        try {
          Object.defineProperty(object, property, { configurable: true, get: getter });
        } catch (_) {
          // A browser may expose this property as non-configurable.
        }
      };
      define(Navigator.prototype, "webdriver", () => undefined);
      define(Navigator.prototype, "languages", () => ["en-US", "en"]);
      define(Navigator.prototype, "plugins", () => [1, 2, 3]);
      if (!window.chrome) {
        Object.defineProperty(window, "chrome", {
          configurable: true,
          value: { runtime: {} },
        });
      }
    })();
    """.strip(),
)


def install_playwright_stealth_scripts(
    target: Any,
    *,
    scripts: tuple[str, ...] | None = None,
) -> int:
    """Install initialization scripts on a Playwright context or page.

    Use a ``BrowserContext`` before creating pages when possible: Playwright
    evaluates context init scripts before every document created in that
    context. A ``Page`` is also accepted for callers that already own one;
    the scripts then apply to its future navigations and child frames.

    ``scripts`` replaces :data:`DEFAULT_PLAYWRIGHT_STEALTH_SCRIPTS` when
    supplied, which keeps provider-specific changes in the calling project.
    The return value is the number of non-empty scripts installed.
    """
    add_init_script = getattr(target, "add_init_script", None)
    if not callable(add_init_script):
        raise TypeError("target must provide Playwright's add_init_script method")

    installed = 0
    for script in DEFAULT_PLAYWRIGHT_STEALTH_SCRIPTS if scripts is None else scripts:
        if not isinstance(script, str):
            raise TypeError("Playwright initialization scripts must be strings")
        source = script.strip()
        if source:
            add_init_script(script=source)
            installed += 1
    return installed


def normalize_string_list(single_value: str, multi_values: Any) -> list[str]:
    """Deduplicate and merge a single string value with a list of strings."""
    values: list[str] = []
    if isinstance(multi_values, list):
        values.extend(str(item).strip() for item in multi_values if str(item).strip())
    single = str(single_value or "").strip()
    if single:
        values.append(single)

    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def normalize_selector_list(single_selector: str, multi_selectors: Any) -> list[str]:
    """Normalize a single selector + list of selectors into a deduplicated list."""
    return normalize_string_list(single_selector, multi_selectors)


def resolve_rotating_user_agent(
    browser_cfg: dict[str, Any],
    *,
    rotation_state_path: Path | None,
    default_user_agents: tuple[str, ...] = DEFAULT_STEALTH_USER_AGENTS,
) -> tuple[str, str]:
    """Select a user agent with round-robin rotation and persistent state.

    Returns (user_agent, source_description).
    """
    candidates = normalize_string_list(
        str(browser_cfg.get("user_agent", "")).strip(),
        browser_cfg.get("user_agents", []),
    )
    source = "config:user_agents" if candidates else ""
    if not candidates:
        candidates = list(default_user_agents)
        source = "default_stealth_user_agents"
    if not candidates:
        return "", ""
    if len(candidates) == 1 or rotation_state_path is None:
        return candidates[0], source

    next_index = 0
    try:
        if rotation_state_path.exists():
            state = json.loads(rotation_state_path.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                next_index = max(0, int(state.get("next_index", 0)))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        next_index = 0

    selected_index = next_index % len(candidates)
    selected_user_agent = candidates[selected_index]
    state_payload = {
        "next_index": next_index + 1,
        "selected_index": selected_index,
        "selected_user_agent": selected_user_agent,
        "candidate_count": len(candidates),
        "updated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        rotation_state_path.parent.mkdir(parents=True, exist_ok=True)
        rotation_state_path.write_text(
            json.dumps(state_payload, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    return (
        selected_user_agent,
        f"{source}; rotated={selected_index + 1}/{len(candidates)}",
    )
