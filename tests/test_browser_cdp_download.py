"""Chrome discovery, the Chrome-for-Testing download path, and the CDP readiness poll.

Network, sleeping and the real filesystem outside ``tmp_path`` are all replaced: ``urlopen`` is
faked, the clock is scripted, ``PATH`` lookups and the home directory are redirected, and the
"Chrome" that gets extracted is a few bytes in a zip built on the fly.
"""

from __future__ import annotations

import json
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from windshield import browser
from windshield._errors import WindshieldError


class Response:
    def __init__(self, body: bytes):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(monkeypatch, *responses):
    """Each call returns/raises the next response; the request is recorded."""
    seen = []
    queue = list(responses)

    def urlopen(request, timeout=None):
        seen.append((request, timeout))
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, BaseException):
            raise item
        return Response(item if isinstance(item, bytes) else item.encode())

    monkeypatch.setattr(browser.urllib.request, "urlopen", urlopen)
    return seen


# --- CDP ----------------------------------------------------------------------------------


def test_cdp_version_is_parsed_from_the_json_endpoint(monkeypatch):
    seen = fake_urlopen(monkeypatch, json.dumps({"Browser": "Chrome/1"}))
    assert browser.fetch_cdp_version("127.0.0.1", 9222) == {"Browser": "Chrome/1"}
    assert seen[0][0] == "http://127.0.0.1:9222/json/version"
    assert seen[0][1] == 1.5


@pytest.mark.parametrize("body", ["not json", "[1, 2]", '"text"'])
def test_cdp_version_that_is_not_an_object_is_none(monkeypatch, body):
    fake_urlopen(monkeypatch, body)
    assert browser.fetch_cdp_version("h", 1) is None


def test_cdp_version_connection_failure_is_none(monkeypatch):
    fake_urlopen(monkeypatch, OSError("refused"))
    assert browser.fetch_cdp_version("h", 1) is None


class Ticker:
    """Clock that advances 0.4s per reading; sleep records the requested pauses."""

    def __init__(self):
        self.now = 0.0
        self.slept = []

    def monotonic(self):
        value = self.now
        self.now += 0.4
        return value

    def sleep(self, seconds):
        self.slept.append(seconds)


@pytest.fixture
def ticker(monkeypatch):
    t = Ticker()
    monkeypatch.setattr(browser, "time", SimpleNamespace(monotonic=t.monotonic, sleep=t.sleep))
    return t


def test_wait_for_cdp_returns_as_soon_as_chrome_answers(monkeypatch, ticker):
    answers = iter([None, None, {"Browser": "Chrome/1"}])
    monkeypatch.setattr(browser, "fetch_cdp_version", lambda h, p, timeout_seconds: next(answers))

    assert browser.wait_for_cdp_version("h", 1, 30, poll_interval_seconds=0.5) == {
        "Browser": "Chrome/1"
    }
    assert ticker.slept == [0.5, 0.5]


def test_wait_for_cdp_gives_up_with_the_endpoint_in_the_message(monkeypatch, ticker):
    monkeypatch.setattr(browser, "fetch_cdp_version", lambda h, p, timeout_seconds: None)

    with pytest.raises(WindshieldError, match="chrome_cdp_not_ready") as info:
        browser.wait_for_cdp_version("10.0.0.5", 9333, 3)

    message = str(info.value)
    assert "host=10.0.0.5" in message
    assert "port=9333" in message
    assert "timeout_seconds=3" in message


def test_wait_for_cdp_never_busy_loops_and_waits_at_least_a_second(monkeypatch, ticker):
    calls = []
    monkeypatch.setattr(
        browser, "fetch_cdp_version", lambda h, p, timeout_seconds: calls.append(1) and None
    )

    with pytest.raises(WindshieldError):
        browser.wait_for_cdp_version("h", 1, 0, poll_interval_seconds=0.0)

    assert min(ticker.slept) == 0.1  # a zero interval is raised to 100ms
    assert len(calls) == 2  # a zero timeout still gets a one-second window (0.4s per reading)


# --- JSON fetch ---------------------------------------------------------------------------


