"""Playwright page interaction primitives — fill, click, type, wait, read, submit."""

from __future__ import annotations

import re
import time
from typing import Any, Callable
from urllib.parse import urlparse

from windshield._errors import WindshieldError


def is_page_or_context_closed_error(exc: Exception) -> bool:
    """Return True if the exception indicates a closed page/context/browser."""
    message = str(exc or "").lower()
    markers = (
        "target page, context or browser has been closed",
        "page has been closed",
        "context has been closed",
        "browser has been closed",
    )
    return any(marker in message for marker in markers)


def iter_locator_contexts(page: Any) -> list[tuple[str, Any]]:
    """Return (name, context) pairs for the main page and same-origin frames."""
    contexts: list[tuple[str, Any]] = [("main", page)]
    page_origin = ""
    try:
        page_origin = urlparse(str(getattr(page, "url", "") or "")).netloc.lower()
    except Exception:  # pylint: disable=broad-except
        page_origin = ""
    try:
        main_frame = page.main_frame
    except Exception:  # pylint: disable=broad-except
        main_frame = None
    try:
        for idx, frame in enumerate(page.frames):
            if main_frame is not None and frame == main_frame:
                continue
            frame_url = str(getattr(frame, "url", "") or "")
            if frame_url:
                parsed = urlparse(frame_url)
                if parsed.scheme in {"http", "https"}:
                    frame_origin = parsed.netloc.lower()
                    if page_origin and frame_origin and frame_origin != page_origin:
                        continue
            contexts.append((f"frame[{idx}]<{frame_url}>", frame))
    except Exception:  # pylint: disable=broad-except
        pass
    return contexts


def iter_page_frames(page: Any) -> list[Any]:
    """Return all frames from a page, falling back to the page itself."""
    frames: list[Any] = []
    try:
        frames = [frame for frame in page.frames if frame is not None]
    except Exception:  # pylint: disable=broad-except
        frames = []
    if not frames:
        try:
            main_frame = page.main_frame
            if main_frame is not None:
                frames = [main_frame]
        except Exception:  # pylint: disable=broad-except
            pass
    if not frames and page is not None:
        frames = [page]
    return frames


def read_page_text(page: Any) -> str:
    """Extract visible text from a page."""
    try:
        return str(page.locator("body").inner_text(timeout=2000) or "")
    except Exception:  # pylint: disable=broad-except
        try:
            return str(page.content() or "")
        except Exception:  # pylint: disable=broad-except
            return ""


def title_contains_any_text(page: Any, snippets: list[str]) -> bool:
    """Return True if the page title contains any of the given text snippets."""
    values = [str(item).strip().lower() for item in snippets if str(item).strip()]
    if not values:
        return False
    try:
        title = str(page.title() or "").lower()
    except Exception:  # pylint: disable=broad-except
        title = ""
    return any(needle in title for needle in values)


def page_contains_any_text(page: Any, snippets: list[str]) -> bool:
    """Return True if the page body contains any of the given text snippets."""
    values = [str(item).strip().lower() for item in snippets if str(item).strip()]
    if not values:
        return False
    text = read_page_text(page)
    haystack = text.lower()
    return any(needle in haystack for needle in values)


def matching_text_snippets(page: Any, snippets: list[str]) -> list[str]:
    """Return which snippets are found in the page text."""
    values = [str(item).strip().lower() for item in snippets if str(item).strip()]
    if not values:
        return []
    haystack = read_page_text(page).lower()
    matches = [needle for needle in values if needle in haystack]
    return list(dict.fromkeys(matches))


def has_any_selector(page: Any, selectors: list[str]) -> bool:
    """Return True if any selector matches in any same-origin context."""
    for _context_name, context in iter_locator_contexts(page):
        for selector in selectors:
            try:
                if context.locator(selector).count() > 0:
                    return True
            except Exception:  # pylint: disable=broad-except
                continue
    return False


