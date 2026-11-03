"""Waiting helpers: selectors, text, URLs, and retries.

Every wait has the same obligations: honour its deadline, recover a page that was closed under it
through ``recover_page`` (and only for a closed-page error), stop immediately on an abort signal,
and say in its error what it was waiting for. Time and sleeping are scripted; there is no browser.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from windshield import WindshieldError
from windshield import page as pg

CLOSED = RuntimeError("Target page, context or browser has been closed")


class El:
    def __init__(self, visible=True, raises=False):
        self.visible = visible
        self.raises = raises

    def is_visible(self):
        if self.raises:
            raise RuntimeError("detached")
        return self.visible


class Locator:
    def __init__(self, elements, raises=False):
        self.elements = elements
        self.raises = raises

    def count(self):
        if self.raises:
            raise RuntimeError("count failed")
        return len(self.elements)

    def nth(self, idx):
        return self.elements[idx]


class Frame:
    def __init__(self, url, elements=None):
        self.url = url
        self.elements = elements or {}

    def locator(self, selector):
        return Locator(self.elements.get(selector, []))


class Page:
    def __init__(self, elements=None, url="https://example.test/", frames=None, body=""):
        self.elements = elements or {}
        self.url = url
        self.frames = frames or []
        self.main_frame = None
        self.body = body
        self.errors = set()
        self.slept = []
        self.sleep_exc = None

    def locator(self, selector):
        if selector == "body":
            return SimpleNamespace(inner_text=lambda timeout=0: self.body)
        return Locator(self.elements.get(selector, []), selector in self.errors)

    def wait_for_timeout(self, ms):
        self.slept.append(ms)
        if self.sleep_exc is not None:
            raise self.sleep_exc


class Clock:
    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


@pytest.fixture
def clock(monkeypatch):
    def install(step=0.4):
        monkeypatch.setattr(pg, "time", SimpleNamespace(monotonic=Clock(step)))

    install()
    return install


class Script:
    """Scripted outcomes in order, repeating the last one; exceptions are raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


# --- wait_for_selector_to_disappear -------------------------------------------------------


def test_selector_gone_returns_true_at_once(clock):
    page = Page()
    assert pg.wait_for_selector_to_disappear(page, ["#spinner"], 5000) is True
    assert page.slept == []


def test_selector_polls_every_250ms_until_it_disappears(clock, monkeypatch):
    monkeypatch.setattr(pg, "has_any_selector", Script(True, True, False))
    page = Page()
    assert pg.wait_for_selector_to_disappear(page, ["#s"], 60000) is True
    assert page.slept == [250, 250]


def test_selector_still_present_at_the_deadline_is_false(clock):
    page = Page({"#s": [El()]})
    assert pg.wait_for_selector_to_disappear(page, ["#s"], 1000) is False
    assert page.slept == [250, 250]


def test_selector_wait_is_at_least_a_second(clock):
    page = Page({"#s": [El()]})
    pg.wait_for_selector_to_disappear(page, ["#s"], 10)
    assert len(page.slept) == 2


def test_selector_that_vanishes_in_the_final_moment_counts(clock, monkeypatch):
    monkeypatch.setattr(pg, "has_any_selector", Script(True, True, False))
    assert pg.wait_for_selector_to_disappear(Page(), ["#s"], 1000) is True


@pytest.mark.parametrize("stage", ["presence_check", "sleep", "final_check"])
def test_selector_wait_recovers_a_closed_page_at_each_stage(clock, monkeypatch, stage):
    reasons = []

    def recover(reason):
        reasons.append(reason)
        return Page()

    page = Page()
    if stage == "presence_check":
        monkeypatch.setattr(pg, "has_any_selector", Script(CLOSED, False))
    elif stage == "sleep":
        monkeypatch.setattr(pg, "has_any_selector", Script(True, False))
        page.sleep_exc = CLOSED
    else:
        clock(step=100.0)
        monkeypatch.setattr(pg, "has_any_selector", Script(CLOSED, False))

    assert pg.wait_for_selector_to_disappear(page, ["#s"], 1000, recover_page=recover) is True
    assert reasons == [f"wait_for_selector_to_disappear:{stage}"]


