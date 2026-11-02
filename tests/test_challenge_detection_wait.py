"""Challenge detection and the wait-for-clear loop, driven by a scripted page and clock.

``is_challenge_page`` decides whether a downloader is looking at a Cloudflare/CAPTCHA wall;
getting it wrong either hammers a wall or abandons a good page. ``wait_for_challenge_to_clear``
must give up fast on known dead ends, recover from a page that was closed under it, and never
swallow an unrelated error. No real browser, sleep or wall clock is used.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from windshield import challenge
from windshield.challenge import (
    extract_reference_code_from_page,
    extract_reference_code_from_text,
    is_challenge_page,
    wait_for_challenge_to_clear,
)

CLOSED = RuntimeError("Target page, context or browser has been closed")


class Loc:
    def __init__(self, count=0, visible=(), raises=False):
        self._count = count
        self._visible = set(visible)
        self._raises = raises

    def count(self):
        if self._raises is True:
            raise RuntimeError("locator failed")
        return self._count

    def nth(self, idx):
        outer = self

        class Item:
            def is_visible(self_inner):
                if idx in outer._visible:
                    return True
                if outer._raises == "visible":
                    raise RuntimeError("detached")
                return False

        return Item()


class Frame:
    def __init__(self, url):
        self.url = url


class Page:
    """A page whose body text, title, content, url, frames and locators are all scripted."""

    def __init__(self, url="https://example.test/", body="Welcome", title="Home", locators=None):
        self.url = url
        self._body = body
        self._title = title
        self.content_html = "<html></html>"
        self.frames = []
        self.locators = locators or {}
        self.content_raises = False
        self.frames_raises = False
        self.slept = []

    def title(self):
        return self._title

    def content(self):
        if self.content_raises:
            raise RuntimeError("no content")
        return self.content_html

    def locator(self, selector):
        if selector == "body":
            return BodyLoc(self._body)
        loc = self.locators.get(selector)
        if loc is None:
            return Loc()
        return loc

    def wait_for_timeout(self, ms):
        self.slept.append(ms)


class BodyLoc:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=0):
        return self.text


# --- is_challenge_page --------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://x.test/?__cf_chl_tk=abc",
        "https://x.test/?cf_chl_opt=1",
        "https://CLOUDFLARE.example/Challenge",
    ],
)
def test_challenge_urls_are_detected(url):
    assert is_challenge_page(Page(url=url), [])


def test_cloudflare_alone_or_challenge_alone_in_the_url_is_not_enough():
    assert not is_challenge_page(Page(url="https://cloudflare.example/blog"), [])
    assert not is_challenge_page(Page(url="https://x.test/challenge-accepted"), [])


def test_a_normal_page_is_not_a_challenge():
    assert not is_challenge_page(Page(), ["verify you are human"])


@pytest.mark.parametrize(
    "frame_url",
    [
        "https://challenges.cloudflare.com/cdn-cgi/x",
        "https://other.test/cdn-cgi/challenge-platform/h/b",
    ],
)
def test_challenge_frames_are_detected(frame_url):
    page = Page()
    page.frames = [Frame("https://example.test/"), Frame(frame_url)]
    assert is_challenge_page(page, [])


def test_an_unrelated_frame_is_not_a_challenge():
    page = Page()
    page.frames = [Frame("https://ads.example/banner")]
    assert not is_challenge_page(page, [])


def test_unreadable_frames_do_not_break_detection():
    class Broken(Page):
        @property
        def frames(self):
            raise RuntimeError("frames gone")

        @frames.setter
        def frames(self, value):
            pass

    assert not is_challenge_page(Broken(), [])


def test_unreadable_content_does_not_break_detection():
    page = Page()
    page.content_raises = True
    assert not is_challenge_page(page, [])


def test_preauth_content_marker_is_detected_case_insensitively():
    page = Page()
    page.content_html = "<script src='/CFI/PreAuthContent/x'></script>"
    assert is_challenge_page(page, [])


@pytest.mark.parametrize(
    "selector",
    [
        "#challenge-stage",
        ".cf-browser-verification",
        ".main-wrapper:has-text('Just a moment')",
        "body:has-text('Just a moment')",
    ],
)
def test_a_visible_strong_selector_is_a_challenge(selector):
    assert is_challenge_page(Page(locators={selector: Loc(count=1, visible={0})}), [])


def test_a_hidden_strong_selector_is_not_a_challenge():
    assert not is_challenge_page(Page(locators={"#challenge-stage": Loc(count=2)}), [])


def test_only_the_first_eight_matches_are_checked_for_visibility():
    page = Page(locators={"#challenge-stage": Loc(count=20, visible={8, 15})})
    assert not is_challenge_page(page, [])
    page = Page(locators={"#challenge-stage": Loc(count=20, visible={7})})
    assert is_challenge_page(page, [])


def test_a_failing_or_detached_selector_is_skipped_not_fatal():
    page = Page(
        locators={
            "#challenge-stage": Loc(raises=True),
            ".cf-browser-verification": Loc(count=1, raises="visible"),
            "body:has-text('Just a moment')": Loc(count=2, visible={1}),
        }
    )
    assert is_challenge_page(page, [])


@pytest.mark.parametrize(
    "selector",
    [
        "div.isotope-challenge-type--tethered",
        "[data-cy='tetheredError']",
        "iframe[src*='challenges.cloudflare.com']",
        "input[name='cf-turnstile-response']",
    ],
)
def test_a_present_strong_selector_is_a_challenge_even_if_hidden(selector):
    assert is_challenge_page(Page(locators={selector: Loc(count=1)}), [])


def test_a_failing_presence_selector_is_skipped():
    page = Page(
        locators={
            "div.isotope-challenge-type--tethered": Loc(raises=True),
            "input[name='cf-turnstile-response']": Loc(count=1),
        }
    )
    assert is_challenge_page(page, [])


@pytest.mark.parametrize("selector", ["script[src*='turnstile']", "form#form_authenticated"])
def test_weak_signals_alone_do_not_make_a_challenge(selector):
    # A turnstile script or an auth form also appears on ordinary login pages.
    page = Page(url="https://example.test/login", locators={selector: Loc(count=1)})
    assert not is_challenge_page(page, [])


def test_text_and_title_snippets_are_matched_case_insensitively():
    assert is_challenge_page(Page(body="PLEASE Verify You Are Human"), ["verify you are human"])
    assert is_challenge_page(Page(title="Just A Moment..."), ["just a moment"])


def test_blank_snippets_never_match():
    assert not is_challenge_page(Page(body="anything"), ["", "   "])


# --- the wait loop ------------------------------------------------------------------------


class Clock:
    def __init__(self, step=0.4):
        self.now = 0.0
        self.step = step
        self.calls = 0

    def __call__(self):
        value = self.now
        self.now += self.step
        self.calls += 1
        return value


class Script:
    """Returns scripted outcomes in order, repeating the last; exceptions are raised."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def wait(monkeypatch):
    def setup(*, is_challenge=(False,), fast_selector=("",), fast_text=(False,), step=0.4):
        clock = Clock(step)
        monkeypatch.setattr(challenge, "time", SimpleNamespace(monotonic=clock))
        scripts = SimpleScripts(Script(*is_challenge), Script(*fast_selector), Script(*fast_text))
        monkeypatch.setattr(challenge, "is_challenge_page", scripts.is_challenge)
        monkeypatch.setattr(challenge, "first_visible_selector_match", scripts.selector)
        monkeypatch.setattr(challenge, "page_contains_any_text", scripts.text)
        scripts.clock = clock
        return scripts

    return setup