def first_visible_selector_match(page: Any, selectors: list[str]) -> str:
    """Return the first selector that has a visible match, or empty string."""
    for context_name, context in iter_locator_contexts(page):
        for selector in selectors:
            try:
                locator = context.locator(selector)
                count = locator.count()
            except Exception:  # pylint: disable=broad-except
                continue
            if count <= 0:
                continue
            for idx in range(min(count, 12)):
                item = locator.nth(idx)
                try:
                    if item.is_visible():
                        return f"{context_name}:{selector}"
                except Exception:  # pylint: disable=broad-except
                    continue
    return ""


def fill_first_visible(page: Any, selectors: list[str], value: str, field_name: str) -> str:
    """Fill the first visible+enabled input matching any selector."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no selectors configured")

    attempts: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count == 0:
            attempts.append(f"{selector} (0 matches)")
            continue

        for idx in range(count):
            item = locator.nth(idx)
            if not item.is_visible():
                continue
            if not item.is_enabled():
                continue
            try:
                item.fill(value)
                return selector
            except Exception as exc:  # pylint: disable=broad-except
                attempts.append(f"{selector}[{idx}] fill-error({type(exc).__name__})")
                continue

        attempts.append(f"{selector} ({count} matches, none visible+enabled)")

    raise WindshieldError(
        f"{field_name}: no visible editable element found; tried selectors: {', '.join(attempts)}"
    )


def type_first_visible(
    page: Any,
    selectors: list[str],
    value: str,
    field_name: str,
    delay_ms: int = 35,
) -> str:
    """Type into the first visible+enabled input matching any selector."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no selectors configured")

    attempts: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count == 0:
            attempts.append(f"{selector} (0 matches)")
            continue

        for idx in range(count):
            item = locator.nth(idx)
            try:
                is_visible = item.is_visible()
            except Exception:  # pylint: disable=broad-except
                is_visible = False
            try:
                is_enabled = item.is_enabled()
            except Exception:  # pylint: disable=broad-except
                is_enabled = False
            if not (is_visible and is_enabled):
                continue
            try:
                item.click()
                item.fill("")
                item.type(value, delay=max(0, int(delay_ms)))
                return selector
            except Exception as exc:  # pylint: disable=broad-except
                attempts.append(f"{selector}[{idx}] type-error({type(exc).__name__})")
                continue

        attempts.append(f"{selector} ({count} matches, none visible+enabled)")

    raise WindshieldError(
        f"{field_name}: no visible editable element for typing; "
        f"tried selectors: {', '.join(attempts)}"
    )


def read_first_visible_input_value(page: Any, selectors: list[str]) -> tuple[str, str]:
    """Read the value of the first visible+enabled input. Returns (selector, value)."""
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count <= 0:
            continue
        for idx in range(count):
            item = locator.nth(idx)
            try:
                if not item.is_visible() or not item.is_enabled():
                    continue
            except Exception:  # pylint: disable=broad-except
                continue
            try:
                value = item.input_value()
            except Exception:  # pylint: disable=broad-except
                try:
                    value = item.evaluate("el => String(el.value || '')")
                except Exception:  # pylint: disable=broad-except
                    value = ""
            return selector, str(value or "")
    return "", ""


