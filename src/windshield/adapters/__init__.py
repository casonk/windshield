"""Windshield adapter layer — multi-backend browser automation."""

from windshield.adapters._factory import create_page
from windshield.adapters._protocol import (
    DEFAULT_ROTATION_ORDER,
    BackendType,
    LocatorAdapter,
    PageAdapter,
    UnsupportedOperationError,
)

__all__ = [
    "BackendType",
    "DEFAULT_ROTATION_ORDER",
    "LocatorAdapter",
    "PageAdapter",
    "UnsupportedOperationError",
    "create_page",
]
