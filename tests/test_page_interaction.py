"""Page interaction primitives: frames, filling, typing, clicking, submitting.

These drive login and download flows, so the properties that matter are: only a visible and
enabled element is touched, a failing strategy falls through to the next one, a value is never
reported as set until it reads back, and no error message ever carries the value that was typed
(it is often a password). The page and its elements are scripted fakes; no browser is involved.
"""

from __future__ import annotations

import pytest

from windshield import WindshieldError
from windshield import page as pg

SECRET = "hunter2-s3cret"


class El:
    """A scriptable element. ``fail`` names operations that raise; ``ignore`` ones that no-op."""

    def __init__(self, *, visible=True, enabled=True, value="", text="", fail=(), ignore=()):
        self.visible = visible
        self.enabled = enabled
        self.value = value
        self.text = text
        self.fail = set(fail)
        self.ignore = set(ignore)
        self.calls = []

    def _do(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if name in self.fail:
            raise RuntimeError(f"{name} failed")

    def is_visible(self):
        self._do("is_visible")
        return self.visible

    def is_enabled(self):
        self._do("is_enabled")
        return self.enabled

    def fill(self, value):
        self._do("fill", value)
        if "fill" not in self.ignore:
            self.value = value

    def type(self, value, delay=0):
        self._do("type", value, delay=delay)
        if "type" not in self.ignore:
            self.value += value

    def click(self, **kwargs):
        self._do("click_force" if kwargs.get("force") else "click", **kwargs)

    def press(self, key):
        self._do("press", key)

    def input_value(self):
        self._do("input_value")
        return self.value

    def evaluate(self, script, arg=None):
        if "innerText" in script:
            self._do("text")
            return self.text
        if script.strip() == "el => el.click()":
            self._do("js_click")
            return None
        if "requestSubmit" in script:
            self._do("submit")
            return None
        if "nextValue" in script:
            self._do("script_set", arg)
            if "script" not in self.ignore:
                self.value = arg
            return None
        self._do("evaluate_value")
        return self.value

    def names(self):
        return [name for name, _, _ in self.calls]


class Locator:
    def __init__(self, elements, count_raises=False):
        self.elements = elements
        self.count_raises = count_raises

    def count(self):
        if self.count_raises:
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
    def __init__(self, elements=None, url="https://example.test/", frames=None):
        self.elements = elements or {}
        self.url = url
        self.frames = frames or []
        self.main_frame = None
        self.count_raises = set()
        self.slept = []

    def locator(self, selector):
        return Locator(self.elements.get(selector, []), selector in self.count_raises)

    def wait_for_timeout(self, ms):
        self.slept.append(ms)


# --- frames and contexts ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Target page, context or browser has been closed", True),
        ("Page has been closed", True),
        ("Context has been closed", True),
        ("Browser has been closed", True),
        ("Timeout 30000ms exceeded", False),
        ("", False),
        (None, False),
    ],
)
def test_closed_page_errors_are_recognised(message, expected):
    assert pg.is_page_or_context_closed_error(RuntimeError(message)) is expected


def test_contexts_are_the_page_plus_same_origin_frames_only():
    same = Frame("https://example.test/embed")
    other = Frame("https://ads.example/banner")
    blank = Frame("")
    inline = Frame("about:blank")
    page = Page(frames=[same, other, blank, inline])

    names = [name for name, _ in pg.iter_locator_contexts(page)]

    assert names[0] == "main"
    assert any("embed" in n for n in names)
    assert not any("ads.example" in n for n in names)
    assert len(names) == 4  # main, same-origin, blank url, about:blank


def test_the_main_frame_is_not_listed_twice():
    main = Frame("https://example.test/")
    page = Page(frames=[main, Frame("https://example.test/child")])
    page.main_frame = main
    assert len(pg.iter_locator_contexts(page)) == 2


def test_contexts_survive_a_page_with_no_frames_attribute():
    class Bare:
        url = "https://example.test/"

    assert [n for n, _ in pg.iter_locator_contexts(Bare())] == ["main"]


