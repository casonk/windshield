"""Tests for named Chrome user-data profile management."""

from __future__ import annotations

import pytest

from windshield import ProfileManager, WindshieldError


def test_creates_and_lists_isolated_profiles(tmp_path) -> None:  # noqa: ANN001
    manager = ProfileManager(tmp_path / "profiles")

    work = manager.create("work")
    personal = manager.create("personal")

    assert work == (tmp_path / "profiles" / "work").resolve()
    assert personal == (tmp_path / "profiles" / "personal").resolve()
    assert manager.exists("work") is True
    assert manager.list_profiles() == ["personal", "work"]


def test_profile_dir_does_not_create_directory(tmp_path) -> None:  # noqa: ANN001
    manager = ProfileManager(tmp_path / "profiles")

    assert manager.profile_dir("research") == (tmp_path / "profiles" / "research").resolve()
    assert manager.exists("research") is False
    assert manager.list_profiles() == []


@pytest.mark.parametrize("name", ["", "../escape", "two words", ".hidden", "a/b"])
def test_rejects_unsafe_profile_names(tmp_path, name: str) -> None:  # noqa: ANN001
    manager = ProfileManager(tmp_path / "profiles")

    with pytest.raises(WindshieldError, match="invalid_profile_name"):
        manager.profile_dir(name)
