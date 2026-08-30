"""Tests for windshield.stealth — user agent rotation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from windshield.stealth import (
    DEFAULT_PLAYWRIGHT_STEALTH_SCRIPTS,
    DEFAULT_STEALTH_USER_AGENTS,
    install_playwright_stealth_scripts,
    normalize_selector_list,
    normalize_string_list,
    resolve_rotating_user_agent,
)


class TestInstallPlaywrightStealthScripts:
    def test_installs_default_scripts(self) -> None:
        context = MagicMock()

        installed = install_playwright_stealth_scripts(context)

        assert installed == len(DEFAULT_PLAYWRIGHT_STEALTH_SCRIPTS)
        context.add_init_script.assert_called_once_with(
            script=DEFAULT_PLAYWRIGHT_STEALTH_SCRIPTS[0]
        )

    def test_uses_caller_supplied_scripts_and_ignores_empty_sources(self) -> None:
        page = MagicMock()

        installed = install_playwright_stealth_scripts(page, scripts=(" one ", "", " two "))

        assert installed == 2
        assert page.add_init_script.call_args_list[0].kwargs == {"script": "one"}
        assert page.add_init_script.call_args_list[1].kwargs == {"script": "two"}

    def test_requires_playwright_init_script_target(self) -> None:
        try:
            install_playwright_stealth_scripts(object())
        except TypeError as exc:
            assert "add_init_script" in str(exc)
        else:  # pragma: no cover - makes the assertion failure explicit
            raise AssertionError("expected TypeError")

    def test_rejects_non_string_custom_script(self) -> None:
        try:
            install_playwright_stealth_scripts(MagicMock(), scripts=("valid", 2))  # type: ignore[arg-type]
        except TypeError as exc:
            assert "must be strings" in str(exc)
        else:  # pragma: no cover - makes the assertion failure explicit
            raise AssertionError("expected TypeError")


class TestNormalizeStringList:
    def test_merges_single_and_multi(self) -> None:
        result = normalize_string_list("single", ["multi1", "multi2"])
        assert result == ["multi1", "multi2", "single"]

    def test_deduplicates(self) -> None:
        result = normalize_string_list("a", ["a", "b", "a"])
        assert result == ["a", "b"]

    def test_empty_inputs(self) -> None:
        assert normalize_string_list("", []) == []


class TestNormalizeSelectorList:
    def test_delegates_to_normalize_string_list(self) -> None:
        result = normalize_selector_list("#a", ["#b", "#c"])
        assert "#a" in result
        assert "#b" in result


class TestResolveRotatingUserAgent:
    def test_returns_default_when_no_config(self) -> None:
        ua, source = resolve_rotating_user_agent({}, rotation_state_path=None)
        assert ua == DEFAULT_STEALTH_USER_AGENTS[0]
        assert "default" in source

    def test_uses_config_user_agent(self) -> None:
        ua, source = resolve_rotating_user_agent(
            {"user_agent": "CustomAgent/1.0"}, rotation_state_path=None
        )
        assert ua == "CustomAgent/1.0"
        assert "config" in source

    def test_rotates_with_state_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "ua_state.json"
            agents = ("Agent/1", "Agent/2", "Agent/3")

            ua1, _ = resolve_rotating_user_agent(
                {}, rotation_state_path=state_path, default_user_agents=agents
            )
            ua2, _ = resolve_rotating_user_agent(
                {}, rotation_state_path=state_path, default_user_agents=agents
            )
            ua3, _ = resolve_rotating_user_agent(
                {}, rotation_state_path=state_path, default_user_agents=agents
            )

            assert ua1 == "Agent/1"
            assert ua2 == "Agent/2"
            assert ua3 == "Agent/3"

            state = json.loads(state_path.read_text(encoding="utf-8"))
            assert state["next_index"] == 3

    def test_wraps_around(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "ua_state.json"
            agents = ("A", "B")

            resolve_rotating_user_agent(
                {}, rotation_state_path=state_path, default_user_agents=agents
            )
            resolve_rotating_user_agent(
                {}, rotation_state_path=state_path, default_user_agents=agents
            )
            ua3, _ = resolve_rotating_user_agent(
                {}, rotation_state_path=state_path, default_user_agents=agents
            )
            assert ua3 == "A"