class SimpleScripts:
    def __init__(self, is_challenge, selector, text):
        self.is_challenge = is_challenge
        self.selector = selector
        self.text = text


def test_a_page_that_is_not_a_challenge_returns_at_once(wait):
    scripts = wait(is_challenge=(False,))
    page = Page()
    assert wait_for_challenge_to_clear(page, ["x"], 5000) is True
    assert page.slept == []
    assert scripts.is_challenge.calls == 1


def test_it_polls_every_350ms_until_the_challenge_clears(wait):
    wait(is_challenge=(True, True, False))
    page = Page()
    assert wait_for_challenge_to_clear(page, ["x"], 60000) is True
    assert page.slept == [350, 350]


def test_a_known_dead_end_selector_fails_fast(wait):
    scripts = wait(is_challenge=(True,), fast_selector=("main:#blocked",))
    page = Page()
    assert wait_for_challenge_to_clear(page, [], 60000, fast_fail_selectors=["#blocked"]) is False
    assert page.slept == []
    assert scripts.is_challenge.calls == 1


def test_a_known_dead_end_text_fails_fast(wait):
    wait(is_challenge=(True,), fast_text=(True,))
    page = Page()
    assert (
        wait_for_challenge_to_clear(page, [], 60000, fast_fail_text_snippets=["access denied"])
        is False
    )
    assert page.slept == []


