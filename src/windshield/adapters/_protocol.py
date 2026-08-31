"""Adapter protocols for multi-backend browser automation."""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


class BackendType(enum.Enum):
    """Supported browser automation backends.

    Listed in privacy-descending order: most private (least detectable) first.
    """

    UNDETECTED = "undetected"
    HTTP = "http"
    PLAYWRIGHT = "playwright"
    SELENIUM = "selenium"


# Default rotation order — most private first, downgrade only when blocked.
DEFAULT_ROTATION_ORDER: list[BackendType] = [
    BackendType.UNDETECTED,
    BackendType.HTTP,
    BackendType.PLAYWRIGHT,
    BackendType.SELENIUM,
]


class UnsupportedOperationError(Exception):
    """Raised when a backend does not support the requested operation."""


@runtime_checkable
class LocatorAdapter(Protocol):
    """Unified interface for element locators across backends.

    Models the Playwright Locator API — other backends adapt to match.
    """

    def count(self) -> int:
        """Return the number of elements matching this locator."""
        ...

    def nth(self, index: int) -> LocatorAdapter:
        """Return a locator pointing to the nth matching element."""
        ...

    def is_visible(self) -> bool:
        """Return whether the first matching element is visible."""
        ...

    def is_enabled(self) -> bool:
        """Return whether the first matching element is enabled."""
        ...

    def inner_text(self, *, timeout: float | None = None) -> str:
        """Return the inner text of the first matching element."""
        ...

    def text_content(self) -> str | None:
        """Return the text content of the first matching element, or None."""
        ...

    def input_value(self) -> str:
        """Return the value of the first matching input element."""
        ...

    def get_attribute(self, name: str) -> str | None:
        """Return the value of the named attribute, or None."""
        ...

    def fill(self, value: str) -> None:
        """Clear and fill the first matching input with *value*."""
        ...

    def type(self, text: str, *, delay: float = 0) -> None:
        """Type *text* into the first matching element key-by-key."""
        ...

    def click(self, *, force: bool = False, timeout: float | None = None) -> None:
        """Click the first matching element."""
        ...

    def press(self, key: str) -> None:
        """Press a keyboard key while the element is focused."""
        ...

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        """Run *expression* in the browser with the element as first argument."""
        ...


@runtime_checkable
class PageAdapter(Protocol):
    """Unified interface for browser pages across backends.

    Models the Playwright sync Page API — other backends adapt to match.
    """

    # ---- properties ----------------------------------------------------------

    @property
    def url(self) -> str:
        """Current page URL."""
        ...

    @property
    def backend_name(self) -> str:
        """Identifier for the underlying backend (e.g. ``'playwright'``)."""
        ...

    @property
    def raw(self) -> Any:
        """Escape hatch — the underlying driver or page object."""
        ...

    # ---- content -------------------------------------------------------------

    def title(self) -> str:
        """Return the page title."""
        ...

    def content(self) -> str:
        """Return the full page HTML."""
        ...

    # ---- element finding -----------------------------------------------------

    def locator(self, selector: str) -> LocatorAdapter:
        """Return a locator for *selector* (CSS or Playwright-style)."""
        ...

    # ---- javascript ----------------------------------------------------------

    def evaluate(self, expression: str, arg: Any = None) -> Any:
        """Evaluate *expression* in the browser and return the result."""
        ...

    # ---- navigation ----------------------------------------------------------

    def goto(self, url: str, **kwargs: Any) -> Any:
        """Navigate to *url*."""
        ...

    def wait_for_timeout(self, timeout_ms: float) -> None:
        """Sleep for *timeout_ms* milliseconds."""
        ...

    def wait_for_url(self, url_or_predicate: Any, **kwargs: Any) -> None:
        """Wait until the page URL matches *url_or_predicate*."""
        ...

    def bring_to_front(self) -> None:
        """Bring the page tab to the front."""
        ...

    # ---- media ---------------------------------------------------------------

    def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes:
        """Capture a screenshot and return the image bytes."""
        ...

    # ---- frames --------------------------------------------------------------

    def frames(self) -> list[Any]:
        """Return all frames in the page as adapter-compatible objects."""
        ...

    @property
    def main_frame(self) -> Any:
        """The main frame of the page."""
        ...

    # ---- context -------------------------------------------------------------

    @property
    def context(self) -> Any:
        """The browser context that owns this page."""
        ...

    # ---- events --------------------------------------------------------------

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """Register an event listener (``console``, ``response``, etc.)."""
        ...

    # ---- lifecycle -----------------------------------------------------------

    def close(self) -> None:
        """Close the page."""
        ...


@runtime_checkable
class AsyncLocatorAdapter(Protocol):
    """Awaitable locator interface for the Playwright async API."""

    async def count(self) -> int: ...

    def nth(self, index: int) -> AsyncLocatorAdapter: ...

    async def is_visible(self) -> bool: ...

    async def is_enabled(self) -> bool: ...

    async def inner_text(self, *, timeout: float | None = None) -> str: ...

    async def text_content(self) -> str | None: ...

    async def input_value(self) -> str: ...

    async def get_attribute(self, name: str) -> str | None: ...

    async def fill(self, value: str) -> None: ...

    async def type(self, text: str, *, delay: float = 0) -> None: ...

    async def click(self, *, force: bool = False, timeout: float | None = None) -> None: ...

    async def press(self, key: str) -> None: ...

    async def evaluate(self, expression: str, arg: Any = None) -> Any: ...


@runtime_checkable
class AsyncPageAdapter(Protocol):
    """Awaitable page interface for the Playwright async API.

    It intentionally mirrors :class:`PageAdapter` without changing the
    synchronous multi-backend contract.
    """

    @property
    def url(self) -> str: ...

    @property
    def backend_name(self) -> str: ...

    @property
    def raw(self) -> Any: ...

    async def title(self) -> str: ...

    async def content(self) -> str: ...

    def locator(self, selector: str) -> AsyncLocatorAdapter: ...

    async def evaluate(self, expression: str, arg: Any = None) -> Any: ...

    async def goto(self, url: str, **kwargs: Any) -> Any: ...

    async def wait_for_timeout(self, timeout_ms: float) -> None: ...

    async def wait_for_url(self, url_or_predicate: Any, **kwargs: Any) -> None: ...

    async def bring_to_front(self) -> None: ...

    async def screenshot(self, *, path: str | None = None, full_page: bool = False) -> bytes: ...

    def frames(self) -> list[Any]: ...

    @property
    def main_frame(self) -> Any: ...

    @property
    def context(self) -> Any: ...

    def on(self, event: str, handler: Callable[..., Any]) -> None: ...

    async def close(self) -> None: ...