def test_contexts_survive_an_unparseable_url():
    class Weird:
        url = object()
        frames = []
        main_frame = None

    assert pg.iter_locator_contexts(Weird())[0][0] == "main"


def test_page_frames_fall_back_to_main_frame_then_the_page_itself():
    f1, f2 = Frame("a"), Frame("b")
    assert pg.iter_page_frames(Page(frames=[f1, None, f2])) == [f1, f2]

    page = Page()
    page.main_frame = f1
    assert pg.iter_page_frames(page) == [f1]

    bare = Page()
    assert pg.iter_page_frames(bare) == [bare]

    class Broken:
        @property
        def frames(self):
            raise RuntimeError

        @property
        def main_frame(self):
            raise RuntimeError

    broken = Broken()
    assert pg.iter_page_frames(broken) == [broken]


def test_read_page_text_prefers_the_body_then_content_then_nothing():
    class Body:
        def inner_text(self, timeout=0):
            return "visible text"

    class Ok:
        def locator(self, sel):
            return Body()

    class NoBody:
        def locator(self, sel):
            raise RuntimeError

        def content(self):
            return "<html>fallback</html>"

    class Nothing:
        def locator(self, sel):
            raise RuntimeError

        def content(self):
            raise RuntimeError

    assert pg.read_page_text(Ok()) == "visible text"
    assert pg.read_page_text(NoBody()) == "<html>fallback</html>"
    assert pg.read_page_text(Nothing()) == ""


def test_title_and_text_matching_helpers():
    class P:
        def title(self):
            return "Sign In - Example"

        def locator(self, sel):
            class B:
                def inner_text(self, timeout=0):
                    return "Welcome. Enter your PASSWORD."

            return B()

    page = P()
    assert pg.title_contains_any_text(page, ["sign in"])
    assert not pg.title_contains_any_text(page, ["", "  ", "logout"])
    assert not pg.title_contains_any_text(page, [])
    assert pg.page_contains_any_text(page, ["password"])
    assert not pg.page_contains_any_text(page, ["", "nothing"])
    assert pg.matching_text_snippets(page, ["Password", "welcome", "absent", "welcome"]) == [
        "password",
        "welcome",
    ]
    assert pg.matching_text_snippets(page, ["", " "]) == []


def test_a_title_that_cannot_be_read_matches_nothing():
    class P:
        def title(self):
            raise RuntimeError("detached")

    assert not pg.title_contains_any_text(P(), ["x"])


def test_has_any_selector_looks_in_same_origin_frames_and_skips_errors():
    frame = Frame("https://example.test/f", {"#in-frame": [El()]})
    page = Page(frames=[frame])
    page.count_raises.add("#broken")
    assert pg.has_any_selector(page, ["#broken", "#in-frame"])
    assert not pg.has_any_selector(page, ["#broken", "#absent"])


def test_first_visible_selector_match_names_the_context_and_skips_hidden_and_broken():
    hidden = El(visible=False)
    detached = El(fail={"is_visible"})
    shown = El()
    page = Page({"#a": [hidden, detached], "#b": [shown]})
    page.count_raises.add("#err")
    assert pg.first_visible_selector_match(page, ["#err", "#a", "#b"]) == "main:#b"
    assert pg.first_visible_selector_match(page, ["#a"]) == ""


def test_first_visible_selector_match_only_checks_twelve_elements():
    page = Page({"#a": [El(visible=False)] * 12 + [El()]})
    assert pg.first_visible_selector_match(page, ["#a"]) == ""


# --- fill ---------------------------------------------------------------------------------


def test_fill_requires_selectors():
    with pytest.raises(WindshieldError, match="user: no selectors configured"):
        pg.fill_first_visible(Page(), [], "x", "user")


def test_fill_uses_the_first_visible_enabled_element_of_the_first_selector_that_has_one():
    hidden = El(visible=False)
    disabled = El(enabled=False)
    good = El()
    page = Page({"#a": [hidden, disabled, good], "#b": [El()]})
    assert pg.fill_first_visible(page, ["#none", "#a", "#b"], "val", "user") == "#a"
    assert good.value == "val"
    assert hidden.names() == ["is_visible"]
    assert disabled.names() == ["is_visible", "is_enabled"]


