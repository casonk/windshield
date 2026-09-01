"""Safe local directory management for separate Chrome user-data profiles."""

from __future__ import annotations

import re
from pathlib import Path

from windshield._errors import WindshieldError

_PROFILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ProfileManager:
    """Manage named, isolated Chrome user-data directories below one root.

    A managed directory is suitable for the existing ``profile_dir`` argument
    of the Selenium and undetected Chrome adapters. Existing Chrome profiles
    are never imported, altered, or removed by this class.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve()

    @property
    def root(self) -> Path:
        """Absolute directory containing managed profile directories."""
        return self._root

    def profile_dir(self, name: str) -> Path:
        """Return the managed directory for *name* without creating it."""
        normalized = self._validate_name(name)
        candidate = (self._root / normalized).resolve()
        if candidate.parent != self._root:
            raise WindshieldError(f"invalid_profile_name: {name!r}")
        return candidate

    def exists(self, name: str) -> bool:
        """Return whether *name* already has a managed directory."""
        return self.profile_dir(name).is_dir()

    def create(self, name: str) -> Path:
        """Create and return an empty managed profile directory."""
        directory = self.profile_dir(name)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def list_profiles(self) -> list[str]:
        """Return valid managed profile names in deterministic order."""
        if not self._root.is_dir():
            return []
        return sorted(
            entry.name
            for entry in self._root.iterdir()
            if entry.is_dir() and _PROFILE_NAME.fullmatch(entry.name)
        )

    @staticmethod
    def _validate_name(name: str) -> str:
        normalized = str(name).strip()
        if not _PROFILE_NAME.fullmatch(normalized):
            raise WindshieldError(
                "invalid_profile_name: use 1-64 ASCII letters, digits, dots, underscores, or hyphens"
            )
        return normalized