def test_fetch_json_url_sends_the_user_agent_and_returns_the_object(monkeypatch):
    seen = fake_urlopen(monkeypatch, '{"a": 1}')
    assert browser.fetch_json_url("https://x.test/j", user_agent="ua/9") == {"a": 1}
    request, timeout = seen[0]
    assert request.get_header("User-agent") == "ua/9"
    assert timeout == 45.0


def test_fetch_json_url_network_failure_names_the_error_type(monkeypatch):
    fake_urlopen(monkeypatch, TimeoutError("slow"))
    with pytest.raises(WindshieldError, match="json_fetch_failed: TimeoutError: slow"):
        browser.fetch_json_url("https://x.test/j")


def test_fetch_json_url_bad_json_does_not_echo_the_body(monkeypatch):
    fake_urlopen(monkeypatch, "<html>secret-token-in-error-page</html>")
    with pytest.raises(WindshieldError) as info:
        browser.fetch_json_url("https://x.test/j")
    assert "json_parse_failed" in str(info.value)
    assert "secret-token" not in str(info.value)


def test_fetch_json_url_requires_an_object(monkeypatch):
    fake_urlopen(monkeypatch, "[1]")
    with pytest.raises(WindshieldError, match="expected object"):
        browser.fetch_json_url("https://x.test/j")


# --- resolving the download ---------------------------------------------------------------


def metadata(**channels):
    return json.dumps({"channels": channels})


def channel(version="130.0.1", **downloads):
    return {"version": version, "downloads": downloads}


def chrome(*items):
    return {"chrome": [dict(platform=p, url=u) for p, u in items]}


def resolve_with(monkeypatch, payload, **kwargs):
    fake_urlopen(monkeypatch, payload)
    return browser.resolve_cft_download_url(**kwargs)


def test_resolve_picks_the_platform_and_returns_the_version(monkeypatch):
    payload = metadata(
        Stable=channel("130.0.1", **chrome(("mac-x64", "https://m"), ("linux64", "https://l")))
    )
    assert resolve_with(monkeypatch, payload) == ("https://l", "130.0.1")


def test_resolve_honours_the_requested_channel(monkeypatch):
    payload = metadata(
        Stable=channel("1", **chrome(("linux64", "https://stable"))),
        Beta=channel("2", **chrome(("linux64", "https://beta"))),
    )
    assert resolve_with(monkeypatch, payload, channel="Beta") == ("https://beta", "2")


def test_resolve_falls_back_to_stable_for_an_unknown_channel(monkeypatch):
    payload = metadata(Stable=channel("1", **chrome(("linux64", "https://stable"))))
    assert resolve_with(monkeypatch, payload, channel="Nightly") == ("https://stable", "1")


def test_resolve_fails_when_not_even_stable_exists(monkeypatch):
    with pytest.raises(WindshieldError, match="chrome_download_channel_not_found: channel=Nightly"):
        resolve_with(monkeypatch, metadata(Beta=channel()), channel="Nightly")


def test_resolve_reports_each_malformed_metadata_shape(monkeypatch):
    with pytest.raises(WindshieldError, match="missing_channels"):
        resolve_with(monkeypatch, json.dumps({"channels": []}))
    with pytest.raises(WindshieldError, match="missing_downloads"):
        resolve_with(monkeypatch, metadata(Stable={"version": "1", "downloads": []}))
    with pytest.raises(WindshieldError, match="missing_chrome_downloads"):
        resolve_with(monkeypatch, metadata(Stable=channel(chrome="nope")))


def test_resolve_skips_junk_entries_and_blank_urls(monkeypatch):
    payload = metadata(
        Stable=channel(
            "7",
            chrome=[
                "junk",
                {"platform": "linux64", "url": "  "},
                {"platform": "linux64", "url": " https://good "},
            ],
        )
    )
    assert resolve_with(monkeypatch, payload) == ("https://good", "7")


def test_resolve_without_a_version_says_unknown(monkeypatch):
    payload = metadata(Stable={"downloads": chrome(("linux64", "https://l"))})
    assert resolve_with(monkeypatch, payload) == ("https://l", "unknown")


def test_resolve_reports_the_fallback_channel_when_the_platform_is_missing(monkeypatch):
    payload = metadata(Stable=channel(**chrome(("mac-x64", "https://m"))))
    with pytest.raises(WindshieldError, match="channel=Stable; platform=linux64"):
        resolve_with(monkeypatch, payload, channel="Nightly")


