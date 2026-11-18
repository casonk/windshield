"""Connect to a containerised Playwright server instead of launching a local browser.

A Playwright client only talks to a server of the *same* version, and a local
browser install drifting out of step with the client is a common source of
"Playwright issues". Running ``playwright run-server`` in a pinned container
(see ``deploy/container``) and connecting to it removes the local browser from
the equation.

The server is selected with ``WINDSHIELD_PLAYWRIGHT_WS`` (or an explicit
``ws_endpoint``). The endpoint must be a loopback address unless
``WINDSHIELD_PLAYWRIGHT_ALLOW_REMOTE=1`` is set, because the server has no
authentication of its own and grants full browser control.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from windshield._errors import WindshieldError

ENDPOINT_ENV = "WINDSHIELD_PLAYWRIGHT_WS"
ALLOW_REMOTE_ENV = "WINDSHIELD_PLAYWRIGHT_ALLOW_REMOTE"
STRICT_ENV = "WINDSHIELD_PLAYWRIGHT_STRICT"
DEFAULT_PORT = 3000
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _flag(env: Mapping[str, str], name: str) -> bool:
    return str(env.get(name, "")).strip().lower() in _TRUTHY


def resolve_endpoint(
    ws_endpoint: str | None = None, env: Mapping[str, str] | None = None
) -> str | None:
    """Return the Playwright server endpoint to use, or ``None`` for a local browser."""
    source = os.environ if env is None else env
    endpoint = (ws_endpoint or str(source.get(ENDPOINT_ENV, ""))).strip()
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname:
        raise WindshieldError(
            f"playwright_endpoint_invalid: expected ws://host:port, got {endpoint!r}"
        )
    if parsed.hostname not in _LOOPBACK_HOSTS and not _flag(source, ALLOW_REMOTE_ENV):
        raise WindshieldError(
            "playwright_endpoint_not_loopback: the Playwright server is unauthenticated; "
            f"set {ALLOW_REMOTE_ENV}=1 to use a non-loopback host"
        )
    return endpoint


def endpoint_reachable(endpoint: str, timeout_seconds: float = 1.5) -> bool:
    """Return True when something accepts TCP connections at *endpoint*."""
    parsed = urlparse(endpoint)
    port = parsed.port or (443 if parsed.scheme == "wss" else DEFAULT_PORT)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def explain_connect_error(exc: BaseException, endpoint: str) -> WindshieldError:
    """Turn a Playwright connect failure into an actionable error."""
    text = str(exc)
    lowered = text.lower()
    if "version" in lowered and ("playwright" in lowered or "mismatch" in lowered):
        hint = (
            "client and server Playwright versions differ; rebuild the container with "
            "scripts/playwright_container.sh build so it matches the installed client"
        )
    else:
        hint = "is the container running? see scripts/playwright_container.sh status"
    first_line = text.strip().splitlines()[0] if text.strip() else type(exc).__name__
    return WindshieldError(f"playwright_connect_failed: endpoint={endpoint}; {hint}; {first_line}")


def _decide(ws_endpoint: str | None, env: Mapping[str, str] | None) -> tuple[str | None, bool]:
    source = os.environ if env is None else env
    endpoint = resolve_endpoint(ws_endpoint, source)
    if endpoint is None:
        return None, False
    if endpoint_reachable(endpoint):
        return endpoint, True
    if _flag(source, STRICT_ENV):
        raise WindshieldError(
            f"playwright_server_unreachable: endpoint={endpoint}; "
            "start it with scripts/playwright_container.sh start"
        )
    return None, False


def launch_or_connect(
    playwright: Any,
    *,
    headless: bool = False,
    ws_endpoint: str | None = None,
    env: Mapping[str, str] | None = None,
    **launch_kwargs: Any,
) -> Any:
    """Return a sync Chromium ``Browser``, from the container when one is configured.

    Falls back to a local launch (with a warning) when the configured server is
    unreachable, unless ``WINDSHIELD_PLAYWRIGHT_STRICT=1``.
    """
    endpoint, use_remote = _decide(ws_endpoint, env)
    if use_remote and endpoint:
        try:
            return playwright.chromium.connect(endpoint)
        except Exception as exc:  # pylint: disable=broad-except
            raise explain_connect_error(exc, endpoint) from exc
    if endpoint is None and (ws_endpoint or (env or os.environ).get(ENDPOINT_ENV)):
        import warnings

        warnings.warn(
            "Playwright server unreachable; falling back to a local browser", stacklevel=2
        )
    return playwright.chromium.launch(headless=headless, **launch_kwargs)


async def async_launch_or_connect(
    playwright: Any,
    *,
    headless: bool = False,
    ws_endpoint: str | None = None,
    env: Mapping[str, str] | None = None,
    **launch_kwargs: Any,
) -> Any:
    """Async counterpart of :func:`launch_or_connect`."""
    endpoint, use_remote = _decide(ws_endpoint, env)
    if use_remote and endpoint:
        try:
            return await playwright.chromium.connect(endpoint)
        except Exception as exc:  # pylint: disable=broad-except
            raise explain_connect_error(exc, endpoint) from exc
    if endpoint is None and (ws_endpoint or (env or os.environ).get(ENDPOINT_ENV)):
        import warnings

        warnings.warn(
            "Playwright server unreachable; falling back to a local browser", stacklevel=2
        )
    return await playwright.chromium.launch(headless=headless, **launch_kwargs)
