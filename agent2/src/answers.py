"""Answer resolution for Easy Apply questions, driven by config/answers.yaml.

resolve(question, kind, options) -> answer string or None. Only questions
covered by the profile are answered; everything else is left for the user.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger("agent")

EXPERIENCE_WORDS = ("experience", "years", "how long", "worked with", "proficien")
LOCATION_WORDS = ("currently located", "current location", "where are you located", "where do you live", "your location", "city", "based in", "reside")
RELOCATE_WORDS = ("relocat", "willing to move", "open to moving", "work from office", "work from the office", "onsite", "on-site", "hybrid", "commute")
SALARY_WORDS = ("salary", "ctc", "compensation", "package", "pay ", "remuneration", "lpa", "lakh")
EXPECT_WORDS = ("expect", "desired", "looking for", "ask")
NOTICE_WORDS = ("notice period", "notice", "joining", "join ", "start date", "how soon", "when can you", "availability", "available to start", "immediate")
NOTICE_OPTION_PREFERENCE = ("immediate", "0 day", "0", "less than 15", "less than 2 week", "within 15", "15 days", "less than 30", "within 30", "30 days", "1 month")
YES_NO = {"yes", "no"}

# (question substrings, section, key) - checked in order, first hit wins.
FIELD_RULES = [
    (("first name", "given name"), "personal", "first_name"),
    (("last name", "surname", "family name"), "personal", "last_name"),
    (("full name", "your name", "candidate name", "name"), "personal", "full_name"),
    (("email",), "personal", "email"),
    (("country code",), "personal", "phone_country_code"),
    (("phone", "mobile", "contact number", "whatsapp"), "personal", "phone"),
    (("linkedin",), "personal", "linkedin"),
    (("github",), "personal", "github"),
    (("portfolio", "website", "personal site"), "personal", "portfolio"),
    (("pin code", "pincode", "postal", "zip"), "personal", "pincode"),
    (("date of birth", "dob", "birth date"), "personal", "date_of_birth"),
    (("gender", "sex"), "personal", "gender"),
    (("current company", "current employer", "employer", "organisation", "organization", "company name", "last company", "previous company", "where do you work"), "work", "current_company"),
    (("current title", "job title", "designation", "current role", "current position", "position held"), "work", "current_title"),
    (("employment type",), "work", "employment_type"),
    (("currently employed", "currently working"), "work", "currently_employed"),
    (("cgpa", "gpa"), "education", "cgpa"),
    (("12th", "xii", "intermediate", "higher secondary"), "education", "percentage_12th"),
    (("10th", "matric", "secondary school"), "education", "percentage_10th"),
    (("graduation year", "year of graduation", "passing year", "year of passing", "completion year", "graduate in", "graduated"), "education", "graduation_year"),
    (("field of study", "major", "specialization", "specialisation", "stream", "branch", "discipline"), "education", "field_of_study"),
    (("university", "college", "institute", "institution", "school name"), "education", "university"),
    (("degree", "qualification", "education level", "level of education", "highest education", "education"), "education", "highest_degree"),
    (("state",), "personal", "state"),
    (("country",), "personal", "country"),
]
SUMMARY_WORDS = ("about yourself", "tell us about", "why should we hire", "why do you want", "cover letter", "summary", "introduce yourself", "why are you", "describe your experience", "message to the hiring", "additional information", "anything else")


@dataclass
class AnswerProfile:
    experience_years_with_tech: str = "1"
    total_experience_years: str = "1"
    location: str = ""
    willing_to_relocate: str = "Yes"
    current_salary_per_year: int = 0
    expected_salary_per_year: int = 0
    notice_period: str = "Immediate joiner"
    notice_period_days: str = "0"
    yes_to: list[str] = field(default_factory=list)
    tech_keywords: list[str] = field(default_factory=list)
    extra_rules: list[dict] = field(default_factory=list)
    personal: dict = field(default_factory=dict)
    work: dict = field(default_factory=dict)
    education: dict = field(default_factory=dict)
    summary: str = ""
    resume_text: str = ""
    ai_fallback: bool = False

    @classmethod
    def load(cls, path: Path, extra_simple_rules: dict | None = None) -> "AnswerProfile":
        raw: dict = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        prof = raw.get("profile") or {}
        rules = list(raw.get("extra_rules") or [])
        for k, v in (extra_simple_rules or {}).items():  # settings.yaml application.answers
            rules.append({"match": [k], "answer": str(v)})
        return cls(
            experience_years_with_tech=str(prof.get("experience_years_with_tech", "1")),
            total_experience_years=str(prof.get("total_experience_years", "1")),
            location=str(prof.get("location", "") or ""),
            willing_to_relocate=str(prof.get("willing_to_relocate", "Yes")),
            current_salary_per_year=int(prof.get("current_salary_per_year", 0) or 0),
            expected_salary_per_year=int(prof.get("expected_salary_per_year", 0) or 0),
            notice_period=str(prof.get("notice_period", "Immediate joiner") or ""),
            notice_period_days=str(prof.get("notice_period_days", 0)),
            yes_to=[str(x).lower() for x in (prof.get("yes_to") or [])],
            tech_keywords=[str(x) for x in (raw.get("tech_keywords") or [])],
            extra_rules=rules,
            personal={k: str(v) for k, v in (raw.get("personal") or {}).items() if v not in (None, "")},
            work={k: str(v) for k, v in (raw.get("work") or {}).items() if v not in (None, "")},
            education={k: str(v) for k, v in (raw.get("education") or {}).items() if v not in (None, "")},
            summary=str(raw.get("summary") or "").strip(),
            resume_text=str(raw.get("resume_text") or "").strip(),
            ai_fallback=bool(raw.get("ai_fallback", False)),
        )

    # ---------- helpers ----------
    def _mentions_tech(self, q: str) -> bool:
        for kw in self.tech_keywords:
            k = kw.lower()
            if len(k) <= 4:  # short tokens (java, css, api, git) must be whole words
                if re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", q):
                    return True
            elif k in q:
                return True
        return False

    @staticmethod
    def _salary_value(q: str, per_year: int, kind: str) -> str:
        """Always digits: LinkedIn validates salary fields as numbers."""
        if per_year <= 0:
            return ""
        if "lpa" in q or "lakh" in q or "lac" in q:
            return f"{per_year / 100000:g}"
        if "month" in q:
            return str(round(per_year / 12))
        return str(per_year)

    @staticmethod
    def _pick_option(answer: str, options: list[str]) -> str | None:
        """Match an answer to a dropdown/radio option label."""
        if not options:
            return answer
        a = answer.strip().lower()
        for o in options:
            if o.strip().lower() == a:
                return o
        for o in options:
            if a and (a in o.lower() or o.lower() in a) and "select" not in o.lower():
                return o
        # abbreviation segments, e.g. option "B.Tech/B.E." vs answer "...(B.E.)"
        a_compact = re.sub(r"[^a-z0-9]", "", a)
        for o in options:
            for seg in re.split(r"[/,]| or ", o.lower()):
                seg_c = re.sub(r"[^a-z0-9]", "", seg)
                if len(seg_c) >= 2 and "." in seg and seg_c in a_compact:
                    return o
        # word overlap, e.g. "Bachelor of Engineering (B.E.)" -> "Bachelor's Degree"
        words = {w for w in re.findall(r"[a-z]{4,}", a)}
        best, best_n = None, 0
        for o in options:
            if "select" in o.lower():
                continue
            n = len(words & set(re.findall(r"[a-z]{4,}", o.lower())))
            if n > best_n:
                best, best_n = o, n
        return best

    # ---------- main ----------
    def resolve(self, question: str, kind: str = "text", options: list[str] | None = None, force_numeric: bool = False) -> str | None:
        """kind: text | number | select | radio | checkbox. options: visible choices.
        force_numeric: the form rejected a text answer -> return digits only."""
        if force_numeric and kind in ("text", "number"):
            kind = "number"
        q = re.sub(r"\s+", " ", (question or "")).strip().lower()
        if not q:
            return None
        options = options or []
        answer: str | None = None

        for rule in self.extra_rules:
            keys = rule.get("match") or []
            if any(str(k).lower() in q for k in keys):
                answer = str(rule.get("answer", ""))
                break

        if answer is None:
            for words, section, key in FIELD_RULES:
                if any(w in q for w in words):
                    # "name" alone is too generic - require a name-like question
                    if key == "full_name" and not re.search(r"\bname\b", q):
                        continue
                    if key in ("state", "country") and any(w in q for w in ("relocat", "authori", "eligib")):
                        continue
                    value = getattr(self, section).get(key)
                    if value:
                        answer = value
                    break

        if answer is None and any(w in q for w in SUMMARY_WORDS) and self.summary and kind == "text":
            answer = self.summary

        if answer is None and any(w in q for w in NOTICE_WORDS) and self.notice_period:
            if kind in ("select", "radio"):
                low = [o.lower() for o in options]
                for pref in NOTICE_OPTION_PREFERENCE:
                    hit = next((o for o, l in zip(options, low) if pref in l and "select" not in l), None)
                    if hit:
                        return hit
                if set(low) & YES_NO:
                    return next(o for o in options if o.lower() == "yes")
                answer = self.notice_period
            elif kind == "number" or re.search(r"days?|number of|how many|how long|\(in ", q):
                return self.notice_period_days  # numeric field: "0"
            else:
                answer = self.notice_period

        if answer is None and any(w in q for w in SALARY_WORDS):
            expected = any(w in q for w in EXPECT_WORDS)
            per_year = self.expected_salary_per_year if expected else self.current_salary_per_year
            answer = self._salary_value(q, per_year, kind) or None

        if answer is None and any(w in q for w in EXPERIENCE_WORDS) and ("year" in q or "experience" in q):
            answer = self.experience_years_with_tech if self._mentions_tech(q) else self.total_experience_years

        if answer is None and any(w in q for w in RELOCATE_WORDS):
            answer = self.willing_to_relocate

        if answer is None and any(w in q for w in LOCATION_WORDS) and self.location:
            answer = self.location

        if answer is None and options and {o.strip().lower() for o in options} & YES_NO:
            if any(w in q for w in self.yes_to):
                answer = "Yes"

        if not answer:
            return None
        if kind in ("select", "radio"):
            picked = self._pick_option(answer, options)
            if picked is None:
                log.info("Answer '%s' has no matching option in %s for '%s'", answer, options, question[:60])
                return None
            return picked
        if kind == "number" or re.search(r"\(in (days|years|months|lpa|lakhs|inr|rs|numbers?)\)|in days|number of|how many", q):
            m = re.search(r"\d+(\.\d+)?", answer)
            return m.group(0) if m else (answer if kind != "number" else None)
        return answer