def script_set_first_visible_value(
    page: Any, selectors: list[str], value: str, field_name: str
) -> str:
    """Set input value via JavaScript for the first visible+enabled match."""
    attempts: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count <= 0:
            attempts.append(f"{selector} (0 matches)")
            continue
        for idx in range(count):
            item = locator.nth(idx)
            try:
                if not item.is_visible() or not item.is_enabled():
                    continue
            except Exception:  # pylint: disable=broad-except
                continue
            try:
                item.evaluate(
                    """(el, nextValue) => {
                        el.focus();
                        el.value = '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.value = nextValue;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    value,
                )
                return selector
            except Exception as exc:  # pylint: disable=broad-except
                attempts.append(f"{selector}[{idx}] script-set-error({type(exc).__name__})")
                continue
        attempts.append(f"{selector} ({count} matches, none visible+enabled)")
    raise WindshieldError(
        f"{field_name}: unable to set value via script; tried selectors: {', '.join(attempts)}"
    )


def set_first_visible_value_robust(
    page: Any,
    selectors: list[str],
    value: str,
    field_name: str,
    input_mode: str = "fill_then_type_verify",
    type_delay_ms: int = 35,
) -> tuple[str, str, int]:
    """Set a value using multiple strategies with verification. Returns (selector, method, length)."""
    mode = str(input_mode or "").strip().lower()
    if mode not in {
        "fill",
        "type",
        "fill_then_type_verify",
        "type_then_fill_verify",
    }:
        mode = "fill_then_type_verify"

    method_order: list[str]
    if mode == "fill":
        method_order = ["fill"]
    elif mode == "type":
        method_order = ["type"]
    elif mode == "type_then_fill_verify":
        method_order = ["type", "fill", "script"]
    else:
        method_order = ["fill", "type", "script"]

    attempt_notes: list[str] = []
    for method in method_order:
        selector_used = ""
        try:
            if method == "fill":
                selector_used = fill_first_visible(page, selectors, value, field_name)
            elif method == "type":
                selector_used = type_first_visible(
                    page=page,
                    selectors=selectors,
                    value=value,
                    field_name=field_name,
                    delay_ms=type_delay_ms,
                )
            else:
                selector_used = script_set_first_visible_value(
                    page=page,
                    selectors=selectors,
                    value=value,
                    field_name=field_name,
                )
        except WindshieldError as exc:
            attempt_notes.append(f"{method}:set_failed({exc})")
            continue

        _selector_checked, current_value = read_first_visible_input_value(page, selectors)
        if current_value == value:
            return selector_used, method, len(current_value)
        attempt_notes.append(
            f"{method}:verify_failed(expected_len={len(value)} got_len={len(current_value)})"
        )

    raise WindshieldError(
        f"{field_name}: could not reliably set value; attempts={'; '.join(attempt_notes)}"
    )


def click_first_visible(
    page: Any,
    selectors: list[str],
    field_name: str,
    allow_force_click: bool = False,
) -> str:
    """Click the first visible+enabled element matching any selector."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no selectors configured")

    attempts: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count == 0:
            attempts.append(f"{selector} (0 matches)")
            continue

        force_click_errors: list[str] = []
        for idx in range(count):
            item = locator.nth(idx)
            try:
                is_visible = item.is_visible()
            except Exception:  # pylint: disable=broad-except
                is_visible = False
            try:
                is_enabled = item.is_enabled()
            except Exception:  # pylint: disable=broad-except
                is_enabled = False

            if is_visible and is_enabled:
                try:
                    item.click()
                    return selector
                except Exception as exc:  # pylint: disable=broad-except
                    attempts.append(f"{selector}[{idx}] click-error({type(exc).__name__})")
                    continue

            if allow_force_click and is_enabled:
                try:
                    item.click(force=True)
                    return selector
                except Exception as exc:  # pylint: disable=broad-except
                    force_click_errors.append(type(exc).__name__)
                    try:
                        item.evaluate("el => el.click()")
                        return selector
                    except Exception as js_exc:  # pylint: disable=broad-except
                        force_click_errors.append(type(js_exc).__name__)
                    continue

        if force_click_errors:
            attempts.append(
                f"{selector} ({count} matches, force click failed: {', '.join(force_click_errors)})"
            )
        else:
            attempts.append(f"{selector} ({count} matches, none visible+enabled)")

    raise WindshieldError(
        f"{field_name}: no visible clickable element found; tried selectors: {', '.join(attempts)}"
    )


