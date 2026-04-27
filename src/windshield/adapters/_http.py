"""HTTP-only adapter — requests + BeautifulSoup, no JS engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _HttpFrameStub:
    """Minimal frame stub for HTTP mode (just URL and name)."""

    def __init__(self, url: str, name: str = "") -> None:
        self.url = url
        self.name = name


class HttpLocatorAdapter:
    """Adapter presenting Playwright-style Locator API over BeautifulSoup elements."""

    def __init__(
        self,
        soup: Any,
        selector: str,
        elements: list[Any] | None = None,
    ) -> None:
        self._soup = soup
        self._selector = selector
        self._elements = elements if elements is not None else soup.select(selector)

    def count(self) -> int:
        return len(self._elements)

    def nth(self, index: int) -> HttpLocatorAdapter:
        if 0 <= index < len(self._elements):
            return HttpLocatorAdapter(self._soup, self._selector, [self._elements[index]])
        return HttpLocatorAdapter(self._soup, self._selector, [])

    def is_visible(self) -> bool:
        return len(self._elements) > 0

    def is_enabled(self) -> bool:
        if not self._elements:
            return False
        el = self._elements[0]
        return not el.has_attr("disabled")

    def inner_text(self, *, timeout: float | None = None) -> str:
        if not self._elements:
            return ""
        return self._elements[0].get_text(strip=True)

    def text_content(self) -> str | None:
        if not self._elements:
            return None
        return self._elements[0].get_text()

    def input_value(self) -> str:
        if not self._elements:
            return ""
        return self._elements[0].get("value", "")

    def get_attribute(self, name: str) -> str | None:
        if not self._elements:
            return None
        return self._elements[0].get(name)

    def fill(self, value: str) -> None:
        if self._elements:
            self._elements[0]["value"] = value

    def type(self, text: str, *, delay: float = 0) -> None:
        self.fill(text)

    def click(self, *, force: bool = False, timeout: float | None = None) -> None:
        pass

    def press(self, key: str) -> None:
        pass

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        from windshield.adapters._protocol import UnsupportedOperationError

        raise UnsupportedOperationError("JavaScript evaluation is not supported in HTTP-only mode")


class HttpPageAdapter:
    """Adapter presenting Playwright-style Page API over requests + BeautifulSoup."""

    def __init__(
        self,
        session: Any | None = None,
        url: str = "",
        html: str = "",
    ) -> None:
        import requests as req_lib
        from bs4 import BeautifulSoup

        self._session = session or req_lib.Session()
        self._url = url
        self._html = html
        self._soup = (
            BeautifulSoup(html, "html.parser") if html else BeautifulSoup("", "html.parser")
        )
        self._event_handlers: dict[str, list[Callable[..., Any]]] = {}

    @property
    def url(self) -> str:
        return self._url

    @property
    def backend_name(self) -> str:
        return "http"

    @property
    def raw(self) -> Any:
        return self._session

    def title(self) -> str:
        tag = self._soup.find("title")
        return tag.get_text(strip=True) if tag else ""

    def content(self) -> str:
        return self._html

    def locator(self, selector: str) -> HttpLocatorAdapter:
        return HttpLocatorAdapter(self._soup, selector)

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        from windshield.adapters._protocol import UnsupportedOperationError

        raise UnsupportedOperationError("JavaScript evaluation is not supported in HTTP-only mode")

    def goto(self, url: str, **kwargs: Any) -> Any:
        from bs4 import BeautifulSoup

        response = self._session.get(url, **kwargs)
        response.raise_for_status()
        self._url = str(response.url)
        self._html = response.text
        self._soup = BeautifulSoup(self._html, "html.parser")
        return response

    def wait_for_timeout(self, timeout_ms: float) -> None:
        import time

        time.sleep(timeout_ms / 1000.0)

    def wait_for_url(self, url_or_predicate: Any, **kwargs: Any) -> None:
        pass

    def bring_to_front(self) -> None:
        pass

    def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        from windshield.adapters._protocol import UnsupportedOperationError

        raise UnsupportedOperationError("Screenshots are not supported in HTTP-only mode")

    def frames(self) -> list[Any]:
        iframes = self._soup.find_all("iframe")
        result: list[Any] = []
        for iframe in iframes:
            src = iframe.get("src", "")
            if src:
                result.append(_HttpFrameStub(src, iframe.get("name", "")))
        return result

    @property
    def main_frame(self) -> Any:
        return self

    @property
    def context(self) -> Any:
        return self._session

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        self._event_handlers.setdefault(event, []).append(handler)

    def close(self) -> None:
        self._session.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            object.__setattr__(self, name, value)