def test_fill_moves_on_after_a_failing_element_and_reports_it_if_nothing_works():
    bad = El(fail={"fill"})
    page = Page({"#a": [bad]})
    with pytest.raises(WindshieldError) as info:
        pg.fill_first_visible(page, ["#a", "#zero"], SECRET, "password")
    message = str(info.value)
    assert "#a[0] fill-error(RuntimeError)" in message
    assert "#a (1 matches, none visible+enabled)" in message
    assert "#zero (0 matches)" in message
    assert "password: no visible editable element found" in message
    assert SECRET not in message


def test_fill_falls_through_to_the_next_selector_when_an_element_errors():
    bad, good = El(fail={"fill"}), El()
    page = Page({"#a": [bad], "#b": [good]})
    assert pg.fill_first_visible(page, ["#a", "#b"], "v", "f") == "#b"


# --- type ---------------------------------------------------------------------------------


def test_type_requires_selectors():
    with pytest.raises(WindshieldError, match="no selectors configured"):
        pg.type_first_visible(Page(), [], "x", "user")


def test_type_clicks_clears_then_types_with_the_delay():
    el = El(value="old")
    page = Page({"#a": [el]})
    el.value = "old"
    assert pg.type_first_visible(page, ["#a"], "new", "user", delay_ms=-5) == "#a"
    assert el.names() == ["is_visible", "is_enabled", "click", "fill", "type"]
    assert el.calls[-1][2]["delay"] == 0  # a negative delay is clamped
    assert el.value == "new"


def test_type_uses_the_requested_delay():
    el = El()
    pg.type_first_visible(Page({"#a": [el]}), ["#a"], "x", "f", delay_ms=70)
    assert el.calls[-1][2]["delay"] == 70


def test_type_treats_an_unreadable_state_as_not_usable_and_skips_it():
    flaky = El(fail={"is_visible"})
    disabled = El(enabled=False)
    page = Page({"#a": [flaky, disabled]})
    with pytest.raises(WindshieldError) as info:
        pg.type_first_visible(page, ["#a", "#none"], SECRET, "password")
    assert "none visible+enabled" in str(info.value)
    assert "#none (0 matches)" in str(info.value)
    assert SECRET not in str(info.value)
    assert flaky.names().count("click") == 0


def test_type_with_an_unreadable_enabled_state_is_skipped():
    el = El(fail={"is_enabled"})
    with pytest.raises(WindshieldError):
        pg.type_first_visible(Page({"#a": [el]}), ["#a"], "v", "f")
    assert "click" not in el.names()


def test_type_error_is_reported_without_the_value():
    el = El(fail={"type"})
    with pytest.raises(WindshieldError) as info:
        pg.type_first_visible(Page({"#a": [el]}), ["#a"], SECRET, "password")
    assert "#a[0] type-error(RuntimeError)" in str(info.value)
    assert SECRET not in str(info.value)


# --- read back ----------------------------------------------------------------------------


def test_read_input_value_returns_the_first_usable_selectors_value():
    page = Page({"#a": [El(visible=False, value="no")], "#b": [El(value="yes")]})
    assert pg.read_first_visible_input_value(page, ["#none", "#a", "#b"]) == ("#b", "yes")


def test_read_input_value_falls_back_to_script_then_empty():
    only_script = El(value="from-script", fail={"input_value"})
    assert pg.read_first_visible_input_value(Page({"#a": [only_script]}), ["#a"]) == (
        "#a",
        "from-script",
    )
    nothing = El(fail={"input_value", "evaluate_value"})
    assert pg.read_first_visible_input_value(Page({"#a": [nothing]}), ["#a"]) == ("#a", "")


def test_read_input_value_skips_elements_whose_state_cannot_be_read():
    page = Page({"#a": [El(fail={"is_visible"}), El(enabled=False)]})
    assert pg.read_first_visible_input_value(page, ["#a"]) == ("", "")


