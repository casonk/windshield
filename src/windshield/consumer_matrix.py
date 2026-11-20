"""Run consumers' own browser test suites once per served Playwright version.

``client_matrix`` proves that each version's client can drive the container. This proves a
consumer's real tests pass on each of them: the suite runs with its usual interpreter, but
the version under test is put first on ``PYTHONPATH`` (from the cached client venv), and
``WINDSHIELD_PLAYWRIGHT_WS`` points at the container's ``/{version}`` route.

Suites are listed in ``~/.config/windshield/consumer-tests.json`` (machine-specific)::

    [{"name": "personal-finance", "cwd": "/path/to/repo", "python": "/path/to/.venv/bin/python",
      "command": ["{python}", "-m", "pytest", "-q", "tests/browser"], "timeout": 1200}]

``python -m windshield.consumer_matrix [--suite NAME] [--size N] [--endpoint ws://host:port]``.
A suite whose Python minor differs from windshield's gets its own client venvs built with
that interpreter (compiled dependencies must import there).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from windshield.client_matrix import (
    DEFAULT_ENDPOINT,
    MATRIX_MAX,
    MATRIX_MIN,
    Runner,
    _run,
    client_venv,
    ensure_client,
    matrix_size,
    select_versions,
)

DEFAULT_TIMEOUT = 1200

SuiteRunner = Callable[
    [Sequence[str], Mapping[str, str], str, int], "subprocess.CompletedProcess[str]"
]


def _run_in(cmd: Sequence[str], env: Mapping[str, str], cwd: str, timeout: int):
    return subprocess.run(  # noqa: S603
        list(cmd),
        env=dict(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass(frozen=True)
class Suite:
    name: str
    cwd: str
    python: str
    command: tuple[str, ...]
    timeout: int = DEFAULT_TIMEOUT
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    suite: str
    version: str
    status: str  # "passed" | "failed" | "skipped"
    detail: str = ""


def suites_file(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    base = source.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(
        source.get("WINDSHIELD_CONSUMER_TESTS_FILE")
        or Path(base) / "windshield" / "consumer-tests.json"
    )


def load_suites(env: Mapping[str, str] | None = None) -> list[Suite]:
    try:
        raw = json.loads(suites_file(env).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    suites = []
    for item in raw if isinstance(raw, list) else []:
        try:
            suites.append(
                Suite(
                    name=str(item["name"]),
                    cwd=str(item["cwd"]),
                    python=str(item["python"]),
                    command=tuple(str(c) for c in item["command"]),
                    timeout=int(item.get("timeout", DEFAULT_TIMEOUT)),
                    env=dict(item.get("env", {})),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return suites


def _site_packages(venv: Path) -> Path | None:
    found = sorted((venv / "lib").glob("python*/site-packages"))
    return found[0] if found else None


def _python_minor(python: str, env: Mapping[str, str], runner: Runner) -> str | None:
    code = 'import sys;print("%d.%d" % sys.version_info[:2])'
    try:
        out = runner([python, "-c", code], env, 60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def run_suite(
    suite: Suite,
    version: str,
    endpoint: str,
    env: Mapping[str, str],
    runner: Runner = _run,
    suite_runner: SuiteRunner = _run_in,
) -> Outcome:
    have = _python_minor(suite.python, env, runner)
    if have is None:
        return Outcome(suite.name, version, "failed", f"cannot run {suite.python}")
    own = f"{sys.version_info[0]}.{sys.version_info[1]}"
    other = None if have == own else have  # build with the suite's Python so compiled deps import
    try:
        ensure_client(
            version, env, runner, base_python=suite.python if other else None, python_minor=other
        )
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        return Outcome(suite.name, version, "failed", f"client unavailable: {exc}")
    site = _site_packages(client_venv(version, env, other))
    if site is None:
        return Outcome(suite.name, version, "failed", "client site-packages not found")
    run_env = {
        **env,
        **suite.env,
        "PYTHONPATH": os.pathsep.join(filter(None, [str(site), env.get("PYTHONPATH", "")])),
        "WINDSHIELD_PLAYWRIGHT_WS": f"{endpoint.rstrip('/')}/{{version}}",
        "WINDSHIELD_PLAYWRIGHT_STRICT": "1",
    }
    command = [part.replace("{python}", suite.python) for part in suite.command]
    try:
        result = suite_runner(command, run_env, suite.cwd, suite.timeout)
    except subprocess.TimeoutExpired:
        return Outcome(suite.name, version, "failed", f"timed out after {suite.timeout}s")
    except OSError as exc:
        return Outcome(suite.name, version, "failed", str(exc))
    tail = (result.stdout or result.stderr or "").strip().splitlines()
    return Outcome(
        suite.name,
        version,
        "passed" if result.returncode == 0 else "failed",
        tail[-1] if tail else "",
    )


def run_matrix(
    suites: Sequence[Suite],
    versions: Sequence[str],
    endpoint: str,
    *,
    size: int | None = None,
    env: Mapping[str, str] | None = None,
    runner: Runner = _run,
    suite_runner: SuiteRunner = _run_in,
) -> list[Outcome]:
    source = dict(os.environ if env is None else env)
    chosen = select_versions(versions, size if size is not None else matrix_size(source))
    return [run_suite(s, v, endpoint, source, runner, suite_runner) for s in suites for v in chosen]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--suite", action="append", help="only these suites (repeatable)")
    parser.add_argument("--versions", help="space/comma separated; default: served versions")
    parser.add_argument("--size", type=int, help=f"last N versions ({MATRIX_MIN}-{MATRIX_MAX})")
    args = parser.parse_args(argv)
    suites = [s for s in load_suites() if not args.suite or s.name in args.suite]
    if not suites:
        print(f"no suites configured in {suites_file()}")
        return 1
    if args.versions:
        versions = args.versions.replace(",", " ").split()
    else:
        from windshield.container_rotation import load_state, state_dir

        versions = load_state(Path(__file__).resolve().parents[2], state_dir()).versions
    size = max(MATRIX_MIN, min(MATRIX_MAX, args.size)) if args.size else None
    outcomes = run_matrix(suites, versions, args.endpoint, size=size)
    for o in outcomes:
        print(f"{o.status.upper():7} {o.suite} on playwright {o.version}  {o.detail}")
    return 0 if outcomes and all(o.status != "failed" for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
