"""Undetected Chrome adapter — extends Selenium with anti-detection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from windshield.adapters._selenium import SeleniumPageAdapter


class UndetectedChromePageAdapter(SeleniumPageAdapter):
    """Adapter for ``undetected-chromedriver``.

    Extends :class:`SeleniumPageAdapter` since ``undetected-chromedriver``
    produces a standard Selenium ``WebDriver`` instance with anti-detection
    patches applied transparently.
    """

    @property
    def backend_name(self) -> str:  # type: ignore[override]
        return "undetected"


def create_undetected_browser(
    *,
    profile_dir: str | Path | None = None,
    headless: bool = False,
    user_agent: str | None = None,
    proxy: str | None = None,
    version_main: int | None = None,
    **uc_kwargs: Any,
) -> UndetectedChromePageAdapter:
    """Create an undetected-chromedriver browser and return an adapter.

    Args:
        profile_dir: Path to an existing Chrome user-data directory for live
            profile reuse (no automation footprint).
        headless: Run headless (less stealthy — avoid if possible).
        user_agent: Override user-agent string.
        proxy: Proxy server URL (e.g. ``"socks5://127.0.0.1:1080"``).
        version_main: Pin Chrome major version for chromedriver compatibility.
        **uc_kwargs: Extra keyword arguments forwarded to ``uc.Chrome()``.

    Returns:
        An :class:`UndetectedChromePageAdapter` wrapping the driver.
    """
    try:
        import undetected_chromedriver as uc
    except ImportError as exc:
        raise ImportError(
            "undetected-chromedriver is required for the 'undetected' backend. "
            "Install it with: pip install undetected-chromedriver"
        ) from exc

    options = uc.ChromeOptions()

    if profile_dir is not None:
        options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")

    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")

    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    if headless:
        options.add_argument("--headless=new")

    driver = uc.Chrome(
        options=options,
        version_main=version_main,
        **uc_kwargs,
    )

    return UndetectedChromePageAdapter(driver)