def test_read_input_value_with_nothing_is_empty():
    assert pg.read_first_visible_input_value(Page(), ["#a"]) == ("", "")


# --- script set ---------------------------------------------------------------------------


def test_script_set_writes_through_javascript_events_and_names_the_selector():
    el = El()
    assert pg.script_set_first_visible_value(Page({"#a": [el]}), ["#a"], "v", "f") == "#a"
    assert el.value == "v"


def test_script_set_reports_failures_without_the_value():
    broken = El(fail={"script_set"})
    hidden = El(visible=False)
    flaky = El(fail={"is_enabled"})
    page = Page({"#a": [broken, hidden, flaky]})
    with pytest.raises(WindshieldError) as info:
        pg.script_set_first_visible_value(page, ["#zero", "#a"], SECRET, "password")
    message = str(info.value)
    assert "#a[0] script-set-error(RuntimeError)" in message
    assert "#zero (0 matches)" in message
    assert "#a (3 matches, none visible+enabled)" in message
    assert SECRET not in message


# --- robust set ---------------------------------------------------------------------------


def test_robust_set_uses_fill_first_and_reports_the_method_and_length():
    el = El()
    assert pg.set_first_visible_value_robust(Page({"#a": [el]}), ["#a"], "abc", "f") == (
        "#a",
        "fill",
        3,
    )


def test_robust_set_falls_back_to_typing_when_fill_does_not_stick():
    el = El(ignore={"fill"})
    selector, method, length = pg.set_first_visible_value_robust(
        Page({"#a": [el]}), ["#a"], "abc", "f"
    )
    assert (selector, method, length) == ("#a", "type", 3)


def test_robust_set_falls_back_to_script_when_neither_fill_nor_type_stick():
    el = El(ignore={"fill", "type"})
    assert pg.set_first_visible_value_robust(Page({"#a": [el]}), ["#a"], "abc", "f")[1] == "script"


def test_type_then_fill_mode_tries_typing_first():
    el = El()
    _, method, _ = pg.set_first_visible_value_robust(
        Page({"#a": [el]}), ["#a"], "abc", "f", input_mode="type_then_fill_verify"
    )
    assert method == "type"
    assert el.names().count("fill") == 1  # the type strategy clears the field with fill("")


@pytest.mark.parametrize("mode", ["fill", "type"])
def test_single_strategy_modes_do_not_fall_back(mode):
    el = El(ignore={"fill", "type"})
    with pytest.raises(WindshieldError, match="could not reliably set value") as info:
        pg.set_first_visible_value_robust(
            Page({"#a": [el]}), ["#a"], SECRET, "password", input_mode=mode
        )
    assert f"{mode}:verify_failed" in str(info.value)
    assert "script" not in str(info.value)


@pytest.mark.parametrize("mode", ["", None, "bogus", "  FILL  "])
def test_unknown_modes_default_to_fill_first_and_known_modes_are_case_insensitive(mode):
    el = El()
    _, method, _ = pg.set_first_visible_value_robust(
        Page({"#a": [el]}), ["#a"], "abc", "f", input_mode=mode
    )
    assert method == "fill"


def test_robust_set_failure_lists_every_attempt_by_length_never_by_value():
    el = El(ignore={"fill", "type", "script"})
    with pytest.raises(WindshieldError) as info:
        pg.set_first_visible_value_robust(Page({"#a": [el]}), ["#a"], SECRET, "password")
    message = str(info.value)
    assert "fill:verify_failed(expected_len=14 got_len=0)" in message
    assert "type:verify_failed" in message
    assert "script:verify_failed" in message
    assert SECRET not in message


def test_robust_set_reports_a_strategy_that_could_not_even_start():
    page = Page({"#a": [El(visible=False)]})
    with pytest.raises(WindshieldError) as info:
        pg.set_first_visible_value_robust(page, ["#a"], SECRET, "password", input_mode="fill")
    assert "fill:set_failed(" in str(info.value)
    assert SECRET not in str(info.value)


