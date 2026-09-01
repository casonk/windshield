"""Tests for explicit cross-backend cookie-state exchange."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from windshield import WindshieldError, export_session_state, import_session_state


def test_playwright_state_round_trip_uses_context() -> None:
    context = MagicMock()
    context.cookies.return_value = [
        {"name": "session", "value": "secret", "domain": "example.test", "path": "/"}
    ]
    page = SimpleNamespace(backend_name="playwright", raw=SimpleNamespace(context=context))

    state = export_session_state(page)
    imported = import_session_state(page, state)

    assert state == {
        "version": 1,
        "cookies": [{"name": "session", "value": "secret", "domain": "example.test", "path": "/"}],
    }
    assert imported == 1
    context.add_cookies.assert_called_once_with(state["cookies"])


def test_selenium_import_drops_playwright_only_cookie_fields() -> None:
    driver = MagicMock()
    page = SimpleNamespace(backend_name="selenium", raw=driver)

    imported = import_session_state(
        page,
        {
            "version": 1,
            "cookies": [
                {
                    "name": "session",
                    "value": "secret",
                    "domain": "example.test",
                    "path": "/",
                    "partitionKey": "https://example.test",
                }
            ],
        },
    )

    assert imported == 1
    driver.add_cookie.assert_called_once_with(
        {"name": "session", "value": "secret", "domain": "example.test", "path": "/"}
    )


def test_http_export_and_import_preserve_cookie_scope() -> None:
    source_session = MagicMock()
    source_session.cookies = [
        SimpleNamespace(
            name="session", value="secret", domain="example.test", path="/", secure=True, expires=12
        )
    ]
    source = SimpleNamespace(backend_name="http", raw=source_session)
    target_session = MagicMock()
    target = SimpleNamespace(backend_name="http", raw=target_session)

    state = export_session_state(source)
    imported = import_session_state(target, state)

    assert imported == 1
    target_session.cookies.set.assert_called_once_with(
        "session", "secret", domain="example.test", path="/"
    )


@pytest.mark.parametrize(
    "state",
    [{}, {"version": 2, "cookies": []}, {"version": 1, "cookies": [{"name": "missing-value"}]}],
)
def test_rejects_invalid_state(state: dict[str, object]) -> None:
    page = SimpleNamespace(backend_name="http", raw=MagicMock())

    with pytest.raises(WindshieldError, match="session"):
        import_session_state(page, state)
