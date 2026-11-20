"""Keep the Playwright container's version window and Node pin current, safely.

``python -m windshield.container_rotation`` (run weekly by a Clockwork timer):

1. asks the npm registry for Playwright minors newer than the newest one served and the
   Node.js release feed for a newer LTS major;
2. plans the new window (new minors rotate in, the oldest are dropped so only ``window``
   remain);
3. builds the candidate image and verifies **every** served version end to end in a
   throwaway container (``scripts/playwright_container.sh verify``);
4. only then writes the new state and restarts the service, re-checking afterwards and
   restoring the previous state if the restarted service is not healthy.

A failed candidate leaves the running service untouched and is remembered, so the same
change is not rebuilt every week (``--force`` retries; a different plan is tried at once).
State lives under ``$WINDSHIELD_STATE_DIR`` (default ``~/.local/state/windshield``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_WINDOW = 5
DEFAULT_NODE_MAJOR = 24
SERVICE = "windshield-playwright.service"
REGISTRY_URL = "https://registry.npmjs.org/playwright"
NODE_INDEX_URL = "https://nodejs.org/dist/index.json"
_STABLE = re.compile(r"^\d+\.\d+\.\d+$")

Runner = Callable[[Sequence[str], Mapping[str, str], int], "subprocess.CompletedProcess[str]"]


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def minor_of(version: str) -> tuple[int, int]:
    major, minor = version_key(version)[:2]
    return major, minor


@dataclass(frozen=True)
class Plan:
    versions: tuple[str, ...]
    node_major: int
    added: tuple[str, ...]
    dropped: tuple[str, ...]
    node_changed: bool

    @property
    def changed(self) -> bool:
        return bool(self.added or self.dropped or self.node_changed)

    @property
    def key(self) -> str:
        """Identity of this plan, used to avoid retrying a change that already failed."""
        return f"{' '.join(self.versions)}|node{self.node_major}"


def plan_rotation(
    current: Sequence[str],
    available: Sequence[str],
    *,
    current_node: int,
    latest_node_lts: int | None,
    window: int = DEFAULT_WINDOW,
) -> Plan:
    """Add every stable minor newer than the newest served, drop the oldest beyond *window*."""
    served = sorted(current, key=version_key)
    newest_minor = minor_of(served[-1]) if served else (0, 0)
    latest_patch: dict[tuple[int, int], str] = {}
    for version in available:
        if not _STABLE.match(version):
            continue
        minor = minor_of(version)
        if minor > newest_minor and (
            minor not in latest_patch or version_key(version) > version_key(latest_patch[minor])
        ):
            latest_patch[minor] = version
    added = tuple(latest_patch[m] for m in sorted(latest_patch))
    merged = sorted([*served, *added], key=version_key)
    dropped: tuple[str, ...] = ()
    if added and len(merged) > window:
        dropped = tuple(merged[: len(merged) - window])
        merged = merged[len(merged) - window :]
    node = current_node
    if latest_node_lts is not None and latest_node_lts > current_node:
        node = latest_node_lts
    return Plan(tuple(merged), node, added, dropped, node != current_node)


# -- registries ---------------------------------------------------------------------------


def _get_json(url: str, headers: Mapping[str, str] | None = None, timeout: float = 60) -> Any:
    request = urllib.request.Request(url, headers=dict(headers or {}))
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def fetch_playwright_versions() -> list[str]:
    """Stable Playwright releases from the npm registry (abbreviated metadata)."""
    data = _get_json(REGISTRY_URL, {"Accept": "application/vnd.npm.install-v1+json"})
    return [v for v in data.get("versions", {}) if _STABLE.match(v)]


def fetch_latest_node_lts() -> int | None:
    """Major version of the newest Node.js LTS release, or None if the feed has none."""
    for release in _get_json(NODE_INDEX_URL):
        if release.get("lts"):
            return int(str(release["version"]).lstrip("v").split(".")[0])
    return None


# -- state --------------------------------------------------------------------------------


def state_dir(env: Mapping[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    root = env.get("WINDSHIELD_STATE_DIR") or str(
        Path(env.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "windshield"
    )
    return Path(root) / "playwright"


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


@dataclass
class State:
    versions: list[str]
    node_major: int


def load_state(repo_dir: Path, directory: Path) -> State:
    """Rotation state if present, else the tracked seed in ``config/``."""
    versions = _read_lines(directory / "versions.txt") or _read_lines(
        repo_dir / "config" / "playwright-versions.txt"
    )
    node_lines = _read_lines(directory / "node-major.txt") or _read_lines(
        repo_dir / "config" / "node-major.txt"
    )
    node = int(node_lines[0]) if node_lines else DEFAULT_NODE_MAJOR
    return State(sorted(versions, key=version_key), node)


def save_state(directory: Path, state: State) -> None:
    _atomic_write(directory / "versions.txt", "\n".join(state.versions) + "\n")
    _atomic_write(directory / "node-major.txt", f"{state.node_major}\n")


def read_status(directory: Path) -> dict[str, Any]:
    try:
        return json.loads((directory / "rotation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_status(directory: Path, **fields: Any) -> None:
    status = read_status(directory)
    status.update(fields, updated=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    _atomic_write(directory / "rotation.json", json.dumps(status, indent=2) + "\n")


# -- the rotation -------------------------------------------------------------------------


def _run(
    cmd: Sequence[str], env: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        list(cmd), env=dict(env), capture_output=True, text=True, timeout=timeout, check=False
    )


def rotate(
    repo_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
    fetch_versions: Callable[[], list[str]] = fetch_playwright_versions,
    fetch_node: Callable[[], int | None] = fetch_latest_node_lts,
    runner: Runner = _run,
    window: int = DEFAULT_WINDOW,
    dry_run: bool = False,
    force: bool = False,
    restart_service: bool = True,
    log: Callable[[str], None] = print,
    notify: Callable[[str, str], None] | None = None,
) -> int:
    """Run one rotation. Returns 0 (nothing to do / promoted / skipped) or 1 (failed)."""
    env = dict(os.environ if env is None else env)
    directory = state_dir(env)
    alert = (
        notify if notify is not None else (lambda subject, body: _alert(env, subject, body, log))
    )
    script = str(repo_dir / "scripts" / "playwright_container.sh")
    state = load_state(repo_dir, directory)
    if not state.versions:
        log("no Playwright versions configured (config/playwright-versions.txt)")
        return 1

    try:
        available = fetch_versions()
        node_lts = fetch_node()
    except Exception as exc:  # pylint: disable=broad-except
        failures = int(read_status(directory).get("check_failures") or 0) + 1
        write_status(
            directory, last_check_error=f"{type(exc).__name__}: {exc}", check_failures=failures
        )
        log(f"registry lookup failed: {type(exc).__name__}: {exc}")
        if failures == 2:  # one blip is noise; two weeks running is not
            alert(
                "windshield-playwright: version checks keep failing",
                f"The weekly registry lookup failed {failures} times in a row: "
                f"{type(exc).__name__}: {exc}\nNew Playwright versions are not being picked up.",
            )
        return 1

    status = read_status(directory)
    node_candidate = node_lts
    if not force and node_lts is not None and status.get("node_rejected") == node_lts:
        node_candidate = None  # this Node major already failed verification; wait for a newer one
    plan = plan_rotation(
        state.versions,
        available,
        current_node=state.node_major,
        latest_node_lts=node_candidate,
        window=window,
    )
    write_status(directory, last_check_error=None, check_failures=0, last_checked_plan=plan.key)
    if not plan.changed:
        log(f"up to date: {' '.join(state.versions)} on node {state.node_major}")
        return 0

    log(
        f"plan: add {list(plan.added) or '-'}, drop {list(plan.dropped) or '-'}, "
        f"node {state.node_major} -> {plan.node_major}"
    )
    if dry_run:
        return 0

    def attempt(candidate: Plan, quiet: bool = False) -> str:
        """Build, verify, promote one candidate: "promoted", "failed" or "skipped"."""
        if not force and read_status(directory).get("failed_plan") == candidate.key:
            log(f"skipping: this plan already failed; use --force to retry ({candidate.key})")
            return "skipped"
        build_env = {
            **env,
            "WINDSHIELD_PLAYWRIGHT_VERSIONS": " ".join(candidate.versions),
            "WINDSHIELD_NODE_MAJOR": str(candidate.node_major),
        }

        def fail(reason: str, output: str = "") -> str:
            tail = "\n".join(output.strip().splitlines()[-12:])
            write_status(
                directory, failed_plan=candidate.key, failed_reason=reason, failed_output=tail
            )
            log(f"candidate rejected ({candidate.key}): {reason}\n{tail}")
            if not quiet and read_status(directory).get("alerted_plan") != candidate.key:
                write_status(directory, alerted_plan=candidate.key)
                alert(
                    "windshield-playwright: rotation failed",
                    f"Plan {candidate.key} was rejected: {reason}.\n"
                    "The running container is unchanged"
                    + (" (previous versions restored)." if "restored" in reason else ".")
                    + (f"\n\n{tail}" if tail else "")
                    + "\n\nRetry: python -m windshield.container_rotation --force",
                )
            return "failed"

        for step, timeout in (("build", 3600), ("verify", 900)):
            try:
                result = runner([script, step], build_env, timeout)
            except subprocess.TimeoutExpired:
                return fail(f"{step} timed out after {timeout}s")
            if result.returncode != 0:
                return fail(f"{step} failed", (result.stdout or "") + (result.stderr or ""))
            log(f"{step}: ok")

        previous = State(list(state.versions), state.node_major)
        save_state(directory, State(list(candidate.versions), candidate.node_major))
        if restart_service:
            restart = runner(["systemctl", "--user", "restart", SERVICE], env, 120)
            healthy = restart.returncode == 0
            if healthy:
                try:
                    healthy = runner([script, "smoke"], env, 600).returncode == 0
                except subprocess.TimeoutExpired:
                    healthy = False
            if not healthy:
                save_state(directory, previous)
                runner(["systemctl", "--user", "restart", SERVICE], env, 120)
                return fail("service unhealthy after promotion; previous versions restored")

        write_status(
            directory,
            failed_plan=None,
            failed_reason=None,
            failed_output=None,
            promoted=candidate.key,
            promoted_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        log(f"promoted: {' '.join(candidate.versions)} on node {candidate.node_major}")
        alert(
            "windshield-playwright: rotated",
            f"Now serving Playwright {' '.join(candidate.versions)} on Node {candidate.node_major}"
            + (f"; added {', '.join(candidate.added)}" if candidate.added else "")
            + (f"; dropped {', '.join(candidate.dropped)}" if candidate.dropped else "")
            + ".",
        )
        prune_images(
            runner,
            env,
            keep_versions=(previous, State(list(candidate.versions), candidate.node_major)),
        )
        return "promoted"

    fallback_follows = plan.node_changed and bool(plan.added)
    outcome = attempt(plan, quiet=fallback_follows)
    if outcome == "promoted":
        return 0
    if outcome == "skipped":
        return 0
    if plan.node_changed and plan.added:
        # Do not let a Node bump hold back new Playwright versions: retry on the current Node.
        fallback = Plan(plan.versions, state.node_major, plan.added, plan.dropped, False)
        log(f"retrying without the Node bump (node stays {state.node_major})")
        outcome = attempt(fallback)
        if outcome == "promoted":
            alert(
                "windshield-playwright: Node bump rejected",
                f"Node {plan.node_major} failed verification, so the container stays on "
                f"Node {state.node_major}. New Playwright versions were still rotated in. "
                "It will try again when a newer Node LTS ships.",
            )
            write_status(directory, node_rejected=plan.node_major)
            log(f"node {plan.node_major} rejected; will wait for a newer LTS")
        return 0 if outcome != "failed" else 1
    if plan.node_changed:
        write_status(directory, node_rejected=plan.node_major)
        log(f"node {plan.node_major} rejected; will wait for a newer LTS")
    return 1


def _alert(env: Mapping[str, str], subject: str, body: str, log: Callable[[str], None]) -> None:
    """Best-effort alert through shock-relay; never lets a send problem fail the rotation."""
    from windshield.notify import send_alert, targets

    try:
        if not targets(env):
            log("alert not sent: no WINDSHIELD_NOTIFY_*_TARGET configured")
            return
        for delivery in send_alert(subject, body, env):
            log(f"alert via {delivery.channel}: {'sent' if delivery.ok else delivery.error}")
    except Exception as exc:  # pylint: disable=broad-except
        log(f"alert failed: {type(exc).__name__}: {exc}")


def _image_tag(state: State) -> str:
    return f"v{'-'.join(state.versions)}-node{state.node_major}"


def prune_images(runner: Runner, env: Mapping[str, str], *, keep_versions: Sequence[State]) -> None:
    """Remove windshield-playwright images other than the current and previous ones."""
    keep = {_image_tag(s) for s in keep_versions}
    try:
        listing = runner(
            ["podman", "images", "--format", "{{.Tag}}", "localhost/windshield-playwright"],
            env,
            60,
        )
        for tag in listing.stdout.split():
            if tag not in keep:
                runner(["podman", "rmi", f"localhost/windshield-playwright:{tag}"], env, 120)
    except Exception:  # pylint: disable=broad-except
        pass  # pruning is best effort


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    parser.add_argument("--force", action="store_true", help="retry a plan that already failed")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="versions to serve")
    parser.add_argument("--no-restart", action="store_true", help="do not restart the service")
    parser.add_argument("--status", action="store_true", help="print rotation state and exit")
    args = parser.parse_args(argv)
    repo_dir = Path(__file__).resolve().parents[2]
    if args.status:
        directory = state_dir()
        state = load_state(repo_dir, directory)
        print(
            json.dumps(
                {"versions": state.versions, "node": state.node_major, **read_status(directory)},
                indent=2,
            )
        )
        return 0
    return rotate(
        repo_dir,
        window=args.window,
        dry_run=args.dry_run,
        force=args.force,
        restart_service=not args.no_restart,
    )


if __name__ == "__main__":
    sys.exit(main())