def test_a_wrong_value_that_reads_back_is_not_accepted():
    el = El(ignore={"fill"}, value="")
    el.value = "pre-existing"
    with pytest.raises(WindshieldError):
        pg.set_first_visible_value_robust(Page({"#a": [el]}), ["#a"], "abc", "f", input_mode="fill")


# --- click --------------------------------------------------------------------------------


def test_click_requires_selectors():
    with pytest.raises(WindshieldError, match="no selectors configured"):
        pg.click_first_visible(Page(), [], "go")


def test_click_takes_the_first_visible_enabled_match():
    skip1, skip2, good = El(visible=False), El(enabled=False), El()
    page = Page({"#a": [skip1, skip2, good]})
    assert pg.click_first_visible(page, ["#none", "#a"], "go") == "#a"
    assert good.names()[-1] == "click"
    assert "click" not in skip1.names() and "click" not in skip2.names()


def test_click_reports_a_failing_click_and_continues_to_the_next_element():
    bad, good = El(fail={"click"}), El()
    assert pg.click_first_visible(Page({"#a": [bad, good]}), ["#a"], "go") == "#a"
    with pytest.raises(WindshieldError, match=r"#a\[0\] click-error\(RuntimeError\)"):
        pg.click_first_visible(Page({"#a": [El(fail={"click"})]}), ["#a"], "go")


def test_a_hidden_element_is_not_force_clicked_unless_allowed():
    hidden = El(visible=False)
    page = Page({"#a": [hidden]})
    with pytest.raises(WindshieldError, match="none visible"):
        pg.click_first_visible(page, ["#a"], "go")
    assert "click_force" not in hidden.names()

    assert pg.click_first_visible(page, ["#a"], "go", allow_force_click=True) == "#a"
    assert "click_force" in hidden.names()


def test_a_disabled_element_is_never_clicked_even_when_forcing():
    disabled = El(enabled=False, visible=False)
    with pytest.raises(WindshieldError):
        pg.click_first_visible(Page({"#a": [disabled]}), ["#a"], "go", allow_force_click=True)
    assert not {"click", "click_force", "js_click"} & set(disabled.names())


def test_force_click_falls_back_to_a_script_click_then_reports_both_errors():
    el = El(visible=False, fail={"click_force"})
    assert pg.click_first_visible(Page({"#a": [el]}), ["#a"], "go", allow_force_click=True) == "#a"
    assert "js_click" in el.names()

    both = El(visible=False, fail={"click_force", "js_click"})
    with pytest.raises(WindshieldError) as info:
        pg.click_first_visible(Page({"#a": [both]}), ["#a"], "go", allow_force_click=True)
    assert "force click failed: RuntimeError, RuntimeError" in str(info.value)


def test_unreadable_state_counts_as_not_clickable():
    el = El(fail={"is_visible", "is_enabled"})
    with pytest.raises(WindshieldError):
        pg.click_first_visible(Page({"#a": [el]}), ["#a"], "go", allow_force_click=True)
    assert not {"click", "click_force"} & set(el.names())


def test_optional_clicks_return_what_was_clicked_and_stop_at_one_per_selector():
    a1, a2, b = El(), El(), El(visible=False)
    page = Page({"#a": [a1, a2], "#b": [b], "#c": []})
    page.count_raises.add("#err")
    clicked = pg.click_optional_selectors(page, ["#err", "#a", "#b", "#c"])
    assert clicked == ["#a", "#b"]
    assert "click" in a1.names() and "click" not in a2.names()
    assert "click_force" in b.names()


def test_optional_clicks_respect_no_force_and_skip_disabled():
    hidden, disabled = El(visible=False), El(enabled=False)
    page = Page({"#a": [hidden], "#b": [disabled]})
    assert pg.click_optional_selectors(page, ["#a", "#b"], allow_force_click=False) == []
    assert "click_force" not in hidden.names()
    assert not {"click", "click_force"} & set(disabled.names())


