"""HTTP opener, URL matching, browser location description, and error redaction."""

from __future__ import annotations

import re
import ssl
import urllib.request
from typing import Any


def build_http_opener(verify_tls: bool) -> urllib.request.OpenerDirector:
    """Build a urllib opener with optional TLS verification bypass."""
    if verify_tls:
        return urllib.request.build_opener()

    insecure_context = ssl.create_default_context()
    insecure_context.check_hostname = False
    insecure_context.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=insecure_context))


def url_contains_any_fragment(url: str, fragments: list[str]) -> bool:
    """Return True if the URL contains any of the given fragments (case-insensitive)."""
    value = str(url or "").strip().lower()
    if not value:
        return False
    for fragment in fragments:
        needle = str(fragment or "").strip().lower()
        if needle and needle in value:
            return True
    return False


def match_browser_route(url: str, route_fragments: dict[str, list[str]] | None = None) -> str:
    """Match a URL against named route fragment sets. Returns the route name or empty."""
    if not isinstance(route_fragments, dict):
        return ""
    for route_name, fragments in route_fragments.items():
        if not isinstance(fragments, list):
            continue
        if url_contains_any_fragment(url, fragments):
            return str(route_name).strip()
    return ""


def describe_browser_location(
    page: Any, route_fragments: dict[str, list[str]] | None = None
) -> str:
    """Summarize the current page URL, title, and matched route."""

    def compact(value: Any, max_len: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > max_len:
            return text[: max_len - 3] + "..."
        return text

    current_url = str(getattr(page, "url", "") or "").strip()
    try:
        title = str(page.title() or "").strip()
    except Exception:  # pylint: disable=broad-except
        title = ""
    route_name = match_browser_route(current_url, route_fragments)
    parts: list[str] = []
    if current_url:
        parts.append(f"url={compact(current_url, 220)}")
    if title:
        parts.append(f"title={compact(title, 120)}")
    if route_name:
        parts.append(f"route={route_name}")
    return "; ".join(parts)


def sanitize_error_text(text: str, secrets: list[str]) -> str:
    """Redact known secrets from error text."""
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "***REDACTED***")
    return redacted


def sanitize_manual_guidance_text(text: Any, max_len: int = 180) -> str:
    """Collapse whitespace, redact long digit sequences, and truncate."""
    value = " ".join(str(text or "").split())
    if not value:
        return ""
    value = re.sub(r"\b\d{4,}\b", "[redacted-digits]", value)
    if len(value) > max_len:
        value = value[: max_len - 3] + "..."
    return value
