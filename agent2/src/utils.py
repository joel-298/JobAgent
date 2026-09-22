"""Small helpers shared across modules."""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime
from urllib.parse import quote, urlparse, urlunparse

log = logging.getLogger("agent")

FILE_EXT_RE = re.compile(r"\.(pdf|docx?|txt)(?![a-z])", re.IGNORECASE)


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def random_sleep(lo: float, hi: float, reason: str = "") -> None:
    """Sleep a random duration inside [lo, hi] so the UI has time to settle."""
    if hi <= 0:
        return
    seconds = random.uniform(lo, hi)
    if reason:
        log.debug("Waiting %.1fs (%s)", seconds, reason)
    time.sleep(seconds)


def normalize_text(text: str | None) -> str:
    """Lowercase, collapse whitespace, strip a trailing file extension."""
    if not text:
        return ""
    t = re.sub(r"\s+", " ", str(text)).strip().lower()
    t = re.sub(r"\.(pdf|docx?|txt)$", "", t)
    return t


def resume_matches(requested: str, candidate: str) -> bool:
    """Confident match between the Excel resume_name and a visible resume label.

    Exact match after normalisation, or one being a prefix of the other
    (handles 'Java Developer Resume' vs 'Java Developer Resume.pdf' vs
    'Java Developer'). Anything looser is deliberately rejected.
    """
    r, c = normalize_text(requested), normalize_text(candidate)
    if not r or not c:
        return False
    return r == c or c.startswith(r) or r.startswith(c)


def pick_resume(requested: str, candidates: list[str]) -> tuple[int | None, str]:
    """Choose the index of the one resume that confidently matches `requested`.

    Order of confidence: exact (after normalisation) -> prefix either way ->
    unique case-insensitive substring. Returns (index, reason) or
    (None, reason) when nothing matches or the match is ambiguous.
    """
    r = normalize_text(requested)
    norm = [normalize_text(c) for c in candidates]
    if not r:
        return None, "empty resume_name"
    exact = [i for i, c in enumerate(norm) if c == r]
    if len(exact) == 1:
        return exact[0], "exact"
    prefix = [i for i, c in enumerate(norm) if c and (c.startswith(r) or r.startswith(c))]
    if len(prefix) == 1:
        return prefix[0], "prefix"
    sub = [i for i, c in enumerate(norm) if r in c]
    if len(sub) == 1:
        return sub[0], "substring"
    if len(exact) > 1 or len(prefix) > 1 or len(sub) > 1:
        return None, "ambiguous"
    return None, "no match"


def contains_any(text: str, keywords: list[str]) -> bool:
    t = f" {normalize_text(text)} "
    return any(k.lower() in t for k in keywords if k)


def is_linkedin_url(url: str, path_part: str = "") -> bool:
    try:
        p = urlparse(str(url).strip())
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc.lower().endswith("linkedin.com"):
        return False
    return path_part in p.path if path_part else True


def clean_profile_url(url: str) -> str:
    """Canonical profile URL: https://www.linkedin.com/in/<slug> (no query/fragment)."""
    p = urlparse(url)
    path = p.path.rstrip("/")
    return urlunparse(("https", "www.linkedin.com", path, "", "", ""))


def company_people_url(company_link: str, keywords: str = "") -> str:
    """Build https://www.linkedin.com/company/<slug>/people/?keywords=..."""
    p = urlparse(company_link.strip())
    base = p.path.rstrip("/")
    for suffix in ("/people", "/about", "/posts", "/jobs", "/life"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    url = f"https://www.linkedin.com{base}/people/"
    if keywords:
        url += f"?keywords={quote(keywords)}"
    return url


def safe_filename(text: str, max_len: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)[:max_len].strip("_") or "item"


def screenshot_name(excel_row: int, tag: str) -> str:
    return f"row_{excel_row:03d}_{safe_filename(tag)}.png"


def print_status_block(**fields) -> None:
    """Print the visible terminal status block described in the spec."""
    print()
    print("-" * 50)
    for k, v in fields.items():
        print(f"{k}: {v}")
    print("-" * 50)
    print()
