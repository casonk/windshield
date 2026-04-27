"""Cloudflare/CAPTCHA challenge page detection and wait-to-clear."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

from windshield.page import (
    first_visible_selector_match,
    is_page_or_context_closed_error,
    page_contains_any_text,
    read_page_text,
    title_contains_any_text,
)


def is_challenge_page(page: Any, snippets: list[str]) -> bool:
    """Detect whether the current page is a Cloudflare or CAPTCHA challenge."""
    if page_contains_any_text(page, snippets):
        return True
    if title_contains_any_text(page, snippets):
        return True

    try:
        content = str(page.content() or "").lower()
    except Exception:  # pylint: disable=broad-except
        content = ""
    if "/cfi/preauthcontent/" in content:
        return True

    url = str(getattr(page, "url", "") or "").lower()
    if "cf_chl" in url or "__cf_chl" in url:
        return True
    if "cloudflare" in url and "challenge" in url:
        return True
    try:
        for frame in page.frames:
            frame_url = str(getattr(frame, "url", "") or "").lower()
            if "challenges.cloudflare.com" in frame_url:
                return True
            if "/cdn-cgi/challenge-platform/" in frame_url:
                return True
    except Exception:  # pylint: disable=broad-except
        pass

    strong_visible_selectors = [
        "#challenge-stage",
        ".cf-browser-verification",
        ".main-wrapper:has-text('Just a moment')",
        "body:has-text('Just a moment')",
    ]
    for selector in strong_visible_selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:  # pylint: disable=broad-except
            continue
        for idx in range(min(count, 8)):
            try:
                if locator.nth(idx).is_visible():
                    return True
            except Exception:  # pylint: disable=broad-except
                continue

    strong_presence_selectors = [
        "div.isotope-challenge-type--tethered",
        "[data-cy='tetheredError']",
        "iframe[src*='challenges.cloudflare.com']",
        "input[name='cf-turnstile-response']",
    ]
    for selector in strong_presence_selectors:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:  # pylint: disable=broad-except
            continue

    weak_presence_selectors = [
        "script[src*='turnstile']",
        "form#form_authenticated",
    ]
    if "cf_chl" in url or "__cf_chl" in url or ("cloudflare" in url and "challenge" in url):
        for selector in weak_presence_selectors:
            try:
                if page.locator(selector).count() > 0:
                    return True
            except Exception:  # pylint: disable=broad-except
                continue
    return False


def wait_for_challenge_to_clear(
    page: Any,
    snippets: list[str],
    timeout_ms: int,
    recover_page: Callable[[str], Any] | None = None,
    fast_fail_text_snippets: list[str] | None = None,
    fast_fail_selectors: list[str] | None = None,
) -> bool:
    """Wait for a challenge page to clear. Returns True if cleared, False on fast-fail."""
    fast_fail_text_snippets = [
        str(item).strip() for item in (fast_fail_text_snippets or []) if str(item).strip()
    ]
    fast_fail_selectors = [
        str(item).strip() for item in (fast_fail_selectors or []) if str(item).strip()
    ]
    deadline = time.monotonic() + max(1000, timeout_ms) / 1000.0
    while time.monotonic() < deadline:
        try:
            if not is_challenge_page(page, snippets):
                return True
            if fast_fail_selectors and first_visible_selector_match(page, fast_fail_selectors):
                return False
            if fast_fail_text_snippets and page_contains_any_text(page, fast_fail_text_snippets):
                return False
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page("wait_for_challenge_to_clear:state_check")
                continue
            raise
        try:
            page.wait_for_timeout(350)
        except Exception as exc:  # pylint: disable=broad-except
            if recover_page and is_page_or_context_closed_error(exc):
                page = recover_page("wait_for_challenge_to_clear:sleep")
                continue
            raise
    try:
        if fast_fail_selectors and first_visible_selector_match(page, fast_fail_selectors):
            return False
        if fast_fail_text_snippets and page_contains_any_text(page, fast_fail_text_snippets):
            return False
        return not is_challenge_page(page, snippets)
    except Exception as exc:  # pylint: disable=broad-except
        if recover_page and is_page_or_context_closed_error(exc):
            page = recover_page("wait_for_challenge_to_clear:final_check")
            if fast_fail_text_snippets and page_contains_any_text(page, fast_fail_text_snippets):
                return False
            return not is_challenge_page(page, snippets)
        raise


def extract_reference_code_from_text(text: str) -> str:
    """Extract a numeric reference code from error/challenge text."""
    haystack = str(text or "")
    if not haystack:
        return ""
    match = re.search(r"reference\s*code\s*[:#-]?\s*(\d{4,12})", haystack, re.I)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def extract_reference_code_from_page(page: Any) -> str:
    """Extract a numeric reference code from the current page text."""
    text = read_page_text(page)
    return extract_reference_code_from_text(text)
