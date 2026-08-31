"""Tests for the Playwright async adapter using mock objects."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from windshield.adapters import AsyncLocatorAdapter, AsyncPageAdapter, create_async_playwright_page
from windshield.adapters._playwright import (
    AsyncPlaywrightLocatorAdapter,
    AsyncPlaywrightPageAdapter,
)


def test_wraps_an_existing_async_page() -> None:
    page = MagicMock()
    type(page).url = PropertyMock(return_value="https://example.com")
    type(page).main_frame = PropertyMock(return_value="main-frame")
    type(page).context = PropertyMock(return_value="context")
    page.frames = ["main-frame", "child-frame"]
    page.title = AsyncMock(return_value="Example")
    page.content = AsyncMock(return_value="<html></html>")
    page.evaluate = AsyncMock(return_value=42)
    page.goto = AsyncMock(return_value="response")
    page.wait_for_timeout = AsyncMock()
    page.wait_for_url = AsyncMock()
    page.bring_to_front = AsyncMock()
    page.screenshot = AsyncMock(return_value=b"png")
    page.close = AsyncMock()

    locator = MagicMock()
    locator.count = AsyncMock(return_value=2)
    locator.is_visible = AsyncMock(return_value=True)
    locator.is_enabled = AsyncMock(return_value=True)
    locator.inner_text = AsyncMock(return_value="hello")
    locator.text_content = AsyncMock(return_value="hello")
    locator.input_value = AsyncMock(return_value="value")
    locator.get_attribute = AsyncMock(return_value="attribute")
    locator.fill = AsyncMock()
    locator.type = AsyncMock()
    locator.click = AsyncMock()
    locator.press = AsyncMock()
    locator.evaluate = AsyncMock(return_value="locator-result")
    page.locator.return_value = locator

    async def exercise() -> None:
        adapter = await create_async_playwright_page(raw=page)
        assert isinstance(adapter, AsyncPageAdapter)
        assert adapter.url == "https://example.com"
        assert adapter.backend_name == "playwright"
        assert adapter.raw is page
        assert await adapter.title() == "Example"
        assert await adapter.content() == "<html></html>"
        assert await adapter.evaluate("1 + 1") == 42
        assert await adapter.goto("https://test.example", wait_until="load") == "response"
        await adapter.wait_for_timeout(10)
        await adapter.wait_for_url("**/ready", timeout=20)
        await adapter.bring_to_front()
        assert await adapter.screenshot(full_page=True) == b"png"
        assert adapter.frames() == ["main-frame", "child-frame"]
        assert adapter.main_frame == "main-frame"
        assert adapter.context == "context"

        selected = adapter.locator("input")
        assert isinstance(selected, AsyncPlaywrightLocatorAdapter)
        assert isinstance(selected, AsyncLocatorAdapter)
        assert await selected.count() == 2
        assert await selected.is_visible() is True
        assert await selected.is_enabled() is True
        assert await selected.inner_text(timeout=30) == "hello"
        assert await selected.text_content() == "hello"
        assert await selected.input_value() == "value"
        assert await selected.get_attribute("name") == "attribute"
        await selected.fill("text")
        await selected.type("text", delay=5)
        await selected.click(force=True, timeout=20)
        await selected.press("Enter")
        assert await selected.evaluate("el => el.value") == "locator-result"
        await adapter.close()

    asyncio.run(exercise())

    page.locator.assert_called_once_with("input")
    page.goto.assert_awaited_once_with("https://test.example", wait_until="load")
    page.wait_for_timeout.assert_awaited_once_with(10)
    page.wait_for_url.assert_awaited_once_with("**/ready", timeout=20)
    page.screenshot.assert_awaited_once_with(path=None, full_page=True)
    locator.inner_text.assert_awaited_once_with(timeout=30)
    locator.click.assert_awaited_once_with(force=True, timeout=20)
    page.close.assert_awaited_once()


def test_async_wrapper_classes_accept_raw_objects() -> None:
    assert isinstance(AsyncPlaywrightPageAdapter(MagicMock()), AsyncPageAdapter)
    assert isinstance(AsyncPlaywrightLocatorAdapter(MagicMock()), AsyncLocatorAdapter)
