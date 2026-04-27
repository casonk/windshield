"""In-page manual-continue overlay and terminal prompt for human-in-the-loop steps."""

from __future__ import annotations

import re
import sys
import time
from typing import Any

from windshield.http import sanitize_manual_guidance_text
from windshield.page import iter_page_frames


def describe_manual_page_guidance(page: Any) -> str:
    """Summarize the current page and likely next manual action."""
    if page is None:
        return ""

    headings: list[str] = []
    buttons: list[str] = []
    inputs: list[str] = []
    checkboxes: list[str] = []
    seen_headings: set[str] = set()
    seen_buttons: set[str] = set()
    seen_inputs: set[str] = set()
    seen_checkboxes: set[str] = set()

    def remember(bucket: list[str], seen: set[str], value: Any, max_len: int = 140) -> None:
        text = sanitize_manual_guidance_text(value, max_len=max_len)
        if not text:
            return
        normalized = text.lower()
        if normalized in seen:
            return
        seen.add(normalized)
        bucket.append(text)

    def first_non_empty_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def get_item_attr(item: Any, name: str) -> str:
        try:
            return str(item.get_attribute(name) or "").strip()
        except Exception:  # pylint: disable=broad-except
            return ""

    def get_item_text(item: Any) -> str:
        for getter_name in ("inner_text", "text_content"):
            try:
                getter = getattr(item, getter_name, None)
                if getter is None:
                    continue
                text = str(getter() or "").strip()
                if text:
                    return text
            except Exception:  # pylint: disable=broad-except
                continue
        return ""

    def get_checkbox_label(item: Any) -> str:
        try:
            label = item.evaluate("""(el) => {
                    const clip = (value, max = 220) =>
                      String(value || "").replace(/\\s+/g, " ").trim().slice(0, max);
                    if (!(el instanceof HTMLInputElement)) return "";
                    if (el.labels && el.labels.length) {
                      const firstLabel = el.labels[0];
                      if (firstLabel) return clip(firstLabel.innerText || firstLabel.textContent || "");
                    }
                    if (el.id) {
                      const linked = document.querySelector(`label[for="${el.id}"]`);
                      if (linked) return clip(linked.innerText || linked.textContent || "");
                    }
                    return clip(el.getAttribute("aria-label") || el.getAttribute("name") || el.id || "");
                }""")
            return str(label or "").strip()
        except Exception:  # pylint: disable=broad-except
            return first_non_empty_text(
                get_item_attr(item, "aria-label"),
                get_item_attr(item, "name"),
                get_item_attr(item, "id"),
            )

    page_title = ""
    try:
        page_title = str(page.title() or "").strip()
    except Exception:  # pylint: disable=broad-except
        page_title = ""

    for target in iter_page_frames(page):
        for selector in ("h1", "h2", "h3", "[role='heading']"):
            try:
                locator = target.locator(selector)
                count = min(locator.count(), 4)
            except Exception:  # pylint: disable=broad-except
                continue
            for idx in range(count):
                try:
                    item = locator.nth(idx)
                    if not item.is_visible():
                        continue
                except Exception:  # pylint: disable=broad-except
                    continue
                remember(headings, seen_headings, get_item_text(item), max_len=120)

        for selector in (
            "button",
            "a",
            "input[type='submit']",
            "input[type='button']",
            "[role='button']",
        ):
            try:
                locator = target.locator(selector)
                count = min(locator.count(), 12)
            except Exception:  # pylint: disable=broad-except
                continue
            for idx in range(count):
                try:
                    item = locator.nth(idx)
                    if not item.is_visible():
                        continue
                except Exception:  # pylint: disable=broad-except
                    continue
                button_label = first_non_empty_text(
                    get_item_text(item),
                    get_item_attr(item, "aria-label"),
                    get_item_attr(item, "value"),
                    get_item_attr(item, "title"),
                    get_item_attr(item, "name"),
                    get_item_attr(item, "id"),
                )
                remember(buttons, seen_buttons, button_label, max_len=100)

        try:
            checkbox_locator = target.locator("input[type='checkbox']")
            checkbox_count = min(checkbox_locator.count(), 6)
        except Exception:  # pylint: disable=broad-except
            checkbox_count = 0
        for idx in range(checkbox_count):
            try:
                item = checkbox_locator.nth(idx)
                if not item.is_visible():
                    continue
            except Exception:  # pylint: disable=broad-except
                continue
            remember(checkboxes, seen_checkboxes, get_checkbox_label(item), max_len=110)

        for selector in ("input", "textarea", "select"):
            try:
                locator = target.locator(selector)
                count = min(locator.count(), 10)
            except Exception:  # pylint: disable=broad-except
                continue
            for idx in range(count):
                try:
                    item = locator.nth(idx)
                    if not item.is_visible():
                        continue
                except Exception:  # pylint: disable=broad-except
                    continue
                input_type = get_item_attr(item, "type").lower()
                if input_type in {
                    "hidden",
                    "submit",
                    "button",
                    "checkbox",
                    "radio",
                    "file",
                }:
                    continue
                input_label = first_non_empty_text(
                    get_item_attr(item, "aria-label"),
                    get_item_attr(item, "placeholder"),
                    get_item_attr(item, "name"),
                    get_item_attr(item, "id"),
                    input_type,
                )
                remember(inputs, seen_inputs, input_label, max_len=100)

    primary_button = ""
    for pattern in (
        r"\baccept\b",
        r"\bi agree\b",
        r"\ballow\b",
        r"\bauthorize\b",
        r"\bcontinue\b",
        r"\bverify\b",
        r"\bsubmit\b",
        r"\bconfirm\b",
        r"\blog\s*in\b",
        r"\bsign\s*in\b",
        r"\bnext\b",
        r"\bdone\b",
        r"\bdownload\b",
        r"\bview\b",
    ):
        primary_button = next(
            (label for label in buttons if re.search(pattern, label, re.IGNORECASE)),
            "",
        )
        if primary_button:
            break
    if not primary_button:
        primary_button = first_non_empty_text(*buttons)

    code_input = next(
        (
            label
            for label in inputs
            if re.search(
                r"\b(code|otp|verification|security|passcode|mfa|2fa)\b",
                label,
                re.IGNORECASE,
            )
        ),
        "",
    )
    login_inputs = [
        label
        for label in inputs
        if re.search(
            r"\b(username|user|login|email|phone|password|passcode)\b",
            label,
            re.IGNORECASE,
        )
    ]
    page_label = first_non_empty_text(
        first_non_empty_text(*headings),
        page_title,
    )

    parts: list[str] = []
    if page_label:
        parts.append(f"Current page: '{sanitize_manual_guidance_text(page_label, 120)}'.")
    if checkboxes and primary_button:
        parts.append(f"Likely next step: check '{checkboxes[0]}' then click '{primary_button}'.")
    elif code_input and primary_button:
        parts.append(
            f"Likely next step: enter the verification code in '{code_input}' "
            f"then click '{primary_button}'."
        )
    elif login_inputs and primary_button:
        login_labels = ", ".join(f"'{label}'" for label in login_inputs[:2])
        parts.append(f"Likely next step: complete {login_labels} then click '{primary_button}'.")
    elif primary_button:
        parts.append(f"Likely next click: '{primary_button}'.")
    elif code_input:
        parts.append(f"Likely next step: enter the verification code in '{code_input}'.")
    if buttons:
        parts.append("Visible actions: " + ", ".join(f"'{label}'" for label in buttons[:3]) + ".")
    return " ".join(part for part in parts if part).strip()


