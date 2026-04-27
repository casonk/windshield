"""Tests for windshield.http — HTTP utilities."""

from __future__ import annotations

from windshield.http import (
    build_http_opener,
    describe_browser_location,
    match_browser_route,
    sanitize_error_text,
    sanitize_manual_guidance_text,
    url_contains_any_fragment,
)


class FakePage:
    def __init__(self, url: str = "", title_text: str = "") -> None:
        self.url = url
        self._title = title_text

    def title(self) -> str:
        return self._title


class TestBuildHttpOpener:
    def test_returns_opener_with_tls(self) -> None:
        opener = build_http_opener(verify_tls=True)
        assert opener is not None

    def test_returns_opener_without_tls(self) -> None:
        opener = build_http_opener(verify_tls=False)
        assert opener is not None


class TestUrlContainsAnyFragment:
    def test_matches_fragment(self) -> None:
        assert url_contains_any_fragment("https://example.com/dashboard", ["dashboard"])

    def test_no_match(self) -> None:
        assert not url_contains_any_fragment("https://example.com/home", ["dashboard"])

    def test_case_insensitive(self) -> None:
        assert url_contains_any_fragment("https://example.com/Dashboard", ["dashboard"])

    def test_empty_url(self) -> None:
        assert not url_contains_any_fragment("", ["dashboard"])


class TestMatchBrowserRoute:
    def test_matches_route(self) -> None:
        routes = {"login": ["/login", "/signin"], "dashboard": ["/dashboard"]}
        assert match_browser_route("https://example.com/login", routes) == "login"

    def test_no_match_returns_empty(self) -> None:
        routes = {"login": ["/login"]}
        assert match_browser_route("https://example.com/home", routes) == ""

    def test_none_routes(self) -> None:
        assert match_browser_route("https://example.com/", None) == ""


class TestDescribeBrowserLocation:
    def test_includes_url_and_title(self) -> None:
        page = FakePage(url="https://example.com/login", title_text="Login Page")
        result = describe_browser_location(page)
        assert "url=" in result
        assert "title=" in result

    def test_includes_route_when_matched(self) -> None:
        page = FakePage(url="https://example.com/login")
        routes = {"login": ["/login"]}
        result = describe_browser_location(page, routes)
        assert "route=login" in result


class TestSanitizeErrorText:
    def test_redacts_secrets(self) -> None:
        result = sanitize_error_text("password is s3cret123", ["s3cret123"])
        assert "s3cret123" not in result
        assert "***REDACTED***" in result


class TestSanitizeManualGuidanceText:
    def test_collapses_whitespace(self) -> None:
        assert sanitize_manual_guidance_text("  hello   world  ") == "hello world"

    def test_redacts_long_digit_sequences(self) -> None:
        result = sanitize_manual_guidance_text("code is 123456789")
        assert "[redacted-digits]" in result

    def test_truncates_long_text(self) -> None:
        result = sanitize_manual_guidance_text("x" * 300, max_len=50)
        assert len(result) == 50
