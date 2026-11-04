"""Manual-step guidance text and the continue overlay/terminal wait, with fake pages and clock."""

from __future__ import annotations

import io

import pytest

from windshield import overlay
from windshield.http import sanitize_manual_guidance_text


class Item:
    def __init__(
        self,
        text="",
        *,
        visible=True,
        attrs=None,
        label=None,
        label_error=False,
        visible_error=False,
        text_error=False,
    ):
        self.text = text
        self.visible = visible
        self.attrs = attrs or {}
        self.label = label
        self.label_error = label_error
        self.visible_error = visible_error
        self.text_error = text_error

    def is_visible(self):
        if self.visible_error:
            raise RuntimeError("detached")
        return self.visible

    def get_attribute(self, name):
        value = self.attrs.get(name)
        if isinstance(value, Exception):
            raise value
        return value

    def inner_text(self):
        if self.text_error:
            raise RuntimeError("no text")
        return self.text

    def text_content(self):
        return self.text

    def evaluate(self, script):
        if self.label_error:
            raise RuntimeError("detached")
        return self.label


class Locator:
    def __init__(self, items, count_error=False):
        self.items = items
        self.count_error = count_error

    def count(self):
        if self.count_error:
            raise RuntimeError("gone")
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class Frame:
    def __init__(self, selectors=None, broken=()):
        self.selectors = selectors or {}
        self.broken = set(broken)

    def locator(self, selector):
        if selector in self.broken:
            return Locator([], count_error=True)
        return Locator(self.selectors.get(selector, []))


class Page(Frame):
    def __init__(self, selectors=None, title="", frames=None, title_error=False, broken=()):
        super().__init__(selectors, broken)
        self._title = title
        self.frames = frames if frames is not None else [self]
        self.title_error = title_error

    def title(self):
        if self.title_error:
            raise RuntimeError("closed")
        return self._title


BUTTON_SELECTORS = (
    "button",
    "a",
    "input[type='submit']",
    "input[type='button']",
    "[role='button']",
)


def page_with(*, headings=(), buttons=(), checkboxes=(), inputs=(), title=""):
    selectors = {
        "h1": [Item(h) for h in headings],
        "button": list(buttons),
        "input[type='checkbox']": list(checkboxes),
        "input": list(inputs),
    }
    return Page(selectors, title=title)


def describe(page):
    return overlay.describe_manual_page_guidance(page)