@pytest.mark.parametrize("stage", ["presence_check", "sleep", "final_check"])
def test_selector_wait_raises_without_a_recovery_hook(clock, monkeypatch, stage):
    page = Page()
    if stage == "presence_check":
        monkeypatch.setattr(pg, "has_any_selector", Script(CLOSED))
    elif stage == "sleep":
        monkeypatch.setattr(pg, "has_any_selector", Script(True))
        page.sleep_exc = CLOSED
    else:
        clock(step=100.0)
        monkeypatch.setattr(pg, "has_any_selector", Script(CLOSED))
    with pytest.raises(RuntimeError, match="has been closed"):
        pg.wait_for_selector_to_disappear(page, ["#s"], 1000)


@pytest.mark.parametrize("stage", ["presence_check", "sleep", "final_check"])
def test_selector_wait_never_swallows_an_unrelated_error(clock, monkeypatch, stage):
    boom = ValueError("bad selector")
    page = Page()
    if stage == "presence_check":
        monkeypatch.setattr(pg, "has_any_selector", Script(boom, False))
    elif stage == "sleep":
        monkeypatch.setattr(pg, "has_any_selector", Script(True, False))
        page.sleep_exc = boom
    else:
        clock(step=100.0)
        monkeypatch.setattr(pg, "has_any_selector", Script(boom, False))
    with pytest.raises(ValueError):
        pg.wait_for_selector_to_disappear(page, ["#s"], 1000, recover_page=lambda r: Page())


# --- wait_for_text_to_disappear -----------------------------------------------------------


def test_text_wait_with_no_snippets_returns_immediately(clock):
    page = Page()
    assert pg.wait_for_text_to_disappear(page, [], 5000) is True
    assert page.slept == []


def test_text_gone_returns_true_and_present_text_times_out(clock):
    assert pg.wait_for_text_to_disappear(Page(body="all done"), ["loading"], 5000) is True
    page = Page(body="Loading...")
    assert pg.wait_for_text_to_disappear(page, ["loading"], 1000) is False
    assert page.slept == [350, 350]


def test_text_wait_floor_and_late_clear(clock, monkeypatch):
    page = Page(body="Loading")
    pg.wait_for_text_to_disappear(page, ["loading"], 10)
    assert len(page.slept) == 2
    monkeypatch.setattr(pg, "page_contains_any_text", Script(True, True, False))
    assert pg.wait_for_text_to_disappear(Page(), ["x"], 1000) is True


@pytest.mark.parametrize("stage", ["presence_check", "sleep", "final_check"])
def test_text_wait_recovers_a_closed_page_at_each_stage(clock, monkeypatch, stage):
    reasons = []

    def recover(reason):
        reasons.append(reason)
        return Page()

    page = Page()
    if stage == "presence_check":
        monkeypatch.setattr(pg, "page_contains_any_text", Script(CLOSED, False))
    elif stage == "sleep":
        monkeypatch.setattr(pg, "page_contains_any_text", Script(True, False))
        page.sleep_exc = CLOSED
    else:
        clock(step=100.0)
        monkeypatch.setattr(pg, "page_contains_any_text", Script(CLOSED, False))

    assert pg.wait_for_text_to_disappear(page, ["x"], 1000, recover_page=recover) is True
    assert reasons == [f"wait_for_text_to_disappear:{stage}"]


