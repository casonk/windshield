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
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

MATRIX_MIN = 3
MATRIX_MAX = 5
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


def _run(cmd: Sequence[str], env: Mapping[str, str], timeout: int):
    return subprocess.run(  # noqa: S603
        list(cmd), env=dict(env), capture_output=True, text=True, timeout=timeout, check=False
    )


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


def ensure_client(version: str, env: Mapping[str, str], runner: Runner = _run) -> Path:
    """Interpreter of a cached venv holding the Python client for ``version``'s minor."""
    minor = minor_of(version)
    venv = clients_dir(env) / minor
    python = venv / "bin" / "python"
    if python.exists():
        probe = runner(
            [str(python), "-c", "import importlib.metadata as m;print(m.version('playwright'))"],
            env,
            60,
        )
        if probe.returncode == 0 and minor_of(probe.stdout.strip()) == minor:
            return python
    created = runner([sys.executable, "-m", "venv", "--clear", str(venv)], env, 120)
    if created.returncode != 0:
        raise RuntimeError(f"venv failed: {(created.stderr or created.stdout).strip()[-200:]}")
    installed = runner(
        [str(python), "-m", "pip", "install", "-q", f"playwright=={minor}.*"], env, 600
    )
    if installed.returncode != 0:
        raise RuntimeError(f"pip install failed: {(installed.stderr or installed.stdout).strip()[-200:]}")
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


def run_matrix(
    versions: Sequence[str],
    endpoint: str,
    *,
    size: int | None = None,
    env: Mapping[str, str] | None = None,
    runner: Runner = _run,
) -> list[Result]:
    source = dict(os.environ if env is None else env)
    chosen = select_versions(versions, size if size is not None else matrix_size(source))
    return [check_version(v, endpoint, source, runner) for v in chosen]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="server base ws:// URL")
    parser.add_argument("--versions", help="space/comma separated; default: served versions")
    parser.add_argument("--size", type=int, help=f"last N versions ({MATRIX_MIN}-{MATRIX_MAX})")
    args = parser.parse_args(argv)
    if args.versions:
        versions = args.versions.replace(",", " ").split()
    else:
        from windshield.container_rotation import load_state, state_dir

        versions = load_state(Path(__file__).resolve().parents[2], state_dir()).versions
    size = max(MATRIX_MIN, min(MATRIX_MAX, args.size)) if args.size else None
    results = run_matrix(versions, args.endpoint, size=size)
    for r in results:
        print(f"{'ok  ' if r.ok else 'FAIL'} python-client {r.version}  {r.detail}")
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
