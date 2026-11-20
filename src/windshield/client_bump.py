"""Keep consumers' Python Playwright client on the newest version the container serves.

Consumers are registered, one interpreter path per line, in
``~/.config/windshield/consumers.txt`` (machine-specific, never tracked; ``#`` comments).
After a rotation promotes a newer version, :func:`bump_clients` installs it into each
interpreter that is behind, drives the container with it, and puts the previous version
back if that fails. A venv gets a plain install; a system interpreter gets ``--user``.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from windshield.client_matrix import _SMOKE, DEFAULT_ENDPOINT, Runner, _run, minor_of

_VERSION_CODE = "import importlib.metadata as m;print(m.version('playwright'))"
_IN_VENV_CODE = "import sys;print(int(sys.prefix != sys.base_prefix))"


@dataclass(frozen=True)
class Bump:
    interpreter: str
    before: str | None
    after: str | None
    status: str  # "current" | "bumped" | "restored" | "failed" | "skipped"
    detail: str = ""


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in minor_of(version).split("."))


def consumers_file(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    base = source.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(
        source.get("WINDSHIELD_CONSUMERS_FILE") or Path(base) / "windshield" / "consumers.txt"
    )


def read_consumers(env: Mapping[str, str] | None = None) -> list[str]:
    try:
        lines = consumers_file(env).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    found: list[str] = []
    for line in lines:
        text = line.split("#", 1)[0].strip()
        if text and text not in found:
            found.append(text)
    return found


def _installed(python: str, env: Mapping[str, str], runner: Runner) -> str | None:
    try:
        out = runner([python, "-c", _VERSION_CODE], env, 60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def _install(python: str, spec: str, env: Mapping[str, str], runner: Runner) -> bool:
    venv = runner([python, "-c", _IN_VENV_CODE], env, 60).stdout.strip() == "1"
    cmd = [
        python,
        "-m",
        "pip",
        "install",
        "-q",
        *([] if venv else ["--user"]),
        f"playwright=={spec}",
    ]
    return runner(cmd, env, 600).returncode == 0


def _smoke(
    python: str, version: str, endpoint: str, env: Mapping[str, str], runner: Runner
) -> bool:
    minor = minor_of(version)
    try:
        return (
            runner([python, "-c", _SMOKE, f"{endpoint.rstrip('/')}/{minor}"], env, 120).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def bump_clients(
    target: str,
    *,
    interpreters: Sequence[str] | None = None,
    endpoint: str = DEFAULT_ENDPOINT,
    env: Mapping[str, str] | None = None,
    runner: Runner = _run,
    log: Callable[[str], None] = print,
) -> list[Bump]:
    """Bring every registered interpreter up to ``target`` (never downgrades)."""
    source = dict(os.environ if env is None else env)
    results: list[Bump] = []
    for python in interpreters if interpreters is not None else read_consumers(source):
        before = _installed(python, source, runner)
        if before is None:
            results.append(Bump(python, None, None, "skipped", "playwright not installed"))
        elif _key(before) >= _key(target):
            results.append(Bump(python, before, before, "current"))
        elif not _install(python, f"{minor_of(target)}.*", source, runner):
            _install(python, before, source, runner)
            results.append(Bump(python, before, before, "failed", "pip install failed"))
        elif _smoke(python, target, endpoint, source, runner):
            results.append(Bump(python, before, target, "bumped"))
        else:
            _install(python, before, source, runner)
            results.append(
                Bump(python, before, before, "restored", f"{target} failed the smoke test")
            )
        log(
            f"client {python}: {results[-1].status} {results[-1].before} -> {results[-1].after} {results[-1].detail}".rstrip()
        )
    return results
