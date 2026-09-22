"""Agent 1: search LinkedIn Jobs and append PENDING rows to agent2's jobs.xlsx.

Filters: location, posted within N hours, Easy Apply only, experience level.
For every result: skip excluded titles, open the job, confirm it is Easy Apply
and not yet applied, read the description, choose the Java or MERN resume,
take the company link, and append a row with the matching messages.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import yaml

# agent2 provides the browser session, settings and Excel handling
from config import Settings  # noqa: E402  (agent2/config.py)
from src import selectors as S  # noqa: E402
from src.browser import BrowserSession  # noqa: E402
from src.excel_manager import ExcelManager  # noqa: E402
from src.exceptions import AgentError, CaptchaDetectedError, LoginRequiredError  # noqa: E402
from src.job_application import JobApplication  # noqa: E402
from src.utils import random_sleep  # noqa: E402

log = logging.getLogger("agent")

SEARCH_URL = "https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}&f_TPR=r{secs}&sortBy=DD"

CARDS_JS = r"""() => {
  const vis = e => e.getClientRects().length > 0;
  const seen = new Set(); const out = [];
  for (const a of document.querySelectorAll('a[href*="/jobs/view/"]')) {
    if (!vis(a)) continue;
    const m = (a.getAttribute('href') || '').match(/\/jobs\/view\/(\d+)/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);
    let card = a, lines = [];
    for (let i = 0; i < 8 && card.parentElement; i++) {
      card = card.parentElement;
      lines = (card.innerText || '').split('\n').map(x => x.trim()).filter(Boolean);
      if (lines.length >= 3) break;
    }
    const title = (lines[0] || (a.innerText || '').split('\n')[0] || '').trim();
    let company = '', location = '';
    for (let i = 1; i < lines.length; i++) {
      if (lines[i] === title || lines[i].startsWith(title)) continue;
      if (!company) { company = lines[i]; continue; }
      if (!location) { location = lines[i]; break; }
    }
    out.push({id: m[1], title, company, location});
  }
  return out;
}"""

DESCRIPTION_JS = r"""() => {
  const main = document.querySelector('main') || document.body;
  const txt = main.innerText || '';
  const i = txt.indexOf('About the job');
  let d = i >= 0 ? txt.slice(i + 13) : txt;
  for (const stop of ['Set alert for similar jobs', 'See how you compare', 'Similar jobs', 'People also viewed']) {
    const j = d.indexOf(stop); if (j > 200) d = d.slice(0, j);
  }
  return d.trim().slice(0, 8000);
}"""

COMPANY_LINK_JS = r"""() => {
  const main = document.querySelector('main') || document.body;
  for (const a of main.querySelectorAll('a[href*="/company/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/linkedin\.com\/company\/([^/?#]+)/) || href.match(/^\/company\/([^/?#]+)/);
    if (m && !/insights/.test(href)) return 'https://www.linkedin.com/company/' + m[1] + '/';
  }
  return '';
}"""


@dataclass
class SearchConfig:
    keywords: list[str]
    location: str = "India"
    posted_within_hours: int = 24
    easy_apply_only: bool = True
    experience_levels: list[int] = field(default_factory=list)
    pages_per_keyword: int = 2
    max_new_jobs: int = 20
    exclude_title_words: list[str] = field(default_factory=list)
    require_any_in_description: list[str] = field(default_factory=list)
    java_name: str = "Java"
    mern_name: str = "Mern"
    java_keywords: list[str] = field(default_factory=list)
    mern_keywords: list[str] = field(default_factory=list)
    messages: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "SearchConfig":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        se, re_ = raw.get("search") or {}, raw.get("resume") or {}
        return cls(
            keywords=list(se.get("keywords") or ["Software Developer"]),
            location=str(se.get("location", "India")),
            posted_within_hours=int(se.get("posted_within_hours", 24)),
            easy_apply_only=bool(se.get("easy_apply_only", True)),
            experience_levels=[int(x) for x in (se.get("experience_levels") or [])],
            pages_per_keyword=max(1, int(se.get("pages_per_keyword", 1))),
            max_new_jobs=int(se.get("max_new_jobs", 20)),
            exclude_title_words=[str(x).lower() for x in (raw.get("exclude_title_words") or [])],
            require_any_in_description=[str(x).lower() for x in (raw.get("require_any_in_description") or [])],
            java_name=str(re_.get("java_name", "Java")),
            mern_name=str(re_.get("mern_name", "Mern")),
            java_keywords=[str(x).lower() for x in (re_.get("java_keywords") or ["java"])],
            mern_keywords=[str(x).lower() for x in (re_.get("mern_keywords") or ["node", "react"])],
            messages=raw.get("messages") or {},
        )

    def search_url(self, keyword: str, start: int = 0) -> str:
        url = SEARCH_URL.format(kw=quote(keyword), loc=quote(self.location), secs=self.posted_within_hours * 3600)
        if self.easy_apply_only:
            url += "&f_AL=true"
        if self.experience_levels:
            url += "&f_E=" + ",".join(str(x) for x in self.experience_levels)
        if start:
            url += f"&start={start}"
        return url


def _count_hits(text: str, keywords: list[str]) -> int:
    total = 0
    for k in keywords:
        if len(k) <= 4:
            total += len(re.findall(rf"(?<![a-z]){re.escape(k)}(?![a-z])", text))
        else:
            total += text.count(k)
    return total


def choose_resume(cfg: SearchConfig, title: str, description: str) -> tuple[str, str]:
    """Return (message type 'java'|'mern', resume name)."""
    t, d = title.lower(), description.lower()
    if re.search(r"(?<![a-z])java(?![a-z])", t) and "javascript" not in t:
        return "java", cfg.java_name
    java_score = _count_hits(d, cfg.java_keywords)
    mern_score = _count_hits(d, cfg.mern_keywords)
    if java_score > mern_score:
        return "java", cfg.java_name
    return "mern", cfg.mern_name


def title_excluded(cfg: SearchConfig, title: str) -> str | None:
    t = f" {title.lower()} "
    for w in cfg.exclude_title_words:
        if len(w) <= 4:
            if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", t):
                return w
        elif w in t:
            return w
    return None


class JobFinder:
    def __init__(self, settings: Settings, cfg: SearchConfig, dry_run: bool = False):
        self.settings = settings
        self.cfg = cfg
        self.dry_run = dry_run
        self.excel = ExcelManager(settings.paths.excel)
        self.added: list[dict] = []
        self.skipped: dict[str, int] = {}

    @property
    def found_file(self) -> Path:
        return self.settings.paths.excel.parent / "jobs_found.json"

    def _save_found(self, entry: dict) -> None:
        """Keep a JSON record of every job added (title, JD, resume) for Jarvis."""
        data: dict = {}
        if self.found_file.exists():
            try:
                data = json.loads(self.found_file.read_text(encoding="utf-8"))
            except ValueError:
                data = {}
        data[entry["job_id"]] = entry
        self.found_file.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    def _skip(self, reason: str, title: str) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1
        log.info("skip (%s): %s", reason, title[:70])

    # ---------- search ----------
    def _collect_cards(self, browser: BrowserSession, url: str) -> list[dict]:
        browser.goto(url)
        page = browser.page
        if not browser.find(["a[href*='/jobs/view/']"], timeout=15):
            log.info("No results at %s", url)
            return []
        # The results list lazy-loads: scroll it until the count stops growing.
        last = -1
        for _ in range(8):
            cards = page.evaluate(CARDS_JS) or []
            if len(cards) == last:
                break
            last = len(cards)
            page.mouse.move(400, 500)
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(1200)
        return page.evaluate(CARDS_JS) or []

    def _inspect_job(self, browser: BrowserSession, job_url: str) -> dict | None:
        app = JobApplication(browser, self.settings, 0, job_url, "")
        info = app.open_and_inspect()
        page = browser.page
        description = page.evaluate(DESCRIPTION_JS) or ""
        company_link = page.evaluate(COMPANY_LINK_JS) or ""
        return {"title": info.title, "company": info.company, "mode": info.mode,
                "description": description, "company_link": company_link}

    def run(self) -> list[dict]:
        cfg = self.cfg
        if not self.dry_run:
            self.excel.check_writable()
        existing = self.excel.existing_job_ids() if self.settings.paths.excel.exists() else set()
        seen: set[str] = set(existing)
        log.info("Excel already has %d job(s); searching %d keyword(s)", len(existing), len(cfg.keywords))
        d = self.settings.delays

        with BrowserSession(self.settings) as browser:
            browser.ensure_logged_in()
            for keyword in cfg.keywords:
                if len(self.added) >= cfg.max_new_jobs:
                    break
                for page_no in range(cfg.pages_per_keyword):
                    if len(self.added) >= cfg.max_new_jobs:
                        break
                    url = cfg.search_url(keyword, start=page_no * 25)
                    log.info("Search '%s' page %d", keyword, page_no + 1)
                    cards = self._collect_cards(browser, url)
                    log.info("  %d result(s)", len(cards))
                    if not cards:
                        break
                    for card in cards:
                        if len(self.added) >= cfg.max_new_jobs:
                            break
                        jid, title = card["id"], card["title"]
                        if jid in seen:
                            continue
                        seen.add(jid)
                        word = title_excluded(cfg, title)
                        if word:
                            self._skip(f"title has '{word}'", title)
                            continue
                        job_url = f"https://www.linkedin.com/jobs/view/{jid}/"
                        try:
                            info = self._inspect_job(browser, job_url)
                        except (CaptchaDetectedError, LoginRequiredError) as exc:
                            browser.handle_interruption(exc, 0)
                            continue
                        except AgentError as exc:
                            self._skip(f"could not read job ({exc.step})", title)
                            continue
                        if info["mode"] == "applied":
                            self._skip("already applied", title)
                            continue
                        if info["mode"] != "easy_apply":
                            self._skip(f"not Easy Apply ({info['mode']})", title)
                            continue
                        if not info["company_link"]:
                            self._skip("no company link", title)
                            continue
                        desc_l = info["description"].lower()
                        if cfg.require_any_in_description and not any(k in desc_l for k in cfg.require_any_in_description):
                            self._skip("description not relevant", title)
                            continue
                        mtype, resume = choose_resume(cfg, info["title"] or title, info["description"])
                        msgs = cfg.messages.get(mtype) or {}
                        from src.excel_manager import looks_like_placeholder

                        if any(not (msgs.get(k) or "").strip() or looks_like_placeholder(msgs.get(k) or "") for k in ("hr", "developer")):
                            self._skip(f"{mtype} messages not configured (placeholder) - fix agent1/config/search.yaml", title)
                            continue
                        row = {
                            "job_link": job_url,
                            "resume_name": resume,
                            "company_link": info["company_link"],
                            f"hr_message_{mtype}": (msgs.get("hr") or "").strip(),
                            f"developer_message_{mtype}": (msgs.get("developer") or "").strip(),
                        }
                        entry = {
                            "job_id": jid,
                            "job_link": job_url,
                            "title": info["title"] or title,
                            "company": info["company"] or card["company"],
                            "company_link": info["company_link"],
                            "location": card.get("location", ""),
                            "resume_name": resume,
                            "type": mtype,
                            "description": info["description"][:2000],
                            "found_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        if self.dry_run:
                            log.info("DRY RUN would add: %s @ %s -> %s", entry["title"], entry["company"], resume)
                        else:
                            entry["excel_row"] = self.excel.append_row(row)
                            log.info("Added row %d: %s @ %s -> %s", entry["excel_row"], entry["title"], entry["company"], resume)
                            self._save_found(entry)
                        self.added.append(entry)
                        random_sleep(d.between_actions_min, d.between_actions_max, "between jobs")
        return self.added
