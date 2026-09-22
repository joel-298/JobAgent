"""Persistent Playwright browser session + page-state validation helpers.

The browser profile lives in browser_profile/ so the LinkedIn login survives
between runs. No credentials are ever handled by this code: the user logs in
manually in the opened window the first time.
"""
from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from config import Settings
from src import selectors as S
from src.exceptions import CaptchaDetectedError, LoginRequiredError
from src.human_intervention import request_intervention
from src.utils import random_sleep, screenshot_name

log = logging.getLogger("agent")

LINKEDIN_FEED = "https://www.linkedin.com/feed/"


class BrowserSession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._pw: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.timeout_ms = int(settings.delays.page_timeout * 1000)

    # ---------- lifecycle ----------
    def start(self) -> Page:
        b = self.settings.browser
        profile_dir: Path = self.settings.paths.browser_profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        launch_kwargs = dict(
            user_data_dir=str(profile_dir),
            headless=b.headless,
            slow_mo=b.slow_mo_ms,
            viewport={"width": b.viewport_width, "height": b.viewport_height},
            args=["--disable-blink-features=AutomationControlled", "--no-first-run"],
        )
        if b.channel in ("chrome", "msedge"):
            launch_kwargs["channel"] = b.channel
        log.info("Launching %s with persistent profile %s", b.channel, profile_dir)
        self.context = self._pw.chromium.launch_persistent_context(**launch_kwargs)
        self.context.set_default_timeout(self.timeout_ms)
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    def stop(self) -> None:
        try:
            if self.context:
                self.context.close()
        except Exception as exc:  # noqa: BLE001
            log.debug("Error closing context: %s", exc)
        try:
            if self._pw:
                self._pw.stop()
        except Exception as exc:  # noqa: BLE001
            log.debug("Error stopping playwright: %s", exc)
        self.context = None
        self.page = None
        self._pw = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    # ---------- navigation ----------
    def goto(self, url: str, wait: str = "domcontentloaded") -> None:
        assert self.page is not None
        log.info("Opening %s", url)
        try:
            self.page.goto(url, wait_until=wait, timeout=self.timeout_ms)
        except PlaywrightTimeoutError:
            log.warning("Page load timed out for %s - continuing with what loaded", url)
        self.settle()
        self.check_page_state()

    def settle(self) -> None:
        """Short pause + wait for network to calm down (best effort)."""
        assert self.page is not None
        try:
            self.page.wait_for_load_state("networkidle", timeout=2500)
        except PlaywrightTimeoutError:
            pass
        d = self.settings.delays
        random_sleep(d.between_actions_min, d.between_actions_max, "settle")

    def short_pause(self) -> None:
        d = self.settings.delays
        random_sleep(min(1.0, d.between_actions_min), min(3.0, d.between_actions_max), "action")

    @property
    def url(self) -> str:
        return self.page.url if self.page else ""

    # ---------- locating ----------
    def find(self, candidates: list[str], root: Page | Locator | None = None, timeout: float = 0) -> Locator | None:
        """Return the first *visible* locator among the candidate selectors, or None."""
        root = root or self.page
        assert root is not None

        def first_visible() -> Locator | None:
            for sel in candidates:
                try:
                    loc = root.locator(sel).filter(visible=True).first
                    if loc.is_visible():
                        return loc
                except Exception as exc:  # noqa: BLE001
                    log.debug("Selector %r failed: %s", sel, exc)
            return None

        found = first_visible()
        if found or not timeout:
            return found
        # Wait once for *any* candidate to appear, then pick by priority order.
        try:
            combined = root.locator(candidates[0])
            for sel in candidates[1:]:
                combined = combined.or_(root.locator(sel))
            combined.filter(visible=True).first.wait_for(state="visible", timeout=int(timeout * 1000))
        except PlaywrightTimeoutError:
            return None
        except Exception as exc:  # noqa: BLE001
            log.debug("Combined wait failed: %s", exc)
            return None
        return first_visible()

    def find_all(self, candidates: list[str], root: Page | Locator | None = None) -> list[Locator]:
        """All *visible* elements for the first candidate selector that yields any."""
        root = root or self.page
        assert root is not None
        for sel in candidates:
            try:
                loc = root.locator(sel).filter(visible=True)
                n = loc.count()
                if n:
                    return [loc.nth(i) for i in range(n)]
            except Exception as exc:  # noqa: BLE001
                log.debug("Selector %r failed: %s", sel, exc)
        return []

    def exists(self, candidates: list[str], root: Page | Locator | None = None) -> bool:
        return self.find(candidates, root) is not None

    def text_of(self, candidates: list[str], root: Page | Locator | None = None) -> str:
        loc = self.find(candidates, root)
        if not loc:
            return ""
        try:
            return (loc.inner_text(timeout=3000) or "").strip()
        except Exception:  # noqa: BLE001
            return ""

    def click(self, candidates: list[str], root: Page | Locator | None = None, timeout: float = 5) -> bool:
        loc = self.find(candidates, root, timeout=timeout)
        if not loc:
            return False
        loc.scroll_into_view_if_needed()
        loc.click()
        self.short_pause()
        return True

    def body_text(self, max_chars: int = 20000) -> str:
        assert self.page is not None
        try:
            return (self.page.locator("body").inner_text(timeout=5000) or "")[:max_chars]
        except Exception:  # noqa: BLE001
            return ""

    # ---------- state validation ----------
    def screenshot(self, excel_row: int, tag: str) -> Path | None:
        if not self.page:
            return None
        path = self.settings.paths.screenshots / screenshot_name(excel_row, tag)
        try:
            self.page.screenshot(path=str(path), full_page=False)
            log.info("Screenshot saved: %s", path.name)
            return path
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not take screenshot: %s", exc)
            return None

    def login_required(self) -> bool:
        url = self.url.lower()
        if any(m in url for m in S.LOGIN_URL_MARKERS):
            return True
        # A LinkedIn page without the global nav and with a sign-in form.
        if self.exists(["form.login__form", "input#session_key", "a[href*='/login']:has-text('Sign in')"]):
            return not self.exists(S.LOGGED_IN_MARKERS)
        return False

    def verification_required(self) -> bool:
        url = self.url.lower()
        if any(m in url for m in S.VERIFICATION_URL_MARKERS):
            return True
        if self.exists(S.VERIFICATION_IFRAMES):
            return True
        text = self.body_text(6000).lower()
        return any(m in text for m in S.VERIFICATION_TEXT_MARKERS)

    def check_page_state(self) -> None:
        """Raise a controlled error if LinkedIn asks for login or verification."""
        if self.verification_required():
            raise CaptchaDetectedError(f"Verification / security check detected at {self.url}")
        if self.login_required():
            raise LoginRequiredError(f"LinkedIn login required at {self.url}")

    def ensure_logged_in(self, excel_row: int = 0) -> None:
        """Open the feed; if a login/verification is required, wait for the user."""
        assert self.page is not None
        for attempt in range(3):
            try:
                self.goto(LINKEDIN_FEED)
                if self.exists(S.LOGGED_IN_MARKERS) or "/feed" in self.url:
                    log.info("LinkedIn session is active")
                    return
                raise LoginRequiredError("Feed did not load a signed-in navigation bar")
            except (LoginRequiredError, CaptchaDetectedError) as exc:
                shot = self.screenshot(excel_row, "login_required" if isinstance(exc, LoginRequiredError) else "verification")
                request_intervention(
                    str(exc),
                    shot,
                    "Log in to LinkedIn in the opened browser window (complete any verification),"
                    "\nthen press ENTER to continue.",
                )
        raise LoginRequiredError("Could not establish a logged-in LinkedIn session")

    def handle_interruption(self, exc: Exception, excel_row: int) -> None:
        """Pause for CAPTCHA/login; after the user continues, re-validate the page."""
        tag = "captcha" if isinstance(exc, CaptchaDetectedError) else "login_required"
        shot = self.screenshot(excel_row, tag)
        request_intervention(str(exc), shot)
        self.settle()
        self.check_page_state()
