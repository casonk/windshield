"""Tests for the browser factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from windshield.adapters._factory import create_page
from windshield.adapters._protocol import BackendType


class TestCreatePage:
    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            create_page("bogus")

    def test_backend_string_normalised(self) -> None:
        adapter = create_page("HTTP", html="<p>hi</p>")
        assert adapter.backend_name == "http"

    def test_backend_enum(self) -> None:
        adapter = create_page(BackendType.HTTP, html="<p>hi</p>")
        assert adapter.backend_name == "http"

    def test_http_with_html(self) -> None:
        adapter = create_page("http", html="<title>Hello</title><p>World</p>")
        assert adapter.title() == "Hello"
        assert adapter.locator("p").count() == 1

    def test_http_with_url(self) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "<title>Fetched</title>"
        mock_response.url = "https://example.com"
        mock_session.get.return_value = mock_response
        adapter = create_page("http", raw=mock_session, url="https://example.com")
        assert adapter.title() == "Fetched"

    def test_playwright_with_raw_page(self) -> None:
        mock_page = MagicMock()
        adapter = create_page("playwright", raw=mock_page)
        assert adapter.backend_name == "playwright"
        assert adapter.raw is mock_page

    def test_selenium_with_raw_driver(self) -> None:
        mock_driver = MagicMock()
        adapter = create_page("selenium", raw=mock_driver)
        assert adapter.backend_name == "selenium"
        assert adapter.raw is mock_driver

    def test_undetected_with_raw_driver(self) -> None:
        mock_driver = MagicMock()
        adapter = create_page("undetected", raw=mock_driver)
        assert adapter.backend_name == "undetected"
        assert adapter.raw is mock_driver

    def test_playwright_no_raw_requires_import(self) -> None:
        with patch.dict("sys.modules", {"playwright": None, "playwright.sync_api": None}):
            with pytest.raises(ImportError, match="playwright"):
                create_page("playwright")

    def test_selenium_no_raw_requires_import(self) -> None:
        with patch.dict("sys.modules", {"selenium": None, "selenium.webdriver": None}):
            with pytest.raises(ImportError, match="selenium"):
                create_page("selenium")