class TestGuidance:
    def test_no_page_means_no_guidance(self):
        assert describe(None) == ""
        assert describe(Page()) == ""

    def test_button_only(self):
        page = page_with(headings=["Welcome"], buttons=[Item("Go on")])
        assert describe(page) == (
            "Current page: 'Welcome'. Likely next click: 'Go on'. Visible actions: 'Go on'."
        )

    def test_checkbox_then_button(self):
        page = page_with(
            buttons=[Item("Continue")],
            checkboxes=[Item(label="I agree to the terms")],
        )
        assert "check 'I agree to the terms' then click 'Continue'" in describe(page)

    def test_code_input_then_button(self):
        page = page_with(
            buttons=[Item("Verify")],
            inputs=[Item(attrs={"type": "text", "aria-label": "Verification code"})],
        )
        text = describe(page)
        assert "enter the verification code in 'Verification code' then click 'Verify'" in text

    def test_code_input_without_a_button(self):
        page = page_with(inputs=[Item(attrs={"type": "text", "name": "otp"})])
        assert describe(page) == "Likely next step: enter the verification code in 'otp'."

    def test_login_inputs_are_listed_two_at_most(self):
        page = page_with(
            buttons=[Item("Sign in")],
            inputs=[
                Item(attrs={"type": "text", "name": "username"}),
                Item(attrs={"type": "password", "name": "password"}),
                Item(attrs={"type": "text", "name": "email"}),
            ],
        )
        assert "complete 'username', 'password' then click 'Sign in'" in describe(page)

    def test_primary_button_follows_the_pattern_priority_not_page_order(self):
        page = page_with(buttons=[Item("Download"), Item("Cancel"), Item("I agree")])
        assert "Likely next click: 'I agree'" in describe(page)
        page = page_with(buttons=[Item("Cancel"), Item("Maybe later")])
        assert "Likely next click: 'Cancel'" in describe(page)

    def test_blank_labels_are_not_listed(self):
        page = page_with(buttons=[Item(""), Item("   "), Item("Real"), Item("Other")])
        assert "Visible actions: 'Real', 'Other'." in describe(page)

    def test_accept_beats_i_agree_and_every_code_word_is_recognised(self):
        page = page_with(buttons=[Item("I agree"), Item("Accept all")])
        assert "Likely next click: 'Accept all'" in describe(page)
        for word in ("verification", "security", "passcode", "mfa", "2fa", "otp", "code"):
            page = page_with(
                buttons=[Item("Go")],
                inputs=[Item(attrs={"type": "text", "name": f"your {word} here"})],
            )
            assert "enter the verification code" in describe(page), word

    def test_visible_actions_are_capped_at_three(self):
        page = page_with(buttons=[Item(f"B{i}") for i in range(5)])
        assert "Visible actions: 'B0', 'B1', 'B2'." in describe(page)

    def test_title_is_the_fallback_for_the_page_label_and_headings_win(self):
        assert describe(page_with(title="Tab title", buttons=[Item("Next")])).startswith(
            "Current page: 'Tab title'."
        )
        assert describe(page_with(headings=["Heading"], title="Tab title")).startswith(
            "Current page: 'Heading'."
        )
        broken = page_with(buttons=[Item("Next")])
        broken.title_error = True
        assert describe(broken).startswith("Likely next click")

    def test_invisible_duplicate_and_broken_elements_are_skipped(self):
        page = page_with(
            buttons=[
                Item("Hidden", visible=False),
                Item("Dup"),
                Item("dup"),
                Item("Gone", visible_error=True),
                Item("", attrs={"aria-label": "From label"}),
            ]
        )
        assert "Visible actions: 'Dup', 'From label'." in describe(page)

    def test_button_label_falls_back_through_the_attributes(self):
        for attr in ("aria-label", "value", "title", "name", "id"):
            page = page_with(buttons=[Item("", attrs={attr: f"via {attr}"})])
            assert f"'via {attr}'" in describe(page), attr

    def test_text_content_is_used_when_inner_text_fails(self):
        page = page_with(buttons=[Item("From text content", text_error=True)])
        assert "'From text content'" in describe(page)

    def test_non_text_inputs_are_not_candidates(self):
        inputs = [
            Item(attrs={"type": kind, "name": "code"})
            for kind in ("hidden", "submit", "button", "checkbox", "radio", "file")
        ]
        assert describe(page_with(inputs=inputs)) == ""

    def test_input_label_precedence(self):
        def label(**attrs):
            return describe(page_with(inputs=[Item(attrs={"type": "text", **attrs})]))

        every = {"aria-label": "code-a", "placeholder": "code-p", "name": "code-n", "id": "code-i"}
        assert "'code-a'" in label(**every)
        every.pop("aria-label")
        assert "'code-p'" in label(**every)
        every.pop("placeholder")
        assert "'code-n'" in label(**every)
        every.pop("name")
        assert "'code-i'" in label(**every)
        # With nothing else to go on the input type itself is the label.
        page = page_with(buttons=[Item("Go")], inputs=[Item(attrs={"type": "password"})])
        assert "'password'" in describe(page)

    def test_heading_limit_is_four(self):
        headings = [Item(f"H{i}", visible=(i >= 4)) for i in range(8)]
        assert describe(Page({"h1": headings})) == ""

    def test_button_limit_is_twelve(self):
        buttons = [Item(f"B{i}", visible=(i >= 12)) for i in range(20)]
        assert describe(Page({"button": buttons})) == ""

    def test_checkbox_limit_is_six(self):
        boxes = [Item(label=f"C{i}", visible=(i >= 6)) for i in range(10)]
        page = Page({"input[type='checkbox']": boxes, "button": [Item("Go")]})
        assert "check" not in describe(page)

    def test_input_limit_is_ten(self):
        inputs = [
            Item(attrs={"type": "text", "name": f"code {i}"}, visible=(i >= 10)) for i in range(15)
        ]
        assert describe(Page({"input": inputs})) == ""

    def test_broken_locators_are_skipped(self):
        page = page_with(headings=["Hi"], buttons=[Item("Next")])
        page.broken = {"button", "input[type='checkbox']", "input"}
        assert describe(page) == "Current page: 'Hi'."

    def test_every_frame_is_inspected(self):
        main = page_with(headings=["Main"])
        inner = Frame({"button": [Item("Inside frame")]})
        main.frames = [main, inner]
        assert "Likely next click: 'Inside frame'" in describe(main)

    def test_checkbox_label_falls_back_when_evaluation_fails(self):
        page = page_with(
            buttons=[Item("Go")],
            checkboxes=[Item(label_error=True, attrs={"aria-label": "Remember me", "name": "r"})],
        )
        assert "check 'Remember me'" in describe(page)
        page = page_with(
            buttons=[Item("Go")],
            checkboxes=[Item(label_error=True, attrs={"name": "remember", "id": "x"})],
        )
        assert "check 'remember'" in describe(page)
        page = page_with(
            buttons=[Item("Go")], checkboxes=[Item(label_error=True, attrs={"id": "only-id"})]
        )
        assert "check 'only-id'" in describe(page)

    def test_attribute_errors_are_swallowed(self):
        page = page_with(buttons=[Item("", attrs={"aria-label": RuntimeError("x"), "title": "ok"})])
        assert "'ok'" in describe(page)

    def test_long_digit_runs_in_page_text_are_redacted(self):
        page = page_with(
            headings=["Code 123456 sent"],
            buttons=[Item("Confirm 9876")],
            inputs=[Item(attrs={"type": "text", "placeholder": "Enter 654321"})],
        )
        text = describe(page)
        assert "123456" not in text and "9876" not in text and "654321" not in text
        assert "[redacted-digits]" in text

    def test_terminal_control_sequences_from_the_page_never_reach_the_guidance(self):
        hostile = "Click\x1b]52;c;ZXZpbA==\x07 here\x1b[2J"
        page = page_with(headings=[hostile], buttons=[Item(hostile)])
        text = describe(page)
        assert "\x1b" not in text and "\x07" not in text
        assert "Click" in text and "here" in text

    def test_text_is_truncated(self):
        long = "x" * 500
        page = page_with(headings=[long], buttons=[Item(long)])
        text = describe(page)
        assert "x" * 117 + "..." in text
        assert "x" * 97 + "..." in text
        assert "x" * 118 not in text