@pytest.mark.parametrize("stage", ["presence_check", "sleep", "final_check"])
def test_text_wait_raises_without_a_hook_and_for_unrelated_errors(clock, monkeypatch, stage):
    for error, hook in ((CLOSED, None), (ValueError("x"), lambda r: Page())):
        page = Page()
        if stage == "presence_check":
            monkeypatch.setattr(pg, "page_contains_any_text", Script(error, False))
        elif stage == "sleep":
            monkeypatch.setattr(pg, "page_contains_any_text", Script(True, False))
            page.sleep_exc = error
        else:
            clock(step=100.0)
            monkeypatch.setattr(pg, "page_contains_any_text", Script(error, False))
        with pytest.raises(type(error)):
            pg.wait_for_text_to_disappear(page, ["x"], 1000, recover_page=hook)
        clock()


# --- wait_for_any_selector ----------------------------------------------------------------


def test_any_selector_requires_selectors_and_a_supported_state():
    with pytest.raises(WindshieldError, match="f: no selectors configured"):
        pg.wait_for_any_selector(Page(), [], 1000, "visible", "f")
    with pytest.raises(WindshieldError, match="unsupported wait state 'hidden'"):
        pg.wait_for_any_selector(Page(), ["#a"], 1000, "hidden", "f")


def test_any_selector_state_defaults_to_visible_and_is_normalised(clock):
    page = Page({"#a": [El(visible=False)]})
    with pytest.raises(WindshieldError, match=r"timeout waiting for selector \(visible\)"):
        pg.wait_for_any_selector(page, ["#a"], 1000, "", "f")
    with pytest.raises(WindshieldError, match=r"\(visible\)"):
        pg.wait_for_any_selector(page, ["#a"], 1000, None, "f")
    assert pg.wait_for_any_selector(Page({"#a": [El()]}), ["#a"], 1000, " VISIBLE ", "f") == "#a"


def test_attached_state_accepts_a_hidden_element(clock):
    page = Page({"#a": [El(visible=False)]})
    assert pg.wait_for_any_selector(page, ["#none", "#a"], 1000, "attached", "f") == "#a"


def test_visible_state_needs_a_visible_one_and_skips_detached_elements(clock):
    page = Page({"#a": [El(raises=True), El(visible=False), El()]})
    assert pg.wait_for_any_selector(page, ["#a"], 1000, "visible", "f") == "#a"


def test_timeout_error_says_what_it_tried(clock):
    page = Page({"#hidden": [El(visible=False)] * 2, "#err": []})
    page.errors.add("#boom")
    with pytest.raises(WindshieldError) as info:
        pg.wait_for_any_selector(page, ["#boom", "#err", "#hidden"], 1000, "visible", "login")
    message = str(info.value)
    assert message.startswith("login: timeout waiting for selector (visible); tried: ")
    assert "#boom (locator error: RuntimeError)" in message
    assert "#err (0 matches)" in message
    assert "#hidden (2 matches, none visible)" in message


def test_the_selector_wait_polls_every_200ms(clock):
    page = Page()
    with pytest.raises(WindshieldError):
        pg.wait_for_any_selector(page, ["#a"], 1000, "visible", "f")
    assert page.slept == [200, 200]


def test_an_abort_signal_stops_the_wait_before_looking(clock):
    page = Page({"#a": [El()]})
    with pytest.raises(WindshieldError, match="f: abort_wait: captcha shown"):
        pg.wait_for_any_selector(
            page, ["#a"], 1000, "visible", "f", abort_check=lambda p: " captcha shown "
        )
    assert page.slept == []


def test_an_abort_signal_that_appears_after_the_sleep_also_stops_it(clock):
    reasons = iter(["", "blocked"])
    page = Page()
    with pytest.raises(WindshieldError, match="abort_wait: blocked"):
        pg.wait_for_any_selector(
            page, ["#a"], 5000, "visible", "f", abort_check=lambda p: next(reasons, "blocked")
        )
    assert len(page.slept) == 1


def test_a_failing_abort_check_is_ignored(clock):
    def broken(page):
        raise RuntimeError("check crashed")

    assert (
        pg.wait_for_any_selector(
            Page({"#a": [El()]}), ["#a"], 1000, "visible", "f", abort_check=broken
        )
        == "#a"
    )
    page = Page()
    with pytest.raises(WindshieldError, match="timeout waiting"):
        pg.wait_for_any_selector(page, ["#a"], 1000, "visible", "f", abort_check=broken)