def test_optional_click_falls_back_to_a_script_click_or_gives_up_quietly():
    el = El(fail={"click"})
    assert pg.click_optional_selectors(Page({"#a": [el]}), ["#a"]) == ["#a"]
    assert "js_click" in el.names()
    dead = El(fail={"click", "js_click"})
    assert pg.click_optional_selectors(Page({"#a": [dead]}), ["#a"]) == []


def test_optional_click_treats_unreadable_visibility_as_hidden():
    el = El(fail={"is_visible"})
    assert pg.click_optional_selectors(Page({"#a": [el]}), ["#a"]) == ["#a"]
    assert "click_force" in el.names()


def test_optional_click_treats_unreadable_enabled_state_as_disabled():
    el = El(fail={"is_enabled"})
    assert pg.click_optional_selectors(Page({"#a": [el]}), ["#a"]) == []


def test_click_selector_any_ignores_blank_and_searches_frames():
    in_frame = El()
    frame = Frame("https://example.test/f", {"#x": [in_frame]})
    page = Page(frames=[frame])
    assert pg.click_selector_any(page, "") is False
    assert pg.click_selector_any(page, "   ") is False
    assert pg.click_selector_any(page, "#x") is True
    assert pg.click_selector_any(page, "#absent") is False


def test_click_selector_any_escalates_normal_force_then_script():
    plain = El(fail={"click"})
    assert pg.click_selector_any(Page({"#a": [plain]}), "#a") is True
    assert plain.names() == ["click", "click_force"]

    script = El(fail={"click", "click_force"})
    assert pg.click_selector_any(Page({"#a": [script]}), "#a") is True
    assert script.names()[-1] == "js_click"

    dead = El(fail={"click", "click_force", "js_click"})
    second = El()
    assert pg.click_selector_any(Page({"#a": [dead, second]}), "#a") is True
    assert "click" in second.names()
    assert pg.click_selector_any(Page({"#a": [dead]}), "#a") is False


def test_click_selector_any_skips_a_selector_that_errors():
    page = Page({"#a": [El()]})
    page.count_raises.add("#a")
    assert pg.click_selector_any(page, "#a") is False


class Clock:
    def __init__(self, step=0.4):
        self.now, self.step = 0.0, step

    def __call__(self):
        value = self.now
        self.now += self.step
        return value


@pytest.fixture
def clock(monkeypatch):
    from types import SimpleNamespace

    def install(step=0.4):
        monkeypatch.setattr(pg, "time", SimpleNamespace(monotonic=Clock(step)))

    install()
    return install


def test_best_effort_click_returns_the_selector_that_worked(clock):
    page = Page({"#b": [El()]})
    assert pg.click_first_selector_best_effort(page, ["", "  ", "#a", "#b"], 1000) == "#b"
    assert page.slept  # waited and retried "#a" until its window closed


def test_best_effort_click_returns_empty_when_nothing_clicks(clock):
    page = Page()
    assert pg.click_first_selector_best_effort(page, ["#a"], 1000) == ""
    assert page.slept == [200, 200]  # 0.4s clock steps in a one-second window


def test_best_effort_click_window_is_at_least_a_second(clock):
    page = Page()
    pg.click_first_selector_best_effort(page, ["#a"], 10)
    assert len(page.slept) == 2


def test_best_effort_click_recovers_a_closed_page_but_raises_anything_else(clock):
    closed = RuntimeError("Page has been closed")
    reasons = []

    class Closing(Page):
        def wait_for_timeout(self, ms):
            raise closed

    fresh = Page({"#a": [El()]})

    def recover(reason):
        reasons.append(reason)
        return fresh

    assert (
        pg.click_first_selector_best_effort(Closing(), ["#a"], 5000, recover_page=recover) == "#a"
    )
    assert reasons == ["click_first_selector_best_effort:#a"]

    with pytest.raises(RuntimeError):
        pg.click_first_selector_best_effort(Closing(), ["#a"], 5000)

    class Broken(Page):
        def wait_for_timeout(self, ms):
            raise OSError("pipe")

    with pytest.raises(OSError):
        pg.click_first_selector_best_effort(Broken(), ["#a"], 5000, recover_page=recover)


# --- click by label -----------------------------------------------------------------------


