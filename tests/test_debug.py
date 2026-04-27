"""Tests for windshield.debug — snapshots and runtime capture."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from windshield.debug import (
    append_debug_jsonl,
    capture_page_snapshot,
    install_page_runtime_debug_capture,
    normalize_runtime_capture_text,
    snapshot_safe_name,
)


class FakePage:
    url = "https://example.test/login"
    frames: list[object] = []

    def __init__(self) -> None:
        self._listeners: dict[str, list[Any]] = {}

    def title(self) -> str:
        return "Login"

    def content(self) -> str:
        return "<html><body>login</body></html>"

    def screenshot(self, *, path: str, full_page: bool) -> None:
        Path(path).write_bytes(b"fake-png")

    def on(self, event: str, handler: Any) -> None:
        self._listeners.setdefault(event, []).append(handler)


class FakeConsoleMessage:
    def __init__(self) -> None:
        self.text = "blocked by challenge script"
        self.type = "warning"
        self.location = {
            "url": "https://example.test/app.js",
            "lineNumber": 12,
            "columnNumber": 3,
        }


class FakeRequest:
    def __init__(self) -> None:
        self.url = "https://example.test/api/login"
        self.method = "POST"
        self.resource_type = "xhr"

    def is_navigation_request(self) -> bool:
        return False

    def failure(self) -> dict[str, str]:
        return {"errorText": "net::ERR_BLOCKED_BY_CLIENT"}


class FakeResponse:
    def __init__(self) -> None:
        self.url = "https://example.test/api/login"
        self.status = 200
        self.ok = True
        self.request = FakeRequest()


class TestSnapshotSafeName:
    def test_sanitizes_special_characters(self) -> None:
        assert snapshot_safe_name("hello world!@#") == "hello_world"

    def test_empty_input(self) -> None:
        assert snapshot_safe_name("") == "snapshot"


class TestCapturePageSnapshot:
    def test_writes_html_json_and_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_dir = Path(tmp)
            capture_page_snapshot(FakePage(), snapshot_dir, "login-page")
            html_paths = sorted(snapshot_dir.glob("*.html"))
            meta_paths = sorted(snapshot_dir.glob("*.json"))
            png_paths = sorted(snapshot_dir.glob("*.png"))

            assert len(html_paths) == 1
            assert len(meta_paths) == 1
            assert len(png_paths) == 1

            meta = json.loads(meta_paths[0].read_text(encoding="utf-8"))
            assert meta["url"] == "https://example.test/login"
            assert meta["title"] == "Login"
            assert meta["screenshot_error"] == ""

    def test_skips_when_snapshot_dir_is_none(self) -> None:
        capture_page_snapshot(FakePage(), None, "should-skip")


class TestAppendDebugJsonl:
    def test_appends_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "debug.jsonl"
            append_debug_jsonl(path, {"event": "test1"})
            append_debug_jsonl(path, {"event": "test2"})
            lines = path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["event"] == "test1"

    def test_skips_none_path(self) -> None:
        append_debug_jsonl(None, {"event": "test"})


class TestNormalizeRuntimeCaptureText:
    def test_collapses_whitespace(self) -> None:
        assert normalize_runtime_capture_text("  hello   world  ") == "hello world"

    def test_truncates_long_text(self) -> None:
        long_text = "x" * 300
        result = normalize_runtime_capture_text(long_text, max_len=50)
        assert len(result) == 50
        assert result.endswith("...")


class TestInstallPageRuntimeDebugCapture:
    def test_installs_listeners_and_captures_events(self) -> None:
        page = FakePage()
        events: list[dict[str, Any]] = []
        install_page_runtime_debug_capture(page, events.append)

        assert hasattr(page, "_windshield_runtime_debug_capture_installed")
        assert page._windshield_runtime_debug_capture_installed is True

        # Trigger console event
        for handler in page._listeners.get("console", []):
            handler(FakeConsoleMessage())
        assert any(e["event"] == "console" for e in events)

        # Trigger request event
        for handler in page._listeners.get("request", []):
            handler(FakeRequest())
        assert any(e["event"] == "request" for e in events)

        # Trigger response event
        for handler in page._listeners.get("response", []):
            handler(FakeResponse())
        assert any(e["event"] == "response" for e in events)

        # Trigger requestfailed event
        for handler in page._listeners.get("requestfailed", []):
            handler(FakeRequest())
        assert any(e["event"] == "requestfailed" for e in events)

    def test_skips_reinstall(self) -> None:
        page = FakePage()
        events: list[dict[str, Any]] = []
        install_page_runtime_debug_capture(page, events.append)
        install_page_runtime_debug_capture(page, events.append)
        # Should only have one set of listeners
        assert len(page._listeners.get("console", [])) == 1
