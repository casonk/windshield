"""Selenium WebDriver adapter — Playwright-style API over Selenium."""

from __future__ import annotations

from typing import Any

from windshield.debug import drain_chromium_cdp_events


class _SeleniumNthLocatorAdapter:
    """Locator adapter that filters to a single element by index."""

    def __init__(self, driver: Any, selector: str, index: int) -> None:
        self._driver = driver
        self._selector = selector
        self._index = index

    # -- element lookup --------------------------------------------------------

    def _find_all(self) -> list[Any]:
        from selenium.webdriver.common.by import By

        return self._driver.find_elements(By.CSS_SELECTOR, self._selector)

    def _find_elements(self) -> list[Any]:
        all_els = self._find_all()
        if 0 <= self._index < len(all_els):
            return [all_els[self._index]]
        return []

    def _find_first(self) -> Any:
        elements = self._find_elements()
        if not elements:
            raise Exception(f"No element at index {self._index} for selector: {self._selector}")
        return elements[0]

    def _retry(self, fn: Any, retries: int = 3) -> Any:
        from selenium.common.exceptions import StaleElementReferenceException

        for attempt in range(retries):
            try:
                return fn()
            except StaleElementReferenceException:
                if attempt == retries - 1:
                    raise
                import time

                time.sleep(0.1)
        return None  # pragma: no cover

    # -- LocatorAdapter protocol -----------------------------------------------

    def count(self) -> int:
        return len(self._find_elements())

    def nth(self, index: int) -> _SeleniumNthLocatorAdapter:
        all_els = self._find_all()
        if 0 <= self._index < len(all_els):
            return _SeleniumNthLocatorAdapter(self._driver, self._selector, index)
        raise Exception(f"Cannot call nth() on empty locator (index {self._index})")

    def is_visible(self) -> bool:
        elements = self._find_elements()
        if not elements:
            return False
        return self._retry(lambda: elements[0].is_displayed())

    def is_enabled(self) -> bool:
        elements = self._find_elements()
        if not elements:
            return False
        return self._retry(lambda: elements[0].is_enabled())

    def inner_text(self, *, timeout: float | None = None) -> str:
        return self._retry(lambda: self._find_first().text)

    def text_content(self) -> str | None:
        elements = self._find_elements()
        if not elements:
            return None
        return self._retry(lambda: elements[0].get_attribute("textContent"))

    def input_value(self) -> str:
        return self._retry(lambda: self._find_first().get_attribute("value") or "")

    def get_attribute(self, name: str) -> str | None:
        elements = self._find_elements()
        if not elements:
            return None
        return self._retry(lambda: elements[0].get_attribute(name))

    def fill(self, value: str) -> None:
        def _do() -> None:
            el = self._find_first()
            el.clear()
            el.send_keys(value)

        self._retry(_do)

    def type(self, text: str, *, delay: float = 0) -> None:
        import time

        def _do() -> None:
            el = self._find_first()
            for char in text:
                el.send_keys(char)
                if delay > 0:
                    time.sleep(delay / 1000.0)

        self._retry(_do)

    def click(self, *, force: bool = False, timeout: float | None = None) -> None:
        if force:

            def _do() -> None:
                el = self._find_first()
                self._driver.execute_script("arguments[0].click()", el)

            self._retry(_do)
        else:
            self._retry(lambda: self._find_first().click())

    def press(self, key: str) -> None:
        from selenium.webdriver.common.keys import Keys

        key_map = {
            "Enter": Keys.ENTER,
            "Tab": Keys.TAB,
            "Escape": Keys.ESCAPE,
            "Backspace": Keys.BACKSPACE,
            "Delete": Keys.DELETE,
            "ArrowUp": Keys.ARROW_UP,
            "ArrowDown": Keys.ARROW_DOWN,
            "ArrowLeft": Keys.ARROW_LEFT,
            "ArrowRight": Keys.ARROW_RIGHT,
        }
        sel_key = key_map.get(key, key)
        self._retry(lambda: self._find_first().send_keys(sel_key))

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        el = self._find_first()
        if arg is not None:
            return self._driver.execute_script(
                f"return (function(el, arg) {{ {expression} }})(arguments[0], arguments[1])",
                el,
                arg,
            )
        return self._driver.execute_script(
            f"return (function(el) {{ {expression} }})(arguments[0])", el
        )


