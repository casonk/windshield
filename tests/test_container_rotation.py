"""Tests for automatic Playwright container rotation (no containers or network needed)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from windshield import container_rotation as rot

CURRENT = ["1.58.2", "1.60.0", "1.62.1", "1.64.1", "1.65.1"]


def plan(current=CURRENT, available=(), node=24, lts=None, window=5):
    return rot.plan_rotation(
        current, list(available), current_node=node, latest_node_lts=lts, window=window
    )


class TestPlan:
    def test_nothing_new_changes_nothing(self) -> None:
        p = plan(available=["1.64.0", "1.65.0", "1.65.1"], lts=24)
        assert not p.changed and list(p.versions) == CURRENT

    def test_new_minor_rotates_in_and_pops_the_oldest(self) -> None:
        p = plan(available=[*CURRENT, "1.66.0"])
        assert list(p.versions) == ["1.60.0", "1.62.1", "1.64.1", "1.65.1", "1.66.0"]
        assert p.added == ("1.66.0",) and p.dropped == ("1.58.2",)

    def test_takes_the_latest_patch_of_the_new_minor(self) -> None:
        p = plan(available=["1.66.0", "1.66.2", "1.66.1"])
        assert p.added == ("1.66.2",)

    def test_several_new_minors_at_once(self) -> None:
        p = plan(available=["1.66.0", "1.67.1"])
        assert list(p.versions) == ["1.62.1", "1.64.1", "1.65.1", "1.66.0", "1.67.1"]
        assert p.dropped == ("1.58.2", "1.60.0")

    def test_prereleases_and_older_minors_are_ignored(self) -> None:
        p = plan(available=["1.66.0-alpha-123", "1.66.0-beta-1", "1.59.0", "1.61.3"])
        assert not p.changed

    def test_grows_until_the_window_is_full(self) -> None:
        p = plan(current=["1.64.1", "1.65.1"], available=["1.66.0"])
        assert list(p.versions) == ["1.64.1", "1.65.1", "1.66.0"] and p.dropped == ()

    def test_numeric_not_lexical_ordering(self) -> None:
        p = plan(current=["1.9.0"], available=["1.10.0"])
        assert list(p.versions) == ["1.9.0", "1.10.0"]

    def test_newer_node_lts_bumps_the_pin_but_never_downgrades(self) -> None:
        assert plan(lts=26).node_major == 26 and plan(lts=26).node_changed
        assert plan(lts=22).node_major == 24 and not plan(lts=22).changed
        assert plan(lts=None).node_major == 24

    def test_plan_key_identifies_the_change(self) -> None:
        a = plan(available=["1.66.0"])
        assert a.key == plan(available=["1.66.0"]).key != plan(available=["1.67.0"]).key


class TestState:
    def test_seed_from_repo_config_until_state_exists(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        (repo / "config").mkdir(parents=True)
        (repo / "config" / "playwright-versions.txt").write_text("# c\n1.60.0\n1.58.2\n")
        (repo / "config" / "node-major.txt").write_text("24\n")
        state = rot.load_state(repo, tmp_path / "state")
        assert state.versions == ["1.58.2", "1.60.0"] and state.node_major == 24

        rot.save_state(tmp_path / "state", rot.State(["1.65.1"], 26))
        state = rot.load_state(repo, tmp_path / "state")
        assert state.versions == ["1.65.1"] and state.node_major == 26


class FakeRunner:
    def __init__(self, fail: str | None = None, timeout: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail, self.timeout = fail, timeout

    def __call__(self, cmd, env, timeout):
        self.calls.append(list(cmd))
        joined = " ".join(cmd)
        if self.timeout and self.timeout in joined:
            raise subprocess.TimeoutExpired(cmd, timeout)
        rc = 1 if self.fail and self.fail in joined else 0
        out = (
            "Tag\nv1.58.2-1.60.0-1.62.1-1.64.1-1.65.1-node24\nv-old-node20\n"
            if "images" in joined
            else ""
        )
        return subprocess.CompletedProcess(cmd, rc, out, "boom" if rc else "")

    def steps(self) -> list[str]:
        return [c[-1] if c[0].endswith(".sh") else " ".join(c[:3]) for c in self.calls]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "repo" / "config").mkdir(parents=True)
    (tmp_path / "repo" / "config" / "playwright-versions.txt").write_text("\n".join(CURRENT))
    (tmp_path / "repo" / "config" / "node-major.txt").write_text("24\n")
    return tmp_path / "repo"


ALERTS: list[tuple[str, str]] = []


def run(
    repo: Path, tmp_path: Path, runner, *, new=("1.66.0",), lts=24, **kw
) -> tuple[int, list[str]]:
    logs: list[str] = []
    ALERTS.clear()
    code = rot.rotate(
        repo,
        env={"WINDSHIELD_STATE_DIR": str(tmp_path / "state")},
        fetch_versions=lambda: [*CURRENT, *new],
        fetch_node=lambda: lts,
        runner=runner,
        log=logs.append,
        notify=lambda subject, body: ALERTS.append((subject, body)),
        **kw,
    )
    return code, logs


def saved(tmp_path: Path) -> rot.State:
    return rot.load_state(tmp_path / "none", tmp_path / "state" / "playwright")


class TestRotate:
    def test_up_to_date_does_nothing(self, repo, tmp_path) -> None:
        r = FakeRunner()
        code, logs = run(repo, tmp_path, r, new=())
        assert code == 0 and r.calls == [] and "up to date" in logs[0]

    def test_dry_run_changes_nothing(self, repo, tmp_path) -> None:
        r = FakeRunner()
        assert run(repo, tmp_path, r, dry_run=True)[0] == 0
        assert r.calls == [] and not (tmp_path / "state" / "playwright" / "versions.txt").exists()

    def test_success_builds_verifies_then_promotes_and_restarts(self, repo, tmp_path) -> None:
        r = FakeRunner()
        code, _ = run(repo, tmp_path, r)
        assert code == 0
        assert r.steps()[:2] == ["build", "verify"]
        order = r.steps()
        assert (
            order.index("verify") < order.index("systemctl --user restart") < order.index("smoke")
        )
        state = saved(tmp_path)
        assert state.versions == ["1.60.0", "1.62.1", "1.64.1", "1.65.1", "1.66.0"]
        # the candidate was built with the planned window, not the old one
        assert any("rmi" in c for c in r.steps()) or "podman rmi" in " ".join(order)

    def test_build_failure_leaves_state_and_service_alone(self, repo, tmp_path) -> None:
        r = FakeRunner(fail="build")
        code, logs = run(repo, tmp_path, r)
        assert code == 1 and "rejected" in logs[-1]
        assert not (tmp_path / "state" / "playwright" / "versions.txt").exists()
        assert not any("restart" in c for c in r.steps())

    def test_verify_failure_is_not_promoted(self, repo, tmp_path) -> None:
        r = FakeRunner(fail="verify")
        assert run(repo, tmp_path, r)[0] == 1
        assert not (tmp_path / "state" / "playwright" / "versions.txt").exists()

    def test_timeouts_are_failures_not_hangs(self, repo, tmp_path) -> None:
        r = FakeRunner(timeout="build")
        code, logs = run(repo, tmp_path, r)
        assert code == 1 and "timed out" in logs[-1]

    def test_a_failed_plan_is_not_retried_until_forced_or_changed(self, repo, tmp_path) -> None:
        assert run(repo, tmp_path, FakeRunner(fail="build"))[0] == 1
        again = FakeRunner()
        code, logs = run(repo, tmp_path, again)
        assert code == 0 and again.calls == [] and "already failed" in logs[-1]
        assert run(repo, tmp_path, FakeRunner(), force=True)[0] == 0
        # a different plan (another new minor) is attempted immediately
        assert run(repo, tmp_path, FakeRunner(fail="build"), new=("1.67.0",))[0] == 1
        retry = FakeRunner()
        assert run(repo, tmp_path, retry, new=("1.67.0", "1.68.0"))[0] == 0 and retry.calls

    def test_unhealthy_after_promotion_rolls_back(self, repo, tmp_path) -> None:
        r = FakeRunner(fail="smoke")
        code, logs = run(repo, tmp_path, r)
        assert code == 1 and "restored" in logs[-1]
        assert saved(tmp_path).versions == CURRENT
        assert [c for c in r.steps()].count("systemctl --user restart") == 2

    def test_a_failing_node_bump_does_not_block_new_playwright_versions(
        self, repo, tmp_path
    ) -> None:
        class NodeFails(FakeRunner):
            def __call__(self, cmd, env, timeout):
                if cmd[-1] in {"build", "verify"} and env.get("WINDSHIELD_NODE_MAJOR") == "26":
                    self.calls.append(list(cmd))
                    return subprocess.CompletedProcess(cmd, 1, "", "hang")
                return super().__call__(cmd, env, timeout)

        code, logs = run(repo, tmp_path, NodeFails(), lts=26)
        assert code == 0
        state = saved(tmp_path)
        assert state.versions[-1] == "1.66.0" and state.node_major == 24
        status = rot.read_status(tmp_path / "state" / "playwright")
        assert status["node_rejected"] == 26
        # next week the rejected Node major is not tried again, and nothing else is pending
        quiet = FakeRunner()
        code, logs = run(repo, tmp_path, quiet, new=("1.66.0",), lts=26)
        assert code == 0 and quiet.calls == [] and "up to date" in logs[-1]
        # a newer LTS is tried again
        assert run(repo, tmp_path, FakeRunner(), new=("1.66.0",), lts=28)[0] == 0
        assert saved(tmp_path).node_major == 28

    def test_node_bump_alone_failing_is_remembered(self, repo, tmp_path) -> None:
        assert run(repo, tmp_path, FakeRunner(fail="verify"), new=(), lts=26)[0] == 1
        assert rot.read_status(tmp_path / "state" / "playwright")["node_rejected"] == 26
        quiet = FakeRunner()
        assert run(repo, tmp_path, quiet, new=(), lts=26)[0] == 0 and quiet.calls == []

    def test_node_bump_alone_triggers_a_rebuild(self, repo, tmp_path) -> None:
        r = FakeRunner()
        assert run(repo, tmp_path, r, new=(), lts=26)[0] == 0
        assert saved(tmp_path).node_major == 26 and saved(tmp_path).versions == CURRENT

    def test_registry_failure_is_reported_not_fatal_to_the_service(self, repo, tmp_path) -> None:
        def boom():
            raise OSError("offline")

        logs: list[str] = []
        code = rot.rotate(
            repo,
            env={"WINDSHIELD_STATE_DIR": str(tmp_path / "state")},
            fetch_versions=boom,
            fetch_node=lambda: 24,
            runner=FakeRunner(),
            log=logs.append,
            notify=lambda subject, body: ALERTS.append((subject, body)),
        )
        assert code == 1 and "offline" in logs[0]
        assert "offline" in rot.read_status(tmp_path / "state" / "playwright")["last_check_error"]


class TestAlerts:
    def test_promotion_is_announced(self, repo, tmp_path) -> None:
        assert run(repo, tmp_path, FakeRunner())[0] == 0
        assert [a[0] for a in ALERTS] == ["windshield-playwright: rotated"]
        assert "1.66.0" in ALERTS[0][1]

    def test_a_failed_rotation_alerts_once_per_plan(self, repo, tmp_path) -> None:
        assert run(repo, tmp_path, FakeRunner(fail="build"))[0] == 1
        assert [a[0] for a in ALERTS] == ["windshield-playwright: rotation failed"]
        assert "--force" in ALERTS[0][1]
        run(repo, tmp_path, FakeRunner(fail="build"))  # skipped: already failed
        assert ALERTS == []
        run(repo, tmp_path, FakeRunner(fail="build"), force=True)  # same plan, already alerted
        assert ALERTS == []

    def test_rollback_alert_says_previous_versions_restored(self, repo, tmp_path) -> None:
        class Unhealthy(FakeRunner):
            def __call__(self, cmd, env, timeout):
                if cmd[-1] == "smoke":
                    self.calls.append(list(cmd))
                    return subprocess.CompletedProcess(cmd, 1, "", "")
                return super().__call__(cmd, env, timeout)

        assert run(repo, tmp_path, Unhealthy())[0] == 1
        assert "restored" in ALERTS[0][1]

    def test_a_node_bump_that_falls_back_does_not_report_a_failure(self, repo, tmp_path) -> None:
        class NodeFails(FakeRunner):
            def __call__(self, cmd, env, timeout):
                if cmd[-1] in {"build", "verify"} and env.get("WINDSHIELD_NODE_MAJOR") == "26":
                    self.calls.append(list(cmd))
                    return subprocess.CompletedProcess(cmd, 1, "", "hang")
                return super().__call__(cmd, env, timeout)

        assert run(repo, tmp_path, NodeFails(), lts=26)[0] == 0
        subjects = [a[0] for a in ALERTS]
        assert "windshield-playwright: rotation failed" not in subjects
        assert "windshield-playwright: Node bump rejected" in subjects

    def test_registry_outage_alerts_on_the_second_consecutive_failure(self, repo, tmp_path) -> None:
        def boom():
            raise OSError("offline")

        def once():
            return rot.rotate(
                repo,
                env={"WINDSHIELD_STATE_DIR": str(tmp_path / "state")},
                fetch_versions=boom,
                fetch_node=lambda: 24,
                runner=FakeRunner(),
                log=lambda _m: None,
                notify=lambda subject, body: ALERTS.append((subject, body)),
            )

        ALERTS.clear()
        once()
        assert ALERTS == []
        once()
        assert [a[0] for a in ALERTS] == ["windshield-playwright: version checks keep failing"]
        once()
        assert len(ALERTS) == 1


class TestSendAlert:
    def test_channels_without_targets_are_skipped(self) -> None:
        from windshield import notify

        assert notify.targets({}) == {}
        assert notify.send_alert("s", "b", {}) == []

    def test_one_channel_failing_does_not_stop_the_others(self, tmp_path) -> None:
        from windshield import notify

        root = tmp_path / "relay"
        for rel, code in (
            ("services/signal-cli/send_message.py", "import sys; sys.exit(3)"),
            ("services/telegram/send_message.py", "print('ok')"),
        ):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(code)
        env = {
            "WINDSHIELD_SHOCK_RELAY_ROOT": str(root),
            "WINDSHIELD_NOTIFY_SIGNAL_TARGET": "x",
            "WINDSHIELD_NOTIFY_TELEGRAM_TARGET": "y",
            "WINDSHIELD_NOTIFY_GMAIL_TARGET": "z",
        }
        result = {d.channel: d for d in notify.send_alert("s", "b", env)}
        assert not result["signal"].ok
        assert result["telegram"].ok
        assert "not found" in (result["gmail"].error or "")