def test_resolve_names_channel_and_platform_when_nothing_matches(monkeypatch):
    payload = metadata(Stable=channel(**chrome(("mac-x64", "https://m"))))
    with pytest.raises(WindshieldError, match="channel=Stable; platform=linux64"):
        resolve_with(monkeypatch, payload)


# --- downloading and extracting -----------------------------------------------------------


def test_download_writes_the_payload_and_creates_parents(monkeypatch, tmp_path):
    seen = fake_urlopen(monkeypatch, b"zip-bytes")
    target = tmp_path / "a" / "b" / "c.zip"
    browser.download_url_to_file("https://x.test/c.zip", target, user_agent="ua/1")
    assert target.read_bytes() == b"zip-bytes"
    assert seen[0][0].get_header("User-agent") == "ua/1"
    assert seen[0][1] == 120.0


def test_a_failed_download_leaves_no_file_and_names_the_url(monkeypatch, tmp_path):
    fake_urlopen(monkeypatch, OSError("reset"))
    target = tmp_path / "c.zip"
    with pytest.raises(WindshieldError, match="download_failed: url=https://x.test/c.zip"):
        browser.download_url_to_file("https://x.test/c.zip", target)
    assert not target.exists()


def make_zip(path: Path, members: dict[str, tuple[bytes, int]]):
    with zipfile.ZipFile(path, "w") as zf:
        for name, (data, mode) in members.items():
            info = zipfile.ZipInfo(name)
            # mode 0 means 'no Unix permissions recorded': only a DOS attribute bit is set
            # (writestr would otherwise substitute 0o600 for a zero attribute word).
            info.external_attr = ((mode & 0xFFFF) << 16) if mode else 0x20
            zf.writestr(info, data)


def test_extraction_restores_unix_permissions_and_masks_special_bits(tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(
        archive,
        {
            "chrome-linux64/chrome": (b"bin", 0o100755),
            "chrome-linux64/readme": (b"txt", 0o100644),
            "chrome-linux64/suid": (b"x", 0o104755),  # setuid bit must not be restored
            "chrome-linux64/nomode": (b"y", 0),
        },
    )
    out = tmp_path / "out"
    out.mkdir()

    browser.extract_zip_with_permissions(archive, out)

    def mode(name):
        return stat.S_IMODE((out / "chrome-linux64" / name).stat().st_mode)

    assert mode("chrome") == 0o755
    assert mode("readme") == 0o644
    assert mode("suid") == 0o755
    assert (out / "chrome-linux64" / "nomode").read_bytes() == b"y"


def test_extraction_cannot_write_outside_the_target_directory(tmp_path):
    archive = tmp_path / "evil.zip"
    make_zip(archive, {"../escaped.txt": (b"pwn", 0o100644)})
    out = tmp_path / "out"
    out.mkdir()

    browser.extract_zip_with_permissions(archive, out)

    assert not (tmp_path / "escaped.txt").exists()


def test_extraction_ignores_a_chmod_that_fails(monkeypatch, tmp_path):
    archive = tmp_path / "a.zip"
    make_zip(archive, {"f": (b"x", 0o100755)})
    out = tmp_path / "out"
    out.mkdir()

    def deny(self, mode):
        raise PermissionError("no")

    monkeypatch.setattr(Path, "chmod", deny)
    browser.extract_zip_with_permissions(archive, out)
    assert (out / "f").read_bytes() == b"x"


def test_runtime_permissions_only_add_execute_to_chrome_and_its_helpers(tmp_path):
    bin_dir = tmp_path / "chrome-linux64"
    bin_dir.mkdir()
    for name in ("chrome", "chrome_crashpad_handler", "chrome-wrapper", "chrome_sandbox",
                 "chrome-sandbox", "unrelated"):  # fmt: skip
        (bin_dir / name).write_bytes(b"x")
        (bin_dir / name).chmod(0o600)
    (bin_dir / "chrome").chmod(0o640)

    browser.ensure_chrome_runtime_permissions(bin_dir / "chrome")

    def mode(name):
        return stat.S_IMODE((bin_dir / name).stat().st_mode)

    assert mode("chrome") == 0o751
    for helper in ("chrome_crashpad_handler", "chrome-wrapper", "chrome_sandbox", "chrome-sandbox"):
        assert mode(helper) == 0o711
    assert mode("unrelated") == 0o600


def test_runtime_permissions_leave_an_already_executable_file_alone(tmp_path):
    exe = tmp_path / "chrome"
    exe.write_bytes(b"x")
    exe.chmod(0o750)
    browser.ensure_chrome_runtime_permissions(exe)
    assert stat.S_IMODE(exe.stat().st_mode) == 0o750


def test_runtime_permissions_survive_a_chmod_that_fails(monkeypatch, tmp_path):
    exe = tmp_path / "chrome"
    exe.write_bytes(b"x")
    exe.chmod(0o600)

    def deny(self, mode):
        raise PermissionError("read-only filesystem")

    monkeypatch.setattr(Path, "chmod", deny)
    browser.ensure_chrome_runtime_permissions(exe)  # must not raise
    assert not exe.stat().st_mode & 0o111


def test_runtime_permissions_tolerate_a_missing_binary_and_directories(tmp_path):
    (tmp_path / "chrome_sandbox").mkdir()
    browser.ensure_chrome_runtime_permissions(tmp_path / "chrome")  # nothing there: no error


# --- finding an executable ----------------------------------------------------------------


def touch_chrome(base: Path, layout="chrome-linux64") -> Path:
    exe = base / layout / "chrome"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"x")
    exe.chmod(0o644)
    return exe