class SeleniumLocatorAdapter:
    """Adapter presenting Playwright-style Locator API over Selenium WebDriver."""

    def __init__(self, driver: Any, selector: str) -> None:
        self._driver = driver
        self._selector = selector

    # -- element lookup --------------------------------------------------------

    def _find_elements(self) -> list[Any]:
        from selenium.webdriver.common.by import By

        return self._driver.find_elements(By.CSS_SELECTOR, self._selector)

    def _find_first(self) -> Any:
        elements = self._find_elements()
        if not elements:
            raise Exception(f"No elements found for selector: {self._selector}")
        return elements[0]

    def _retry(self, fn: Any, retries: int = 3) -> Any:
        """Retry on StaleElementReferenceException."""
        from selenium.common.exceptions import StaleElementReferenceException

        for attempt in range(retries):
            try:
                return fn()
            except StaleElementReferenceException:
                if attempt == retries - 1:
                    raise
                import time

                time.sleep(0.1)
        return None  # pragma: no cover

    # -- LocatorAdapter protocol -----------------------------------------------

    def count(self) -> int:
        return len(self._find_elements())

    def nth(self, index: int) -> _SeleniumNthLocatorAdapter:
        return _SeleniumNthLocatorAdapter(self._driver, self._selector, index)

    def is_visible(self) -> bool:
        elements = self._find_elements()
        if not elements:
            return False
        return self._retry(lambda: elements[0].is_displayed())

    def is_enabled(self) -> bool:
        elements = self._find_elements()
        if not elements:
            return False
        return self._retry(lambda: elements[0].is_enabled())

    def inner_text(self, *, timeout: float | None = None) -> str:
        return self._retry(lambda: self._find_first().text)

    def text_content(self) -> str | None:
        elements = self._find_elements()
        if not elements:
            return None
        return self._retry(lambda: elements[0].get_attribute("textContent"))

    def input_value(self) -> str:
        return self._retry(lambda: self._find_first().get_attribute("value") or "")

    def get_attribute(self, name: str) -> str | None:
        elements = self._find_elements()
        if not elements:
            return None
        return self._retry(lambda: elements[0].get_attribute(name))

    def fill(self, value: str) -> None:
        def _do() -> None:
            el = self._find_first()
            el.clear()
            el.send_keys(value)

        self._retry(_do)

    def type(self, text: str, *, delay: float = 0) -> None:
        import time

        def _do() -> None:
            el = self._find_first()
            for char in text:
                el.send_keys(char)
                if delay > 0:
                    time.sleep(delay / 1000.0)

        self._retry(_do)

    def click(self, *, force: bool = False, timeout: float | None = None) -> None:
        if force:

            def _do() -> None:
                el = self._find_first()
                self._driver.execute_script("arguments[0].click()", el)

            self._retry(_do)
        else:
            self._retry(lambda: self._find_first().click())

    def press(self, key: str) -> None:
        from selenium.webdriver.common.keys import Keys

        key_map = {
            "Enter": Keys.ENTER,
            "Tab": Keys.TAB,
            "Escape": Keys.ESCAPE,
            "Backspace": Keys.BACKSPACE,
            "Delete": Keys.DELETE,
            "ArrowUp": Keys.ARROW_UP,
            "ArrowDown": Keys.ARROW_DOWN,
            "ArrowLeft": Keys.ARROW_LEFT,
            "ArrowRight": Keys.ARROW_RIGHT,
        }
        sel_key = key_map.get(key, key)
        self._retry(lambda: self._find_first().send_keys(sel_key))

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        el = self._find_first()
        if arg is not None:
            return self._driver.execute_script(
                f"return (function(el, arg) {{ {expression} }})(arguments[0], arguments[1])",
                el,
                arg,
            )
        return self._driver.execute_script(
            f"return (function(el) {{ {expression} }})(arguments[0])", el
        )


class _SeleniumFrameLocatorAdapter(SeleniumLocatorAdapter):
    """Locator that switches into an iframe before finding elements."""

    def __init__(self, driver: Any, iframe_element: Any, selector: str) -> None:
        super().__init__(driver, selector)
        self._iframe = iframe_element

    def _find_elements(self) -> list[Any]:
        from selenium.webdriver.common.by import By

        self._driver.switch_to.frame(self._iframe)
        try:
            return self._driver.find_elements(By.CSS_SELECTOR, self._selector)
        finally:
            self._driver.switch_to.default_content()


