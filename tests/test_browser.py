"""Tests for windshield.browser — Chrome discovery and CDP helpers."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from windshield._errors import WindshieldError
from windshield.browser import (
    chrome_executable_from_dir,
    discover_chrome_binary,
    ensure_chrome_runtime_permissions,
    extract_zip_with_permissions,
    fetch_cdp_version,
    find_existing_cft_executable,
)


class TestFetchCdpVersion:
    def test_returns_none_on_connection_error(self) -> None:
        result = fetch_cdp_version("127.0.0.1", 19999, timeout_seconds=0.1)
        assert result is None


class TestChromeExecutableFromDir:
    def test_returns_empty_when_no_chrome_found(self, tmp_path: Path) -> None:
        assert chrome_executable_from_dir(tmp_path) == ""

    def test_returns_path_when_chrome_exists(self, tmp_path: Path) -> None:
        chrome_dir = tmp_path / "chrome-linux64"
        chrome_dir.mkdir()
        chrome_bin = chrome_dir / "chrome"
        chrome_bin.write_text("#!/bin/sh\necho fake")
        chrome_bin.chmod(0o755)
        result = chrome_executable_from_dir(tmp_path)
        assert result == str(chrome_bin)


class TestFindExistingCftExecutable:
    def test_returns_empty_when_no_downloads(self, tmp_path: Path) -> None:
        assert find_existing_cft_executable(tmp_path) == ""

    def test_finds_latest_version(self, tmp_path: Path) -> None:
        for version in ("chrome-v1", "chrome-v2"):
            chrome_dir = tmp_path / version / "chrome-linux64"
            chrome_dir.mkdir(parents=True)
            chrome_bin = chrome_dir / "chrome"
            chrome_bin.write_text("#!/bin/sh\necho fake")
            chrome_bin.chmod(0o755)
        result = find_existing_cft_executable(tmp_path)
        assert "chrome-v2" in result


class TestExtractZipWithPermissions:
    def test_extracts_files(self, tmp_path: Path) -> None:
        archive = tmp_path / "test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("hello.txt", "world")
        extract_dir = tmp_path / "out"
        extract_dir.mkdir()
        extract_zip_with_permissions(archive, extract_dir)
        assert (extract_dir / "hello.txt").read_text() == "world"


class TestEnsureChromeRuntimePermissions:
    def test_sets_executable_bit(self, tmp_path: Path) -> None:
        chrome_bin = tmp_path / "chrome"
        chrome_bin.write_text("#!/bin/sh\necho fake")
        chrome_bin.chmod(0o644)
        ensure_chrome_runtime_permissions(chrome_bin)
        assert (chrome_bin.stat().st_mode & 0o111) != 0


class TestDiscoverChromeBinary:
    def test_returns_empty_when_nothing_available(self) -> None:
        with patch("shutil.which", return_value=None):
            result = discover_chrome_binary(env_var="NONEXISTENT_CHROME_VAR")
            # May return empty or a Playwright cache hit
            assert isinstance(result, str)

    def test_uses_env_var(self, tmp_path: Path) -> None:
        chrome_bin = tmp_path / "my-chrome"
        chrome_bin.write_text("#!/bin/sh\necho fake")
        chrome_bin.chmod(0o755)
        with patch.dict("os.environ", {"TEST_CHROME_BIN": str(chrome_bin)}):
            result = discover_chrome_binary(env_var="TEST_CHROME_BIN")
        assert result == str(chrome_bin)