def test_chrome_executable_prefers_linux64_and_makes_it_runnable(tmp_path):
    older = touch_chrome(tmp_path, "chrome-linux")
    newer = touch_chrome(tmp_path, "chrome-linux64")
    assert browser.chrome_executable_from_dir(tmp_path) == str(newer)
    assert newer.stat().st_mode & 0o111
    assert not older.stat().st_mode & 0o111


def test_chrome_executable_falls_back_to_the_older_layout(tmp_path):
    only = touch_chrome(tmp_path, "chrome-linux")
    assert browser.chrome_executable_from_dir(tmp_path) == str(only)


def test_existing_cft_prefers_the_newest_and_the_linux64_layout(tmp_path):
    touch_chrome(tmp_path / "chrome-stable-100-linux64")
    newest = touch_chrome(tmp_path / "chrome-stable-130-linux64")
    assert browser.find_existing_cft_executable(tmp_path) == str(newest)


def test_existing_cft_falls_back_to_the_older_layout(tmp_path):
    only = touch_chrome(tmp_path / "chrome-stable-1-linux64", "chrome-linux")
    assert browser.find_existing_cft_executable(tmp_path) == str(only)


def test_existing_cft_none(tmp_path):
    assert browser.find_existing_cft_executable(tmp_path) == ""


def test_download_returns_an_existing_install_without_touching_the_network(monkeypatch, tmp_path):
    exe = touch_chrome(tmp_path / "chrome-stable-1-linux64")
    monkeypatch.setattr(
        browser, "resolve_cft_download_url", lambda **kw: pytest.fail("must not resolve")
    )
    assert browser.download_chrome_for_testing(tmp_path) == str(exe)


def stub_download(monkeypatch, tmp_path, *, files, version="130.0.1"):
    calls = SimpleNamespace(downloads=[], resolved=[])

    def resolve(channel, platform):
        calls.resolved.append((channel, platform))
        return "https://dl.test/chrome.zip", version

    def download(url, target, timeout_seconds):
        calls.downloads.append((url, target.name, timeout_seconds))
        make_zip(target, files)

    monkeypatch.setattr(browser, "resolve_cft_download_url", resolve)
    monkeypatch.setattr(browser, "download_url_to_file", download)
    return calls


CHROME_ZIP = {"chrome-linux64/chrome": (b"bin", 0o100644)}


def test_download_fetches_extracts_and_returns_the_executable(monkeypatch, tmp_path):
    calls = stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)

    exe = browser.download_chrome_for_testing(tmp_path, channel="Stable", platform="linux64")

    expected = tmp_path / "chrome-stable-130.0.1-linux64" / "chrome-linux64" / "chrome"
    assert exe == str(expected)
    assert expected.stat().st_mode & 0o111
    assert calls.resolved == [("Stable", "linux64")]
    assert calls.downloads == [
        ("https://dl.test/chrome.zip", "chrome-stable-130.0.1-linux64.zip", 180)
    ]