class _SeleniumFrameAdapter:
    """Adapter for accessing iframe content in Selenium."""

    def __init__(self, driver: Any, iframe_element: Any) -> None:
        self._driver = driver
        self._iframe = iframe_element

    @property
    def url(self) -> str:
        return self._iframe.get_attribute("src") or ""

    @property
    def name(self) -> str:
        return self._iframe.get_attribute("name") or ""

    def locator(self, selector: str) -> _SeleniumFrameLocatorAdapter:
        return _SeleniumFrameLocatorAdapter(self._driver, self._iframe, selector)

    def content(self) -> str:
        self._driver.switch_to.frame(self._iframe)
        try:
            return self._driver.page_source
        finally:
            self._driver.switch_to.default_content()


class SeleniumPageAdapter:
    """Adapter presenting Playwright-style Page API over Selenium WebDriver."""

    def __init__(self, driver: Any) -> None:
        self._driver = driver
        self._event_handlers: dict[str, list[Any]] = {}

    # -- PageAdapter protocol: properties --------------------------------------

    @property
    def url(self) -> str:
        return self._driver.current_url

    @property
    def backend_name(self) -> str:
        return "selenium"

    @property
    def raw(self) -> Any:
        return self._driver

    # -- content ---------------------------------------------------------------

    def title(self) -> str:
        return self._driver.title

    def content(self) -> str:
        return self._driver.page_source

    # -- element finding -------------------------------------------------------

    def locator(self, selector: str) -> SeleniumLocatorAdapter:
        return SeleniumLocatorAdapter(self._driver, selector)

    # -- javascript ------------------------------------------------------------

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        if arg is not None:
            return self._driver.execute_script(f"return {expression}", arg)
        return self._driver.execute_script(f"return {expression}")

    # -- navigation ------------------------------------------------------------

    def goto(self, url: str, **kwargs: Any) -> None:
        self._driver.get(url)

    def wait_for_timeout(self, timeout_ms: float) -> None:
        import time

        time.sleep(timeout_ms / 1000.0)

    def wait_for_url(self, url_or_predicate: Any, **kwargs: Any) -> None:
        from selenium.webdriver.support.ui import WebDriverWait

        timeout = kwargs.get("timeout", 30000) / 1000.0
        if callable(url_or_predicate):
            WebDriverWait(self._driver, timeout).until(lambda d: url_or_predicate(d.current_url))
        else:
            WebDriverWait(self._driver, timeout).until(
                lambda d: str(url_or_predicate) in d.current_url
            )

    def bring_to_front(self) -> None:
        self._driver.switch_to.window(self._driver.current_window_handle)

    # -- media -----------------------------------------------------------------

    def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        png = self._driver.get_screenshot_as_png()
        if path:
            from pathlib import Path

            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(png)
        return png

    # -- frames ----------------------------------------------------------------

    def frames(self) -> list[Any]:
        from selenium.webdriver.common.by import By

        iframe_elements = self._driver.find_elements(By.TAG_NAME, "iframe")
        return [_SeleniumFrameAdapter(self._driver, el) for el in iframe_elements]

    @property
    def main_frame(self) -> Any:
        return self

    # -- context ---------------------------------------------------------------

    @property
    def context(self) -> Any:
        return self._driver

    # -- events ----------------------------------------------------------------

    def on(self, event: str, handler: Any) -> None:
        self._event_handlers.setdefault(event, []).append(handler)

    def drain_cdp_events(self) -> list[dict[str, Any]]:
        """Dispatch currently available Chrome performance-log events.

        Configure performance logging when creating the driver, then call this
        from the application's own polling loop. Handlers registered through
        :meth:`on` receive normalized event dictionaries.
        """
        events = drain_chromium_cdp_events(self._driver)
        for event in events:
            for handler in self._event_handlers.get(str(event.get("event", "")), []):
                try:
                    handler(event)
                except Exception:  # pylint: disable=broad-except
                    continue
        return events

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        self._driver.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._driver, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            object.__setattr__(self, name, value)
