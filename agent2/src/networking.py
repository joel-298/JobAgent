"""Connection requests with a note, for HR and developer candidates.

Rules (spec sections 15-19):
  * never send a duplicate request (SQLite log + on-page connection state)
  * never message existing connections (MVP)
  * the note is the Excel message, verbatim
  * ambiguous UI -> log, screenshot and skip / pause; never guess
"""
from __future__ import annotations

import logging

from config import Settings
from src import selectors as S
from src import state_manager as sm
from src.browser import BrowserSession
from src.company_people import PersonCandidate
from src.exceptions import CaptchaDetectedError, ConnectionRequestError, LoginRequiredError
from src.state_manager import StateManager
from src.utils import print_status_block, random_sleep

log = logging.getLogger("agent")

MAX_CONSECUTIVE_PROFILE_ERRORS = 3
LINKEDIN_NOTE_LIMIT = 300


class InvitationLimitError(ConnectionRequestError):
    """LinkedIn reports the weekly invitation limit; the run must stop."""


class Networker:
    def __init__(
        self,
        browser: BrowserSession,
        settings: Settings,
        state: StateManager,
        excel_row: int,
        company_link: str,
        company_name: str = "",
    ):
        self.b = browser
        self.settings = settings
        self.state = state
        self.excel_row = excel_row
        self.company_link = company_link
        self.company_name = company_name

    # ---------- batch ----------
    def process(
        self,
        candidates: list[PersonCandidate],
        category: str,
        message: str,
        target_min: int,
        target_max: int,
        dry_run: bool = False,
        status_extra: dict | None = None,
    ) -> int:
        """Send requests until target_max successes. Returns the success count.

        Raises ConnectionRequestError if fewer than target_min could be sent.
        """
        successful = self.state.count_successful(self.excel_row, category)
        seen = self.state.seen_profiles(self.excel_row, category)
        attempted = len(seen)
        consecutive_errors = 0
        d = self.settings.delays

        for cand in candidates:
            if successful >= target_max:
                break
            if cand.url in seen:
                continue
            if self.state.already_contacted(cand.url):
                log.info("Skipping %s - a request was already sent in an earlier run", cand.name)
                continue

            print_status_block(
                **(status_extra or {}),
                Step=f"{category} outreach",
                Profile=f"{cand.name} - {cand.headline[:70]}",
                Progress=f"{successful} / {target_max}",
                Status="DRY RUN" if dry_run else "RUNNING",
            )
            try:
                result = self.connect(cand, message, dry_run)
                consecutive_errors = 0
            except (CaptchaDetectedError, LoginRequiredError):
                raise
            except InvitationLimitError:
                raise
            except ConnectionRequestError as exc:
                consecutive_errors += 1
                result = sm.CONN_ERROR
                log.error("Connection error for %s: %s", cand.name, exc)
                self.b.screenshot(self.excel_row, f"{category.lower()}_connection_error")
                if consecutive_errors >= MAX_CONSECUTIVE_PROFILE_ERRORS:
                    raise ConnectionRequestError(
                        f"{consecutive_errors} consecutive profile errors in {category} outreach - pausing"
                    ) from exc

            if not dry_run:
                self.state.record_connection(
                    self.excel_row, self.company_link, cand.url, category, result, cand.name, cand.headline, message
                )
            attempted += 1
            if result in sm.CONN_SUCCESS_STATES or (dry_run and result == sm.CONN_DRY_RUN):
                successful += 1
            if not dry_run:
                self._update_counters(category, attempted, successful)
            log.info("%s: %s (%s)", result, cand.name, cand.headline[:60])
            if successful < target_max:
                random_sleep(d.between_profiles_min, d.between_profiles_max, "between profiles")

        if successful >= target_min:
            log.info("%s target reached: %d", category, successful)
            return successful
        raise ConnectionRequestError(
            f"Only {successful} of the required minimum {target_min} {category} requests could be sent "
            f"({len(candidates)} candidates available)"
        )

    def _update_counters(self, category: str, attempted: int, successful: int) -> None:
        if category == "HR":
            self.state.update_run(self.excel_row, hr_attempted=attempted, hr_successful=successful)
        else:
            self.state.update_run(self.excel_row, developer_attempted=attempted, developer_successful=successful)

    # ---------- single profile ----------
    def connect(self, cand: PersonCandidate, message: str, dry_run: bool = False) -> str:
        self.b.goto(cand.url)
        if "/in/" not in self.b.url.lower():
            raise ConnectionRequestError(f"Profile did not open: {self.b.url}")
        if not self.b.find(S.PROFILE_READY + S.PROFILE_NAME, timeout=15):
            raise ConnectionRequestError("Profile page loaded without a recognisable top card")
        self.b.settle()
        title = self.b.page.title() or ""
        page_name = title.split("|")[0].strip() if "linkedin" in title.lower() else ""
        if page_name:
            log.info("Profile: %s", page_name)

        state = self.connection_state()
        if state == "connected":
            return sm.CONN_ALREADY_CONNECTED
        if state == "pending":
            return sm.CONN_PENDING
        if state == "unknown":
            self.b.screenshot(self.excel_row, "connect_button_missing")
            return sm.CONN_NO_CONNECT_BUTTON

        if dry_run:
            log.info("DRY RUN: would send a connection request with note to %s", cand.name)
            return sm.CONN_DRY_RUN

        if not self._open_connect_dialog():
            self.b.screenshot(self.excel_row, "connect_dialog_error")
            raise ConnectionRequestError("Connect dialog did not open")

        if self.b.exists(S.CONNECT_EMAIL_REQUIRED):
            log.info("%s requires an email address to connect - skipping", cand.name)
            self._dismiss_dialog()
            return sm.CONN_NO_CONNECT_BUTTON

        note_ok = self._add_note(message)
        if not note_ok:
            if self.settings.networking.send_without_note_if_unavailable:
                if self.b.click(S.CONNECT_SEND_WITHOUT_NOTE, timeout=3):
                    return self._confirm_sent(sm.CONN_SENT_NO_NOTE)
                self._dismiss_dialog()
                raise ConnectionRequestError("Neither 'Add a note' nor 'Send without a note' was available")
            log.info("'Add a note' unavailable for %s - skipping (send_without_note_if_unavailable=false)", cand.name)
            self._dismiss_dialog()
            return sm.CONN_NOTE_UNAVAILABLE

        if not self.b.click(S.CONNECT_SEND, timeout=5):
            self.b.screenshot(self.excel_row, "connect_send_missing")
            self._dismiss_dialog()
            raise ConnectionRequestError("Send button not found after adding the note")
        return self._confirm_sent(sm.CONN_SENT)

    def _degree(self) -> str:
        """'1st' / '2nd' / '3rd' / '3rd+' from the top card, or ''."""
        try:
            info = self.b.page.evaluate(S.PROFILE_TOPCARD_JS) or {}
            return str(info.get("degree") or "").lower()
        except Exception as exc:  # noqa: BLE001
            log.debug("Top card read failed: %s", exc)
            return ""

    def connection_state(self) -> str:
        """connectable | connected | pending | unknown - from the visible top card.

        Note: a "Message" button no longer implies a connection (LinkedIn shows
        it for 3rd-degree profiles too), so only the degree badge decides that.
        """
        degree = self._degree()
        if degree.startswith("1st"):
            return "connected"
        if self.b.exists(S.PROFILE_PENDING_BUTTON):
            return "pending"
        if self.b.exists(S.PROFILE_CONNECT_BUTTON):
            return "connectable"
        # 2026 UI: Connect lives inside the "More" menu.
        if self.b.click(S.PROFILE_MORE_BUTTON, timeout=3):
            found = self.b.find(S.PROFILE_MORE_CONNECT_ITEM, timeout=3) is not None
            self.b.page.keyboard.press("Escape")
            self.b.short_pause()
            if found:
                return "connectable"
        log.info("No Connect action found (degree=%s)", degree or "unknown")
        return "unknown"

    def _open_connect_dialog(self) -> bool:
        if self.b.click(S.PROFILE_CONNECT_BUTTON, timeout=3):
            pass
        elif self.b.click(S.PROFILE_MORE_BUTTON, timeout=3):
            if not self.b.click(S.PROFILE_MORE_CONNECT_ITEM, timeout=5):
                self.b.page.keyboard.press("Escape")
                return False
        else:
            return False
        return self.b.find(S.CONNECT_DIALOG, timeout=10) is not None

    def _add_note(self, message: str) -> bool:
        from src.excel_manager import looks_like_placeholder

        if not message.strip() or looks_like_placeholder(message):
            # Last line of defence: never send an unfinished note.
            self._dismiss_dialog()
            raise InvitationLimitError(f"Refusing to send a placeholder/empty note: {message[:60]!r}")
        if len(message) > LINKEDIN_NOTE_LIMIT:
            log.warning("Message is %d chars; LinkedIn notes allow %d", len(message), LINKEDIN_NOTE_LIMIT)
        if not self.b.click(S.CONNECT_ADD_NOTE, timeout=3):
            return False
        if self.b.exists(S.CONNECT_NOTE_LIMIT_MARKERS) and not self.b.exists(S.CONNECT_NOTE_TEXTAREA):
            log.warning("LinkedIn reports no personalised invitations left")
            return False
        box = self.b.find(S.CONNECT_NOTE_TEXTAREA, timeout=5)
        if not box:
            return False
        box.fill(message)
        if (box.input_value() or "").strip() != message.strip():
            raise ConnectionRequestError("Note text did not match the Excel message after typing")
        self.b.short_pause()
        return True

    def _confirm_sent(self, result: str) -> str:
        self.b.short_pause()
        if self.b.exists(S.INVITATION_LIMIT_MARKERS):
            self.b.screenshot(self.excel_row, "invitation_limit")
            self._dismiss_dialog()
            raise InvitationLimitError("LinkedIn weekly invitation limit reached")
        dialog_gone = self.b.find(S.CONNECT_DIALOG) is None
        toast = self.b.find(S.INVITATION_SENT_TOAST, timeout=4) is not None
        if toast or dialog_gone:
            return result
        self.b.screenshot(self.excel_row, "connect_unconfirmed")
        self._dismiss_dialog()
        raise ConnectionRequestError("Invitation was not confirmed (dialog still open, no toast)")

    def _dismiss_dialog(self) -> None:
        try:
            if not self.b.click(S.CONNECT_DIALOG_DISMISS, timeout=2):
                self.b.page.keyboard.press("Escape")
        except Exception as exc:  # noqa: BLE001
            log.debug("Dismiss failed: %s", exc)
