"""Opt-in real Chromium coverage for the synchronous Playwright adapter."""

from __future__ import annotations

import pytest

from windshield.adapters._playwright import PlaywrightPageAdapter
from windshield.page import click_first_visible, fill_first_visible


def test_playwright_adapter_drives_a_real_chromium_document() -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except sync_api.Error as exc:
                pytest.skip(f"Chromium is unavailable: {exc}")
            try:
                raw_page = browser.new_page()
                raw_page.set_content("""
                    <input id="name" />
                    <button id="save" onclick="document.querySelector('#result').textContent = document.querySelector('#name').value">
                      Save
                    </button>
                    <output id="result"></output>
                    """)
                page = PlaywrightPageAdapter(raw_page)

                assert fill_first_visible(page, ["#name"], "Ada", "name") == "#name"
                assert click_first_visible(page, ["#save"], "save") == "#save"
                assert page.locator("#result").inner_text() == "Ada"
            finally:
                browser.close()
    except sync_api.Error as exc:
        pytest.skip(f"Playwright could not start: {exc}")
