"""Playwright adapter — thin pass-through to sync Page / Locator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class PlaywrightLocatorAdapter:
    """Adapter wrapping a Playwright sync ``Locator``."""

    def __init__(self, locator: Any) -> None:
        self._locator = locator

    def count(self) -> int:
        return self._locator.count()

    def nth(self, index: int) -> PlaywrightLocatorAdapter:
        return PlaywrightLocatorAdapter(self._locator.nth(index))

    def is_visible(self) -> bool:
        return self._locator.is_visible()

    def is_enabled(self) -> bool:
        return self._locator.is_enabled()

    def inner_text(self, *, timeout: float | None = None) -> str:
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self._locator.inner_text(**kwargs)

    def text_content(self) -> str | None:
        return self._locator.text_content()

    def input_value(self) -> str:
        return self._locator.input_value()

    def get_attribute(self, name: str) -> str | None:
        return self._locator.get_attribute(name)

    def fill(self, value: str) -> None:
        self._locator.fill(value)

    def type(self, text: str, *, delay: float = 0) -> None:
        self._locator.type(text, delay=delay)

    def click(self, *, force: bool = False, timeout: float | None = None) -> None:
        kwargs: dict[str, Any] = {"force": force}
        if timeout is not None:
            kwargs["timeout"] = timeout
        self._locator.click(**kwargs)

    def press(self, key: str) -> None:
        self._locator.press(key)

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        return self._locator.evaluate(expression, arg)


class PlaywrightPageAdapter:
    """Adapter wrapping a Playwright sync ``Page``."""

    _INTERNAL_ATTRS = frozenset({"_page"})

    def __init__(self, page: Any) -> None:
        object.__setattr__(self, "_page", page)

    # -- dynamic attribute delegation ------------------------------------------

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in self._INTERNAL_ATTRS:
            object.__setattr__(self, name, value)
        else:
            setattr(self._page, name, value)

    # -- properties ------------------------------------------------------------

    @property
    def url(self) -> str:
        return self._page.url

    @property
    def backend_name(self) -> str:
        return "playwright"

    @property
    def raw(self) -> Any:
        return self._page

    # -- content ---------------------------------------------------------------

    def title(self) -> str:
        return self._page.title()

    def content(self) -> str:
        return self._page.content()

    # -- element finding -------------------------------------------------------

    def locator(self, selector: str) -> PlaywrightLocatorAdapter:
        return PlaywrightLocatorAdapter(self._page.locator(selector))

    # -- javascript ------------------------------------------------------------

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        return self._page.evaluate(expression, arg)

    # -- navigation ------------------------------------------------------------

    def goto(self, url: str, **kwargs: Any) -> Any:
        return self._page.goto(url, **kwargs)

    def wait_for_timeout(self, timeout_ms: float) -> None:
        self._page.wait_for_timeout(timeout_ms)

    def wait_for_url(self, url_or_predicate: Any, **kwargs: Any) -> None:
        self._page.wait_for_url(url_or_predicate, **kwargs)

    def bring_to_front(self) -> None:
        self._page.bring_to_front()

    # -- media -----------------------------------------------------------------

    def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        return self._page.screenshot(path=path, full_page=full_page)

    # -- frames ----------------------------------------------------------------

    def frames(self) -> list[Any]:
        return self._page.frames

    @property
    def main_frame(self) -> Any:
        return self._page.main_frame

    # -- context ---------------------------------------------------------------

    @property
    def context(self) -> Any:
        return self._page.context

    # -- events ----------------------------------------------------------------

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        self._page.on(event, handler)

    # -- lifecycle -------------------------------------------------------------

    def close(self) -> None:
        self._page.close()
