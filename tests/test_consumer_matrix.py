"""Consumer suite matrix (fake runners; no pip, no browser)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from windshield import consumer_matrix as cm

VERSIONS = ["1.58.2", "1.60.0", "1.62.1", "1.64.1", "1.65.1"]


def done(cmd, code=0, out=""):
    return subprocess.CompletedProcess(cmd, code, out, "")


built_with: list[str] = []


OWN = f"{sys.version_info[0]}.{sys.version_info[1]}"


def fake_runner(py_minor: str = OWN):
    """Creates the client venv layout on `venv`, answers pip/python probes."""

    def runner(cmd, env, timeout):
        if "venv" in cmd:
            built_with.append(cmd[0])
            venv = Path(cmd[-1])
            (venv / "bin").mkdir(parents=True, exist_ok=True)
            (venv / "bin" / "python").write_text("")
            (venv / "lib" / f"python{py_minor}" / "site-packages").mkdir(
                parents=True, exist_ok=True
            )
            return done(cmd)
        if "importlib.metadata" in cmd[-1]:  # probe of a cached client venv
            return done(cmd, out=Path(cmd[0]).parent.parent.name + ".0")
        if "sys.version_info" in cmd[-1]:
            return done(cmd, out=py_minor)
        return done(cmd)

    return runner


def suite(**kw) -> cm.Suite:
    base = dict(
        name="pf",
        cwd="/repo",
        python="/repo/.venv/bin/python",
        command=("{python}", "-m", "pytest"),
    )
    return cm.Suite(**{**base, **kw})


class TestRunSuite:
    def test_runs_with_the_version_under_test_first_on_pythonpath(self, tmp_path: Path) -> None:
        seen = {}

        def suite_runner(cmd, env, cwd, timeout):
            seen.update(cmd=cmd, env=env, cwd=cwd, timeout=timeout)
            return done(cmd, out="12 passed")

        env = {"WINDSHIELD_STATE_DIR": str(tmp_path), "PYTHONPATH": "/existing"}
        out = cm.run_suite(
            suite(), "1.64.1", "ws://127.0.0.1:3000", env, fake_runner(), suite_runner
        )
        assert out.status == "passed" and out.detail == "12 passed"
        assert seen["cmd"] == ["/repo/.venv/bin/python", "-m", "pytest"]
        assert seen["cwd"] == "/repo"
        paths = seen["env"]["PYTHONPATH"].split(":")
        assert (
            paths[0].endswith(f"clients/1.64/lib/python{OWN}/site-packages")
            and paths[1] == "/existing"
        )
        assert seen["env"]["WINDSHIELD_PLAYWRIGHT_WS"] == "ws://127.0.0.1:3000/{version}"
        assert seen["env"]["WINDSHIELD_PLAYWRIGHT_STRICT"] == "1"

    def test_failure_and_timeout_are_failed_outcomes(self, tmp_path: Path) -> None:
        env = {"WINDSHIELD_STATE_DIR": str(tmp_path)}
        bad = cm.run_suite(
            suite(),
            "1.65.1",
            "ws://x:1",
            env,
            fake_runner(),
            lambda c, e, d, t: done(c, 1, "1 failed"),
        )
        assert bad.status == "failed" and bad.detail == "1 failed"

        def slow(cmd, e, d, t):
            raise subprocess.TimeoutExpired(cmd, t)

        late = cm.run_suite(suite(timeout=5), "1.65.1", "ws://x:1", env, fake_runner(), slow)
        assert late.status == "failed" and "timed out after 5s" in late.detail

    def test_other_python_minor_gets_its_own_client_built_with_that_python(
        self, tmp_path: Path
    ) -> None:
        built_with.clear()
        seen = {}

        def suite_runner(cmd, env, cwd, timeout):
            seen["path"] = env["PYTHONPATH"]
            return done(cmd, out="ok")

        out = cm.run_suite(
            suite(),
            "1.65.1",
            "ws://x:1",
            {"WINDSHIELD_STATE_DIR": str(tmp_path)},
            fake_runner("3.99"),
            suite_runner,
        )
        assert out.status == "passed"
        assert built_with == ["/repo/.venv/bin/python"]
        assert "clients/1.65-py3.99/lib/python3.99/site-packages" in seen["path"]


class TestMatrix:
    def test_every_suite_runs_on_each_selected_version(self, tmp_path: Path) -> None:
        calls: list[str] = []

        def suite_runner(cmd, env, cwd, timeout):
            calls.append(env["PYTHONPATH"].split("/clients/")[1].split("/")[0])
            return done(cmd, out="ok")

        outcomes = cm.run_matrix(
            [suite(name="a"), suite(name="b")],
            VERSIONS,
            "ws://x:1",
            size=3,
            env={"WINDSHIELD_STATE_DIR": str(tmp_path)},
            runner=fake_runner(),
            suite_runner=suite_runner,
        )
        assert calls == ["1.62", "1.64", "1.65"] * 2
        assert [o.suite for o in outcomes] == ["a"] * 3 + ["b"] * 3


class TestConfig:
    def test_loads_valid_suites_and_ignores_malformed_ones(self, tmp_path: Path) -> None:
        f = tmp_path / "s.json"
        f.write_text(
            json.dumps(
                [
                    {
                        "name": "a",
                        "cwd": "/r",
                        "python": "/p",
                        "command": ["{python}", "-V"],
                        "timeout": 9,
                        "env": {"X": "1"},
                    },
                    {"name": "broken"},
                ]
            )
        )
        suites = cm.load_suites({"WINDSHIELD_CONSUMER_TESTS_FILE": str(f)})
        assert (
            [s.name for s in suites] == ["a"]
            and suites[0].timeout == 9
            and suites[0].env == {"X": "1"}
        )

    def test_missing_or_corrupt_file_means_no_suites(self, tmp_path: Path) -> None:
        assert cm.load_suites({"WINDSHIELD_CONSUMER_TESTS_FILE": str(tmp_path / "no")}) == []
        bad = tmp_path / "bad.json"
        bad.write_text("{")
        assert cm.load_suites({"WINDSHIELD_CONSUMER_TESTS_FILE": str(bad)}) == []