def test_a_quiet_abort_check_does_not_interfere(clock):
    assert (
        pg.wait_for_any_selector(
            Page({"#a": [El()]}), ["#a"], 1000, "visible", "f", abort_check=lambda p: None
        )
        == "#a"
    )


def test_a_closed_page_while_sleeping_is_recovered_or_reported(clock):
    reasons = []
    fresh = Page({"#a": [El()]})

    def recover(reason):
        reasons.append(reason)
        return fresh

    page = Page()
    page.sleep_exc = CLOSED
    assert (
        pg.wait_for_any_selector(page, ["#a"], 5000, "visible", "f", recover_page=recover) == "#a"
    )
    assert reasons == ["f:wait_for_any_selector"]

    closed = Page()
    closed.sleep_exc = CLOSED
    with pytest.raises(WindshieldError, match="f: page closed while waiting for selector"):
        pg.wait_for_any_selector(closed, ["#a"], 5000, "visible", "f")

    other = Page()
    other.sleep_exc = ValueError("x")
    with pytest.raises(WindshieldError, match="page closed while waiting") as info:
        pg.wait_for_any_selector(other, ["#a"], 5000, "visible", "f", recover_page=recover)
    assert isinstance(info.value.__cause__, ValueError)


# --- wait_for_any_selector_in_contexts ----------------------------------------------------


def test_contexts_wait_requires_selectors_and_a_supported_state():
    with pytest.raises(WindshieldError, match="no selectors configured"):
        pg.wait_for_any_selector_in_contexts(Page(), [], 1000, "visible", "f")
    with pytest.raises(WindshieldError, match="unsupported wait state"):
        pg.wait_for_any_selector_in_contexts(Page(), ["#a"], 1000, "gone", "f")


def test_contexts_wait_returns_the_context_selector_and_its_name(clock):
    frame = Frame("https://example.test/f", {"#in": [El()]})
    page = Page(frames=[frame])
    context, selector, name = pg.wait_for_any_selector_in_contexts(
        page, ["#none", "#in"], 1000, "visible", "f"
    )
    assert context is frame
    assert selector == "#in"
    assert name.startswith("frame[0]<")


def test_contexts_wait_prefers_the_main_page(clock):
    main_el = El()
    frame = Frame("https://example.test/f", {"#a": [El()]})
    page = Page({"#a": [main_el]}, frames=[frame])
    context, _, name = pg.wait_for_any_selector_in_contexts(page, ["#a"], 1000, "attached", "f")
    assert context is page and name == "main"


def test_contexts_wait_visible_skips_hidden_and_detached(clock):
    page = Page({"#a": [El(raises=True), El(visible=False)]})
    with pytest.raises(WindshieldError):
        pg.wait_for_any_selector_in_contexts(page, ["#a"], 1000, "visible", "f")


def test_contexts_wait_timeout_names_each_context_and_selector(clock):
    page = Page({"#hid": [El(visible=False)]})
    page.errors.add("#boom")
    with pytest.raises(WindshieldError) as info:
        pg.wait_for_any_selector_in_contexts(page, ["#boom", "#none", "#hid"], 1000, "", "f")
    message = str(info.value)
    assert "main:#boom (locator error: RuntimeError)" in message
    assert "main:#none (0 matches)" in message
    assert "main:#hid (1 matches, none visible)" in message
    assert "(visible)" in message