def controls(*pairs):
    return {
        "button, a, [role='button'], input[type='submit'], input[type='button']": [
            El(text=text, **kw) for text, kw in pairs
        ]
    }


def test_labels_are_required():
    with pytest.raises(WindshieldError, match="no labels configured"):
        pg.click_control_with_labels(Page(), ["", "  "], "go")


def test_label_click_matches_substrings_case_insensitively_and_names_the_control():
    page = Page(controls(("Cancel", {}), ("  Continue to Sign In  ", {})))
    assert pg.click_control_with_labels(page, ["sign in"], "go") == "main:Continue to Sign In"


def test_short_labels_match_whole_words_only():
    page = Page(controls(("Gone", {}), ("Go back", {}), ("Go", {})))
    result = pg.click_control_with_labels(page, ["go"], "go")
    assert result == "main:Go back"  # 'Gone' is not the word 'go'; the next control is


def test_label_click_skips_controls_without_text_or_unreadable_text():
    unreadable = El(fail={"text"}, text="Submit")
    blank = El(text="   ")
    good = El(text="Submit")
    key = "button, a, [role='button'], input[type='submit'], input[type='button']"
    assert pg.click_control_with_labels(Page({key: [unreadable, blank, good]}), ["submit"], "go")


def test_label_click_escalates_then_reports_the_script_error():
    forced = El(text="Go on", fail={"click"})
    key = "button, a, [role='button'], input[type='submit'], input[type='button']"
    assert pg.click_control_with_labels(Page({key: [forced]}), ["go on"], "go") == "main:Go on"
    assert forced.names()[-1] == "click_force"

    scripted = El(text="Go on", fail={"click", "click_force"})
    pg.click_control_with_labels(Page({key: [scripted]}), ["go on"], "go")
    assert scripted.names()[-1] == "js_click"

    dead = El(text="Go on", fail={"click", "click_force", "js_click"})
    with pytest.raises(WindshieldError) as info:
        pg.click_control_with_labels(Page({key: [dead]}), ["go on"], "go")
    assert "main:Go on:click-error(RuntimeError)" in str(info.value)


def test_label_click_with_no_match_says_so():
    with pytest.raises(WindshieldError, match="no clickable control matched labels"):
        pg.click_control_with_labels(Page(controls(("Other", {}))), ["nothing"], "go")


def test_label_click_only_scans_the_configured_number_of_controls():
    pairs = [(f"Item {i}", {}) for i in range(5)] + [("Target", {})]
    with pytest.raises(WindshieldError):
        pg.click_control_with_labels(Page(controls(*pairs)), ["target"], "go", 3)
    assert pg.click_control_with_labels(Page(controls(*pairs)), ["target"], "go", 6)


def test_label_click_reports_a_context_whose_controls_cannot_be_counted():
    class Bad(Frame):
        def locator(self, selector):
            return Locator([], count_raises=True)

    page = Page(frames=[Bad("https://example.test/f")])
    with pytest.raises(WindshieldError) as info:
        pg.click_control_with_labels(page, ["x"], "go")
    assert "control-count-error(RuntimeError)" in str(info.value)


def test_label_click_searches_same_origin_frames():
    key = "button, a, [role='button'], input[type='submit'], input[type='button']"
    frame = Frame("https://example.test/f", {key: [El(text="Accept all")]})
    assert pg.click_control_with_labels(Page(frames=[frame]), ["accept"], "go").endswith(
        "Accept all"
    )


# --- submit and enter ---------------------------------------------------------------------


def test_submit_requires_selectors():
    with pytest.raises(WindshieldError, match="no form selectors configured"):
        pg.submit_first_matching_form(Page(), [], "login")


def test_submit_submits_the_first_matching_form():
    el = El()
    assert pg.submit_first_matching_form(Page({"form": [el]}), ["#none", "form"], "login") == "form"
    assert "submit" in el.names()