def click_optional_selectors(
    page: Any,
    selectors: list[str],
    allow_force_click: bool = True,
) -> list[str]:
    """Best-effort click on each selector; returns list of selectors that were clicked."""
    clicked: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        try:
            count = locator.count()
        except Exception:  # pylint: disable=broad-except
            continue
        if count <= 0:
            continue
        for idx in range(count):
            item = locator.nth(idx)
            try:
                visible = item.is_visible()
            except Exception:  # pylint: disable=broad-except
                visible = False
            try:
                enabled = item.is_enabled()
            except Exception:  # pylint: disable=broad-except
                enabled = False
            if not enabled:
                continue
            try:
                if visible:
                    item.click()
                    clicked.append(selector)
                    break
                if allow_force_click:
                    item.click(force=True)
                    clicked.append(selector)
                    break
            except Exception:  # pylint: disable=broad-except
                try:
                    item.evaluate("el => el.click()")
                    clicked.append(selector)
                    break
                except Exception:  # pylint: disable=broad-except
                    continue
    return clicked


def click_selector_any(page: Any, selector: str) -> bool:
    """Best-effort click on a selector across all contexts. Returns True on success."""
    sel = str(selector or "").strip()
    if not sel:
        return False

    for _context_name, context in iter_locator_contexts(page):
        try:
            locator = context.locator(sel)
            count = locator.count()
        except Exception:  # pylint: disable=broad-except
            continue
        if count <= 0:
            continue

        for idx in range(count):
            item = locator.nth(idx)
            try:
                item.click(timeout=1200)
                return True
            except Exception:  # pylint: disable=broad-except
                try:
                    item.click(force=True, timeout=1200)
                    return True
                except Exception:  # pylint: disable=broad-except
                    try:
                        item.evaluate("el => el.click()")
                        return True
                    except Exception:  # pylint: disable=broad-except
                        continue
    return False


def click_first_selector_best_effort(
    page: Any,
    selectors: list[str],
    step_timeout_ms: int = 8000,
    recover_page: Callable[[str], Any] | None = None,
) -> str:
    """Try each selector in order with retry until one clicks. Returns matched selector."""
    for selector in selectors:
        sel = str(selector or "").strip()
        if not sel:
            continue
        deadline = time.monotonic() + max(1000, step_timeout_ms) / 1000.0
        while time.monotonic() < deadline:
            if click_selector_any(page, sel):
                return sel
            try:
                page.wait_for_timeout(200)
            except Exception as exc:  # pylint: disable=broad-except
                if recover_page and is_page_or_context_closed_error(exc):
                    page = recover_page(f"click_first_selector_best_effort:{sel}")
                    continue
                raise
    return ""


def click_control_with_labels(
    page: Any,
    labels: list[str],
    field_name: str,
    max_controls_per_context: int = 250,
) -> str:
    """Click the first button/link whose text matches any label."""
    normalized = [label.lower() for label in labels if str(label).strip()]
    if not normalized:
        raise WindshieldError(f"{field_name}: no labels configured")

    attempts: list[str] = []
    for context_name, context in iter_locator_contexts(page):
        controls = context.locator(
            "button, a, [role='button'], input[type='submit'], input[type='button']"
        )
        try:
            count = controls.count()
        except Exception as exc:  # pylint: disable=broad-except
            attempts.append(f"{context_name}:control-count-error({type(exc).__name__})")
            continue
        if count == 0:
            continue

        limit = min(count, max_controls_per_context)
        for idx in range(limit):
            item = controls.nth(idx)
            try:
                raw_text = item.evaluate(
                    "el => (el.innerText || el.textContent || el.value "
                    "|| el.getAttribute('aria-label') || '').trim()"
                )
            except Exception:  # pylint: disable=broad-except
                raw_text = ""
            text = str(raw_text or "").strip()
            haystack = text.lower()
            if not haystack:
                continue
            matched = False
            for label in normalized:
                if len(label) <= 3:
                    if re.search(rf"\b{re.escape(label)}\b", haystack):
                        matched = True
                        break
                elif label in haystack:
                    matched = True
                    break
            if not matched:
                continue

            try:
                item.click()
                return f"{context_name}:{text}"
            except Exception:  # pylint: disable=broad-except
                try:
                    item.click(force=True)
                    return f"{context_name}:{text}"
                except Exception:  # pylint: disable=broad-except
                    try:
                        item.evaluate("el => el.click()")
                        return f"{context_name}:{text}"
                    except Exception as js_exc:  # pylint: disable=broad-except
                        attempts.append(
                            f"{context_name}:{text}:click-error({type(js_exc).__name__})"
                        )

    raise WindshieldError(
        f"{field_name}: no clickable control matched labels; attempts: {', '.join(attempts)}"
    )