def test_contexts_wait_sleep_closed_page_handling(clock):
    reasons = []
    fresh = Page({"#a": [El()]})

    def recover(reason):
        reasons.append(reason)
        return fresh

    page = Page()
    page.sleep_exc = CLOSED
    context, _, _ = pg.wait_for_any_selector_in_contexts(
        page, ["#a"], 5000, "visible", "f", recover_page=recover
    )
    assert context is fresh
    assert reasons == ["f:wait_for_any_selector_in_contexts"]

    closed = Page()
    closed.sleep_exc = CLOSED
    with pytest.raises(WindshieldError, match="page closed while waiting for selector"):
        pg.wait_for_any_selector_in_contexts(closed, ["#a"], 5000, "visible", "f")

    other = Page()
    other.sleep_exc = ValueError("x")
    with pytest.raises(WindshieldError, match="page closed"):
        pg.wait_for_any_selector_in_contexts(
            other, ["#a"], 5000, "visible", "f", recover_page=recover
        )


# --- wait_for_url_contains ----------------------------------------------------------------


def test_url_wait_requires_fragments():
    with pytest.raises(WindshieldError, match="f: no URL fragments configured"):
        pg.wait_for_url_contains(Page(), [], 1000, "f")


def test_url_wait_returns_the_matching_fragment(clock):
    page = Page(url="https://example.test/account/home?x=1")
    assert pg.wait_for_url_contains(page, ["/login", "/account"], 1000, "f") == "/account"


def test_url_wait_times_out_with_the_url_and_fragments(clock):
    page = Page(url="https://example.test/login")
    with pytest.raises(WindshieldError) as info:
        pg.wait_for_url_contains(page, ["/a", "/b"], 1000, "f")
    message = str(info.value)
    assert "f: timeout waiting for URL fragment match" in message
    assert "url=https://example.test/login" in message
    assert "fragments=/a, /b" in message
    assert page.slept == [200, 200]


def test_url_wait_notices_a_url_change_while_waiting(clock):
    urls = iter(["https://x.test/a", "https://x.test/a", "https://x.test/done"])

    class Moving(Page):
        @property
        def url(self):
            return next(urls, "https://x.test/done")

        @url.setter
        def url(self, value):
            pass

    assert pg.wait_for_url_contains(Moving(), ["/done"], 5000, "f") == "/done"


def test_url_wait_abort_signal_before_and_after_the_sleep(clock):
    page = Page(url="https://example.test/a")
    with pytest.raises(WindshieldError, match="f: abort_wait: stop now"):
        pg.wait_for_url_contains(page, ["/zzz"], 1000, "f", abort_check=lambda p: "stop now")
    assert page.slept == []

    answers = iter(["", "late stop"])
    page2 = Page(url="https://example.test/a")
    with pytest.raises(WindshieldError, match="abort_wait: late stop"):
        pg.wait_for_url_contains(
            page2, ["/zzz"], 5000, "f", abort_check=lambda p: next(answers, "late stop")
        )
    assert len(page2.slept) == 1


def test_url_wait_ignores_a_crashing_abort_check(clock):
    def broken(page):
        raise RuntimeError("x")

    page = Page(url="https://example.test/ok")
    assert pg.wait_for_url_contains(page, ["/ok"], 1000, "f", abort_check=broken) == "/ok"
    with pytest.raises(WindshieldError, match="timeout waiting for URL"):
        pg.wait_for_url_contains(Page(), ["/zzz"], 1000, "f", abort_check=broken)


def test_url_wait_closed_page_handling(clock):
    reasons = []
    fresh = Page(url="https://example.test/done")

    def recover(reason):
        reasons.append(reason)
        return fresh

    page = Page()
    page.sleep_exc = CLOSED
    assert pg.wait_for_url_contains(page, ["/done"], 5000, "f", recover_page=recover) == "/done"
    assert reasons == ["f:wait_for_url_contains"]

    closed = Page()
    closed.sleep_exc = CLOSED
    with pytest.raises(WindshieldError, match="f: page closed while waiting for URL"):
        pg.wait_for_url_contains(closed, ["/zzz"], 5000, "f")

    other = Page()
    other.sleep_exc = ValueError("x")
    with pytest.raises(WindshieldError, match="page closed while waiting for URL"):
        pg.wait_for_url_contains(other, ["/zzz"], 5000, "f", recover_page=recover)