def test_submit_can_require_visibility():
    hidden, flaky = El(visible=False), El(fail={"is_visible"})
    page = Page({"form": [hidden, flaky]})
    with pytest.raises(WindshieldError, match="submit failed"):
        pg.submit_first_matching_form(page, ["form"], "login", require_visible=True)
    assert "submit" not in hidden.names() + flaky.names()

    assert pg.submit_first_matching_form(page, ["form"], "login") == "form"


def test_submit_errors_are_collected_per_element():
    bad = El(fail={"submit"})
    with pytest.raises(WindshieldError) as info:
        pg.submit_first_matching_form(Page({"form": [bad], "#z": []}), ["form", "#z"], "login")
    message = str(info.value)
    assert "form[0] submit-error(RuntimeError)" in message
    assert "form (1 matches, submit failed)" in message
    assert "#z (0 matches)" in message


def test_press_enter_requires_selectors():
    with pytest.raises(WindshieldError, match="no selectors configured"):
        pg.press_enter_first_visible(Page(), [], "go")


def test_press_enter_targets_the_first_usable_element():
    skip, good = El(visible=False), El()
    page = Page({"#a": [skip, good]})
    assert pg.press_enter_first_visible(page, ["#none", "#a"], "go") == "press_enter:#a"
    assert ("press", ("Enter",), {}) in good.calls
    assert "press" not in skip.names()


def test_press_enter_failures_are_reported():
    bad = El(fail={"press"})
    flaky = El(fail={"is_visible"})
    disabled = El(enabled=False)
    page = Page({"#a": [bad, flaky, disabled], "#z": []})
    with pytest.raises(WindshieldError) as info:
        pg.press_enter_first_visible(page, ["#a", "#z"], "go")
    message = str(info.value)
    assert "#a[0] press-error(RuntimeError)" in message
    assert "#a (3 matches, none visible+enabled)" in message
    assert "#z (0 matches)" in message


def test_press_enter_unreadable_enabled_state_is_skipped():
    el = El(fail={"is_enabled"})
    with pytest.raises(WindshieldError):
        pg.press_enter_first_visible(Page({"#a": [el]}), ["#a"], "go")
    assert "press" not in el.names()


def test_contexts_survive_a_url_that_urlparse_rejects():
    page = Page(url="http://[::1", frames=[Frame("https://example.test/f")])
    names = [n for n, _ in pg.iter_locator_contexts(page)]
    assert names[0] == "main"
    assert len(names) == 2  # with no usable origin, frames are kept rather than dropped


def test_text_matching_with_only_blank_snippets_never_reads_the_page():
    class Explodes:
        def locator(self, sel):
            raise AssertionError("must not read the page")

        def content(self):
            raise AssertionError("must not read the page")

    assert pg.page_contains_any_text(Explodes(), ["", "   "]) is False
    assert pg.matching_text_snippets(Explodes(), []) == []


def test_first_visible_selector_match_skips_selectors_with_no_matches():
    page = Page({"#b": [El()]})
    assert pg.first_visible_selector_match(page, ["#absent", "#b"]) == "main:#b"


def test_frames_that_are_not_http_are_kept_even_with_a_different_authority():
    # Extension and data frames carry no web origin to compare, so they are not filtered out.
    ext = Frame("chrome-extension://abcdef/widget.html")
    page = Page(url="https://example.test/", frames=[ext])
    contexts = pg.iter_locator_contexts(page)
    assert [c for _, c in contexts] == [page, ext]


@pytest.mark.parametrize(
    "mode", ["  TYPE_THEN_FILL_VERIFY  ", "Type_Then_Fill_Verify", " type_then_fill_verify"]
)
def test_the_input_mode_is_trimmed_and_case_insensitive(mode):
    _, method, _ = pg.set_first_visible_value_robust(
        Page({"#a": [El()]}), ["#a"], "abc", "f", input_mode=mode
    )
    assert method == "type"  # not the default fill-first order


def test_click_selector_any_never_clicks_for_a_blank_selector():
    target = El()
    page = Page({"": [target], "  ": [target]})
    assert pg.click_selector_any(page, "") is False
    assert pg.click_selector_any(page, "  ") is False
    assert pg.click_selector_any(page, None) is False
    assert target.calls == []