def test_fast_fail_checks_run_only_while_a_challenge_is_showing(wait):
    scripts = wait(is_challenge=(False,), fast_selector=("main:#blocked",), fast_text=(True,))
    assert (
        wait_for_challenge_to_clear(
            Page(), [], 60000, fast_fail_selectors=["#b"], fast_fail_text_snippets=["t"]
        )
        is True
    )
    assert scripts.selector.calls == 0
    assert scripts.text.calls == 0


def test_blank_fast_fail_entries_are_ignored_and_never_consulted(wait):
    scripts = wait(is_challenge=(True, False), fast_selector=("main:x",), fast_text=(True,))
    page = Page()
    result = wait_for_challenge_to_clear(
        page, [], 60000, fast_fail_selectors=["", "  "], fast_fail_text_snippets=[" ", ""]
    )
    assert result is True
    assert scripts.selector.calls == 0
    assert scripts.text.calls == 0


def test_the_wait_is_at_least_one_second_even_for_a_tiny_timeout(wait):
    scripts = wait(is_challenge=(True,))
    page = Page()
    assert wait_for_challenge_to_clear(page, [], 10) is False
    # 0.4s clock steps against a 1.0s floor: two polls, then the deadline passes.
    assert page.slept == [350, 350]
    assert scripts.is_challenge.calls == 3  # two polls plus the final check


def test_a_longer_timeout_polls_longer(wait):
    wait(is_challenge=(True,))
    page = Page()
    assert wait_for_challenge_to_clear(page, [], 3000) is False
    assert len(page.slept) > 2


def test_a_challenge_that_clears_in_the_last_moment_counts_as_cleared(wait):
    wait(is_challenge=(True, True, False))
    page = Page()
    assert wait_for_challenge_to_clear(page, [], 1000) is True


def test_a_challenge_still_showing_at_the_deadline_is_a_failure(wait):
    wait(is_challenge=(True,))
    assert wait_for_challenge_to_clear(Page(), [], 1000) is False


def test_the_final_check_still_honours_dead_ends(wait):
    # Not a dead end while polling, but one when the deadline arrives.
    wait(is_challenge=(False,), fast_selector=("main:#b",), step=100.0)
    assert wait_for_challenge_to_clear(Page(), [], 1000, fast_fail_selectors=["#b"]) is False


def test_the_final_text_dead_end_wins_over_a_cleared_page(wait):
    wait(is_challenge=(False,), fast_text=(True,), step=100.0)
    assert (
        wait_for_challenge_to_clear(Page(), [], 1000, fast_fail_text_snippets=["denied"]) is False
    )


def test_a_closed_page_during_the_check_is_recovered_and_the_wait_continues(wait):
    wait(is_challenge=(CLOSED, False))
    fresh = Page()
    reasons = []

    def recover(reason):
        reasons.append(reason)
        return fresh

    assert wait_for_challenge_to_clear(Page(), [], 60000, recover_page=recover) is True
    assert reasons == ["wait_for_challenge_to_clear:state_check"]


