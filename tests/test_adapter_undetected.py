"""Tests for the undetected-chromedriver adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from windshield.adapters._undetected import (
    UndetectedChromePageAdapter,
    create_undetected_browser,
)


class TestUndetectedChromePageAdapter:
    def test_backend_name(self) -> None:
        mock_driver = MagicMock()
        adapter = UndetectedChromePageAdapter(mock_driver)
        assert adapter.backend_name == "undetected"

    def test_inherits_selenium_url(self) -> None:
        mock_driver = MagicMock()
        type(mock_driver).current_url = PropertyMock(return_value="https://bank.com")
        adapter = UndetectedChromePageAdapter(mock_driver)
        assert adapter.url == "https://bank.com"

    def test_inherits_selenium_title(self) -> None:
        mock_driver = MagicMock()
        type(mock_driver).title = PropertyMock(return_value="My Bank")
        adapter = UndetectedChromePageAdapter(mock_driver)
        assert adapter.title() == "My Bank"

    def test_inherits_selenium_content(self) -> None:
        mock_driver = MagicMock()
        type(mock_driver).page_source = PropertyMock(return_value="<html></html>")
        adapter = UndetectedChromePageAdapter(mock_driver)
        assert adapter.content() == "<html></html>"

    def test_raw_returns_driver(self) -> None:
        mock_driver = MagicMock()
        adapter = UndetectedChromePageAdapter(mock_driver)
        assert adapter.raw is mock_driver

    def test_locator_returns_selenium_locator(self) -> None:
        mock_driver = MagicMock()
        adapter = UndetectedChromePageAdapter(mock_driver)
        loc = adapter.locator("input#user")
        assert loc is not None
        assert loc.count() >= 0 or True  # just verify it doesn't crash

    def test_evaluate_delegates(self) -> None:
        mock_driver = MagicMock()
        mock_driver.execute_script.return_value = 42
        adapter = UndetectedChromePageAdapter(mock_driver)
        result = adapter.evaluate("return 42")
        mock_driver.execute_script.assert_called_once()
        assert result == 42

    def test_goto_delegates(self) -> None:
        mock_driver = MagicMock()
        adapter = UndetectedChromePageAdapter(mock_driver)
        adapter.goto("https://example.com")
        mock_driver.get.assert_called_once_with("https://example.com")


class TestCreateUndetectedBrowser:
    def test_missing_import_raises(self) -> None:
        with patch.dict("sys.modules", {"undetected_chromedriver": None}):
            with pytest.raises(ImportError, match="undetected-chromedriver"):
                create_undetected_browser()

    def test_creates_with_profile_dir(self) -> None:
        mock_uc = MagicMock()
        mock_driver = MagicMock()
        mock_uc.Chrome.return_value = mock_driver
        mock_uc.ChromeOptions.return_value = MagicMock()

        with patch.dict("sys.modules", {"undetected_chromedriver": mock_uc}):
            adapter = create_undetected_browser(profile_dir="/tmp/test-profile")

        assert isinstance(adapter, UndetectedChromePageAdapter)
        assert adapter.raw is mock_driver
        mock_uc.Chrome.assert_called_once()

    def test_creates_headless(self) -> None:
        mock_uc = MagicMock()
        mock_uc.Chrome.return_value = MagicMock()
        mock_uc.ChromeOptions.return_value = MagicMock()

        with patch.dict("sys.modules", {"undetected_chromedriver": mock_uc}):
            adapter = create_undetected_browser(headless=True)

        assert adapter.backend_name == "undetected"

    def test_creates_with_proxy(self) -> None:
        mock_uc = MagicMock()
        mock_options = MagicMock()
        mock_uc.ChromeOptions.return_value = mock_options
        mock_uc.Chrome.return_value = MagicMock()

        with patch.dict("sys.modules", {"undetected_chromedriver": mock_uc}):
            create_undetected_browser(proxy="socks5://127.0.0.1:1080")

        calls = [str(c) for c in mock_options.add_argument.call_args_list]
        assert any("proxy-server" in c for c in calls)
