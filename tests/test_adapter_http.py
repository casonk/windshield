"""Tests for the HTTP-only adapter."""

from unittest.mock import MagicMock

import pytest

from windshield.adapters._protocol import UnsupportedOperationError


def test_page_from_html():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(
        html="<html><head><title>Test</title></head><body><p>Hello</p></body></html>"
    )
    assert adapter.title() == "Test"
    assert adapter.backend_name == "http"
    assert "Hello" in adapter.content()


def test_locator_count():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<div class='item'>A</div><div class='item'>B</div>")
    assert adapter.locator("div.item").count() == 2


def test_locator_text():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<p id='msg'>Hello World</p>")
    assert adapter.locator("#msg").inner_text() == "Hello World"


def test_evaluate_raises():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<p>test</p>")
    with pytest.raises(UnsupportedOperationError):
        adapter.evaluate("1 + 1")


def test_screenshot_raises():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<p>test</p>")
    with pytest.raises(UnsupportedOperationError):
        adapter.screenshot()


def test_input_value():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html='<input id="name" value="Alice">')
    assert adapter.locator("#name").input_value() == "Alice"


def test_fill_updates_value():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html='<input id="name" value="">')
    adapter.locator("#name").fill("Bob")
    assert adapter.locator("#name").input_value() == "Bob"


def test_locator_nth():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<li>A</li><li>B</li><li>C</li>")
    assert adapter.locator("li").nth(1).inner_text() == "B"


def test_locator_is_visible():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<p>exists</p>")
    assert adapter.locator("p").is_visible() is True
    assert adapter.locator("span").is_visible() is False


def test_goto_fetches_url():
    from windshield.adapters._http import HttpPageAdapter

    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "<html><title>Fetched</title></html>"
    mock_response.url = "https://example.com"
    mock_session.get.return_value = mock_response

    adapter = HttpPageAdapter(session=mock_session)
    adapter.goto("https://example.com")
    assert adapter.title() == "Fetched"
    assert adapter.url == "https://example.com"


def test_locator_evaluate_raises():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<p>test</p>")
    with pytest.raises(UnsupportedOperationError):
        adapter.locator("p").evaluate("el => el.textContent")


def test_locator_is_enabled():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html='<input id="a"><input id="b" disabled>')
    assert adapter.locator("#a").is_enabled() is True
    assert adapter.locator("#b").is_enabled() is False


def test_text_content():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html="<p> spaced </p>")
    assert adapter.locator("p").text_content() == " spaced "
    assert adapter.locator("missing").text_content() is None


def test_get_attribute():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(html='<a href="/link">go</a>')
    assert adapter.locator("a").get_attribute("href") == "/link"
    assert adapter.locator("a").get_attribute("missing") is None


def test_frames():
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(
        html='<iframe src="https://x.com/f" name="f1"></iframe><iframe></iframe>'
    )
    f = adapter.frames()
    assert len(f) == 1
    assert f[0].url == "https://x.com/f"
    assert f[0].name == "f1"


def test_close():
    mock_session = MagicMock()
    from windshield.adapters._http import HttpPageAdapter

    adapter = HttpPageAdapter(session=mock_session)
    adapter.close()
    mock_session.close.assert_called_once()
