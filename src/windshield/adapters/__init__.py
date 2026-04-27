"""Windshield adapter layer — multi-backend browser automation."""

from windshield.adapters._factory import create_page
from windshield.adapters._protocol import (
    BackendType,
    LocatorAdapter,
    PageAdapter,
    UnsupportedOperationError,
)

__all__ = [
    "BackendType",
    "LocatorAdapter",
    "PageAdapter",
    "UnsupportedOperationError",
    "create_page",
]
