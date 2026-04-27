"""Tests for windshield.challenge — challenge detection."""

from __future__ import annotations

from typing import Any

from windshield.challenge import (
    extract_reference_code_from_text,
    is_challenge_page,
)
from windshield.page import read_page_text


class FakeLocator:
    def __init__(self, count: int = 0, visible: bool = False) -> None:
        self._count = count
        self._visible = visible

    def count(self) -> int:
        return self._count

    def nth(self, idx: int) -> "FakeLocator":
        return self

    def is_visible(self) -> bool:
        return self._visible


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://example.test/login",
        title_text: str = "Login",
        body_text: str = "Welcome",
        content_html: str = "",
    ) -> None:
        self.url = url
        self._title = title_text
        self._body_text = body_text
        self._content_html = content_html or f"<html><body>{body_text}</body></html>"
        self.frames: list[Any] = []
        self.main_frame = None

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._content_html

    def locator(self, selector: str) -> FakeLocator:
        if selector == "body":
            return FakeBodyLocator(self._body_text)
        return FakeLocator()


class FakeBodyLocator:
    def __init__(self, text: str) -> None:
        self._text = text

    def inner_text(self, timeout: int = 2000) -> str:
        return self._text

    def count(self) -> int:
        return 1

    def nth(self, idx: int) -> "FakeBodyLocator":
        return self


class TestIsChallengePageCloudflareUrl:
    def test_detects_cf_chl_in_url(self) -> None:
        page = FakePage(url="https://example.test/?cf_chl_opt=something")
        assert is_challenge_page(page, [])

    def test_detects_cloudflare_challenge_url(self) -> None:
        page = FakePage(url="https://cloudflare.com/challenge/verify")
        assert is_challenge_page(page, [])

    def test_normal_page_not_challenge(self) -> None:
        page = FakePage(url="https://example.test/dashboard", body_text="Welcome back")
        assert not is_challenge_page(page, [])


class TestIsChallengePageSnippets:
    def test_detects_snippet_in_body(self) -> None:
        page = FakePage(body_text="Please verify you are human")
        assert is_challenge_page(page, ["verify you are human"])

    def test_detects_snippet_in_title(self) -> None:
        page = FakePage(title_text="Just a moment...")
        assert is_challenge_page(page, ["just a moment"])


class TestIsChallengePageContent:
    def test_detects_preauth_content(self) -> None:
        page = FakePage(content_html="<html>/cfi/preauthcontent/check</html>")
        assert is_challenge_page(page, [])


class TestExtractReferenceCode:
    def test_extracts_code(self) -> None:
        assert extract_reference_code_from_text("Reference code: 12345678") == "12345678"

    def test_returns_empty_when_no_code(self) -> None:
        assert extract_reference_code_from_text("No reference here") == ""

    def test_handles_various_formats(self) -> None:
        assert extract_reference_code_from_text("reference code #9876") == "9876"
        assert extract_reference_code_from_text("Reference Code-54321") == "54321"
