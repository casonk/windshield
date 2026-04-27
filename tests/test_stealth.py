"""Tests for windshield.stealth — user agent rotation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from windshield.stealth import (
    DEFAULT_STEALTH_USER_AGENTS,
    normalize_selector_list,
    normalize_string_list,
    resolve_rotating_user_agent,
)


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