class TestSanitize:
    def test_collapses_whitespace_and_truncates(self):
        assert sanitize_manual_guidance_text("  a \n\t b  ") == "a b"
        assert sanitize_manual_guidance_text("x" * 30, max_len=10) == "x" * 7 + "..."
        assert sanitize_manual_guidance_text(None) == ""
        assert sanitize_manual_guidance_text("   ") == ""

    def test_text_that_exactly_fits_is_not_truncated(self):
        assert sanitize_manual_guidance_text("x" * 10, max_len=10) == "x" * 10
        assert sanitize_manual_guidance_text("x" * 11, max_len=10) == "x" * 7 + "..."

    def test_removing_a_control_character_never_leaves_a_double_space(self):
        assert sanitize_manual_guidance_text("a \x07 b") == "a b"
        assert sanitize_manual_guidance_text("\x1b\x07") == ""

    def test_digit_redaction_boundaries(self):
        assert sanitize_manual_guidance_text("123") == "123"
        assert sanitize_manual_guidance_text("1234") == "[redacted-digits]"
        assert sanitize_manual_guidance_text("ref ab1234") == "ref ab1234"

    @pytest.mark.parametrize("char", ["\x00", "\x07", "\x1b", "\x7f", "\x9b", "​"])
    def test_control_characters_are_removed(self, char):
        assert sanitize_manual_guidance_text(f"a{char}b") == "ab"


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class WaitPage:
    def __init__(
        self,
        *,
        flag_after=None,
        clock=None,
        inject_result=True,
        poll_error_after=None,
        inject_error=False,
        front_error=False,
    ):
        self.clock = clock
        self.flag_after = flag_after
        self.inject_result = inject_result
        self.poll_error_after = poll_error_after
        self.inject_error = inject_error
        self.front_error = front_error
        self.calls = []
        self.polls = 0
        self.brought = False

    def bring_to_front(self):
        if self.front_error:
            raise RuntimeError("no front")
        self.brought = True

    def title(self):
        return ""

    frames = []

    def evaluate(self, script, arg=None):
        self.calls.append((script, arg))
        if isinstance(arg, dict) and "titleText" in arg:
            if self.inject_error:
                raise RuntimeError("injection blocked")
            return self.inject_result
        if isinstance(arg, str):
            self.polls += 1
            if self.poll_error_after is not None and self.polls > self.poll_error_after:
                raise RuntimeError("navigated")
            return self.flag_after is not None and self.polls > self.flag_after
        return None

    def injections(self):
        return [a for _, a in self.calls if isinstance(a, dict) and "titleText" in a]

    def removals(self):
        return [a for s, a in self.calls if isinstance(a, dict) and set(a) == {"overlayId"}]

    def forced(self):
        return [
            a
            for s, a in self.calls
            if isinstance(a, dict) and "continueFlag" in a and "titleText" not in a
        ]


