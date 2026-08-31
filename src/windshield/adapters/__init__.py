"""Windshield adapter layer — multi-backend browser automation."""

from windshield.adapters._factory import create_async_playwright_page, create_page
from windshield.adapters._protocol import (
    DEFAULT_ROTATION_ORDER,
    AsyncLocatorAdapter,
    AsyncPageAdapter,
    BackendType,
    LocatorAdapter,
    PageAdapter,
    UnsupportedOperationError,
)

__all__ = [
    "AsyncLocatorAdapter",
    "AsyncPageAdapter",
    "BackendType",
    "DEFAULT_ROTATION_ORDER",
    "LocatorAdapter",
    "PageAdapter",
    "UnsupportedOperationError",
    "create_async_playwright_page",
    "create_page",
]
