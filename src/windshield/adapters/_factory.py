"""Browser factory — create browser pages using any supported backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from windshield.adapters._protocol import AsyncPageAdapter, BackendType, PageAdapter


def create_page(
    backend: str | BackendType = BackendType.PLAYWRIGHT,
    *,
    raw: Any = None,
    profile_dir: str | Path | None = None,
    headless: bool = False,
    user_agent: str | None = None,
    proxy: str | None = None,
    url: str = "",
    html: str = "",
    **kwargs: Any,
) -> PageAdapter:
    """Create a browser page adapter for the specified backend.

    This is the primary entry point for multi-backend browser automation.
    Pass an existing driver/page via *raw*, or let the factory create one.

    Args:
        backend: Backend to use — ``"playwright"``, ``"selenium"``,
            ``"undetected"``, or ``"http"`` (or a :class:`BackendType` enum).
        raw: An existing Playwright Page, Selenium WebDriver, or
            ``requests.Session`` to wrap.  When provided, the factory wraps it
            without creating a new browser instance.
        profile_dir: Chrome user-data directory for live profile reuse
            (Selenium/Undetected only).
        headless: Launch in headless mode.
        user_agent: Override user-agent string.
        proxy: Proxy server URL.
        url: Initial URL to load (HTTP backend uses this with ``goto``).
        html: Raw HTML to parse (HTTP backend only, alternative to *url*).
        **kwargs: Extra keyword arguments forwarded to the backend constructor.

    Returns:
        A :class:`PageAdapter` wrapping the backend-specific page/driver.

    Raises:
        ValueError: If *backend* is not recognised.
        ImportError: If the backend's optional dependency is not installed.
    """
    if isinstance(backend, str):
        try:
            backend = BackendType(backend.lower())
        except ValueError:
            valid = ", ".join(b.value for b in BackendType)
            raise ValueError(f"Unknown backend {backend!r}. Valid backends: {valid}") from None

    if backend is BackendType.PLAYWRIGHT:
        return _create_playwright(raw=raw, headless=headless, **kwargs)

    if backend is BackendType.SELENIUM:
        return _create_selenium(
            raw=raw,
            profile_dir=profile_dir,
            headless=headless,
            user_agent=user_agent,
            proxy=proxy,
            **kwargs,
        )

    if backend is BackendType.UNDETECTED:
        return _create_undetected(
            raw=raw,
            profile_dir=profile_dir,
            headless=headless,
            user_agent=user_agent,
            proxy=proxy,
            **kwargs,
        )

    if backend is BackendType.HTTP:
        return _create_http(raw=raw, url=url, html=html, **kwargs)

    raise ValueError(f"Unsupported backend: {backend}")  # pragma: no cover


# -- backend constructors -----------------------------------------------------


def _create_playwright(*, raw: Any = None, headless: bool = False, **kwargs: Any) -> PageAdapter:
    from windshield.adapters._playwright import PlaywrightPageAdapter

    if raw is not None:
        return PlaywrightPageAdapter(raw)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "playwright is required for the 'playwright' backend. "
            "Install it with: pip install playwright && playwright install"
        ) from exc

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=headless, **kwargs)
    page = browser.new_page()
    return PlaywrightPageAdapter(page)


async def create_async_playwright_page(
    *, raw: Any = None, headless: bool = False, **kwargs: Any
) -> AsyncPageAdapter:
    """Create or wrap a page using Playwright's async API.

    This is deliberately Playwright-only. Other backends retain the existing
    synchronous :func:`create_page` contract until they can provide equivalent
    awaitable behavior.
    """
    from windshield.adapters._playwright import AsyncPlaywrightPageAdapter

    if raw is not None:
        return AsyncPlaywrightPageAdapter(raw)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise ImportError(
            "playwright is required for the async Playwright backend. "
            "Install it with: pip install playwright && playwright install"
        ) from exc

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=headless, **kwargs)
    page = await browser.new_page()
    return AsyncPlaywrightPageAdapter(page)


def _create_selenium(
    *,
    raw: Any = None,
    profile_dir: str | Path | None = None,
    headless: bool = False,
    user_agent: str | None = None,
    proxy: str | None = None,
    **kwargs: Any,
) -> PageAdapter:
    from windshield.adapters._selenium import SeleniumPageAdapter

    if raw is not None:
        return SeleniumPageAdapter(raw)

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as exc:
        raise ImportError(
            "selenium is required for the 'selenium' backend. Install it with: pip install selenium"
        ) from exc

    options = Options()
    if profile_dir:
        options.add_argument(f"--user-data-dir={Path(profile_dir).resolve()}")
    if headless:
        options.add_argument("--headless=new")
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    driver = webdriver.Chrome(options=options, **kwargs)
    return SeleniumPageAdapter(driver)


def _create_undetected(
    *,
    raw: Any = None,
    profile_dir: str | Path | None = None,
    headless: bool = False,
    user_agent: str | None = None,
    proxy: str | None = None,
    **kwargs: Any,
) -> PageAdapter:
    from windshield.adapters._undetected import UndetectedChromePageAdapter

    if raw is not None:
        return UndetectedChromePageAdapter(raw)

    from windshield.adapters._undetected import create_undetected_browser

    return create_undetected_browser(
        profile_dir=profile_dir,
        headless=headless,
        user_agent=user_agent,
        proxy=proxy,
        **kwargs,
    )


def _create_http(
    *,
    raw: Any = None,
    url: str = "",
    html: str = "",
    **kwargs: Any,
) -> PageAdapter:
    from windshield.adapters._http import HttpPageAdapter

    session = raw
    adapter = HttpPageAdapter(session=session, url=url, html=html, **kwargs)
    if url and not html:
        adapter.goto(url)
    return adapter
