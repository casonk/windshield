"""Chrome binary discovery, Chrome for Testing download, and CDP helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from windshield._errors import WindshieldError

CHROME_FOR_TESTING_LKG_URL = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "last-known-good-versions-with-downloads.json"
)

DEFAULT_USER_AGENT = "windshield/0.1"


def fetch_cdp_version(host: str, port: int, timeout_seconds: float = 1.5) -> dict[str, Any] | None:
    """Query a Chrome DevTools Protocol endpoint for version info."""
    url = f"http://{host}:{int(port)}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=float(timeout_seconds)) as response:
            payload = response.read().decode("utf-8", errors="ignore")
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # pylint: disable=broad-except
        return None
    return None


def wait_for_cdp_version(
    host: str,
    port: int,
    timeout_seconds: int,
    poll_interval_seconds: float = 0.25,
) -> dict[str, Any]:
    """Poll until a CDP server is ready and return its version payload."""
    deadline = time.monotonic() + max(1, int(timeout_seconds))
    while time.monotonic() < deadline:
        payload = fetch_cdp_version(host, port, timeout_seconds=1.5)
        if payload is not None:
            return payload
        time.sleep(max(0.1, float(poll_interval_seconds)))
    raise WindshieldError(
        f"chrome_cdp_not_ready: host={host}; port={port}; timeout_seconds={timeout_seconds}"
    )


def fetch_json_url(
    url: str, timeout_seconds: int = 45, user_agent: str = DEFAULT_USER_AGENT
) -> dict[str, Any]:
    """Fetch a JSON URL and return the parsed dict."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
            raw = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # pylint: disable=broad-except
        raise WindshieldError(f"json_fetch_failed: {type(exc).__name__}: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except Exception as exc:  # pylint: disable=broad-except
        raise WindshieldError(f"json_parse_failed: {type(exc).__name__}") from exc
    if not isinstance(parsed, dict):
        raise WindshieldError("json_parse_failed: expected object")
    return parsed


def resolve_cft_download_url(
    channel: str = "Stable",
    platform: str = "linux64",
) -> tuple[str, str]:
    """Resolve the Chrome for Testing download URL for a given channel/platform."""
    payload = fetch_json_url(CHROME_FOR_TESTING_LKG_URL, timeout_seconds=45)
    channels = payload.get("channels", {})
    if not isinstance(channels, dict):
        raise WindshieldError("chrome_download_metadata_missing_channels")
    channel_payload = channels.get(channel)
    if not isinstance(channel_payload, dict):
        fallback_payload = channels.get("Stable")
        if not isinstance(fallback_payload, dict):
            raise WindshieldError(f"chrome_download_channel_not_found: channel={channel}")
        channel_payload = fallback_payload
        channel = "Stable"

    downloads = channel_payload.get("downloads", {})
    if not isinstance(downloads, dict):
        raise WindshieldError("chrome_download_metadata_missing_downloads")
    chrome_downloads = downloads.get("chrome", [])
    if not isinstance(chrome_downloads, list):
        raise WindshieldError("chrome_download_metadata_missing_chrome_downloads")
    for item in chrome_downloads:
        if not isinstance(item, dict):
            continue
        if str(item.get("platform", "")).strip() != platform:
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        version = str(channel_payload.get("version", "")).strip() or "unknown"
        return url, version
    raise WindshieldError(f"chrome_download_url_not_found: channel={channel}; platform={platform}")


def download_url_to_file(
    url: str,
    target_path: Path,
    timeout_seconds: int = 120,
    user_agent: str = DEFAULT_USER_AGENT,
) -> None:
    """Download a URL to a local file."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
            payload = response.read()
    except Exception as exc:  # pylint: disable=broad-except
        raise WindshieldError(f"download_failed: url={url}; {type(exc).__name__}: {exc}") from exc
    target_path.write_bytes(payload)


def extract_zip_with_permissions(archive_path: Path, extract_dir: Path) -> None:
    """Extract a zip archive preserving Unix file permissions."""
    with zipfile.ZipFile(archive_path, "r") as zip_ref:
        for member in zip_ref.infolist():
            zip_ref.extract(member, path=extract_dir)
            mode = (member.external_attr >> 16) & 0o777
            if mode <= 0:
                continue
            target_path = extract_dir / member.filename
            try:
                if target_path.exists() and target_path.is_file():
                    target_path.chmod(mode)
            except Exception:  # pylint: disable=broad-except
                continue


def ensure_chrome_runtime_permissions(executable_path: Path) -> None:
    """Ensure Chrome binary and companion files are executable."""
    bin_dir = executable_path.parent
    candidates = [
        executable_path,
        bin_dir / "chrome_crashpad_handler",
        bin_dir / "chrome-wrapper",
        bin_dir / "chrome_sandbox",
        bin_dir / "chrome-sandbox",
    ]
    for candidate in candidates:
        try:
            if not candidate.exists() or not candidate.is_file():
                continue
            current_mode = candidate.stat().st_mode & 0o777
            if (current_mode & 0o111) == 0:
                candidate.chmod(current_mode | 0o111)
        except Exception:  # pylint: disable=broad-except
            continue


def chrome_executable_from_dir(base_dir: Path) -> str:
    """Locate the Chrome executable within a Chrome for Testing directory."""
    candidates = [
        base_dir / "chrome-linux64" / "chrome",
        base_dir / "chrome-linux" / "chrome",
    ]
    for candidate in candidates:
        if candidate.exists():
            ensure_chrome_runtime_permissions(candidate)
            return str(candidate)
    return ""


def find_existing_cft_executable(download_dir: Path) -> str:
    """Find a previously downloaded Chrome for Testing executable."""
    candidates: list[Path] = []
    candidates.extend(sorted(download_dir.glob("chrome-*/chrome-linux64/chrome")))
    candidates.extend(sorted(download_dir.glob("chrome-*/chrome-linux/chrome")))
    for candidate in reversed(candidates):
        if candidate.exists():
            ensure_chrome_runtime_permissions(candidate)
            return str(candidate)
    return ""


def download_chrome_for_testing(
    download_dir: Path | None = None,
    channel: str = "Stable",
    platform: str = "linux64",
    force_download: bool = False,
    default_download_dir: Path | None = None,
) -> str:
    """Download Chrome for Testing and return the executable path.

    Args:
        download_dir: Where to store Chrome binaries. Falls back to default_download_dir.
        channel: Chrome release channel (default: "Stable").
        platform: Target platform (default: "linux64").
        force_download: Re-download even if a binary exists.
        default_download_dir: Default directory if download_dir is None.
    """
    fallback = default_download_dir or Path.cwd() / "chrome-for-testing"
    target_dir = (download_dir or fallback).expanduser()
    if not target_dir.is_absolute():
        target_dir = Path.cwd() / target_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    if not force_download:
        existing_any = find_existing_cft_executable(target_dir)
        if existing_any:
            return existing_any

    url, version = resolve_cft_download_url(channel=channel, platform=platform)
    version_tag = re.sub(r"[^A-Za-z0-9._-]+", "-", version) or "unknown"
    extract_dir = target_dir / f"chrome-{channel.lower()}-{version_tag}-{platform}"
    existing_executable = chrome_executable_from_dir(extract_dir)
    if existing_executable and not force_download:
        return existing_executable

    archive_path = target_dir / f"chrome-{channel.lower()}-{version_tag}-{platform}.zip"
    if force_download or not archive_path.exists():
        download_url_to_file(url, archive_path, timeout_seconds=180)
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        extract_zip_with_permissions(archive_path, extract_dir)
    except Exception as exc:  # pylint: disable=broad-except
        raise WindshieldError(f"chrome_extract_failed: {type(exc).__name__}: {exc}") from exc

    executable = chrome_executable_from_dir(extract_dir)
    if not executable:
        raise WindshieldError(f"chrome_executable_not_found_after_extract: dir={extract_dir}")
    return executable


def discover_chrome_binary(
    env_var: str = "CHROME_BIN",
    default_download_dir: Path | None = None,
) -> str:
    """Discover a Chrome/Chromium binary from the environment, PATH, or cached downloads.

    Args:
        env_var: Environment variable name pointing to a Chrome binary.
        default_download_dir: Directory to search for Chrome for Testing downloads.
    """
    env_bin = str(os.getenv(env_var, "")).strip()
    if env_bin:
        env_path = Path(env_bin).expanduser()
        if not env_path.is_absolute():
            resolved = shutil.which(str(env_path))
            if resolved:
                return resolved
        elif env_path.exists():
            return str(env_path)

    for candidate in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    if default_download_dir is not None:
        cft_default_exe = chrome_executable_from_dir(default_download_dir)
        if cft_default_exe:
            return cft_default_exe
        cft_candidates = sorted(default_download_dir.glob("chrome-*/chrome-linux64/chrome"))
        if not cft_candidates:
            cft_candidates = sorted(default_download_dir.glob("chrome-*/chrome-linux/chrome"))
        if cft_candidates:
            return str(cft_candidates[-1])

    home = Path.home()
    discovered: list[Path] = []
    discovered.extend(sorted(home.glob(".cache/ms-playwright/chromium-*/chrome-linux/chrome")))
    discovered.extend(sorted(home.glob(".cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    discovered = [path for path in discovered if path.exists()]
    if discovered:
        discovered.sort(key=lambda path: str(path))
        return str(discovered[-1])

    return ""
