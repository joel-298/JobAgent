"""Configuration loading: paths, .env and config/settings.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")


def _path(env_name: str, default: str) -> Path:
    value = os.getenv(env_name, default)
    p = Path(value)
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass
class Paths:
    root: Path = PROJECT_ROOT
    excel: Path = field(default_factory=lambda: _path("JOBS_EXCEL", "data/jobs.xlsx"))
    settings: Path = field(default_factory=lambda: _path("SETTINGS_FILE", "config/settings.yaml"))
    browser_profile: Path = field(default_factory=lambda: _path("BROWSER_PROFILE_DIR", "browser_profile"))
    db: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "agent.db")
    logs: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    screenshots: Path = field(default_factory=lambda: PROJECT_ROOT / "screenshots")

    def ensure_dirs(self) -> None:
        for d in (self.excel.parent, self.db.parent, self.logs, self.screenshots, self.browser_profile):
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class NetworkingConfig:
    hr_min: int = 2
    hr_max: int = 2
    developer_min: int = 2
    developer_max: int = 2
    max_search_pages: int = 3
    send_without_note_if_unavailable: bool = False
    hr_search_terms: list[str] = field(default_factory=lambda: ["Recruiter", "Talent Acquisition"])
    hr_title_keywords: list[str] = field(default_factory=lambda: ["recruit", "talent", "human resources"])
    developer_search_terms: list[str] = field(default_factory=lambda: ["Software Engineer"])
    developer_title_keywords: list[str] = field(default_factory=lambda: ["engineer", "developer"])
    developer_exclude_keywords: list[str] = field(default_factory=lambda: ["recruit", "talent"])
    developer_priority_keywords: list[str] = field(default_factory=lambda: ["software engineer", "software developer", "developer", "engineer"])


@dataclass
class ApplicationConfig:
    external_apply: str = "pause"  # pause | skip
    answers: dict[str, str] = field(default_factory=dict)


@dataclass
class DelayConfig:
    between_profiles_min: float = 20
    between_profiles_max: float = 60
    between_actions_min: float = 2
    between_actions_max: float = 8
    between_companies_min: float = 120
    between_companies_max: float = 300
    page_timeout: float = 30


@dataclass
class BrowserConfig:
    channel: str = "chromium"
    headless: bool = False
    slow_mo_ms: int = 50
    viewport_width: int = 1366
    viewport_height: int = 850


@dataclass
class RunConfig:
    retry_failed: str = "skip"  # retry | skip
    resume_paused: str = "ask"  # ask | yes | no
    max_consecutive_failures: int = 2


@dataclass
class Settings:
    networking: NetworkingConfig = field(default_factory=NetworkingConfig)
    application: ApplicationConfig = field(default_factory=ApplicationConfig)
    delays: DelayConfig = field(default_factory=DelayConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    run: RunConfig = field(default_factory=RunConfig)
    paths: Paths = field(default_factory=Paths)

    def validate(self) -> list[str]:
        """Return a list of human-readable problems (empty list = valid)."""
        problems: list[str] = []
        n, d = self.networking, self.delays
        if n.hr_min < 0 or n.hr_max < n.hr_min:
            problems.append("networking.hr_min/hr_max must satisfy 0 <= min <= max")
        if n.developer_min < 0 or n.developer_max < n.developer_min:
            problems.append("networking.developer_min/developer_max must satisfy 0 <= min <= max")
        for lo, hi in (
            ("between_profiles_min", "between_profiles_max"),
            ("between_actions_min", "between_actions_max"),
            ("between_companies_min", "between_companies_max"),
        ):
            if getattr(d, lo) < 0 or getattr(d, hi) < getattr(d, lo):
                problems.append(f"delays.{lo}/{hi} must satisfy 0 <= min <= max")
        if self.application.external_apply not in ("pause", "skip"):
            problems.append("application.external_apply must be 'pause' or 'skip'")
        if self.run.retry_failed not in ("retry", "skip"):
            problems.append("run.retry_failed must be 'retry' or 'skip'")
        if self.run.resume_paused not in ("ask", "yes", "no"):
            problems.append("run.resume_paused must be 'ask', 'yes' or 'no'")
        if self.browser.channel not in ("chromium", "chrome", "msedge"):
            problems.append("browser.channel must be 'chromium', 'chrome' or 'msedge'")
        return problems


def _fill(dc_type, data: dict | None):
    """Build a dataclass from a dict, ignoring unknown keys."""
    data = data or {}
    known = {f.name for f in dc_type.__dataclass_fields__.values()}
    return dc_type(**{k: v for k, v in data.items() if k in known})


def load_settings(settings_file: Path | None = None) -> Settings:
    paths = Paths()
    file = settings_file or paths.settings
    raw: dict = {}
    if file.exists():
        with open(file, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    settings = Settings(
        networking=_fill(NetworkingConfig, raw.get("networking")),
        application=_fill(ApplicationConfig, raw.get("application")),
        delays=_fill(DelayConfig, raw.get("delays")),
        browser=_fill(BrowserConfig, raw.get("browser")),
        run=_fill(RunConfig, raw.get("run")),
        paths=paths,
    )
    if settings.application.answers is None:
        settings.application.answers = {}
    problems = settings.validate()
    if problems:
        raise ValueError("Invalid settings:\n  - " + "\n  - ".join(problems))
    return settings
