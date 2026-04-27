"""Tests for windshield.rotation — backend rotation strategy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from windshield.adapters._protocol import BackendType
from windshield.rotation import RotationStrategy

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def strategy() -> RotationStrategy:
    """Three-backend strategy with short cooldown for testing."""
    return RotationStrategy(
        backends=[BackendType.UNDETECTED, BackendType.PLAYWRIGHT, BackendType.SELENIUM],
        cooldown_seconds=300.0,
    )


# ---------------------------------------------------------------------------
# 1. next_backend returns first backend when nothing blocked
# ---------------------------------------------------------------------------


def test_next_backend_returns_first_when_clean(strategy: RotationStrategy) -> None:
    assert strategy.next_backend() is BackendType.UNDETECTED


# ---------------------------------------------------------------------------
# 2. After report_block, next_backend skips blocked backend
# ---------------------------------------------------------------------------


def test_next_backend_skips_blocked(strategy: RotationStrategy) -> None:
    strategy.report_block(BackendType.UNDETECTED, reason="CAPTCHA")
    assert strategy.next_backend() is BackendType.PLAYWRIGHT


# ---------------------------------------------------------------------------
# 3. After cooldown expires, blocked backend is available again
# ---------------------------------------------------------------------------


def test_cooldown_expires_makes_backend_available(strategy: RotationStrategy) -> None:
    base = 1000.0
    with patch("windshield.rotation.time") as mock_time:
        mock_time.time.return_value = base
        strategy.report_block(BackendType.UNDETECTED, reason="blocked")

        # Still within cooldown
        mock_time.time.return_value = base + 200
        assert strategy.next_backend() is BackendType.PLAYWRIGHT

        # After cooldown — reset index so rotation starts from the beginning
        strategy._current_index = 0
        mock_time.time.return_value = base + 301
        assert strategy.next_backend() is BackendType.UNDETECTED


# ---------------------------------------------------------------------------
# 4. report_success clears block history
# ---------------------------------------------------------------------------


def test_report_success_clears_blocks(strategy: RotationStrategy) -> None:
    strategy.report_block(BackendType.UNDETECTED, reason="blocked")
    assert BackendType.UNDETECTED in strategy.block_history

    strategy.report_success(BackendType.UNDETECTED)
    assert BackendType.UNDETECTED not in strategy.block_history
    # Backend is available again immediately
    strategy._current_index = 0
    assert strategy.next_backend() is BackendType.UNDETECTED


# ---------------------------------------------------------------------------
# 5. All backends blocked → falls back to least-recently-blocked
# ---------------------------------------------------------------------------


def test_all_blocked_falls_back_to_oldest(strategy: RotationStrategy) -> None:
    base = 1000.0
    with patch("windshield.rotation.time") as mock_time:
        mock_time.time.return_value = base
        strategy.report_block(BackendType.UNDETECTED, reason="blocked")

        mock_time.time.return_value = base + 10
        strategy.report_block(BackendType.PLAYWRIGHT, reason="blocked")

        mock_time.time.return_value = base + 20
        strategy.report_block(BackendType.SELENIUM, reason="blocked")

        # All blocked — should return UNDETECTED (oldest block)
        mock_time.time.return_value = base + 30
        assert strategy.next_backend() is BackendType.UNDETECTED


# ---------------------------------------------------------------------------
# 6. reset clears everything
# ---------------------------------------------------------------------------


def test_reset_clears_state(strategy: RotationStrategy) -> None:
    strategy.report_block(BackendType.UNDETECTED, reason="blocked")
    strategy.report_success(BackendType.PLAYWRIGHT)
    strategy.reset()

    assert strategy.block_history == {}
    assert strategy.next_backend() is BackendType.UNDETECTED


# ---------------------------------------------------------------------------
# 7. summary returns correct diagnostic info
# ---------------------------------------------------------------------------


def test_summary_content(strategy: RotationStrategy) -> None:
    base = 1000.0
    with patch("windshield.rotation.time") as mock_time:
        mock_time.time.return_value = base
        strategy.report_block(BackendType.UNDETECTED, reason="blocked")
        strategy.report_success(BackendType.PLAYWRIGHT)

        mock_time.time.return_value = base + 10
        info = strategy.summary()

    assert "undetected" in info
    assert info["undetected"]["total_blocks"] == 1
    assert info["undetected"]["recent_blocks"] == 1
    assert info["undetected"]["available"] is False
    assert info["playwright"]["successes"] == 1
    assert info["playwright"]["available"] is True
    assert info["selenium"]["available"] is True


# ---------------------------------------------------------------------------
# 8. String backend names work in report_block / report_success
# ---------------------------------------------------------------------------


def test_string_backend_names(strategy: RotationStrategy) -> None:
    strategy.report_block("undetected", reason="test")
    assert BackendType.UNDETECTED in strategy.block_history

    strategy.report_success("undetected")
    assert BackendType.UNDETECTED not in strategy.block_history


# ---------------------------------------------------------------------------
# 9. Custom backend order is respected
# ---------------------------------------------------------------------------


def test_custom_backend_order() -> None:
    s = RotationStrategy(
        backends=[BackendType.HTTP, BackendType.SELENIUM, BackendType.PLAYWRIGHT],
    )
    assert s.backends == [BackendType.HTTP, BackendType.SELENIUM, BackendType.PLAYWRIGHT]
    assert s.next_backend() is BackendType.HTTP


# ---------------------------------------------------------------------------
# 10. create_page returns (backend, adapter) tuple
# ---------------------------------------------------------------------------


def test_create_page_returns_tuple(strategy: RotationStrategy) -> None:
    mock_adapter = MagicMock()
    with patch("windshield.rotation.create_page", return_value=mock_adapter) as mock_cp:
        backend, page = strategy.create_page(headless=True)

    assert backend is BackendType.UNDETECTED
    assert page is mock_adapter
    mock_cp.assert_called_once_with(BackendType.UNDETECTED, headless=True)
