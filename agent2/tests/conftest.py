import tempfile
from pathlib import Path

import pytest

import config
from src.browser import BrowserSession


@pytest.fixture(scope="session")
def settings() -> config.Settings:
    s = config.load_settings()
    s.browser.headless = True
    s.browser.slow_mo_ms = 0
    s.paths.browser_profile = Path(tempfile.mkdtemp(prefix="pw_profile_"))
    s.paths.screenshots = Path(tempfile.mkdtemp(prefix="pw_shots_"))
    # keep tests fast
    s.delays.between_actions_min = 0
    s.delays.between_actions_max = 0.05
    s.delays.between_profiles_min = 0
    s.delays.between_profiles_max = 0.05
    s.delays.page_timeout = 5
    return s


@pytest.fixture(scope="module")
def browser(settings) -> BrowserSession:
    b = BrowserSession(settings)
    b.start()
    yield b
    b.stop()


class MockSite:
    """Route linkedin.com URLs to in-memory HTML pages."""

    def __init__(self, page):
        self.page = page
        self.routes: dict[str, str] = {}
        page.route("**/*", self._handle)

    def add(self, url_prefix: str, html: str) -> None:
        self.routes[url_prefix] = html

    def _handle(self, route, request):
        url = request.url.split("?")[0]
        for prefix, html in sorted(self.routes.items(), key=lambda kv: -len(kv[0])):
            if url.startswith(prefix):
                route.fulfill(status=200, content_type="text/html", body=html)
                return
        route.fulfill(status=404, content_type="text/html", body="<html><body><h1>Page not found</h1></body></html>")


@pytest.fixture
def site(browser):
    m = MockSite(browser.page)
    yield m
    browser.page.unroute("**/*")
