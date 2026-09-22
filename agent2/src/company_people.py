"""Company page -> people discovery -> candidate collection.

2026 LinkedIn UI: the company page exposes its numeric id in an
"N employees" link; people are found with LinkedIn's people search filtered
by that id plus a keyword. If no id can be read, the company People tab with
?keywords= is used instead. Candidates are filtered purely on the visible
headline text against the configurable keyword lists.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

from config import Settings
from src import selectors as S
from src.browser import BrowserSession
from src.exceptions import CompanyPageError, PeopleSearchError
from src.utils import clean_profile_url, company_people_url, contains_any

log = logging.getLogger("agent")

CATEGORY_HR = "HR"
CATEGORY_DEVELOPER = "DEVELOPER"


@dataclass
class PersonCandidate:
    url: str
    name: str
    headline: str
    category: str
    search_term: str = ""
    degree: str = ""


class CompanyPeople:
    def __init__(self, browser: BrowserSession, settings: Settings, excel_row: int, company_link: str):
        self.b = browser
        self.settings = settings
        self.excel_row = excel_row
        self.company_link = company_link
        self.company_id: str = ""
        self.company_name: str = ""

    # ---------- company page ----------
    def open_company(self) -> str:
        """Navigate to the company page, verify it, return the company name."""
        self.b.goto(self.company_link)
        url = self.b.url.lower()
        if "/company/" not in url and "/school/" not in url:
            self.b.screenshot(self.excel_row, "company_page_error")
            raise CompanyPageError(f"Not a LinkedIn company page: {self.b.url}")
        if self.b.exists(S.COMPANY_NOT_FOUND):
            self.b.screenshot(self.excel_row, "company_not_found")
            raise CompanyPageError(f"Company page not found: {self.company_link}")
        if not self.b.find(S.COMPANY_PAGE_MARKERS, timeout=15):
            self.b.screenshot(self.excel_row, "company_page_error")
            raise CompanyPageError("Company page loaded but was not recognised")

        # Name: "<Company>: Posts | LinkedIn" or "<Company> | LinkedIn"
        title = self.b.page.title() or ""
        name = title.split("|")[0].split(":")[0].strip()
        self.company_name = name or self.b.text_of(S.COMPANY_NAME)

        self.company_id = self._read_company_id()
        log.info("Company page loaded: %s (id=%s)", self.company_name, self.company_id or "unknown")
        return self.company_name

    def _read_company_id(self) -> str:
        for link in self.b.find_all(S.COMPANY_ID_LINK):
            try:
                href = unquote(link.get_attribute("href") or "")
                m = re.search(r'currentCompany=\["?(\d+)"?\]', href)
                if m:
                    return m.group(1)
            except Exception as exc:  # noqa: BLE001
                log.debug("Company id read failed: %s", exc)
        return ""

    # ---------- people pages ----------
    def _search_url(self, keywords: str) -> str:
        if self.company_id:
            return S.PEOPLE_SEARCH_URL.format(company_id=self.company_id, keywords=quote(keywords))
        return company_people_url(self.company_link, keywords)

    def open_people(self, keywords: str = "") -> None:
        url = self._search_url(keywords)
        self.b.goto(url)
        u = self.b.url.lower()
        if "/search/results/people" not in u and "/people" not in u:
            self.b.screenshot(self.excel_row, "people_section_error")
            raise PeopleSearchError(f"People results did not open (landed on {self.b.url})")

    def _collect_cards(self) -> list[dict]:
        try:
            cards = self.b.page.evaluate(S.PEOPLE_CARDS_JS) or []
        except Exception as exc:  # noqa: BLE001
            log.debug("Card extraction failed: %s", exc)
            return []
        out = []
        for c in cards:
            href = c.get("href") or ""
            if not href:
                continue
            url = clean_profile_url(href if href.startswith("http") else f"https://www.linkedin.com{href}")
            if url.rstrip("/").endswith("/in"):
                continue
            out.append({"url": url, "name": c.get("name", ""), "headline": c.get("headline", ""), "degree": c.get("degree", "")})
        return out

    def search(
        self,
        category: str,
        search_terms: list[str],
        title_keywords: list[str],
        exclude_keywords: list[str] | None = None,
        max_needed: int | None = None,
    ) -> list[PersonCandidate]:
        """Run each search term and collect headline-matching candidates."""
        exclude_keywords = exclude_keywords or []
        max_pages = max(1, self.settings.networking.max_search_pages)
        found: dict[str, PersonCandidate] = {}
        rejected = 0
        for term in search_terms:
            if max_needed and len(found) >= max_needed:
                break
            log.info("%s search: '%s'", category, term)
            self.open_people(term)
            if self.b.exists(S.PEOPLE_NO_RESULTS):
                log.info("No results for '%s'", term)
                continue
            if not self.b.find(S.PEOPLE_RESULT_LINKS, timeout=10):
                # Treated as "nobody found" rather than a hard error; the
                # min/max targets decide whether the row can still complete.
                log.warning("No people cards rendered for '%s' - treating as no results", term)
                self.b.screenshot(self.excel_row, f"{category.lower()}_search_empty")
                continue
            for page_no in range(max_pages):
                for c in self._collect_cards():
                    url = c["url"]
                    if url in found:
                        continue
                    if not contains_any(c["headline"], title_keywords):
                        rejected += 1
                        continue
                    if contains_any(c["headline"], exclude_keywords):
                        rejected += 1
                        continue
                    found[url] = PersonCandidate(url, c["name"], c["headline"], category, term, c["degree"])
                    log.debug("Candidate: %s | %s", c["name"], c["headline"])
                if max_needed and len(found) >= max_needed:
                    break
                if page_no < max_pages - 1 and (
                    self.b.click(S.PEOPLE_NEXT_PAGE, timeout=2) or self.b.click(S.PEOPLE_SHOW_MORE, timeout=2)
                ):
                    self.b.settle()
                else:
                    break
        log.info("%s candidates found: %d (rejected by headline: %d)", category, len(found), rejected)
        return list(found.values())

    @staticmethod
    def prioritise(candidates: list[PersonCandidate], priority_keywords: list[str]) -> list[PersonCandidate]:
        """Stable sort: earlier priority keyword in the headline -> contacted first."""

        def tier(c: PersonCandidate) -> int:
            h = f" {c.headline.lower()} "
            for i, k in enumerate(priority_keywords):
                if k.lower() in h:
                    return i
            return len(priority_keywords)

        return sorted(candidates, key=tier)

    # convenience wrappers using the settings lists
    def search_hr(self, max_needed: int | None = None) -> list[PersonCandidate]:
        n = self.settings.networking
        return self.search(CATEGORY_HR, n.hr_search_terms, n.hr_title_keywords, [], max_needed)

    def search_developers(self, max_needed: int | None = None) -> list[PersonCandidate]:
        n = self.settings.networking
        log.info("Cleared HR/Talent filters - starting developer search")
        found = self.search(
            CATEGORY_DEVELOPER, n.developer_search_terms, n.developer_title_keywords, n.developer_exclude_keywords, max_needed
        )
        return self.prioritise(found, n.developer_priority_keywords)