def submit_first_matching_form(
    page: Any,
    selectors: list[str],
    field_name: str,
    require_visible: bool = False,
) -> str:
    """Submit the form containing the first matched element."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no form selectors configured")

    attempts: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count == 0:
            attempts.append(f"{selector} (0 matches)")
            continue
        for idx in range(count):
            item = locator.nth(idx)
            if require_visible:
                try:
                    if not item.is_visible():
                        continue
                except Exception:  # pylint: disable=broad-except
                    continue
            try:
                item.evaluate("""
                    (el) => {
                      const form = el instanceof HTMLFormElement ? el : el.closest('form');
                      if (!form) {
                        throw new Error('form_not_found');
                      }
                      if (typeof form.requestSubmit === 'function') {
                        form.requestSubmit();
                      } else {
                        form.submit();
                      }
                    }
                    """)
                return selector
            except Exception as exc:  # pylint: disable=broad-except
                attempts.append(f"{selector}[{idx}] submit-error({type(exc).__name__})")

        attempts.append(f"{selector} ({count} matches, submit failed)")

    raise WindshieldError(
        f"{field_name}: unable to submit form; tried selectors: {', '.join(attempts)}"
    )


def press_enter_first_visible(page: Any, selectors: list[str], field_name: str) -> str:
    """Press Enter on the first visible+enabled element matching any selector."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no selectors configured")

    attempts: list[str] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = locator.count()
        if count == 0:
            attempts.append(f"{selector} (0 matches)")
            continue

        for idx in range(count):
            item = locator.nth(idx)
            try:
                is_visible = item.is_visible()
            except Exception:  # pylint: disable=broad-except
                is_visible = False
            try:
                is_enabled = item.is_enabled()
            except Exception:  # pylint: disable=broad-except
                is_enabled = False
            if not (is_visible and is_enabled):
                continue
            try:
                item.press("Enter")
                return f"press_enter:{selector}"
            except Exception as exc:  # pylint: disable=broad-except
                attempts.append(f"{selector}[{idx}] press-error({type(exc).__name__})")
                continue

        attempts.append(f"{selector} ({count} matches, none visible+enabled)")

    raise WindshieldError(
        f"{field_name}: no visible editable element for Enter submit; "
        f"tried selectors: {', '.join(attempts)}"
    )


# ---------------------------------------------------------------------------
# Waiting helpers
# ---------------------------------------------------------------------------


def wait_for_selector_to_disappear(
    page: Any,
    selectors: list[str],
    timeout_ms: int,
    recover_page: Callable[[str], Any] | None = None,
) -> bool:
    """Wait until none of the selectors match. Returns True if cleared."""
    deadline = time.monotonic() + max(1000, timeout_ms) / 1000.0
    while time.monotonic() < deadline:
        try:
            if not has_any_selector(page, selectors):
                return True
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page("wait_for_selector_to_disappear:presence_check")
                continue
            raise
        try:
            page.wait_for_timeout(250)
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page("wait_for_selector_to_disappear:sleep")
                continue
            raise
    try:
        return not has_any_selector(page, selectors)
    except Exception as exc:  # pylint: disable=broad-except
        if recover_page and is_page_or_context_closed_error(exc):
            page = recover_page("wait_for_selector_to_disappear:final_check")
            return not has_any_selector(page, selectors)
        raise