def test_a_page_without_a_url_reads_as_empty(clock):
    class NoUrl:
        def wait_for_timeout(self, ms):
            pass

    with pytest.raises(WindshieldError, match="url=; fragments=/x"):
        pg.wait_for_url_contains(NoUrl(), ["/x"], 1000, "f")


# --- retry_browser_wait -------------------------------------------------------------------


def make_wait(*outcomes):
    script = Script(*outcomes)
    return script


def test_retry_returns_the_first_success_without_pausing():
    pauses, notes = [], []
    wait = make_wait("matched")
    result = pg.retry_browser_wait(
        wait_fn=wait,
        field_name="f",
        retry_cycles=3,
        retry_pause_seconds=1,
        pause_fn=lambda ms, why: pauses.append((ms, why)),
        note_fn=notes.append,
    )
    assert result == "matched" and wait.calls == 1 and not pauses and not notes


def test_retry_pauses_and_notes_between_attempts_then_succeeds():
    pauses, notes = [], []
    wait = make_wait(WindshieldError("f: timeout A"), WindshieldError("f: timeout B"), "ok")
    result = pg.retry_browser_wait(
        wait_fn=wait,
        field_name="f",
        retry_cycles=2,
        retry_pause_seconds=1.5,
        pause_fn=lambda ms, why: pauses.append((ms, why)),
        note_fn=notes.append,
    )
    assert result == "ok" and wait.calls == 3
    assert pauses == [(1500, "f:retry_pause_1"), (1500, "f:retry_pause_2")]
    assert notes == [
        "f_retry_scheduled attempt=2/3; pause_seconds=1.5; error=f: timeout A",
        "f_retry_scheduled attempt=3/3; pause_seconds=1.5; error=f: timeout B",
    ]


def test_retry_raises_the_last_error_when_cycles_run_out():
    wait = make_wait(WindshieldError("first"), WindshieldError("last"))
    with pytest.raises(WindshieldError, match="last"):
        pg.retry_browser_wait(wait_fn=wait, field_name="f", retry_cycles=1, retry_pause_seconds=0)
    assert wait.calls == 2


def test_retry_never_retries_an_abort():
    wait = make_wait(WindshieldError("f: abort_wait: blocked"), "ok")
    notes = []
    with pytest.raises(WindshieldError, match="abort_wait: blocked"):
        pg.retry_browser_wait(
            wait_fn=wait,
            field_name="f",
            retry_cycles=5,
            retry_pause_seconds=1,
            note_fn=notes.append,
        )
    assert wait.calls == 1 and notes == []


def test_retry_with_no_cycles_runs_once():
    wait = make_wait(WindshieldError("boom"), "ok")
    with pytest.raises(WindshieldError, match="boom"):
        pg.retry_browser_wait(wait_fn=wait, field_name="f", retry_cycles=0, retry_pause_seconds=1)
    assert wait.calls == 1


def test_retry_clamps_a_negative_pause_to_none():
    pauses = []
    wait = make_wait(WindshieldError("a"), "ok")
    result = pg.retry_browser_wait(
        wait_fn=wait,
        field_name="f",
        retry_cycles=1,
        retry_pause_seconds=-1,
        pause_fn=lambda ms, why: pauses.append(ms),
    )
    assert result == "ok"
    assert pauses == []  # a negative pause becomes zero, which means no pause at all


def test_retry_clamps_negative_cycles_to_a_single_attempt():
    wait = make_wait(WindshieldError("a"), "ok")
    with pytest.raises(WindshieldError, match="a"):
        pg.retry_browser_wait(wait_fn=wait, field_name="f", retry_cycles=-4, retry_pause_seconds=0)
    assert wait.calls == 1


def test_retry_only_catches_windshield_errors():
    wait = make_wait(ValueError("not ours"), "ok")
    with pytest.raises(ValueError):
        pg.retry_browser_wait(wait_fn=wait, field_name="f", retry_cycles=3, retry_pause_seconds=0)
    assert wait.calls == 1