@pytest.fixture
def clock(monkeypatch):
    fake = Clock()
    monkeypatch.setattr(overlay.time, "monotonic", fake.monotonic)
    monkeypatch.setattr(overlay.time, "sleep", fake.sleep)
    monkeypatch.setattr(overlay.sys, "stdin", io.StringIO(""))
    return fake


def run(page, **kwargs):
    defaults = dict(timeout_seconds=30, title="T", body="B", button_text="Go")
    defaults.update(kwargs)
    return overlay.wait_for_manual_continue(page, **defaults)


class TestWaitForContinue:
    def test_clicking_continue_returns_true_and_removes_the_overlay(self, clock):
        page = WaitPage(flag_after=2)
        assert run(page) is True
        assert page.brought
        assert page.removals() == [{"overlayId": "ws-manual-continue-overlay"}]

    def test_injection_arguments_and_defaults(self, clock):
        page = WaitPage(flag_after=0)
        run(page, title="  ", body="", button_text=None, overlay_id=" ", continue_flag="")
        (args,) = page.injections()
        assert args == {
            "overlayId": "ws-manual-continue-overlay",
            "continueFlag": "__wsManualContinue",
            "titleText": "Manual Step Required",
            "bodyText": "Complete the manual step, then continue.",
            "buttonText": "Continue",
        }

    def test_custom_values_are_trimmed_and_used(self, clock):
        page = WaitPage(flag_after=0)
        run(
            page,
            title=" Title ",
            body=" Body ",
            button_text=" Go ",
            overlay_id=" id ",
            continue_flag=" f ",
        )
        (args,) = page.injections()
        assert (args["titleText"], args["bodyText"], args["buttonText"]) == ("Title", "Body", "Go")
        assert (args["overlayId"], args["continueFlag"]) == ("id", "f")
        assert page.removals() == [{"overlayId": "id"}]

    def test_page_guidance_is_appended_to_the_body(self, clock, monkeypatch):
        monkeypatch.setattr(
            overlay, "describe_manual_page_guidance", lambda page: "Likely next click: 'X'."
        )
        page = WaitPage(flag_after=0)
        run(page, body="Do it")
        assert page.injections()[0]["bodyText"] == "Do it\n\nLikely next click: 'X'."

    def test_timeout_is_at_least_ten_seconds_and_returns_false(self, clock):
        page = WaitPage()
        assert run(page, timeout_seconds=1) is False
        assert 10.0 <= clock.now - 1000.0 <= 10.6
        clock.now = 1000.0
        assert run(WaitPage(), timeout_seconds=25) is False
        assert 25.0 <= clock.now - 1000.0 <= 25.6

    def test_polls_every_half_second_at_most(self, clock):
        run(WaitPage(), timeout_seconds=10)
        assert max(clock.sleeps) <= 0.5 and len(clock.sleeps) >= 20

    def test_overlay_disabled_does_not_inject_but_still_waits(self, clock):
        page = WaitPage(flag_after=0)
        assert run(page, overlay_enabled=False, timeout_seconds=10) is False
        assert page.injections() == [] and not page.brought
        assert page.removals()  # cleanup is unconditional and harmless

    def test_failed_injection_degrades_to_waiting_out_the_timeout(self, clock):
        page = WaitPage(inject_error=True)
        assert run(page, timeout_seconds=10) is False

    def test_injection_that_reports_false_means_no_polling(self, clock):
        page = WaitPage(inject_result=False, flag_after=0)
        assert run(page, timeout_seconds=10) is False
        assert page.polls == 0

    def test_bring_to_front_failure_is_ignored(self, clock):
        page = WaitPage(flag_after=0, front_error=True)
        assert run(page) is True

    def test_poll_errors_stop_polling_but_not_the_wait(self, clock):
        page = WaitPage(poll_error_after=1, flag_after=99)
        assert run(page, timeout_seconds=10) is False
        assert page.polls == 2

    def test_auto_continue_clicks_for_the_user_after_the_delay(self, clock):
        page = WaitPage()
        assert run(page, timeout_seconds=60, auto_continue_seconds=3) is True
        assert 3.0 <= clock.now - 1000.0 <= 3.6
        assert len(page.forced()) == 1

    def test_an_auto_continue_longer_than_the_timeout_is_just_a_timeout(self, clock):
        page = WaitPage()
        assert run(page, timeout_seconds=10, auto_continue_seconds=500) is False
        assert clock.now - 1000.0 <= 10.6
        assert page.forced() == []

    def test_negative_auto_continue_is_ignored(self, clock):
        assert run(WaitPage(), timeout_seconds=10, auto_continue_seconds=-5) is False

    def test_unexpected_errors_return_false_and_still_clean_up(self, clock, monkeypatch):
        class BrokenStdin:
            def isatty(self):
                raise RuntimeError("stdin closed")

        monkeypatch.setattr(overlay.sys, "stdin", BrokenStdin())
        page = WaitPage(flag_after=99)
        assert run(page) is False
        assert page.removals()

    def test_cleanup_failures_are_swallowed(self, clock):
        class Dying(WaitPage):
            def evaluate(self, script, arg=None):
                if isinstance(arg, dict) and set(arg) == {"overlayId"}:
                    raise RuntimeError("page closed")
                return super().evaluate(script, arg)

        assert run(Dying(flag_after=0)) is True


