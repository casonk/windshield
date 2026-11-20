"""Client matrix and consumer bump (no network, no real pip)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from windshield import client_bump as bump
from windshield import client_matrix as matrix
from windshield import container_rotation as rot

VERSIONS = ["1.58.2", "1.60.0", "1.62.1", "1.64.1", "1.65.1", "1.9.0"]


def done(cmd, code=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, code, out, err)


class TestSelection:
    def test_last_n_by_numeric_order(self) -> None:
        assert matrix.select_versions(VERSIONS, 3) == ["1.62.1", "1.64.1", "1.65.1"]
        assert matrix.select_versions(VERSIONS, 5)[0] == "1.58.2"

    def test_size_defaults_to_five_and_is_clamped(self) -> None:
        assert matrix.matrix_size({}) == 5
        assert matrix.matrix_size({"WINDSHIELD_MATRIX_SIZE": "1"}) == 3
        assert matrix.matrix_size({"WINDSHIELD_MATRIX_SIZE": "99"}) == 5
        assert matrix.matrix_size({"WINDSHIELD_MATRIX_SIZE": "4"}) == 4
        assert matrix.matrix_size({"WINDSHIELD_MATRIX_SIZE": "x"}) == 5


class TestMatrix:
    def test_each_version_is_driven_through_its_own_minor(self, tmp_path: Path) -> None:
        calls: list[list[str]] = []

        def runner(cmd, env, timeout):
            calls.append(list(cmd))
            if "venv" in cmd:
                Path(cmd[-1], "bin").mkdir(parents=True)
                Path(cmd[-1], "bin", "python").write_text("")
                return done(cmd)
            if "pip" in cmd:
                return done(cmd)
            return done(cmd, out="chromium 159")

        env = {"WINDSHIELD_STATE_DIR": str(tmp_path)}
        results = matrix.run_matrix(
            VERSIONS[:5], "ws://127.0.0.1:3900", size=3, env=env, runner=runner, pythons=["host"]
        )
        assert [r.version for r in results] == ["1.62.1", "1.64.1", "1.65.1"]
        assert all(r.ok for r in results)
        endpoints = [c[-1] for c in calls if c[-1].startswith("ws://")]
        assert endpoints == [
            "ws://127.0.0.1:3900/1.62",
            "ws://127.0.0.1:3900/1.64",
            "ws://127.0.0.1:3900/1.65",
        ]

    def test_a_failing_client_is_reported_not_raised(self, tmp_path: Path) -> None:
        def runner(cmd, env, timeout):
            if "venv" in cmd:
                Path(cmd[-1], "bin").mkdir(parents=True)
                Path(cmd[-1], "bin", "python").write_text("")
            if cmd[-1].startswith("ws://") and "1.62" in cmd[-1]:
                return done(cmd, 1, err="Error: Playwright version mismatch")
            return done(cmd, out="ok")

        results = matrix.run_matrix(
            ["1.62.1", "1.64.1", "1.65.1"],
            "ws://x:1",
            env={"WINDSHIELD_STATE_DIR": str(tmp_path)},
            runner=runner,
            pythons=["host"],
        )
        assert [r.ok for r in results] == [False, True, True]
        assert "mismatch" in results[0].detail

    def test_pip_failure_is_a_failed_result(self, tmp_path: Path) -> None:
        def runner(cmd, env, timeout):
            if "venv" in cmd:
                Path(cmd[-1], "bin").mkdir(parents=True)
                Path(cmd[-1], "bin", "python").write_text("")
                return done(cmd)
            return done(cmd, 1, err="no matching distribution")

        r = matrix.check_version(
            "1.65.1", "ws://x:1", {"WINDSHIELD_STATE_DIR": str(tmp_path)}, runner
        )
        assert not r.ok and "pip install failed" in r.detail


class FakeConsumer:
    """Stands in for pip/python of consumer interpreters."""

    def __init__(self, versions: dict[str, str], smoke_ok: bool = True, install_ok: bool = True):
        self.versions, self.smoke_ok, self.install_ok = dict(versions), smoke_ok, install_ok
        self.installs: list[tuple[str, str, bool]] = []

    def __call__(self, cmd, env, timeout):
        python = cmd[0]
        if "metadata" in cmd[-1]:
            v = self.versions.get(python)
            return done(cmd, 0 if v else 1, v or "")
        if "base_prefix" in cmd[-1]:
            return done(cmd, out="1" if python.endswith("venv-python") else "0")
        if "pip" in cmd:
            spec = cmd[-1].split("==")[1]
            self.installs.append((python, spec, "--user" in cmd))
            if self.install_ok or spec != "1.65.*":
                self.versions[python] = spec
            return done(cmd, 0 if self.install_ok or spec != "1.65.*" else 1)
        return done(cmd, 0 if self.smoke_ok else 1)


class TestBump:
    def test_behind_interpreters_are_bumped_and_current_ones_left_alone(self) -> None:
        r = FakeConsumer({"/sys/python": "1.58.0", "/x/venv-python": "1.65.1"})
        out = bump.bump_clients(
            "1.65.1", interpreters=["/sys/python", "/x/venv-python"], runner=r, log=lambda _m: None
        )
        assert [b.status for b in out] == ["bumped", "current"]
        assert r.installs == [("/sys/python", "1.65.*", True)]  # system python gets --user

    def test_venv_gets_a_plain_install(self) -> None:
        r = FakeConsumer({"/x/venv-python": "1.64.1"})
        bump.bump_clients("1.65.1", interpreters=["/x/venv-python"], runner=r, log=lambda _m: None)
        assert r.installs == [("/x/venv-python", "1.65.*", False)]

    def test_never_downgrades(self) -> None:
        r = FakeConsumer({"/p": "1.66.0"})
        out = bump.bump_clients("1.65.1", interpreters=["/p"], runner=r, log=lambda _m: None)
        assert out[0].status == "current" and r.installs == []

    def test_failed_smoke_restores_the_previous_version(self) -> None:
        r = FakeConsumer({"/p": "1.64.1"}, smoke_ok=False)
        out = bump.bump_clients("1.65.1", interpreters=["/p"], runner=r, log=lambda _m: None)
        assert out[0].status == "restored" and r.versions["/p"] == "1.64.1"

    def test_failed_install_leaves_the_previous_version(self) -> None:
        r = FakeConsumer({"/p": "1.64.1"}, install_ok=False)
        out = bump.bump_clients("1.65.1", interpreters=["/p"], runner=r, log=lambda _m: None)
        assert out[0].status == "failed" and r.versions["/p"] == "1.64.1"

    def test_interpreter_without_playwright_is_skipped(self) -> None:
        out = bump.bump_clients(
            "1.65.1", interpreters=["/none"], runner=FakeConsumer({}), log=lambda _m: None
        )
        assert out[0].status == "skipped"

    def test_consumers_file_parsing(self, tmp_path: Path) -> None:
        f = tmp_path / "c.txt"
        f.write_text("# comment\n/a/python\n\n/b/python  # trailing\n/a/python\n")
        assert bump.read_consumers({"WINDSHIELD_CONSUMERS_FILE": str(f)}) == [
            "/a/python",
            "/b/python",
        ]
        assert bump.read_consumers({"WINDSHIELD_CONSUMERS_FILE": str(tmp_path / "no")}) == []


class TestRotationWiring:
    def test_sync_alerts_on_bump_and_on_failure(self, tmp_path: Path) -> None:
        f = tmp_path / "c.txt"
        f.write_text("/p\n")
        env = {"WINDSHIELD_CONSUMERS_FILE": str(f)}
        sent: list[tuple[str, str]] = []
        rot.sync_clients(
            ["1.64.1", "1.65.1"],
            env,
            lambda s, b: sent.append((s, b)),
            lambda _m: None,
            FakeConsumer({"/p": "1.64.1"}),
        )
        assert sent[0][0].endswith("clients updated") and "1.64.1 -> 1.65.1" in sent[0][1]
        sent.clear()
        rot.sync_clients(
            ["1.64.1", "1.65.1"],
            env,
            lambda s, b: sent.append((s, b)),
            lambda _m: None,
            FakeConsumer({"/p": "1.64.1"}, smoke_ok=False),
        )
        assert sent[0][0].endswith("client bump failed")

    def test_sync_is_quiet_when_nothing_is_behind(self, tmp_path: Path) -> None:
        f = tmp_path / "c.txt"
        f.write_text("/p\n")
        sent: list = []
        rot.sync_clients(
            ["1.65.1"],
            {"WINDSHIELD_CONSUMERS_FILE": str(f)},
            lambda s, b: sent.append(s),
            lambda _m: None,
            FakeConsumer({"/p": "1.65.1"}),
        )
        assert sent == []


CYCLES = [
    {"cycle": "3.16", "releaseDate": "2027-10-01", "eol": "2032-10-31"},  # not released yet
    {"cycle": "3.15", "releaseDate": "2026-10-01", "eol": "2031-10-31"},
    {"cycle": "3.14", "releaseDate": "2025-10-07", "eol": "2030-10-31"},
    {"cycle": "3.13", "releaseDate": "2024-10-07", "eol": "2029-10-31"},
    {"cycle": "3.12", "releaseDate": "2023-10-02", "eol": "2028-10-31"},
    {"cycle": "3.8", "releaseDate": "2019-10-14", "eol": "2024-10-07"},  # end of life
    {"cycle": "2.7", "releaseDate": "2010-07-03", "eol": "2020-01-01"},
]


class TestPythonAxis:
    def test_latest_three_released_supported_minors_oldest_first(self) -> None:
        from datetime import date

        got = matrix.latest_python_minors({}, lambda: CYCLES, today=date(2026, 11, 20))
        assert got == ["3.13", "3.14", "3.15"]

    def test_a_new_release_shifts_the_window(self) -> None:
        from datetime import date

        got = matrix.latest_python_minors({}, lambda: CYCLES, today=date(2027, 11, 1))
        assert got == ["3.14", "3.15", "3.16"]

    def test_override_and_offline_fallback(self) -> None:
        assert matrix.latest_python_minors({"WINDSHIELD_PYTHON_VERSIONS": "3.12, 3.13"}) == [
            "3.12",
            "3.13",
        ]

        def offline():
            raise OSError("no network")

        assert matrix.latest_python_minors({}, offline) == list(matrix.PYTHON_FALLBACK)

    def test_every_playwright_version_runs_on_every_python_in_a_container(
        self, tmp_path: Path
    ) -> None:
        calls: list[list[str]] = []

        def runner(cmd, env, timeout):
            calls.append(list(cmd))
            return done(cmd, out="chromium 159")

        results = matrix.run_matrix(
            ["1.62.1", "1.64.1", "1.65.1"], "ws://127.0.0.1:3900", size=3,
            env={"WINDSHIELD_STATE_DIR": str(tmp_path)}, runner=runner, pythons=["3.13", "3.14"],
        )  # fmt: skip
        assert len(results) == 6 and all(r.ok for r in results)
        assert {(r.python, r.version) for r in results} == {
            (p, v) for p in ("3.13", "3.14") for v in ("1.62.1", "1.64.1", "1.65.1")
        }
        pulls = [c for c in calls if c[1] == "pull"]
        assert {c[-1] for c in pulls} == {
            "docker.io/library/python:3.13-slim", "docker.io/library/python:3.14-slim"
        }  # fmt: skip
        builds = [c for c in calls if c[1] == "build"]
        assert {c[c.index("-t") + 1] for c in builds} == {
            "localhost/windshield-matrix-python:3.13", "localhost/windshield-matrix-python:3.14"
        }  # fmt: skip
        assert (
            "libatomic1"
            in (tmp_path / "playwright" / "matrix-images" / "Containerfile.3.13").read_text()
        )
        run = next(
            c for c in calls if "localhost/windshield-matrix-python:3.13" in c and c[1] == "run"
        )
        assert "--network=host" in run and run[run.index("sh") + 1] == "-c"
        assert "1.62.*" in run or "1.64.*" in run or "1.65.*" in run
        assert any(a.startswith("ws://127.0.0.1:3900/1.6") for a in run)

    def test_a_failing_cell_is_reported_with_its_python(self, tmp_path: Path) -> None:
        def runner(cmd, env, timeout):
            if cmd[1] == "run" and "matrix-python:3.15" in " ".join(cmd):
                return done(cmd, 1, out="ERROR: no matching distribution")
            return done(cmd, out="ok")

        results = matrix.run_matrix(
            ["1.64.1", "1.65.1", "1.62.1"], "ws://x:1", env={"WINDSHIELD_STATE_DIR": str(tmp_path)},
            runner=runner, pythons=["3.14", "3.15"],
        )  # fmt: skip
        failed = [r for r in results if not r.ok]
        assert failed and all(r.python == "3.15" for r in failed)
