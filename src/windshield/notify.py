"""Send alerts through shock-relay (Signal, Telegram, Gmail).

Recipients come from ``WINDSHIELD_NOTIFY_<CHANNEL>_TARGET`` (channel: SIGNAL,
TELEGRAM, GMAIL), usually loaded from an owner-only ``~/.config/windshield/notify.env``.
A channel without a target is skipped; one channel failing never stops the others.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

CHANNELS = ("signal", "telegram", "gmail")
SERVICE_SCRIPTS = {
    "signal": "services/signal-cli/send_message.py",
    "telegram": "services/telegram/send_message.py",
    "gmail": "services/gmail-imap/send_email.py",
}
ROOT_ENV = "WINDSHIELD_SHOCK_RELAY_ROOT"


@dataclass(frozen=True)
class Delivery:
    channel: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def shock_relay_root(env: Mapping[str, str] | None = None) -> Path:
    source = os.environ if env is None else env
    if source.get(ROOT_ENV):
        return Path(source[ROOT_ENV]).expanduser()
    return Path(__file__).resolve().parents[3] / "shock-relay"


def targets(env: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if env is None else env
    found = {}
    for channel in CHANNELS:
        value = str(source.get(f"WINDSHIELD_NOTIFY_{channel.upper()}_TARGET", "")).strip()
        if value:
            found[channel] = value
    return found


def send_alert(subject: str, body: str, env: Mapping[str, str] | None = None) -> list[Delivery]:
    """Send to every configured channel. Returns one Delivery per channel attempted."""
    source = os.environ if env is None else env
    root = shock_relay_root(source)
    deliveries = []
    for channel, target in targets(source).items():
        script = root / SERVICE_SCRIPTS[channel]
        if not script.exists():
            deliveries.append(Delivery(channel, f"shock-relay script not found: {script}"))
            continue
        if channel == "gmail":
            command = [sys.executable, str(script), target, subject, body]
        else:
            command = [sys.executable, str(script), target, f"{subject}\n{body}"]
        config = str(source.get(f"WINDSHIELD_NOTIFY_{channel.upper()}_CONFIG", "")).strip()
        if config:
            command += ["--config", config]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env={**os.environ, "PYTHONPATH": str(script.parent)},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            deliveries.append(Delivery(channel, str(exc)))
            continue
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            deliveries.append(
                Delivery(channel, detail[-1] if detail else f"exit {result.returncode}")
            )
        else:
            deliveries.append(Delivery(channel))
    return deliveries
