"""Tests for the containerised Playwright server support."""

from __future__ import annotations

import socket
import warnings
from unittest.mock import MagicMock

import pytest

from windshield import remote
from windshield._errors import WindshieldError
from windshield.adapters._factory import create_page


def test_no_endpoint_means_local_launch() -> None:
    assert remote.resolve_endpoint(env={}) is None
    pw = MagicMock()
    remote.launch_or_connect(pw, headless=True, env={})
    pw.chromium.launch.assert_called_once_with(headless=True)
    pw.chromium.connect.assert_not_called()


@pytest.mark.parametrize("bad", ["http://127.0.0.1:3000", "127.0.0.1:3000", "ws://"])
def test_invalid_endpoint_is_rejected(bad: str) -> None:
    with pytest.raises(WindshieldError, match="endpoint_invalid"):
        remote.resolve_endpoint(bad, env={})


def test_non_loopback_requires_explicit_opt_in() -> None:
    with pytest.raises(WindshieldError, match="not_loopback"):
        remote.resolve_endpoint("ws://10.0.0.5:3000", env={})
    ok = remote.resolve_endpoint("ws://10.0.0.5:3000", env={remote.ALLOW_REMOTE_ENV: "1"})
    assert ok == "ws://10.0.0.5:3000"


@pytest.fixture
def listening_port():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    yield server.getsockname()[1]
    server.close()


def test_connects_when_server_is_reachable(listening_port: int) -> None:
    pw = MagicMock()
    endpoint = f"ws://127.0.0.1:{listening_port}/"
    browser = remote.launch_or_connect(pw, env={remote.ENDPOINT_ENV: endpoint})
    pw.chromium.connect.assert_called_once_with(endpoint)
    pw.chromium.launch.assert_not_called()
    assert browser is pw.chromium.connect.return_value


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_unreachable_server_falls_back_with_warning() -> None:
    pw = MagicMock()
    env = {remote.ENDPOINT_ENV: f"ws://127.0.0.1:{_closed_port()}/"}
    with pytest.warns(UserWarning, match="falling back"):
        remote.launch_or_connect(pw, headless=True, env=env)
    pw.chromium.launch.assert_called_once_with(headless=True)


def test_strict_mode_refuses_to_fall_back() -> None:
    pw = MagicMock()
    env = {
        remote.ENDPOINT_ENV: f"ws://127.0.0.1:{_closed_port()}/",
        remote.STRICT_ENV: "1",
    }
    with pytest.raises(WindshieldError, match="server_unreachable"):
        remote.launch_or_connect(pw, env=env)
    pw.chromium.launch.assert_not_called()


def test_version_mismatch_gets_an_actionable_message(listening_port: int) -> None:
    pw = MagicMock()
    pw.chromium.connect.side_effect = RuntimeError(
        "Playwright version mismatch: server 1.50.0, client 1.58.0\nstack..."
    )
    env = {remote.ENDPOINT_ENV: f"ws://127.0.0.1:{listening_port}/"}
    with pytest.raises(WindshieldError, match="versions differ") as info:
        remote.launch_or_connect(pw, env=env)
    assert "1.50.0" in str(info.value)
    assert "stack" not in str(info.value)


def test_other_connect_errors_point_at_the_container(listening_port: int) -> None:
    pw = MagicMock()
    pw.chromium.connect.side_effect = RuntimeError("boom")
    env = {remote.ENDPOINT_ENV: f"ws://127.0.0.1:{listening_port}/"}
    with pytest.raises(WindshieldError, match="container running"):
        remote.launch_or_connect(pw, env=env)


def test_async_connect_and_fallback(listening_port: int) -> None:
    import asyncio
    from unittest.mock import AsyncMock

    pw = MagicMock()
    pw.chromium.connect = AsyncMock(return_value="remote")
    pw.chromium.launch = AsyncMock(return_value="local")
    env = {remote.ENDPOINT_ENV: f"ws://127.0.0.1:{listening_port}/"}
    assert asyncio.run(remote.async_launch_or_connect(pw, env=env)) == "remote"
    assert asyncio.run(remote.async_launch_or_connect(pw, env={})) == "local"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        env = {remote.ENDPOINT_ENV: f"ws://127.0.0.1:{_closed_port()}/"}
        assert asyncio.run(remote.async_launch_or_connect(pw, env=env)) == "local"


def test_factory_uses_remote_browser_when_configured(
    monkeypatch: pytest.MonkeyPatch, listening_port: int
) -> None:
    pw = MagicMock()
    fake_api = MagicMock()
    fake_api.sync_playwright.return_value.start.return_value = pw
    monkeypatch.setitem(__import__("sys").modules, "playwright.sync_api", fake_api)
    monkeypatch.setenv(remote.ENDPOINT_ENV, f"ws://127.0.0.1:{listening_port}/")
    adapter = create_page("playwright", headless=True)
    pw.chromium.connect.assert_called_once()
    pw.chromium.launch.assert_not_called()
    assert adapter.backend_name == "playwright"