class FakeTty(io.StringIO):
    def __init__(self, text="", tty=True):
        super().__init__(text)
        self.tty = tty

    def isatty(self):
        return self.tty


class TestTerminalPrompt:
    def setup_select(self, monkeypatch, clock, ready_after=None, error=None):
        calls = []

        def fake_select(rlist, wlist, xlist, timeout):
            calls.append(timeout)
            if error:
                raise error
            clock.now += timeout
            if ready_after is not None and len(calls) > ready_after:
                return rlist, [], []
            return [], [], []

        import select

        monkeypatch.setattr(select, "select", fake_select)
        return calls

    def test_pressing_enter_continues_and_the_prompt_names_the_options(
        self, clock, monkeypatch, capsys
    ):
        monkeypatch.setattr(overlay.sys, "stdin", FakeTty("\n"))
        self.setup_select(monkeypatch, clock, ready_after=1)
        page = WaitPage()
        assert run(page, timeout_seconds=60, auto_continue_seconds=20) is True
        assert clock.now - 1000.0 < 20  # Enter, not the auto-continue, ended the wait
        out = capsys.readouterr().out
        assert out.startswith("[manual] T: B ")
        assert (
            "Click 'Go' in browser or press Enter here (timeout 60s). Auto-continue in 20s." in out
        )

    def test_prompt_without_auto_continue_note(self, clock, monkeypatch, capsys):
        monkeypatch.setattr(overlay.sys, "stdin", FakeTty("\n"))
        self.setup_select(monkeypatch, clock, ready_after=0)
        assert run(WaitPage(), timeout_seconds=60) is True
        assert "Auto-continue" not in capsys.readouterr().out

    def test_terminal_prompt_can_be_disabled(self, clock, monkeypatch, capsys):
        monkeypatch.setattr(overlay.sys, "stdin", FakeTty("\n"))
        calls = self.setup_select(monkeypatch, clock, ready_after=0)
        assert run(WaitPage(), timeout_seconds=10, terminal_prompt_enabled=False) is False
        assert calls == [] and capsys.readouterr().out == ""

    def test_non_tty_stdin_is_never_read(self, clock, monkeypatch, capsys):
        monkeypatch.setattr(overlay.sys, "stdin", FakeTty("\n", tty=False))
        calls = self.setup_select(monkeypatch, clock, ready_after=0)
        assert run(WaitPage(), timeout_seconds=10) is False
        assert calls == [] and capsys.readouterr().out == ""

    def test_select_slices_are_at_most_half_a_second(self, clock, monkeypatch):
        monkeypatch.setattr(overlay.sys, "stdin", FakeTty(""))
        calls = self.setup_select(monkeypatch, clock)
        run(WaitPage(), timeout_seconds=10)
        assert calls and max(calls) <= 0.5

    def test_a_failing_select_falls_back_to_sleeping(self, clock, monkeypatch):
        monkeypatch.setattr(overlay.sys, "stdin", FakeTty(""))
        self.setup_select(monkeypatch, clock, error=OSError("bad fd"))
        assert run(WaitPage(), timeout_seconds=10) is False
        assert clock.sleeps

    def test_stdin_without_isatty_is_treated_as_non_interactive(self, clock, monkeypatch):
        class Bare:
            pass

        monkeypatch.setattr(overlay.sys, "stdin", Bare())
        assert run(WaitPage(), timeout_seconds=10) is False


class TestOtpWrapper:
    def test_uses_the_otp_specific_ids_and_wording(self, clock):
        page = WaitPage(flag_after=0)
        assert overlay.wait_for_manual_otp_continue(page, 30) is True
        (args,) = page.injections()
        assert args["overlayId"] == "ws-manual-otp-overlay"
        assert args["continueFlag"] == "__wsManualOtpContinue"
        assert args["titleText"] == "Manual Verification Required"
        assert "verification code" in args["bodyText"]
        assert args["buttonText"] == "Continue"
