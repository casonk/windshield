"""Tests for the Playwright adapter using mock objects."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

from windshield.adapters._playwright import PlaywrightLocatorAdapter, PlaywrightPageAdapter

# ---------------------------------------------------------------------------
# PlaywrightLocatorAdapter
# ---------------------------------------------------------------------------


class TestLocatorAdapter:
    def test_count(self) -> None:
        loc = MagicMock()
        loc.count.return_value = 5
        adapter = PlaywrightLocatorAdapter(loc)
        assert adapter.count() == 5
        loc.count.assert_called_once()

    def test_nth_returns_adapter(self) -> None:
        loc = MagicMock()
        adapter = PlaywrightLocatorAdapter(loc)
        result = adapter.nth(2)
        assert isinstance(result, PlaywrightLocatorAdapter)
        loc.nth.assert_called_once_with(2)

    def test_is_visible(self) -> None:
        loc = MagicMock()
        loc.is_visible.return_value = True
        assert PlaywrightLocatorAdapter(loc).is_visible() is True

    def test_is_enabled(self) -> None:
        loc = MagicMock()
        loc.is_enabled.return_value = False
        assert PlaywrightLocatorAdapter(loc).is_enabled() is False

    def test_inner_text(self) -> None:
        loc = MagicMock()
        loc.inner_text.return_value = "hello"
        assert PlaywrightLocatorAdapter(loc).inner_text() == "hello"
        loc.inner_text.assert_called_once_with()

    def test_inner_text_with_timeout(self) -> None:
        loc = MagicMock()
        loc.inner_text.return_value = "hi"
        assert PlaywrightLocatorAdapter(loc).inner_text(timeout=3000) == "hi"
        loc.inner_text.assert_called_once_with(timeout=3000)

    def test_text_content(self) -> None:
        loc = MagicMock()
        loc.text_content.return_value = None
        assert PlaywrightLocatorAdapter(loc).text_content() is None

    def test_input_value(self) -> None:
        loc = MagicMock()
        loc.input_value.return_value = "val"
        assert PlaywrightLocatorAdapter(loc).input_value() == "val"

    def test_get_attribute(self) -> None:
        loc = MagicMock()
        loc.get_attribute.return_value = "bar"
        assert PlaywrightLocatorAdapter(loc).get_attribute("foo") == "bar"
        loc.get_attribute.assert_called_once_with("foo")

    def test_fill(self) -> None:
        loc = MagicMock()
        PlaywrightLocatorAdapter(loc).fill("text")
        loc.fill.assert_called_once_with("text")

    def test_type(self) -> None:
        loc = MagicMock()
        PlaywrightLocatorAdapter(loc).type("abc", delay=50)
        loc.type.assert_called_once_with("abc", delay=50)

    def test_click(self) -> None:
        loc = MagicMock()
        PlaywrightLocatorAdapter(loc).click(force=True, timeout=1000)
        loc.click.assert_called_once_with(force=True, timeout=1000)

    def test_click_defaults(self) -> None:
        loc = MagicMock()
        PlaywrightLocatorAdapter(loc).click()
        loc.click.assert_called_once_with(force=False)

    def test_press(self) -> None:
        loc = MagicMock()
        PlaywrightLocatorAdapter(loc).press("Enter")
        loc.press.assert_called_once_with("Enter")

    def test_evaluate(self) -> None:
        loc = MagicMock()
        loc.evaluate.return_value = 42
        assert PlaywrightLocatorAdapter(loc).evaluate("el => el.id", "arg") == 42
        loc.evaluate.assert_called_once_with("el => el.id", "arg")


# ---------------------------------------------------------------------------
# PlaywrightPageAdapter
# ---------------------------------------------------------------------------


class TestPageAdapter:
    def _make_page(self, **overrides: object) -> MagicMock:
        page = MagicMock()
        type(page).url = PropertyMock(return_value="https://example.com")
        for k, v in overrides.items():
            setattr(page, k, v) if not isinstance(v, property) else None
        return page

    def test_url(self) -> None:
        adapter = PlaywrightPageAdapter(self._make_page())
        assert adapter.url == "https://example.com"

    def test_backend_name(self) -> None:
        assert PlaywrightPageAdapter(MagicMock()).backend_name == "playwright"

    def test_raw(self) -> None:
        page = MagicMock()
        assert PlaywrightPageAdapter(page).raw is page

    def test_title(self) -> None:
        page = MagicMock()
        page.title.return_value = "My Page"
        assert PlaywrightPageAdapter(page).title() == "My Page"

    def test_content(self) -> None:
        page = MagicMock()
        page.content.return_value = "<html></html>"
        assert PlaywrightPageAdapter(page).content() == "<html></html>"

    def test_locator_returns_adapter(self) -> None:
        page = MagicMock()
        adapter = PlaywrightPageAdapter(page)
        loc = adapter.locator("input#name")
        assert isinstance(loc, PlaywrightLocatorAdapter)
        page.locator.assert_called_once_with("input#name")

    def test_evaluate(self) -> None:
        page = MagicMock()
        page.evaluate.return_value = 99
        assert PlaywrightPageAdapter(page).evaluate("1+1", "x") == 99
        page.evaluate.assert_called_once_with("1+1", "x")

    def test_goto(self) -> None:
        page = MagicMock()
        PlaywrightPageAdapter(page).goto("https://test.com", wait_until="load")
        page.goto.assert_called_once_with("https://test.com", wait_until="load")

    def test_wait_for_timeout(self) -> None:
        page = MagicMock()
        PlaywrightPageAdapter(page).wait_for_timeout(500)
        page.wait_for_timeout.assert_called_once_with(500)

    def test_wait_for_url(self) -> None:
        page = MagicMock()
        PlaywrightPageAdapter(page).wait_for_url("**/done", timeout=3000)
        page.wait_for_url.assert_called_once_with("**/done", timeout=3000)

    def test_bring_to_front(self) -> None:
        page = MagicMock()
        PlaywrightPageAdapter(page).bring_to_front()
        page.bring_to_front.assert_called_once()

    def test_screenshot(self) -> None:
        page = MagicMock()
        page.screenshot.return_value = b"\x89PNG"
        result = PlaywrightPageAdapter(page).screenshot(full_page=True)
        assert result == b"\x89PNG"
        page.screenshot.assert_called_once_with(path=None, full_page=True)

    def test_frames(self) -> None:
        page = MagicMock()
        page.frames = ["f1", "f2"]
        assert PlaywrightPageAdapter(page).frames() == ["f1", "f2"]

    def test_main_frame(self) -> None:
        page = MagicMock()
        type(page).main_frame = PropertyMock(return_value="mf")
        assert PlaywrightPageAdapter(page).main_frame == "mf"

    def test_context(self) -> None:
        page = MagicMock()
        type(page).context = PropertyMock(return_value="ctx")
        assert PlaywrightPageAdapter(page).context == "ctx"

    def test_on(self) -> None:
        page = MagicMock()
        handler = lambda msg: None  # noqa: E731
        PlaywrightPageAdapter(page).on("console", handler)
        page.on.assert_called_once_with("console", handler)

    def test_close(self) -> None:
        page = MagicMock()
        PlaywrightPageAdapter(page).close()
        page.close.assert_called_once()

    def test_setattr_delegates_unknown(self) -> None:
        page = MagicMock()
        adapter = PlaywrightPageAdapter(page)
        adapter._windshield_runtime_debug_capture_installed = True
        # Should have been set on the underlying page mock
        assert page._windshield_runtime_debug_capture_installed is True

    def test_getattr_delegates_unknown(self) -> None:
        page = MagicMock()
        page.some_custom_attr = "custom"
        adapter = PlaywrightPageAdapter(page)
        assert adapter.some_custom_attr == "custom"

    def test_protocol_isinstance(self) -> None:
        """Adapter satisfies the runtime-checkable PageAdapter protocol."""
        from windshield.adapters._protocol import LocatorAdapter, PageAdapter

        page_adapter = PlaywrightPageAdapter(MagicMock())
        assert isinstance(page_adapter, PageAdapter)

        loc_adapter = PlaywrightLocatorAdapter(MagicMock())
        assert isinstance(loc_adapter, LocatorAdapter)