def wait_for_text_to_disappear(
    page: Any,
    snippets: list[str],
    timeout_ms: int,
    recover_page: Callable[[str], Any] | None = None,
) -> bool:
    """Wait until none of the text snippets appear on the page."""
    if not snippets:
        return True
    deadline = time.monotonic() + max(1000, timeout_ms) / 1000.0
    while time.monotonic() < deadline:
        try:
            if not page_contains_any_text(page, snippets):
                return True
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page("wait_for_text_to_disappear:presence_check")
                continue
            raise
        try:
            page.wait_for_timeout(350)
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page("wait_for_text_to_disappear:sleep")
                continue
            raise
    try:
        return not page_contains_any_text(page, snippets)
    except Exception as exc:  # pylint: disable=broad-except
        if recover_page and is_page_or_context_closed_error(exc):
            page = recover_page("wait_for_text_to_disappear:final_check")
            return not page_contains_any_text(page, snippets)
        raise


def wait_for_any_selector(
    page: Any,
    selectors: list[str],
    timeout_ms: int,
    state: str,
    field_name: str,
    recover_page: Callable[[str], Any] | None = None,
    abort_check: Callable[[Any], str] | None = None,
) -> str:
    """Wait until any selector matches in the given state. Returns the matched selector."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no selectors configured")

    state = (state or "visible").strip().lower()
    if state not in {"visible", "attached"}:
        raise WindshieldError(f"{field_name}: unsupported wait state {state!r}")

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_attempts: list[str] = []
    while time.monotonic() < deadline:
        if abort_check is not None:
            try:
                abort_reason = str(abort_check(page) or "").strip()
            except Exception:  # pylint: disable=broad-except
                abort_reason = ""
            if abort_reason:
                raise WindshieldError(f"{field_name}: abort_wait: {abort_reason}")
        attempts: list[str] = []
        for selector in selectors:
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception as exc:  # pylint: disable=broad-except
                attempts.append(f"{selector} (locator error: {type(exc).__name__})")
                continue
            if count == 0:
                attempts.append(f"{selector} (0 matches)")
                continue

            if state == "attached":
                return selector

            for idx in range(count):
                item = locator.nth(idx)
                try:
                    if item.is_visible():
                        return selector
                except Exception:  # pylint: disable=broad-except
                    continue

            attempts.append(f"{selector} ({count} matches, none visible)")

        last_attempts = attempts
        try:
            page.wait_for_timeout(200)
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page(f"{field_name}:wait_for_any_selector")
                continue
            raise WindshieldError(
                f"{field_name}: page closed while waiting for selector ({state})"
            ) from exc
        if abort_check is not None:
            try:
                abort_reason = str(abort_check(page) or "").strip()
            except Exception:  # pylint: disable=broad-except
                abort_reason = ""
            if abort_reason:
                raise WindshieldError(f"{field_name}: abort_wait: {abort_reason}")

    raise WindshieldError(
        f"{field_name}: timeout waiting for selector ({state}); tried: {', '.join(last_attempts)}"
    )


def wait_for_any_selector_in_contexts(
    page: Any,
    selectors: list[str],
    timeout_ms: int,
    state: str,
    field_name: str,
    recover_page: Callable[[str], Any] | None = None,
) -> tuple[Any, str, str]:
    """Wait for any selector in any context. Returns (context, selector, context_name)."""
    if not selectors:
        raise WindshieldError(f"{field_name}: no selectors configured")

    state = (state or "visible").strip().lower()
    if state not in {"visible", "attached"}:
        raise WindshieldError(f"{field_name}: unsupported wait state {state!r}")

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_attempts: list[str] = []
    while time.monotonic() < deadline:
        attempts: list[str] = []
        for context_name, context in iter_locator_contexts(page):
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    count = locator.count()
                except Exception as exc:  # pylint: disable=broad-except
                    attempts.append(
                        f"{context_name}:{selector} (locator error: {type(exc).__name__})"
                    )
                    continue
                if count == 0:
                    attempts.append(f"{context_name}:{selector} (0 matches)")
                    continue

                if state == "attached":
                    return context, selector, context_name

                for idx in range(count):
                    item = locator.nth(idx)
                    try:
                        if item.is_visible():
                            return context, selector, context_name
                    except Exception:  # pylint: disable=broad-except
                        continue

                attempts.append(f"{context_name}:{selector} ({count} matches, none visible)")

        last_attempts = attempts
        try:
            page.wait_for_timeout(200)
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page(f"{field_name}:wait_for_any_selector_in_contexts")
                continue
            raise WindshieldError(
                f"{field_name}: page closed while waiting for selector ({state})"
            ) from exc

    raise WindshieldError(
        f"{field_name}: timeout waiting for selector ({state}); tried: {', '.join(last_attempts)}"
    )


def wait_for_url_contains(
    page: Any,
    fragments: list[str],
    timeout_ms: int,
    field_name: str,
    recover_page: Callable[[str], Any] | None = None,
    abort_check: Callable[[Any], str] | None = None,
) -> str:
    """Wait until the page URL contains any of the given fragments."""
    if not fragments:
        raise WindshieldError(f"{field_name}: no URL fragments configured")

    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        if abort_check is not None:
            try:
                abort_reason = str(abort_check(page) or "").strip()
            except Exception:  # pylint: disable=broad-except
                abort_reason = ""
            if abort_reason:
                raise WindshieldError(f"{field_name}: abort_wait: {abort_reason}")
        current_url = str(getattr(page, "url", "") or "")
        for fragment in fragments:
            if fragment in current_url:
                return fragment
        try:
            page.wait_for_timeout(200)
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page(f"{field_name}:wait_for_url_contains")
                continue
            raise WindshieldError(f"{field_name}: page closed while waiting for URL") from exc
        if abort_check is not None:
            try:
                abort_reason = str(abort_check(page) or "").strip()
            except Exception:  # pylint: disable=broad-except
                abort_reason = ""
            if abort_reason:
                raise WindshieldError(f"{field_name}: abort_wait: {abort_reason}")

    current_url = str(getattr(page, "url", "") or "")
    raise WindshieldError(
        f"{field_name}: timeout waiting for URL fragment match; "
        f"url={current_url}; fragments={', '.join(fragments)}"
    )


def retry_browser_wait(
    *,
    wait_fn: Callable[[], str],
    field_name: str,
    retry_cycles: int,
    retry_pause_seconds: float,
    pause_fn: Callable[[int, str], None] | None = None,
    note_fn: Callable[[str], None] | None = None,
) -> str:
    """Retry a wait function with configurable cycles and pauses."""
    retry_cycles = max(0, int(retry_cycles))
    retry_pause_seconds = max(0.0, float(retry_pause_seconds))
    total_attempts = retry_cycles + 1
    for attempt_idx in range(total_attempts):
        try:
            return wait_fn()
        except WindshieldError as exc:
            if "abort_wait:" in str(exc):
                raise
            if attempt_idx >= retry_cycles:
                raise
            if note_fn is not None:
                note_fn(
                    f"{field_name}_retry_scheduled attempt={attempt_idx + 2}/{total_attempts}; "
                    f"pause_seconds={retry_pause_seconds:.1f}; error={exc}"
                )
            if pause_fn is not None and retry_pause_seconds > 0.0:
                pause_fn(
                    int(retry_pause_seconds * 1000),
                    f"{field_name}:retry_pause_{attempt_idx + 1}",
                )
    raise WindshieldError(f"{field_name}: retry exhaustion")