def test_a_closed_page_without_a_recovery_hook_is_raised(wait):
    wait(is_challenge=(CLOSED,))
    with pytest.raises(RuntimeError, match="has been closed"):
        wait_for_challenge_to_clear(Page(), [], 60000)


def test_an_unrelated_error_is_never_swallowed_even_with_recovery(wait):
    wait(is_challenge=(ValueError("selector syntax"),))
    reasons = []
    with pytest.raises(ValueError, match="selector syntax"):
        wait_for_challenge_to_clear(
            Page(), [], 60000, recover_page=lambda reason: reasons.append(reason)
        )
    assert reasons == []


def test_a_closed_page_while_sleeping_is_recovered(wait):
    wait(is_challenge=(True, False))
    reasons = []

    class Closing(Page):
        def wait_for_timeout(self, ms):
            raise CLOSED

    def recover(reason):
        reasons.append(reason)
        return Page()

    assert wait_for_challenge_to_clear(Closing(), [], 60000, recover_page=recover) is True
    assert reasons == ["wait_for_challenge_to_clear:sleep"]


def test_an_error_while_sleeping_is_raised_without_a_recovery_hook(wait):
    wait(is_challenge=(True,))

    class Closing(Page):
        def wait_for_timeout(self, ms):
            raise CLOSED

    with pytest.raises(RuntimeError):
        wait_for_challenge_to_clear(Closing(), [], 60000)


def test_an_unrelated_error_while_sleeping_is_raised_even_with_recovery(wait):
    wait(is_challenge=(True,))

    class Broken(Page):
        def wait_for_timeout(self, ms):
            raise OSError("pipe broke")

    with pytest.raises(OSError, match="pipe broke"):
        wait_for_challenge_to_clear(Broken(), [], 60000, recover_page=lambda r: Page())


def test_a_closed_page_at_the_deadline_is_recovered_for_the_final_answer(wait):
    wait(is_challenge=(CLOSED, False), step=100.0)
    reasons = []

    def recover(reason):
        reasons.append(reason)
        return Page()

    assert wait_for_challenge_to_clear(Page(), [], 1000, recover_page=recover) is True
    assert reasons == ["wait_for_challenge_to_clear:final_check"]


def test_a_recovered_page_at_the_deadline_is_still_checked_for_dead_ends(wait):
    wait(is_challenge=(False,), fast_text=(CLOSED, True), step=100.0)
    result = wait_for_challenge_to_clear(
        Page(), [], 1000, recover_page=lambda r: Page(), fast_fail_text_snippets=["denied"]
    )
    assert result is False


def test_a_closed_page_at_the_deadline_without_a_hook_is_raised(wait):
    wait(is_challenge=(CLOSED,), step=100.0)
    with pytest.raises(RuntimeError):
        wait_for_challenge_to_clear(Page(), [], 1000)


def test_an_unrelated_error_at_the_deadline_is_raised(wait):
    wait(is_challenge=(ValueError("boom"), False), step=100.0)
    with pytest.raises(ValueError):
        wait_for_challenge_to_clear(Page(), [], 1000, recover_page=lambda r: Page())


# --- reference codes ----------------------------------------------------------------------


def test_reference_code_is_read_from_the_page_text():
    page = Page(body="Error. Reference Code: 123456 please contact support")
    assert extract_reference_code_from_page(page) == "123456"


def test_reference_code_needs_four_to_twelve_digits():
    assert extract_reference_code_from_text("reference code 123") == ""
    assert extract_reference_code_from_text("reference code 1234") == "1234"
    assert extract_reference_code_from_text("reference code 123456789012") == "123456789012"


def test_reference_code_of_empty_or_none_text():
    assert extract_reference_code_from_text("") == ""
    assert extract_reference_code_from_text(None) == ""


def test_reference_code_missing_from_the_page():
    assert extract_reference_code_from_page(Page(body="all good")) == ""


def test_reference_code_is_capped_at_twelve_digits():
    assert extract_reference_code_from_text("reference code 1234567890123") == "123456789012"