def test_a_hostile_version_string_cannot_escape_the_download_directory(monkeypatch, tmp_path):
    stub_download(monkeypatch, tmp_path, files=CHROME_ZIP, version="../../etc/x y")
    exe = Path(browser.download_chrome_for_testing(tmp_path))
    assert tmp_path in exe.parents
    # every separator became a dash, so the whole version is one harmless directory name
    assert exe.relative_to(tmp_path).parts[0] == "chrome-stable-..-..-etc-x-y-linux64"


def test_a_version_of_only_symbols_becomes_unknown(monkeypatch, tmp_path):
    stub_download(monkeypatch, tmp_path, files=CHROME_ZIP, version="///")
    exe = Path(browser.download_chrome_for_testing(tmp_path))
    assert exe.relative_to(tmp_path).parts[0] == "chrome-stable---linux64"


def test_an_already_extracted_version_is_reused_without_downloading(monkeypatch, tmp_path):
    calls = stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)
    extracted = tmp_path / "chrome-stable-130.0.1-linux64"
    exe = touch_chrome(extracted)
    # find_existing_cft_executable looks for chrome-*/chrome-linux64/chrome, so force the
    # second lookup by hiding the first.
    monkeypatch.setattr(browser, "find_existing_cft_executable", lambda d: "")

    assert browser.download_chrome_for_testing(tmp_path) == str(exe)
    assert calls.downloads == []


def test_force_download_re_downloads_and_replaces_the_old_extraction(monkeypatch, tmp_path):
    calls = stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)
    extracted = tmp_path / "chrome-stable-130.0.1-linux64"
    stale = touch_chrome(extracted)
    (extracted / "stale-leftover").write_text("old")

    exe = browser.download_chrome_for_testing(tmp_path, force_download=True)

    assert exe == str(stale)
    assert not (extracted / "stale-leftover").exists()
    assert len(calls.downloads) == 1


def test_force_download_replaces_a_cached_archive(monkeypatch, tmp_path):
    calls = stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)
    make_zip(tmp_path / "chrome-stable-130.0.1-linux64.zip", {"stale": (b"old", 0o100644)})

    exe = browser.download_chrome_for_testing(tmp_path, force_download=True)

    assert len(calls.downloads) == 1
    assert Path(exe).exists()  # the stale archive had no chrome; the fresh one did


def test_a_cached_archive_is_reused_unless_forced(monkeypatch, tmp_path):
    calls = stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)
    make_zip(tmp_path / "chrome-stable-130.0.1-linux64.zip", CHROME_ZIP)

    browser.download_chrome_for_testing(tmp_path)

    assert calls.downloads == []


def test_a_corrupt_archive_is_reported_as_an_extract_failure(monkeypatch, tmp_path):
    stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)
    (tmp_path / "chrome-stable-130.0.1-linux64.zip").write_bytes(b"this is not a zip")
    with pytest.raises(WindshieldError, match="chrome_extract_failed: BadZipFile"):
        browser.download_chrome_for_testing(tmp_path)


def test_an_archive_without_chrome_is_an_error(monkeypatch, tmp_path):
    stub_download(monkeypatch, tmp_path, files={"README": (b"x", 0o100644)})
    with pytest.raises(WindshieldError, match="chrome_executable_not_found_after_extract"):
        browser.download_chrome_for_testing(tmp_path)


def test_relative_and_default_download_dirs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    stub_download(monkeypatch, tmp_path, files=CHROME_ZIP)

    relative = browser.download_chrome_for_testing(Path("rel-dir"))
    assert relative.startswith(str(tmp_path / "rel-dir"))

    default = browser.download_chrome_for_testing(None, default_download_dir=tmp_path / "dflt")
    assert default.startswith(str(tmp_path / "dflt"))

    cwd_default = browser.download_chrome_for_testing(None)
    assert cwd_default.startswith(str(tmp_path / "chrome-for-testing"))


# --- discovery ----------------------------------------------------------------------------


