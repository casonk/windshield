"""Page snapshots, runtime event capture, and JSONL debug logging."""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def snapshot_safe_name(value: str) -> str:
    """Sanitize a string for use as a snapshot filename stem."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "snapshot"


def write_text(path: Path, text: str) -> None:
    """Write text to a file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def capture_page_snapshot(
    page: Any,
    snapshot_dir: Path | None,
    label: str,
) -> None:
    """Save a page snapshot: HTML content, metadata JSON, and PNG screenshot."""
    if snapshot_dir is None:
        return
    try:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        stem = snapshot_safe_name(f"{ts}_{label}")
        html_path = snapshot_dir / f"{stem}.html"
        meta_path = snapshot_dir / f"{stem}.json"
        screenshot_path = snapshot_dir / f"{stem}.png"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        page_url = str(getattr(page, "url", "") or "")
        try:
            title = str(page.title())
        except Exception:  # pylint: disable=broad-except
            title = ""
        frame_urls: list[str] = []
        try:
            for frame in page.frames:
                frame_urls.append(str(getattr(frame, "url", "") or ""))
        except Exception:  # pylint: disable=broad-except
            pass
        try:
            html = str(page.content() or "")
        except Exception:  # pylint: disable=broad-except
            html = ""
        screenshot_error = ""
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as exc:  # pylint: disable=broad-except
            screenshot_error = f"{type(exc).__name__}: {exc}"

        write_text(
            meta_path,
            json.dumps(
                {
                    "label": label,
                    "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "url": page_url,
                    "title": title,
                    "frame_urls": frame_urls,
                    "screenshot_path": (str(screenshot_path) if screenshot_path.exists() else ""),
                    "screenshot_error": screenshot_error,
                },
                ensure_ascii=True,
                indent=2,
            )
            + "\n",
        )
        write_text(html_path, html)
    except Exception:  # pylint: disable=broad-except
        return


def append_debug_jsonl(path: Path | None, payload: dict[str, Any]) -> None:
    """Append a JSON object as a line to a JSONL debug log file."""
    if path is None or not isinstance(payload, dict):
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:  # pylint: disable=broad-except
        return


def normalize_runtime_capture_text(value: Any, max_len: int = 260) -> str:
    """Collapse whitespace and truncate text for debug event payloads."""
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def install_page_runtime_debug_capture(
    page: Any,
    record_event: Callable[[dict[str, Any]], None],
) -> None:
    """Install Playwright event listeners for console, errors, requests, and responses.

    Events are normalized and forwarded to ``record_event``.
    """
    if page is None:
        return
    try:
        if bool(getattr(page, "_windshield_runtime_debug_capture_installed", False)):
            return
    except Exception:  # pylint: disable=broad-except
        pass

    def emit(payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        normalized: dict[str, Any] = {}
        for key in (
            "event",
            "type",
            "text",
            "url",
            "method",
            "resource_type",
            "failure",
            "source",
            "step",
        ):
            if key in payload:
                normalized[key] = normalize_runtime_capture_text(payload.get(key))
        for key in ("status", "ok", "navigation"):
            if key in payload:
                normalized[key] = payload.get(key)
        if "location" in payload and isinstance(payload.get("location"), dict):
            location = payload.get("location") or {}
            normalized["location"] = {
                "url": normalize_runtime_capture_text(location.get("url")),
                "lineNumber": location.get("lineNumber"),
                "columnNumber": location.get("columnNumber"),
            }
        normalized["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        record_event(normalized)

    def on_console(message: Any) -> None:
        text_value = ""
        message_type = ""
        location: dict[str, Any] = {}
        try:
            text_value = str(message.text or "")
        except Exception:  # pylint: disable=broad-except
            text_value = ""
        try:
            message_type = str(message.type or "")
        except Exception:  # pylint: disable=broad-except
            message_type = ""
        try:
            location = dict(message.location or {})
        except Exception:  # pylint: disable=broad-except
            location = {}
        emit(
            {
                "event": "console",
                "type": message_type,
                "text": text_value,
                "location": location,
            }
        )

    def on_pageerror(error: Any) -> None:
        emit(
            {
                "event": "pageerror",
                "text": str(error or ""),
            }
        )

    def on_request(request: Any) -> None:
        navigation = False
        try:
            navigation = bool(request.is_navigation_request())
        except Exception:  # pylint: disable=broad-except
            navigation = False
        emit(
            {
                "event": "request",
                "url": str(getattr(request, "url", "") or ""),
                "method": str(getattr(request, "method", "") or ""),
                "resource_type": str(getattr(request, "resource_type", "") or ""),
                "navigation": navigation,
            }
        )

    def on_response(response: Any) -> None:
        request = None
        try:
            request = response.request
        except Exception:  # pylint: disable=broad-except
            request = None
        emit(
            {
                "event": "response",
                "url": str(getattr(response, "url", "") or ""),
                "status": getattr(response, "status", None),
                "ok": bool(getattr(response, "ok", False)),
                "method": str(getattr(request, "method", "") or ""),
                "resource_type": str(getattr(request, "resource_type", "") or ""),
            }
        )

    def on_requestfailed(request: Any) -> None:
        failure = ""
        try:
            failure_obj = request.failure
            if callable(failure_obj):
                failure_obj = failure_obj()
            if isinstance(failure_obj, dict):
                failure = str(failure_obj.get("errorText", "") or "")
            elif failure_obj is not None:
                failure = str(failure_obj)
        except Exception:  # pylint: disable=broad-except
            failure = ""
        emit(
            {
                "event": "requestfailed",
                "url": str(getattr(request, "url", "") or ""),
                "method": str(getattr(request, "method", "") or ""),
                "resource_type": str(getattr(request, "resource_type", "") or ""),
                "failure": failure,
            }
        )

    with contextlib.suppress(Exception):
        page.on("console", on_console)
    with contextlib.suppress(Exception):
        page.on("pageerror", on_pageerror)
    with contextlib.suppress(Exception):
        page.on("request", on_request)
    with contextlib.suppress(Exception):
        page.on("response", on_response)
    with contextlib.suppress(Exception):
        page.on("requestfailed", on_requestfailed)
    with contextlib.suppress(Exception):
        page._windshield_runtime_debug_capture_installed = True
