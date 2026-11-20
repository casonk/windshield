"""Test the Python client of each of the last few Playwright versions against the container.

The container's own smoke test drives every served version with that version's *Node*
client. Consumers use the *Python* client, so this installs ``playwright==<version>`` into
a cached virtualenv per version and drives the server with it, over ``/{major.minor}``.

``python -m windshield.client_matrix --endpoint ws://127.0.0.1:3000`` checks the last
``WINDSHIELD_MATRIX_SIZE`` served versions (default 5, clamped to 3-5). Rotation runs it
against the candidate container before promoting anything.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from pathlib import Path

MATRIX_MIN = 3
MATRIX_MAX = 5
PYTHON_COUNT = 3
PYTHON_FALLBACK = ("3.13", "3.14", "3.15")
PYTHON_FEED = "https://endoflife.date/api/python.json"
PYTHON_BASE = "docker.io/library/python:{minor}-slim"
PYTHON_IMAGE = "localhost/windshield-matrix-python:{minor}"
# Playwright 1.65's bundled Node driver links libatomic, which python:*-slim does not ship.
_IMAGE_FILE = """FROM {base}
RUN apt-get update \\
 && apt-get install -y --no-install-recommends libatomic1 \\
 && rm -rf /var/lib/apt/lists/*
"""
DEFAULT_ENDPOINT = "ws://127.0.0.1:3000"

Runner = Callable[[Sequence[str], Mapping[str, str], int], "subprocess.CompletedProcess[str]"]

_SMOKE = """
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.connect(sys.argv[1])
    page = b.new_page()
    page.goto("data:text/html,<title>ok</title>")
    assert page.title() == "ok", "wrong title"
    print("chromium " + b.version)
    b.close()
"""


@dataclass(frozen=True)
class Result:
    version: str
    ok: bool
    detail: str
    python: str | None = None  # None = the host's own interpreter


def _run(cmd: Sequence[str], env: Mapping[str, str], timeout: int):
    return subprocess.run(  # noqa: S603
        list(cmd), env=dict(env), capture_output=True, text=True, timeout=timeout, check=False
    )


def _fetch_python_cycles() -> list[dict]:
    request = urllib.request.Request(PYTHON_FEED, headers={"User-Agent": "windshield"})
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
        return json.load(response)


def latest_python_minors(
    env: Mapping[str, str] | None = None,
    fetch: Callable[[], list[dict]] = _fetch_python_cycles,
    count: int = PYTHON_COUNT,
    today: date | None = None,
) -> list[str]:
    """The newest ``count`` supported CPython minors, oldest first.

    ``WINDSHIELD_PYTHON_VERSIONS`` overrides; otherwise endoflife.date decides (released and
    not yet end-of-life), falling back to a built-in list when the feed is unreachable.
    """
    source = os.environ if env is None else env
    override = str(source.get("WINDSHIELD_PYTHON_VERSIONS", "")).replace(",", " ").split()
    if override:
        return override
    today = today or date.today()
    try:
        found = []
        for cycle in fetch():
            minor = str(cycle.get("cycle", ""))
            released = str(cycle.get("releaseDate") or "9999")
            eol = cycle.get("eol")
            alive = eol is False or (isinstance(eol, str) and eol > today.isoformat())
            if re.fullmatch(r"3\.\d+", minor) and released <= today.isoformat() and alive:
                found.append(minor)
        found.sort(key=lambda m: int(m.split(".")[1]), reverse=True)
        if len(found) >= count:
            return sorted(found[:count], key=lambda m: int(m.split(".")[1]))
    except Exception:  # pylint: disable=broad-except
        pass
    return list(PYTHON_FALLBACK[-count:])


def matrix_size(env: Mapping[str, str] | None = None) -> int:
    raw = str((os.environ if env is None else env).get("WINDSHIELD_MATRIX_SIZE", "")).strip()
    try:
        size = int(raw) if raw else MATRIX_MAX
    except ValueError:
        size = MATRIX_MAX
    return max(MATRIX_MIN, min(MATRIX_MAX, size))


def select_versions(versions: Sequence[str], size: int = MATRIX_MAX) -> list[str]:
    """The newest ``size`` versions, oldest first (numeric order)."""
    ordered = sorted(set(versions), key=lambda v: tuple(int(p) for p in v.split(".")))
    return ordered[-size:]


def clients_dir(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    base = source.get("WINDSHIELD_STATE_DIR") or (
        Path(source.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "windshield"
    )
    return Path(base) / "playwright" / "clients"


def minor_of(version: str) -> str:
    """``1.65.1`` -> ``1.65``. Client and server only have to agree on this much, and PyPI's
    patch numbers do not follow npm's, so clients are chosen by minor."""
    return ".".join(version.split(".")[:2])


def client_venv(version: str, env: Mapping[str, str], python_minor: str | None = None) -> Path:
    """Where the cached client for ``version`` lives (one per Python minor if not the default)."""
    name = minor_of(version) + (f"-py{python_minor}" if python_minor else "")
    return clients_dir(env) / name


def ensure_client(
    version: str,
    env: Mapping[str, str],
    runner: Runner = _run,
    *,
    base_python: str | None = None,
    python_minor: str | None = None,
) -> Path:
    """Interpreter of a cached venv holding the Python client for ``version``'s minor.

    ``base_python``/``python_minor`` build it with another interpreter, for suites whose
    Python differs from windshield's (compiled dependencies must import there).
    """
    minor = minor_of(version)
    venv = client_venv(version, env, python_minor)
    python = venv / "bin" / "python"
    if python.exists():
        probe = runner(
            [str(python), "-c", "import importlib.metadata as m;print(m.version('playwright'))"],
            env,
            60,
        )
        if probe.returncode == 0 and minor_of(probe.stdout.strip()) == minor:
            return python
    created = runner([base_python or sys.executable, "-m", "venv", "--clear", str(venv)], env, 120)
    if created.returncode != 0:
        raise RuntimeError(f"venv failed: {(created.stderr or created.stdout).strip()[-200:]}")
    installed = runner(
        [str(python), "-m", "pip", "install", "-q", f"playwright=={minor}.*"], env, 600
    )
    if installed.returncode != 0:
        raise RuntimeError(
            f"pip install failed: {(installed.stderr or installed.stdout).strip()[-200:]}"
        )
    return python


def check_version(
    version: str, endpoint: str, env: Mapping[str, str], runner: Runner = _run
) -> Result:
    minor = minor_of(version)
    try:
        python = ensure_client(version, env, runner)
        out = runner([str(python), "-c", _SMOKE, f"{endpoint.rstrip('/')}/{minor}"], env, 120)
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        return Result(version, False, f"{type(exc).__name__}: {exc}")
    text = (out.stdout or out.stderr or "").strip().splitlines()
    return Result(version, out.returncode == 0, text[-1] if text else f"exit {out.returncode}")


def ensure_images(
    pythons: Sequence[str], env: Mapping[str, str], runner: Runner, engine: str
) -> None:
    """Pull each interpreter image (newest patch release) and layer the driver's libraries on it."""
    directory = clients_dir(env).parent / "matrix-images"
    directory.mkdir(parents=True, exist_ok=True)
    for python in pythons:
        base = PYTHON_BASE.format(minor=python)
        runner([engine, "pull", "-q", base], env, 600)
        recipe = directory / f"Containerfile.{python}"
        recipe.write_text(_IMAGE_FILE.format(base=base), encoding="utf-8")
        built = runner(
            [engine, "build", "-q", "-t", PYTHON_IMAGE.format(minor=python), "-f", str(recipe), str(directory)],
            env,
            900,
        )  # fmt: skip
        if built.returncode != 0:
            raise RuntimeError(
                f"building the python {python} image failed: {(built.stderr or built.stdout).strip()[-200:]}"
            )


def check_cell(
    python: str,
    version: str,
    endpoint: str,
    env: Mapping[str, str],
    runner: Runner = _run,
    engine: str = "podman",
) -> Result:
    """One matrix cell: ``playwright==<minor>.*`` on CPython ``python`` in a throwaway container."""
    minor = minor_of(version)
    cache = clients_dir(env).parent / "pip-cache" / python
    cache.mkdir(parents=True, exist_ok=True)
    script = 'pip install -q --disable-pip-version-check "playwright==$0" && python -c "$1" "$2"'
    command = [
        engine, "run", "--rm", "--network=host", "-v", f"{cache}:/root/.cache/pip:z",
        PYTHON_IMAGE.format(minor=python), "sh", "-c", script,
        f"{minor}.*", _SMOKE, f"{endpoint.rstrip('/')}/{minor}",
    ]  # fmt: skip
    try:
        out = runner(command, env, 600)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return Result(version, False, f"{type(exc).__name__}: {exc}", python)
    text = (out.stdout or out.stderr or "").strip().splitlines()
    return Result(
        version, out.returncode == 0, text[-1] if text else f"exit {out.returncode}", python
    )


def run_matrix(
    versions: Sequence[str],
    endpoint: str,
    *,
    size: int | None = None,
    env: Mapping[str, str] | None = None,
    runner: Runner = _run,
    pythons: Sequence[str] | None = None,
    engine: str | None = None,
) -> list[Result]:
    """Playwright versions x Python versions. ``pythons=["host"]`` uses the host interpreter."""
    source = dict(os.environ if env is None else env)
    chosen = select_versions(versions, size if size is not None else matrix_size(source))
    wanted = list(pythons) if pythons else latest_python_minors(source)
    if wanted == ["host"]:
        return [check_version(v, endpoint, source, runner) for v in chosen]
    engine = engine or source.get("CONTAINER_ENGINE", "podman")
    ensure_images(wanted, source, runner, engine)
    cells = [(python, v) for python in wanted for v in chosen]
    with ThreadPoolExecutor(max_workers=len(wanted)) as pool:
        return list(
            pool.map(
                lambda cell: check_cell(cell[0], cell[1], endpoint, source, runner, engine), cells
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="server base ws:// URL")
    parser.add_argument("--versions", help="space/comma separated; default: served versions")
    parser.add_argument("--size", type=int, help=f"last N versions ({MATRIX_MIN}-{MATRIX_MAX})")
    parser.add_argument(
        "--python",
        default="auto",
        help="auto (latest 3 CPython in containers), host, or e.g. 3.13,3.14",
    )
    args = parser.parse_args(argv)
    if args.versions:
        versions = args.versions.replace(",", " ").split()
    else:
        from windshield.container_rotation import load_state, state_dir

        versions = load_state(Path(__file__).resolve().parents[2], state_dir()).versions
    size = max(MATRIX_MIN, min(MATRIX_MAX, args.size)) if args.size else None
    pythons = None if args.python == "auto" else args.python.replace(",", " ").split()
    results = run_matrix(versions, args.endpoint, size=size, pythons=pythons)
    for r in results:
        label = f"py{r.python}" if r.python else "host"
        print(
            f"{'ok  ' if r.ok else 'FAIL'} python-client {label} playwright {r.version}  {r.detail}"
        )
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
