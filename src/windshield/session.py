"""Explicit, in-memory cookie-state exchange across supported backends."""

from __future__ import annotations

import json
from typing import Any

from windshield._errors import WindshieldError


def export_session_state(page: Any) -> dict[str, Any]:
    """Return a JSON-serializable cookie snapshot for an adapter or raw page.

    The function performs no file I/O. Cookies are bearer credentials, so the
    caller must choose an appropriate secure store before persisting the
    returned mapping.
    """
    backend = _backend_name(page)
    raw = getattr(page, "raw", page)
    if backend == "playwright":
        context = getattr(raw, "context", None)
        cookies = context.cookies() if context is not None else []
    elif backend in {"selenium", "undetected"}:
        cookies = raw.get_cookies()
    elif backend == "http":
        cookies = [_http_cookie_to_dict(cookie) for cookie in raw.cookies]
    else:
        raise WindshieldError(f"unsupported_session_backend: {backend}")
    return {"version": 1, "cookies": _json_cookie_list(cookies)}


def import_session_state(page: Any, state: dict[str, Any]) -> int:
    """Import a cookie snapshot and return the number of cookies applied.

    Selenium can add cookies only for the current browser domain; callers must
    navigate to each target domain before importing multi-domain state.
    """
    cookies = _state_cookies(state)
    backend = _backend_name(page)
    raw = getattr(page, "raw", page)
    if backend == "playwright":
        context = getattr(raw, "context", None)
        if context is None:
            raise WindshieldError("playwright_session_context_missing")
        context.add_cookies(cookies)
    elif backend in {"selenium", "undetected"}:
        for cookie in cookies:
            raw.add_cookie(_selenium_cookie(cookie))
    elif backend == "http":
        for cookie in cookies:
            kwargs = {
                key: value
                for key, value in (("domain", cookie.get("domain")), ("path", cookie.get("path")))
                if value
            }
            raw.cookies.set(str(cookie["name"]), str(cookie["value"]), **kwargs)
    else:
        raise WindshieldError(f"unsupported_session_backend: {backend}")
    return len(cookies)


def _backend_name(page: Any) -> str:
    backend = str(getattr(page, "backend_name", "") or "").lower()
    if not backend:
        raise WindshieldError("session_backend_missing")
    return backend


def _json_cookie_list(cookies: Any) -> list[dict[str, Any]]:
    if not isinstance(cookies, list):
        raise WindshieldError("session_cookies_invalid")
    normalized: list[dict[str, Any]] = []
    for cookie in cookies:
        if not isinstance(cookie, dict) or not cookie.get("name"):
            raise WindshieldError("session_cookie_invalid")
        normalized.append(json.loads(json.dumps(cookie, ensure_ascii=True)))
    return normalized


def _state_cookies(state: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(state, dict) or state.get("version") != 1:
        raise WindshieldError("session_state_invalid")
    cookies = _json_cookie_list(state.get("cookies"))
    for cookie in cookies:
        if "value" not in cookie:
            raise WindshieldError("session_cookie_value_missing")
    return cookies


def _selenium_cookie(cookie: dict[str, Any]) -> dict[str, Any]:
    """Drop Playwright-only cookie fields before handing one to Selenium."""
    return {
        key: value
        for key, value in cookie.items()
        if key in {"name", "value", "path", "domain", "secure", "httpOnly", "expiry", "sameSite"}
    }


def _http_cookie_to_dict(cookie: Any) -> dict[str, Any]:
    return {
        "name": str(cookie.name),
        "value": str(cookie.value),
        "domain": str(getattr(cookie, "domain", "") or ""),
        "path": str(getattr(cookie, "path", "") or ""),
        "secure": bool(getattr(cookie, "secure", False)),
        "expiry": getattr(cookie, "expires", None),
    }
