"""Tests for windshield.page — page interaction primitives."""

from __future__ import annotations

from typing import Any

import pytest

from windshield._errors import WindshieldError
from windshield.page import (
    click_first_visible,
    fill_first_visible,
    first_visible_selector_match,
    has_any_selector,
    is_page_or_context_closed_error,
    iter_locator_contexts,
    iter_page_frames,
    matching_text_snippets,
    page_contains_any_text,
    read_page_text,
    title_contains_any_text,
    wait_for_any_selector,
)


class FakeLocatorItem:
    def __init__(self, *, visible: bool = True, enabled: bool = True, text: str = "") -> None:
        self._visible = visible
        self._enabled = enabled
        self._text = text
        self._filled = ""
        self._clicked = False

    def is_visible(self) -> bool:
        return self._visible

    def is_enabled(self) -> bool:
        return self._enabled

    def fill(self, value: str) -> None:
        self._filled = value

    def click(self, **kwargs: Any) -> None:
        self._clicked = True

    def press(self, key: str) -> None:
        pass

    def type(self, text: str, delay: int = 0) -> None:
        self._filled = text

    def evaluate(self, expr: str, *args: Any) -> Any:
        return self._text

    def input_value(self) -> str:
        return self._filled

    def inner_text(self, timeout: int = 2000) -> str:
        return self._text

    def get_attribute(self, name: str) -> str:
        return ""


class FakeLocator:
    def __init__(self, items: list[FakeLocatorItem] | None = None) -> None:
        self._items = items or []

    def count(self) -> int:
        return len(self._items)

    def nth(self, idx: int) -> FakeLocatorItem:
        return self._items[idx]


class FakePage:
    def __init__(
        self,
        *,
        url: str = "https://example.test/page",
        title_text: str = "Test Page",
        body_text: str = "Hello World",
        locators: dict[str, FakeLocator] | None = None,
    ) -> None:
        self.url = url
        self._title = title_text
        self._body_text = body_text
        self._locators = locators or {}
        self.frames: list[Any] = []
        self.main_frame = None

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return f"<html><body>{self._body_text}</body></html>"

    def locator(self, selector: str) -> FakeLocator:
        return self._locators.get(selector, FakeLocator())

    def wait_for_timeout(self, ms: int) -> None:
        pass


class TestIsPageOrContextClosedError:
    def test_detects_closed_page(self) -> None:
        assert is_page_or_context_closed_error(
            Exception("Target page, context or browser has been closed")
        )

    def test_ignores_other_errors(self) -> None:
        assert not is_page_or_context_closed_error(Exception("some other error"))


class TestIterLocatorContexts:
    def test_returns_main_page_context(self) -> None:
        page = FakePage()
        contexts = iter_locator_contexts(page)
        assert len(contexts) == 1
        assert contexts[0][0] == "main"


class TestIterPageFrames:
    def test_returns_page_when_no_frames(self) -> None:
        page = FakePage()
        frames = iter_page_frames(page)
        assert len(frames) == 1
        assert frames[0] is page


class TestReadPageText:
    def test_reads_body_text(self) -> None:
        item = FakeLocatorItem(text="Hello World")
        page = FakePage(locators={"body": FakeLocator([item])})
        text = read_page_text(page)
        assert "Hello World" in text


class TestTitleContainsAnyText:
    def test_finds_matching_title(self) -> None:
        page = FakePage(title_text="My Dashboard")
        assert title_contains_any_text(page, ["dashboard"])

    def test_returns_false_for_no_match(self) -> None:
        page = FakePage(title_text="My Dashboard")
        assert not title_contains_any_text(page, ["settings"])


class TestPageContainsAnyText:
    def test_finds_text_in_body(self) -> None:
        page = FakePage(body_text="Welcome to the dashboard")
        assert page_contains_any_text(page, ["dashboard"])


class TestMatchingTextSnippets:
    def test_returns_matching_snippets(self) -> None:
        page = FakePage(body_text="Welcome to the dashboard settings")
        result = matching_text_snippets(page, ["dashboard", "settings", "missing"])
        assert "dashboard" in result
        assert "settings" in result
        assert "missing" not in result


class TestHasAnySelector:
    def test_returns_true_when_selector_matches(self) -> None:
        item = FakeLocatorItem()
        page = FakePage(locators={"#btn": FakeLocator([item])})
        assert has_any_selector(page, ["#btn"])

    def test_returns_false_when_no_match(self) -> None:
        page = FakePage()
        assert not has_any_selector(page, ["#nonexistent"])


class TestFirstVisibleSelectorMatch:
    def test_returns_selector_when_visible(self) -> None:
        item = FakeLocatorItem(visible=True)
        page = FakePage(locators={"#btn": FakeLocator([item])})
        result = first_visible_selector_match(page, ["#btn"])
        assert "#btn" in result

    def test_returns_empty_when_not_visible(self) -> None:
        item = FakeLocatorItem(visible=False)
        page = FakePage(locators={"#btn": FakeLocator([item])})
        result = first_visible_selector_match(page, ["#btn"])
        assert result == ""


class TestFillFirstVisible:
    def test_fills_visible_input(self) -> None:
        item = FakeLocatorItem(visible=True, enabled=True)
        page = FakePage(locators={"#user": FakeLocator([item])})
        result = fill_first_visible(page, ["#user"], "testuser", "username")
        assert result == "#user"
        assert item._filled == "testuser"

    def test_raises_when_no_match(self) -> None:
        page = FakePage()
        with pytest.raises(WindshieldError, match="no visible editable element"):
            fill_first_visible(page, ["#user"], "testuser", "username")


class TestClickFirstVisible:
    def test_clicks_visible_button(self) -> None:
        item = FakeLocatorItem(visible=True, enabled=True)
        page = FakePage(locators={"#btn": FakeLocator([item])})
        result = click_first_visible(page, ["#btn"], "submit")
        assert result == "#btn"
        assert item._clicked

    def test_raises_when_no_match(self) -> None:
        page = FakePage()
        with pytest.raises(WindshieldError, match="no visible clickable element"):
            click_first_visible(page, ["#btn"], "submit")


class TestWaitForAnySelector:
    def test_returns_immediately_when_attached(self) -> None:
        item = FakeLocatorItem()
        page = FakePage(locators={"#el": FakeLocator([item])})
        result = wait_for_any_selector(
            page, ["#el"], timeout_ms=1000, state="attached", field_name="test"
        )
        assert result == "#el"

    def test_raises_on_timeout(self) -> None:
        page = FakePage()
        with pytest.raises(WindshieldError, match="timeout"):
            wait_for_any_selector(
                page, ["#missing"], timeout_ms=100, state="attached", field_name="test"
            )
