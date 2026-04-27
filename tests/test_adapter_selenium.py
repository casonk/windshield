"""Mock-based tests for the Selenium WebDriver adapter.

No real browser or selenium installation is required — all Selenium types
are replaced with ``unittest.mock`` fakes.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap fake ``selenium`` package so the adapter can import from it
# without an actual installation.
# ---------------------------------------------------------------------------

_by_mod = types.ModuleType("selenium.webdriver.common.by")
_by_mod.By = type("By", (), {"CSS_SELECTOR": "css selector", "TAG_NAME": "tag name"})  # type: ignore[assignment]

_keys_mod = types.ModuleType("selenium.webdriver.common.keys")
_keys_mod.Keys = type(  # type: ignore[assignment]
    "Keys",
    (),
    {
        "ENTER": "\ue007",
        "TAB": "\ue004",
        "ESCAPE": "\ue00c",
        "BACKSPACE": "\ue003",
        "DELETE": "\ue017",
        "ARROW_UP": "\ue013",
        "ARROW_DOWN": "\ue015",
        "ARROW_LEFT": "\ue012",
        "ARROW_RIGHT": "\ue014",
    },
)

_exc_mod = types.ModuleType("selenium.common.exceptions")


class _StaleElementReferenceException(Exception):
    pass


_exc_mod.StaleElementReferenceException = _StaleElementReferenceException  # type: ignore[attr-defined]

_wait_mod = types.ModuleType("selenium.webdriver.support.ui")


class _FakeWebDriverWait:
    def __init__(self, driver: object, timeout: float) -> None:
        self._driver = driver
        self._timeout = timeout

    def until(self, cond):  # noqa: ANN001,ANN201
        return cond(self._driver)


_wait_mod.WebDriverWait = _FakeWebDriverWait  # type: ignore[attr-defined]

# Wire the fake modules into sys.modules before importing the adapter.
_selenium_pkg = types.ModuleType("selenium")
_selenium_common = types.ModuleType("selenium.common")
_selenium_webdriver = types.ModuleType("selenium.webdriver")
_selenium_webdriver_common = types.ModuleType("selenium.webdriver.common")
_selenium_webdriver_support = types.ModuleType("selenium.webdriver.support")

sys.modules.update(
    {
        "selenium": _selenium_pkg,
        "selenium.common": _selenium_common,
        "selenium.common.exceptions": _exc_mod,
        "selenium.webdriver": _selenium_webdriver,
        "selenium.webdriver.common": _selenium_webdriver_common,
        "selenium.webdriver.common.by": _by_mod,
        "selenium.webdriver.common.keys": _keys_mod,
        "selenium.webdriver.support": _selenium_webdriver_support,
        "selenium.webdriver.support.ui": _wait_mod,
    }
)

from windshield.adapters._selenium import (  # noqa: E402
    SeleniumLocatorAdapter,
    SeleniumPageAdapter,
    _SeleniumNthLocatorAdapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_driver(**overrides: object) -> MagicMock:
    driver = MagicMock()
    driver.current_url = overrides.get("current_url", "https://example.com")
    driver.title = overrides.get("title", "Example")
    driver.page_source = overrides.get("page_source", "<html></html>")
    driver.current_window_handle = "main"
    return driver


def _make_element(**overrides: object) -> MagicMock:
    el = MagicMock()
    el.text = overrides.get("text", "hello")
    el.is_displayed.return_value = overrides.get("visible", True)
    el.is_enabled.return_value = overrides.get("enabled", True)
    el.get_attribute.side_effect = lambda name: {
        "value": overrides.get("value", "val"),
        "textContent": overrides.get("textContent", "hello"),
    }.get(name)
    return el


# ===========================================================================
# SeleniumPageAdapter tests
# ===========================================================================


class TestSeleniumPageAdapter:
    def test_url(self) -> None:
        driver = _make_driver(current_url="https://test.dev/page")
        page = SeleniumPageAdapter(driver)
        assert page.url == "https://test.dev/page"

    def test_backend_name(self) -> None:
        page = SeleniumPageAdapter(_make_driver())
        assert page.backend_name == "selenium"

    def test_title(self) -> None:
        driver = _make_driver(title="My Title")
        page = SeleniumPageAdapter(driver)
        assert page.title() == "My Title"

    def test_content(self) -> None:
        driver = _make_driver(page_source="<body>hi</body>")
        page = SeleniumPageAdapter(driver)
        assert page.content() == "<body>hi</body>"

    def test_raw(self) -> None:
        driver = _make_driver()
        page = SeleniumPageAdapter(driver)
        assert page.raw is driver

    def test_evaluate_no_arg(self) -> None:
        driver = _make_driver()
        driver.execute_script.return_value = 42
        page = SeleniumPageAdapter(driver)
        result = page.evaluate("1 + 1")
        driver.execute_script.assert_called_once_with("return 1 + 1")
        assert result == 42

    def test_evaluate_with_arg(self) -> None:
        driver = _make_driver()
        driver.execute_script.return_value = "ok"
        page = SeleniumPageAdapter(driver)
        page.evaluate("document.title", "arg1")
        driver.execute_script.assert_called_once_with("return document.title", "arg1")

    def test_goto(self) -> None:
        driver = _make_driver()
        page = SeleniumPageAdapter(driver)
        page.goto("https://new.url")
        driver.get.assert_called_once_with("https://new.url")

    def test_screenshot_returns_bytes(self) -> None:
        driver = _make_driver()
        driver.get_screenshot_as_png.return_value = b"\x89PNG"
        page = SeleniumPageAdapter(driver)
        result = page.screenshot()
        assert result == b"\x89PNG"

    def test_screenshot_writes_file(self, tmp_path) -> None:  # noqa: ANN001
        driver = _make_driver()
        driver.get_screenshot_as_png.return_value = b"\x89PNG"
        page = SeleniumPageAdapter(driver)
        dest = str(tmp_path / "shots" / "img.png")
        page.screenshot(path=dest)
        from pathlib import Path

        assert Path(dest).read_bytes() == b"\x89PNG"

    def test_bring_to_front(self) -> None:
        driver = _make_driver()
        page = SeleniumPageAdapter(driver)
        page.bring_to_front()
        driver.switch_to.window.assert_called_once_with("main")

    def test_close(self) -> None:
        driver = _make_driver()
        page = SeleniumPageAdapter(driver)
        page.close()
        driver.close.assert_called_once()

    def test_locator_returns_adapter(self) -> None:
        driver = _make_driver()
        page = SeleniumPageAdapter(driver)
        loc = page.locator("div.cls")
        assert isinstance(loc, SeleniumLocatorAdapter)

    def test_on_stores_handler(self) -> None:
        page = SeleniumPageAdapter(_make_driver())
        handler = MagicMock()
        page.on("console", handler)
        assert handler in page._event_handlers["console"]

    def test_context_is_driver(self) -> None:
        driver = _make_driver()
        page = SeleniumPageAdapter(driver)
        assert page.context is driver

    def test_main_frame_is_self(self) -> None:
        page = SeleniumPageAdapter(_make_driver())
        assert page.main_frame is page

    def test_frames_returns_list(self) -> None:
        driver = _make_driver()
        iframe_el = MagicMock()
        driver.find_elements.return_value = [iframe_el]
        page = SeleniumPageAdapter(driver)
        result = page.frames()
        assert len(result) == 1

    def test_wait_for_url_string(self) -> None:
        driver = _make_driver(current_url="https://example.com/done")
        page = SeleniumPageAdapter(driver)
        page.wait_for_url("done", timeout=5000)

    def test_wait_for_url_predicate(self) -> None:
        driver = _make_driver(current_url="https://example.com/done")
        page = SeleniumPageAdapter(driver)
        page.wait_for_url(lambda u: "done" in u, timeout=5000)

    def test_getattr_delegates(self) -> None:
        driver = _make_driver()
        driver.some_custom_attr = "custom"
        page = SeleniumPageAdapter(driver)
        assert page.some_custom_attr == "custom"


# ===========================================================================
# SeleniumLocatorAdapter tests
# ===========================================================================


class TestSeleniumLocatorAdapter:
    def test_count(self) -> None:
        driver = _make_driver()
        els = [_make_element(), _make_element(), _make_element()]
        driver.find_elements.return_value = els
        loc = SeleniumLocatorAdapter(driver, "li")
        assert loc.count() == 3

    def test_is_visible(self) -> None:
        driver = _make_driver()
        el = _make_element(visible=True)
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "div")
        assert loc.is_visible() is True

    def test_is_visible_no_elements(self) -> None:
        driver = _make_driver()
        driver.find_elements.return_value = []
        loc = SeleniumLocatorAdapter(driver, "div")
        assert loc.is_visible() is False

    def test_is_enabled(self) -> None:
        driver = _make_driver()
        el = _make_element(enabled=True)
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "input")
        assert loc.is_enabled() is True

    def test_fill(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "input")
        loc.fill("test value")
        el.clear.assert_called_once()
        el.send_keys.assert_called_once_with("test value")

    def test_click_normal(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "button")
        loc.click()
        el.click.assert_called_once()

    def test_click_force_uses_js(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "button")
        loc.click(force=True)
        driver.execute_script.assert_called_once_with("arguments[0].click()", el)

    def test_inner_text(self) -> None:
        driver = _make_driver()
        el = _make_element(text="content text")
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "p")
        assert loc.inner_text() == "content text"

    def test_text_content(self) -> None:
        driver = _make_driver()
        el = _make_element(textContent="full text")
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "p")
        assert loc.text_content() == "full text"

    def test_input_value(self) -> None:
        driver = _make_driver()
        el = _make_element(value="input-val")
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "input")
        assert loc.input_value() == "input-val"

    def test_get_attribute(self) -> None:
        driver = _make_driver()
        el = MagicMock()
        el.get_attribute.return_value = "bar"
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "a")
        assert loc.get_attribute("href") == "bar"

    def test_nth_returns_nth_adapter(self) -> None:
        driver = _make_driver()
        loc = SeleniumLocatorAdapter(driver, "li")
        nth = loc.nth(2)
        assert isinstance(nth, _SeleniumNthLocatorAdapter)

    def test_press_enter(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "input")
        loc.press("Enter")
        el.send_keys.assert_called_once_with("\ue007")

    def test_type_sends_chars(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        loc = SeleniumLocatorAdapter(driver, "input")
        loc.type("abc")
        assert el.send_keys.call_count == 3

    def test_evaluate(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        driver.execute_script.return_value = "result"
        loc = SeleniumLocatorAdapter(driver, "div")
        result = loc.evaluate("return el.id")
        assert result == "result"


# ===========================================================================
# _SeleniumNthLocatorAdapter tests
# ===========================================================================


class TestSeleniumNthLocatorAdapter:
    def test_filters_to_single_element(self) -> None:
        driver = _make_driver()
        els = [_make_element(text="a"), _make_element(text="b"), _make_element(text="c")]
        driver.find_elements.return_value = els
        nth = _SeleniumNthLocatorAdapter(driver, "li", 1)
        assert nth.count() == 1
        assert nth.inner_text() == "b"

    def test_out_of_bounds_returns_empty(self) -> None:
        driver = _make_driver()
        driver.find_elements.return_value = [_make_element()]
        nth = _SeleniumNthLocatorAdapter(driver, "li", 5)
        assert nth.count() == 0

    def test_click(self) -> None:
        driver = _make_driver()
        els = [_make_element(), _make_element()]
        driver.find_elements.return_value = els
        nth = _SeleniumNthLocatorAdapter(driver, "li", 1)
        nth.click()
        els[1].click.assert_called_once()
        els[0].click.assert_not_called()


# ===========================================================================
# Stale element retry tests
# ===========================================================================


class TestStaleElementRetry:
    def test_retry_succeeds_after_stale(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]

        call_count = 0

        def flaky_click() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _StaleElementReferenceException("stale")
            return None

        el.click.side_effect = flaky_click
        loc = SeleniumLocatorAdapter(driver, "button")
        loc.click()
        assert call_count == 2

    def test_retry_exhausted_raises(self) -> None:
        driver = _make_driver()
        el = _make_element()
        driver.find_elements.return_value = [el]
        el.is_displayed.side_effect = _StaleElementReferenceException("stale")
        loc = SeleniumLocatorAdapter(driver, "div")
        with pytest.raises(_StaleElementReferenceException):
            loc.is_visible()
