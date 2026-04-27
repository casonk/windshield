"""Backend rotation — automatic fallback when a backend is blocked."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from windshield.adapters._factory import create_page
from windshield.adapters._protocol import BackendType, PageAdapter

logger = logging.getLogger(__name__)


@dataclass
class BlockEvent:
    """Record of a backend being blocked."""

    backend: BackendType
    reason: str
    timestamp: float = field(default_factory=time.time)


class RotationStrategy:
    """Manage browser backend rotation with block tracking and cooldown.

    Usage::

        strategy = RotationStrategy(
            backends=[BackendType.UNDETECTED, BackendType.PLAYWRIGHT, BackendType.SELENIUM],
            cooldown_seconds=300,
        )

        # Get next available backend
        backend = strategy.next_backend()
        page = create_page(backend, profile_dir="/path/to/profile")

        # If it gets blocked, report it and try next
        strategy.report_block(backend, reason="CAPTCHA detected")
        backend = strategy.next_backend()
        page = create_page(backend)

        # On success, report it to boost priority
        strategy.report_success(backend)
    """

    def __init__(
        self,
        backends: list[BackendType | str] | None = None,
        cooldown_seconds: float = 300.0,
        max_blocks_before_cooldown: int = 1,
    ) -> None:
        if backends is None:
            backends = [
                BackendType.UNDETECTED,
                BackendType.PLAYWRIGHT,
                BackendType.SELENIUM,
                BackendType.HTTP,
            ]
        self._backends = [BackendType(b) if isinstance(b, str) else b for b in backends]
        self._cooldown_seconds = cooldown_seconds
        self._max_blocks = max_blocks_before_cooldown
        self._block_history: dict[BackendType, list[BlockEvent]] = {}
        self._success_count: dict[BackendType, int] = {}
        self._current_index = 0

    @property
    def backends(self) -> list[BackendType]:
        return list(self._backends)

    @property
    def block_history(self) -> dict[BackendType, list[BlockEvent]]:
        return dict(self._block_history)

    def _is_cooled_down(self, backend: BackendType) -> bool:
        """Return whether a blocked backend has cooled down enough to retry."""
        events = self._block_history.get(backend, [])
        if not events:
            return True
        cutoff = time.time() - self._cooldown_seconds
        recent = [e for e in events if e.timestamp > cutoff]
        return len(recent) < self._max_blocks

    def next_backend(self) -> BackendType:
        """Return the next available backend, skipping blocked ones.

        Raises RuntimeError if all backends are blocked.
        """
        for i in range(len(self._backends)):
            idx = (self._current_index + i) % len(self._backends)
            candidate = self._backends[idx]
            if self._is_cooled_down(candidate):
                self._current_index = idx
                logger.debug("Selected backend: %s", candidate.value)
                return candidate

        # All blocked — return the one with the oldest block
        oldest_backend = self._backends[0]
        oldest_time = float("inf")
        for b in self._backends:
            events = self._block_history.get(b, [])
            if events:
                latest = max(e.timestamp for e in events)
                if latest < oldest_time:
                    oldest_time = latest
                    oldest_backend = b
            else:
                oldest_backend = b
                break

        logger.warning(
            "All backends blocked. Falling back to least-recently-blocked: %s",
            oldest_backend.value,
        )
        return oldest_backend

    def report_block(self, backend: BackendType | str, reason: str = "") -> None:
        """Record that a backend was blocked/detected."""
        if isinstance(backend, str):
            backend = BackendType(backend)
        event = BlockEvent(backend=backend, reason=reason, timestamp=time.time())
        self._block_history.setdefault(backend, []).append(event)
        logger.info("Backend %s blocked: %s", backend.value, reason)
        # Advance past the blocked backend
        try:
            idx = self._backends.index(backend)
            self._current_index = (idx + 1) % len(self._backends)
        except ValueError:
            pass

    def report_success(self, backend: BackendType | str) -> None:
        """Record a successful operation — clears recent block history."""
        if isinstance(backend, str):
            backend = BackendType(backend)
        self._success_count[backend] = self._success_count.get(backend, 0) + 1
        self._block_history.pop(backend, None)
        logger.debug(
            "Backend %s succeeded (total: %d)",
            backend.value,
            self._success_count[backend],
        )

    def reset(self) -> None:
        """Clear all block history and reset to first backend."""
        self._block_history.clear()
        self._success_count.clear()
        self._current_index = 0

    def create_page(self, **kwargs: Any) -> tuple[BackendType, PageAdapter]:
        """Convenience: pick the next backend and create a page.

        Returns a (backend, page_adapter) tuple so the caller knows which
        backend was chosen and can report blocks/successes.
        """
        backend = self.next_backend()
        page = create_page(backend, **kwargs)
        return backend, page

    def summary(self) -> dict[str, Any]:
        """Return a diagnostic summary of rotation state."""
        now = time.time()
        result = {}
        for b in self._backends:
            events = self._block_history.get(b, [])
            recent = [e for e in events if e.timestamp > now - self._cooldown_seconds]
            result[b.value] = {
                "available": self._is_cooled_down(b),
                "total_blocks": len(events),
                "recent_blocks": len(recent),
                "successes": self._success_count.get(b, 0),
            }
        return result