def wait_for_manual_continue(
    page: Any,
    timeout_seconds: int,
    title: str,
    body: str,
    button_text: str,
    auto_continue_seconds: float = 0.0,
    overlay_id: str = "ws-manual-continue-overlay",
    continue_flag: str = "__wsManualContinue",
    overlay_enabled: bool = True,
    terminal_prompt_enabled: bool = True,
) -> bool:
    """Show an in-page overlay and/or terminal prompt, wait for user to continue.

    Returns True if the user continued, False on timeout.
    """
    timeout_ms = max(10_000, int(timeout_seconds) * 1000)
    safe_auto_continue_seconds = max(0.0, float(auto_continue_seconds))
    safe_title = str(title or "").strip() or "Manual Step Required"
    safe_body = str(body or "").strip() or "Complete the manual step, then continue."
    manual_guidance = describe_manual_page_guidance(page)
    if manual_guidance:
        safe_body = f"{safe_body}\n\n{manual_guidance}"
    safe_button = str(button_text or "").strip() or "Continue"
    safe_overlay_id = str(overlay_id or "").strip() or "ws-manual-continue-overlay"
    safe_continue_flag = str(continue_flag or "").strip() or "__wsManualContinue"
    overlay_injected = False

    try:
        if overlay_enabled:
            try:
                page.bring_to_front()
            except Exception:  # pylint: disable=broad-except
                pass

            overlay_injected = bool(
                page.evaluate(
                    """
                    ({overlayId, continueFlag, titleText, bodyText, buttonText}) => {
                      try {
                        const existing = document.getElementById(overlayId);
                        if (existing) existing.remove();
                      } catch (_err) {}

                      window[continueFlag] = false;

                      const overlay = document.createElement('div');
                      overlay.id = overlayId;
                      overlay.style.position = 'fixed';
                      overlay.style.inset = '0';
                      overlay.style.background = 'rgba(0, 0, 0, 0.65)';
                      overlay.style.zIndex = '2147483647';
                      overlay.style.display = 'flex';
                      overlay.style.alignItems = 'center';
                      overlay.style.justifyContent = 'center';
                      overlay.style.padding = '24px';

                      const card = document.createElement('div');
                      card.style.maxWidth = '600px';
                      card.style.background = '#ffffff';
                      card.style.borderRadius = '12px';
                      card.style.padding = '20px';
                      card.style.fontFamily = 'Arial, sans-serif';
                      card.style.color = '#111111';
                      card.style.boxShadow = '0 14px 48px rgba(0,0,0,0.25)';

                      const title = document.createElement('h2');
                      title.textContent = String(titleText || '');
                      title.style.margin = '0 0 10px 0';
                      title.style.fontSize = '22px';

                      const body = document.createElement('p');
                      body.textContent = String(bodyText || '');
                      body.style.margin = '0 0 16px 0';
                      body.style.fontSize = '15px';
                      body.style.lineHeight = '1.45';
                      body.style.whiteSpace = 'pre-wrap';

                      const button = document.createElement('button');
                      button.type = 'button';
                      button.textContent = String(buttonText || 'Continue');
                      button.style.padding = '10px 16px';
                      button.style.fontSize = '15px';
                      button.style.border = '0';
                      button.style.background = '#005a49';
                      button.style.color = '#ffffff';
                      button.style.borderRadius = '8px';
                      button.style.cursor = 'pointer';
                      button.addEventListener('click', () => {
                        window[continueFlag] = true;
                        overlay.remove();
                      });

                      card.appendChild(title);
                      card.appendChild(body);
                      card.appendChild(button);
                      overlay.appendChild(card);
                      document.body.appendChild(overlay);
                      return true;
                    }
                    """,
                    {
                        "overlayId": safe_overlay_id,
                        "continueFlag": safe_continue_flag,
                        "titleText": safe_title,
                        "bodyText": safe_body,
                        "buttonText": safe_button,
                    },
                )
            )

        can_prompt_terminal = (
            bool(hasattr(sys.stdin, "isatty") and getattr(sys.stdin, "isatty")())
            and terminal_prompt_enabled
        )
        select_module = None
        if can_prompt_terminal:
            try:
                import select as _select  # pylint: disable=import-outside-toplevel

                select_module = _select
            except Exception:  # pylint: disable=broad-except
                can_prompt_terminal = False

        if can_prompt_terminal:
            auto_continue_note = ""
            if safe_auto_continue_seconds > 0.0:
                auto_continue_note = f" Auto-continue in {int(round(safe_auto_continue_seconds))}s."
            print(
                "[manual] "
                f"{safe_title}: {safe_body} "
                f"Click '{safe_button}' in browser or press Enter here "
                f"(timeout {timeout_ms // 1000}s).{auto_continue_note}",
                flush=True,
            )

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        auto_continue_deadline = 0.0
        if safe_auto_continue_seconds > 0.0:
            auto_continue_deadline = min(
                deadline,
                time.monotonic() + safe_auto_continue_seconds,
            )
        while time.monotonic() < deadline:
            if overlay_injected:
                try:
                    continued = bool(
                        page.evaluate(
                            "(flag) => window[flag] === true",
                            safe_continue_flag,
                        )
                    )
                    if continued:
                        return True
                except Exception:  # pylint: disable=broad-except
                    overlay_injected = False

            if auto_continue_deadline and time.monotonic() >= auto_continue_deadline:
                try:
                    page.evaluate(
                        """
                        ({overlayId, continueFlag}) => {
                          window[continueFlag] = true;
                          const overlay = document.getElementById(overlayId);
                          if (overlay) overlay.remove();
                        }
                        """,
                        {
                            "overlayId": safe_overlay_id,
                            "continueFlag": safe_continue_flag,
                        },
                    )
                except Exception:  # pylint: disable=broad-except
                    pass
                return True

            remaining = max(0.0, deadline - time.monotonic())
            if can_prompt_terminal and select_module is not None and remaining > 0:
                wait_slice = min(0.5, remaining)
                try:
                    ready, _, _ = select_module.select([sys.stdin], [], [], wait_slice)
                except Exception:  # pylint: disable=broad-except
                    can_prompt_terminal = False
                    ready = []
                if ready:
                    try:
                        _ = sys.stdin.readline()
                    except Exception:  # pylint: disable=broad-except
                        pass
                    return True
            elif remaining > 0:
                time.sleep(min(0.5, remaining))

        return False
    except Exception:  # pylint: disable=broad-except
        return False
    finally:
        try:
            page.evaluate(
                """
                ({overlayId}) => {
                  const overlay = document.getElementById(overlayId);
                  if (overlay) overlay.remove();
                }
                """,
                {"overlayId": safe_overlay_id},
            )
        except Exception:  # pylint: disable=broad-except
            pass


def wait_for_manual_otp_continue(
    page: Any,
    timeout_seconds: int,
) -> bool:
    """Convenience wrapper for OTP verification manual step."""
    return wait_for_manual_continue(
        page=page,
        timeout_seconds=timeout_seconds,
        title="Manual Verification Required",
        body=(
            "Enter the verification code in the page, submit it there if "
            "needed, then click Continue below."
        ),
        button_text="Continue",
        overlay_id="ws-manual-otp-overlay",
        continue_flag="__wsManualOtpContinue",
    )