@pytest.fixture
def no_chrome(monkeypatch, tmp_path):
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr(browser.shutil, "which", lambda name: None)
    monkeypatch.setattr(browser.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return tmp_path


def test_discovery_finds_nothing_on_a_bare_machine(no_chrome):
    assert browser.discover_chrome_binary() == ""


def test_an_absolute_env_binary_must_exist(monkeypatch, no_chrome):
    exe = no_chrome / "my-chrome"
    exe.write_bytes(b"x")
    monkeypatch.setenv("CHROME_BIN", str(exe))
    assert browser.discover_chrome_binary() == str(exe)

    monkeypatch.setenv("CHROME_BIN", str(no_chrome / "gone"))
    assert browser.discover_chrome_binary() == ""


def test_a_relative_env_binary_is_looked_up_on_path(monkeypatch, no_chrome):
    monkeypatch.setenv("MY_BIN", "my-chrome")
    monkeypatch.setattr(
        browser.shutil, "which", lambda name: "/usr/bin/my-chrome" if name == "my-chrome" else None
    )
    assert browser.discover_chrome_binary(env_var="MY_BIN") == "/usr/bin/my-chrome"


def test_a_relative_env_binary_not_on_path_falls_through(monkeypatch, no_chrome):
    monkeypatch.setenv("CHROME_BIN", "nonexistent-chrome")
    assert browser.discover_chrome_binary() == ""


def test_well_known_names_are_tried_in_order(monkeypatch, no_chrome):
    tried = []

    def which(name):
        tried.append(name)
        return "/usr/bin/chromium" if name == "chromium" else None

    monkeypatch.setattr(browser.shutil, "which", which)
    assert browser.discover_chrome_binary() == "/usr/bin/chromium"
    assert tried == ["google-chrome", "google-chrome-stable", "chromium"]


def test_the_env_override_wins_over_path(monkeypatch, no_chrome):
    exe = no_chrome / "pinned"
    exe.write_bytes(b"x")
    monkeypatch.setenv("CHROME_BIN", str(exe))
    monkeypatch.setattr(browser.shutil, "which", lambda name: "/usr/bin/" + name)
    assert browser.discover_chrome_binary() == str(exe)


def test_a_cached_download_is_used_when_path_has_nothing(no_chrome):
    dl = no_chrome / "dl"
    exe = touch_chrome(dl / "chrome-stable-1-linux64")
    assert browser.discover_chrome_binary(default_download_dir=dl) == str(exe)


def test_a_direct_layout_download_dir_is_used_first(no_chrome):
    dl = no_chrome / "dl"
    direct = touch_chrome(dl)
    touch_chrome(dl / "chrome-stable-1-linux64")
    assert browser.discover_chrome_binary(default_download_dir=dl) == str(direct)


def test_the_older_cached_layout_is_found_and_the_newest_wins(no_chrome):
    dl = no_chrome / "dl"
    touch_chrome(dl / "chrome-stable-1-linux64", "chrome-linux")
    newest = touch_chrome(dl / "chrome-stable-2-linux64", "chrome-linux")
    assert browser.discover_chrome_binary(default_download_dir=dl) == str(newest)


def test_a_playwright_cache_is_the_last_resort_and_the_newest_wins(no_chrome):
    home = no_chrome / "home" / ".cache" / "ms-playwright"
    touch_chrome(home / "chromium-1000", "chrome-linux")
    newest = touch_chrome(home / "chromium-1200", "chrome-linux64")
    assert browser.discover_chrome_binary() == str(newest)


def test_a_dangling_playwright_entry_is_not_returned(no_chrome):
    home = no_chrome / "home" / ".cache" / "ms-playwright"
    good = touch_chrome(home / "chromium-1000", "chrome-linux")
    broken = home / "chromium-1200" / "chrome-linux" / "chrome"
    broken.parent.mkdir(parents=True)
    broken.symlink_to(no_chrome / "does-not-exist")
    assert browser.discover_chrome_binary() == str(good)


def test_path_beats_every_cache(monkeypatch, no_chrome):
    touch_chrome(no_chrome / "home" / ".cache" / "ms-playwright" / "chromium-1")
    monkeypatch.setattr(
        browser.shutil, "which", lambda name: "/usr/bin/chrome" if name == "chrome" else None
    )
    assert browser.discover_chrome_binary() == "/usr/bin/chrome"
