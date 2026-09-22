"""LinkedIn job application through the normal Easy Apply UI.

Rules implemented here (see spec sections 9-12):
  * only the resume named in Excel is ever selected - never a different one
  * only fields explicitly configured in settings.yaml `application.answers`
    are filled; anything unknown and required pauses for the user
  * submit only when the modal reaches the recognised review/submit state
  * CAPTCHA / verification -> stop and wait for the user
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from playwright.sync_api import Locator

from config import Settings
from src import selectors as S
from src import state_manager as sm
from src.browser import BrowserSession
from src.exceptions import (
    ApplicationFailedError,
    JobClosedError,
    ResumeNotFoundError,
    UnexpectedPageError,
    UnknownUIError,
)
from src.ai_answers import AIAnswerer
from src.answers import AnswerProfile
from src.human_intervention import request_intervention
from src.utils import FILE_EXT_RE, normalize_text, pick_resume

log = logging.getLogger("agent")

MAX_FORM_STEPS = 15
MAX_QUESTION_INTERVENTIONS = 3


@dataclass
class JobInfo:
    title: str = ""
    company: str = ""
    mode: str = "unknown"  # easy_apply | external | applied | closed | unknown


class JobApplication:
    def __init__(self, browser: BrowserSession, settings: Settings, excel_row: int, job_link: str, resume_name: str):
        self.b = browser
        self.settings = settings
        self.excel_row = excel_row
        self.job_link = job_link
        self.resume_name = resume_name
        self.answers = AnswerProfile.load(
            settings.paths.root / "config" / "answers.yaml", settings.application.answers
        )
        self.ai = AIAnswerer(self.answers.resume_text) if self.answers.ai_fallback else None

    # ---------- inspection ----------
    def open_and_inspect(self) -> JobInfo:
        self.b.goto(self.job_link)
        url = self.b.url.lower()
        if not any(m in url for m in S.JOB_PAGE_URL_MARKERS):
            raise UnexpectedPageError(f"Not recognised as a LinkedIn job page: {self.b.url}", "APPLICATION")
        info = JobInfo()
        # Wait for something actionable to render, then read the title from
        # document.title ("<Job> | <Company> | LinkedIn") - the 2026 page has no h1.
        self.b.find(S.EASY_APPLY_BUTTON + S.EXTERNAL_APPLY_BUTTON + S.ALREADY_APPLIED_MARKERS + S.JOB_TITLE, timeout=15)
        parts = [x.strip() for x in (self.b.page.title() or "").split("|")]
        if len(parts) >= 2 and parts[-1].lower() == "linkedin":
            info.title = parts[0]
            info.company = parts[1] if len(parts) >= 3 else ""
        info.title = info.title or self.b.text_of(S.JOB_TITLE)
        info.company = info.company or self.b.text_of(S.JOB_COMPANY_NAME)
        if not info.title:
            raise UnexpectedPageError("Job page loaded but no job title was found", "APPLICATION")
        if self.b.exists(S.ALREADY_APPLIED_MARKERS):
            info.mode = "applied"
        elif self.b.exists(S.JOB_CLOSED_MARKERS):
            info.mode = "closed"
        elif self.b.exists(S.EASY_APPLY_BUTTON):
            info.mode = "easy_apply"
        elif self.b.exists(S.EXTERNAL_APPLY_BUTTON):
            info.mode = "external"
        log.info("Job: %s @ %s (%s)", info.title, info.company, info.mode)
        return info

    # ---------- main flow ----------
    def apply(self, dry_run: bool = False) -> str:
        """Return an application_status constant."""
        info = self.open_and_inspect()
        if info.mode == "applied":
            log.info("Already applied to this job - skipping application")
            return sm.APP_ALREADY_APPLIED
        if info.mode == "closed":
            raise JobClosedError("Job is no longer accepting applications")
        if info.mode == "external":
            return self._handle_external(dry_run)
        if info.mode != "easy_apply":
            self.b.screenshot(self.excel_row, "application_error")
            raise UnknownUIError("No Easy Apply / Apply button recognised on the job page", "APPLICATION")

        if dry_run:
            log.info("DRY RUN: would click Easy Apply and select resume '%s'", self.resume_name)
            return self._dry_run_walk()

        if not self.b.click(S.EASY_APPLY_BUTTON):
            raise UnknownUIError("Easy Apply button disappeared before it could be clicked", "APPLICATION")
        modal = self._wait_modal()
        log.info("Application form detected")
        return self._walk_form(modal, submit=True)

    def _handle_external(self, dry_run: bool) -> str:
        mode = self.settings.application.external_apply
        if dry_run:
            log.info("DRY RUN: job uses external apply; config says '%s'", mode)
            return sm.APP_DRY_RUN
        if mode == "skip":
            log.info("External application - skipping per configuration")
            return sm.APP_SKIPPED_EXTERNAL
        shot = self.b.screenshot(self.excel_row, "external_apply")
        request_intervention(
            "This job does not use Easy Apply (external application site).",
            shot,
            "Complete the application manually in the browser (or skip it),\n"
            "then press ENTER to continue with networking for this company.",
        )
        return sm.APP_MANUAL

    # ---------- modal handling ----------
    def _wait_modal(self) -> Locator:
        modal = self.b.find(S.APPLY_MODAL, timeout=15)
        if not modal:
            self.b.screenshot(self.excel_row, "application_error")
            raise UnknownUIError("Easy Apply modal did not open", "APPLICATION")
        # The dialog appears before its content finishes loading: wait until an
        # action button is rendered, then give the sections a moment to settle.
        self.b.find(S.APPLY_SUBMIT + S.APPLY_NEXT + S.APPLY_REVIEW, modal, timeout=15)
        self.b.settle()
        return modal

    def _modal(self) -> Locator | None:
        return self.b.find(S.APPLY_MODAL)

    def _heading(self, modal: Locator) -> str:
        return normalize_text(self.b.text_of(S.APPLY_MODAL_HEADING, modal))

    def _dry_run_walk(self) -> str:
        """Open the modal, walk up to the review step without submitting, discard."""
        if not self.b.click(S.EASY_APPLY_BUTTON):
            return sm.APP_DRY_RUN
        try:
            modal = self._wait_modal()
            self._walk_form(modal, submit=False)
        finally:
            self._discard()
        return sm.APP_DRY_RUN

    def _walk_form(self, modal: Locator, submit: bool) -> str:
        interventions = 0
        resume_done = False
        for step in range(MAX_FORM_STEPS):
            self.b.check_page_state()
            modal = self._modal() or modal
            heading = self._heading(modal)
            log.info("Form step %d: %s", step + 1, heading or "(no heading)")

            if not resume_done and self._is_resume_step(modal, heading):
                self._select_resume(modal)
                resume_done = True

            self._fill_configured_fields(modal)

            if self.b.find(S.APPLY_SUBMIT, modal):
                if not resume_done:
                    # Some flows have no separate resume step (resume pre-attached).
                    log.warning("Reached submit without a resume step; checking resume cards on this screen")
                    if self._is_resume_step(modal, "resume"):
                        self._select_resume(modal)
                    else:
                        raise ResumeNotFoundError(
                            f"Could not find a resume selection step to choose '{self.resume_name}'"
                        )
                if not submit:
                    log.info("DRY RUN: reached the submit step - not submitting")
                    return sm.APP_DRY_RUN
                return self._submit(modal)

            clicked = self.b.click(S.APPLY_REVIEW, modal, timeout=2) or self.b.click(S.APPLY_NEXT, modal, timeout=2)
            if not clicked:
                self.b.screenshot(self.excel_row, "application_error")
                raise UnknownUIError("Neither Next, Review nor Submit was found in the application form", "APPLICATION")

            self.b.short_pause()
            errors = self._form_errors()
            for _repair_round in range(2):
                if not errors:
                    break
                modal = self._modal() or modal
                changed = self._repair_invalid(modal)
                if self.ai:
                    self._fill_configured_fields(modal, use_ai_for_all=True)
                if not changed and not self.ai:
                    break
                if self.b.click(S.APPLY_REVIEW, modal, timeout=2) or self.b.click(S.APPLY_NEXT, modal, timeout=2):
                    self.b.short_pause()
                    errors = self._form_errors()
                else:
                    break
            if errors:
                interventions += 1
                if interventions > MAX_QUESTION_INTERVENTIONS:
                    raise ApplicationFailedError("Form still has unanswered questions after repeated attempts")
                questions = self._visible_questions(self._modal() or modal)
                shot = self.b.screenshot(self.excel_row, "application_question")
                log.warning("Unanswered application question(s): %s | errors: %s", questions, errors)
                request_intervention(
                    "The application form has question(s) the agent is not configured to answer:\n  "
                    + "\n  ".join(questions or errors),
                    shot,
                    "Answer the highlighted question(s) in the browser. Do NOT click Submit.\n"
                    "Then press ENTER and the agent will continue the form.",
                )
        raise ApplicationFailedError(f"Application form did not finish within {MAX_FORM_STEPS} steps")

    def _submit(self, modal: Locator) -> str:
        for attempt in range(MAX_QUESTION_INTERVENTIONS + 1):
            log.info("Submitting application")
            if not self.b.click(S.APPLY_SUBMIT, modal):
                raise UnknownUIError("Submit button vanished", "APPLICATION")
            self.b.settle()
            if self.b.find(S.APPLY_SUCCESS, timeout=10):
                log.info("Application submitted")
                self.b.click(S.APPLY_DISMISS, timeout=3)
                return sm.APP_COMPLETED
            errors = self._form_errors()
            if errors and attempt < 2:
                modal = self._modal() or modal
                self._repair_invalid(modal)
                if self.ai:
                    self._fill_configured_fields(modal, use_ai_for_all=True)
                continue  # retry submit with repaired answers
            if not self._modal():
                # Dialog closed without an error: confirm via the job page.
                if self.b.exists(S.ALREADY_APPLIED_MARKERS):
                    log.info("Application submitted (confirmed by job page state)")
                    return sm.APP_COMPLETED
                self.b.page.reload()
                self.b.settle()
                if self.b.exists(S.ALREADY_APPLIED_MARKERS):
                    log.info("Application submitted (confirmed after reload)")
                    return sm.APP_COMPLETED
                self.b.screenshot(self.excel_row, "application_submit_unconfirmed")
                raise ApplicationFailedError("Submit clicked and dialog closed, but the job page does not show 'Applied'")
            if not errors or attempt == MAX_QUESTION_INTERVENTIONS:
                self.b.screenshot(self.excel_row, "application_submit_error")
                raise ApplicationFailedError(
                    "Submit clicked but no confirmation was seen" + (f": {errors}" if errors else "")
                )
            modal = self._modal() or modal
            questions = self._visible_questions(modal)
            shot = self.b.screenshot(self.excel_row, "application_question")
            log.warning("Form rejected submit - unanswered question(s): %s | errors: %s", questions, errors)
            request_intervention(
                "The application form has question(s) the agent is not configured to answer:\n  "
                + "\n  ".join(questions or errors),
                shot,
                "Answer the highlighted question(s) in the browser. Do NOT click Submit.\n"
                "Then press ENTER and the agent will submit.",
            )
        raise ApplicationFailedError("Application could not be submitted")

    def _discard(self) -> None:
        try:
            if self._modal():
                if not self.b.click(S.APPLY_DISMISS, timeout=3):
                    self.b.page.keyboard.press("Escape")
                    self.b.short_pause()
                self.b.click(S.APPLY_DISCARD, timeout=3)
        except Exception as exc:  # noqa: BLE001
            log.debug("Discard failed: %s", exc)

    # ---------- resume ----------
    def _is_resume_step(self, modal: Locator, heading: str) -> bool:
        if any(m in heading for m in S.RESUME_STEP_MARKERS):
            return True
        return bool(self._resume_cards(modal))

    def _card_name(self, card: Locator) -> str:
        name = self.b.text_of(S.RESUME_CARD_NAME, card)
        if name and FILE_EXT_RE.search(name):
            return name.strip()
        lines = [ln.strip() for ln in (card.inner_text(timeout=2000) or "").splitlines() if ln.strip()]
        for ln in lines:  # prefer the line that looks like a file name
            if FILE_EXT_RE.search(ln):
                return ln
        return (name or (lines[0] if lines else "")).strip()

    def _resume_cards(self, modal: Locator) -> list[tuple[str, Locator]]:
        cards: list[tuple[str, Locator]] = []
        # 2026 UI: the radio itself carries the file name in aria-label.
        for radio in self.b.find_all(S.RESUME_RADIO_LABELLED, modal):
            try:
                name = (radio.get_attribute("aria-label") or "").strip()
                if name and FILE_EXT_RE.search(name):
                    cards.append((name, radio))
            except Exception as exc:  # noqa: BLE001
                log.debug("Labelled radio read failed: %s", exc)
        if cards:
            return cards
        for card in self.b.find_all(S.RESUME_CARDS, modal):
            try:
                cards.append((self._card_name(card), card))
            except Exception as exc:  # noqa: BLE001
                log.debug("Resume card read failed: %s", exc)
        if cards:
            return cards
        # Fallback: discover cards from the radio controls (current LinkedIn UI:
        # "<PDF badge> <file name> <date> <download> <radio>").
        seen: set[str] = set()
        for radio in self.b.find_all(S.RESUME_RADIOS, modal):
            try:
                card = radio.locator(S.RESUME_CARD_FROM_RADIO_XPATH).first
                if not card.count():
                    continue
                name = self._card_name(card)
                if not name or name in seen:
                    continue
                seen.add(name)
                cards.append((name, card))
            except Exception as exc:  # noqa: BLE001
                log.debug("Radio-based resume card read failed: %s", exc)
        return cards

    def _card_selected(self, card: Locator) -> bool:
        try:
            cls = (card.get_attribute("class") or "").lower()
            if "selected" in cls:
                return True
            radio = card.locator("input[type='radio']").first
            if radio.count() and radio.is_checked():
                return True
            if (card.get_attribute("aria-checked") or "").lower() == "true":
                return True
            if card.locator("[aria-checked='true'], .artdeco-button--selected, input:checked, [class*='selected']").count():
                return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _select_resume(self, modal: Locator) -> None:
        # Resume controls can render a little after the rest of the form.
        self.b.find(S.RESUME_RADIO_LABELLED + S.RESUME_CARDS + S.RESUME_RADIOS, modal, timeout=10)
        for attempt in range(2):
            cards = self._resume_cards(modal)
            names = [n for n, _ in cards]
            log.info("Resumes visible: %s", names or "none")
            idx, reason = pick_resume(self.resume_name, names)
            if idx is None and reason == "ambiguous":
                self.b.screenshot(self.excel_row, "resume_ambiguous")
                raise ResumeNotFoundError(
                    f"Resume '{self.resume_name}' is ambiguous - several visible resumes match: {names}"
                )
            if idx is not None:
                name, card = cards[idx]
                log.info("Resume match (%s): '%s' -> '%s'", reason, self.resume_name, name)
                if not self._card_selected(card):
                    if not self.b.click(S.RESUME_CARD_SELECT_BUTTON, card, timeout=3):
                        card.click()
                        self.b.short_pause()
                    if not self._card_selected(card):
                        log.warning("Could not confirm the resume card became selected; re-checking")
                        self.b.short_pause()
                        if not self._card_selected(card):
                            self.b.screenshot(self.excel_row, "resume_select_error")
                            raise ResumeNotFoundError(f"Clicked resume '{name}' but it did not become selected")
                log.info("Resume selected: %s", name)
                return
            if attempt == 0 and self.b.click(S.RESUME_SHOW_MORE, modal, timeout=2):
                continue
            break
        self.b.screenshot(self.excel_row, "resume_not_found")
        raise ResumeNotFoundError(
            f"Resume '{self.resume_name}' not found. Visible resumes: {names or 'none'}"
        )

    # ---------- configured fields ----------
    def _read_fields(self, modal: Locator) -> list[dict]:
        try:
            return modal.evaluate(S.FORM_FIELDS_JS) or []
        except Exception as exc:  # noqa: BLE001
            log.debug("Field extraction failed: %s", exc)
            return []

    def _fill_configured_fields(self, modal: Locator, use_ai_for_all: bool = False) -> None:
        """Fill empty fields: profile rules first, then the AI fallback for
        required fields (or every empty field when use_ai_for_all, i.e. after
        LinkedIn rejected the submit)."""
        for f in self._read_fields(modal):
            label = (f.get("label") or "").strip()
            if not label:
                continue
            value = (f.get("value") or "").strip()
            kind = f.get("kind", "text")
            if value and not (kind == "select" and value.lower().startswith("select")):
                continue  # keep LinkedIn's / the user's existing value
            answer = self.answers.resolve(label, kind, f.get("options") or [])
            if answer is None and self.ai and (f.get("required") or use_ai_for_all):
                answer = self.ai.answer(label, kind, f.get("options") or [])
            if answer is None:
                continue
            try:
                if self._fill_field(modal, f, answer):
                    log.info("Filled '%s' -> '%s'", label[:60], answer)
            except Exception as exc:  # noqa: BLE001
                log.warning("Could not fill '%s': %s", label[:60], exc)

    def _fill_field(self, modal: Locator, f: dict, answer: str, clear: bool = False) -> bool:
        el = modal.locator(S.FORM_FIELD_BY_IDX.format(idx=f["idx"])).first
        kind = f.get("kind")
        if kind in ("text", "number"):
            maxlen = int(f.get("maxlen") or 0)
            if maxlen and len(answer) > maxlen:
                answer = answer[:maxlen].rstrip()
            el.click()
            if clear:
                el.fill("")
            el.fill(answer)
            self.b.short_pause()
            return True
        if kind == "select":
            try:
                el.select_option(label=answer)
            except Exception:  # noqa: BLE001
                el.select_option(value=answer)
            self.b.short_pause()
            return True
        if kind == "radio":
            opt = el.locator(f"[role='radio'][aria-label='{answer}']").first
            if opt.count():
                opt.click()
            else:
                lab = el.locator("label").filter(has_text=answer).first
                if lab.count():
                    lab.click()
                else:
                    return False
            self.b.short_pause()
            return True
        return False

    # ---------- errors / questions ----------
    def _invalid_fields(self, modal: Locator) -> list[tuple[dict, str]]:
        """[(field, error text)] for fields LinkedIn flagged after Next/Review/Submit."""
        fields = {f["idx"]: f for f in self._read_fields(modal)}
        try:
            errs = modal.evaluate(S.FORM_ERRORS_JS) or []
        except Exception as exc:  # noqa: BLE001
            log.debug("Error extraction failed: %s", exc)
            errs = []
        out: list[tuple[dict, str]] = []
        seen: set[int] = set()
        for e in errs:
            idx = e.get("idx")
            if idx is None or idx in seen or idx not in fields:
                continue
            seen.add(idx)
            out.append((fields[idx], e.get("text", "")))
        return out

    def _repair_invalid(self, modal: Locator) -> int:
        """Re-answer flagged fields: numeric re-answer first, then the AI with the
        error text. Returns how many fields were changed."""
        fixed = 0
        for f, err in self._invalid_fields(modal):
            label, kind, options = (f.get("label") or "").strip(), f.get("kind", "text"), f.get("options") or []
            current = (f.get("value") or "").strip()
            answer = None
            if kind in ("text", "number"):
                answer = self.answers.resolve(label, kind, options, force_numeric=True)
                if answer == current:
                    answer = None
            if answer is None and self.ai:
                answer = self.ai.answer(
                    f"{label} (previous answer {current!r} was rejected with: {err}; max length {f.get('maxlen') or 'n/a'})",
                    kind, options,
                )
                if answer == current:
                    answer = None
            if answer is None:
                log.warning("Could not repair '%s' (%s): %s", label[:60], current, err)
                continue
            try:
                if self._fill_field(modal, f, answer, clear=True):
                    fixed += 1
                    log.info("Repaired '%s': %r -> %r (%s)", label[:60], current, answer, err)
            except Exception as exc:  # noqa: BLE001
                log.warning("Repair failed for '%s': %s", label[:60], exc)
        return fixed

    def _form_errors(self) -> list[str]:
        modal = self._modal()
        if not modal:
            return []
        try:
            self._read_fields(modal)
            js_errs = [e.get("text", "") for e in (modal.evaluate(S.FORM_ERRORS_JS) or [])]
        except Exception:  # noqa: BLE001
            js_errs = []
        out: list[str] = [t for t in js_errs if t]
        for sel in S.APPLY_ERROR:
            for loc in self.b.find_all([sel], modal):
                try:
                    t = (loc.inner_text(timeout=1000) or "").strip()
                    if not t and sel.startswith("[aria-invalid"):
                        t = f"invalid field: {loc.get_attribute('aria-label') or loc.get_attribute('id') or 'unnamed'}"
                    if t and t not in out:
                        out.append(t[:120])
                except Exception:  # noqa: BLE001
                    pass
        return out

    def _visible_questions(self, modal: Locator) -> list[str]:
        """Labels of fields that are still empty (best effort, for the pause message)."""
        out = []
        for f in self._read_fields(modal):
            label = (f.get("label") or "").strip()
            value = (f.get("value") or "").strip()
            if label and (not value or (f.get("kind") == "select" and value.lower().startswith("select"))):
                out.append(label[:100])
        return out
