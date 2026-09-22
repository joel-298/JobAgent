"""Row-by-row orchestration: Excel -> application -> HR -> developers -> COMPLETED.

The single most important rule (spec section 40): a row is marked COMPLETED
only when every configured phase finished. Anything else ends in PAUSED /
FAILED with the step recorded so the run can be resumed.
"""
from __future__ import annotations

import logging
import traceback

from config import Settings
from src import state_manager as sm
from src.browser import BrowserSession
from src.company_people import CATEGORY_DEVELOPER, CATEGORY_HR, CompanyPeople
from src.excel_manager import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_IN_PROGRESS,
    STATUS_PAUSED,
    STATUS_PENDING,
    ExcelManager,
    JobRow,
)
from src.exceptions import AgentError, CaptchaDetectedError, JobClosedError, LoginRequiredError, UserAbortError
from src.human_intervention import ask_yes_no, request_intervention
from src.job_application import JobApplication
from src.networking import InvitationLimitError, Networker
from src.state_manager import StateManager
from src.utils import now_iso, print_status_block, random_sleep

log = logging.getLogger("agent")

MAX_INTERRUPTION_RETRIES = 3


class AgentRunner:
    def __init__(self, settings: Settings, dry_run: bool = False, test_one: bool = False, resume: bool = False):
        self.settings = settings
        self.dry_run = dry_run
        self.test_one = test_one
        self.resume_flag = resume
        settings.paths.ensure_dirs()
        self.excel = ExcelManager(settings.paths.excel)
        # Dry runs must leave the real state untouched.
        self.state = StateManager(":memory:" if dry_run else settings.paths.db)
        self.stop_requested = False

    # ---------- row selection ----------
    def select_rows(self, rows: list[JobRow]) -> list[JobRow]:
        eligible: list[JobRow] = []
        resumable: list[JobRow] = []
        for row in rows:
            if not row.is_valid:
                log.warning("Row %d skipped - invalid: %s", row.excel_row, "; ".join(row.problems))
                continue
            if row.status == STATUS_COMPLETED:
                continue
            if row.status in (STATUS_PAUSED, STATUS_IN_PROGRESS):
                resumable.append(row)
            elif row.status == STATUS_FAILED:
                if self.settings.run.retry_failed == "retry":
                    eligible.append(row)
                else:
                    log.info("Row %d is FAILED - skipped (run.retry_failed=skip)", row.excel_row)
            else:  # PENDING / blank
                eligible.append(row)

        if resumable:
            mode = "yes" if self.resume_flag else self.settings.run.resume_paused
            ids = ", ".join(str(r.excel_row) for r in resumable)
            if mode == "ask":
                for r in resumable:
                    run = self.state.get_run(r.excel_row)
                    step = run.current_step if run else "?"
                    print(f"  row {r.excel_row}: {r.status} at step {step} - {r.last_error or ''}".rstrip(" -"))
                do_resume = ask_yes_no(f"Resume interrupted work on row(s) {ids}?", default=False)
            else:
                do_resume = mode == "yes"
            if do_resume:
                eligible.extend(resumable)
                log.info("Resuming rows %s", ids)
            else:
                log.info("Leaving PAUSED/IN_PROGRESS rows %s untouched", ids)

        eligible.sort(key=lambda r: r.excel_row)
        if self.test_one:
            eligible = eligible[:1]
        return eligible

    # ---------- run ----------
    def run(self) -> int:
        """Process all eligible rows. Returns the number of rows completed."""
        self.excel.ensure_tracking_columns()
        rows = self.excel.load_rows()
        log.info("Excel loaded: %d row(s)", len(rows))
        eligible = self.select_rows(rows)
        if not eligible:
            print("Nothing to do: no eligible rows (PENDING) in the Excel file.")
            return 0

        mode = "DRY RUN" if self.dry_run else ("TEST ONE" if self.test_one else "FULL RUN")
        print(f"\n{mode}: {len(eligible)} row(s) to process: {[r.excel_row for r in eligible]}\n")
        completed = 0
        consecutive_failures = 0
        with BrowserSession(self.settings) as browser:
            browser.ensure_logged_in()
            for idx, row in enumerate(eligible, start=1):
                ok = self.process_row(browser, row, idx, len(eligible))
                if ok:
                    completed += 1
                    consecutive_failures = 0
                elif ok is False:
                    consecutive_failures += 1
                # ok is None -> row skipped (e.g. job closed): not counted either way
                if self.stop_requested:
                    log.warning("Stopping the run as requested")
                    break
                if consecutive_failures >= self.settings.run.max_consecutive_failures:
                    log.error("%d consecutive row failures - stopping the run for safety", consecutive_failures)
                    break
                if idx < len(eligible):
                    d = self.settings.delays
                    lo, hi = (0, 0) if self.dry_run else (d.between_companies_min, d.between_companies_max)
                    log.info("Waiting before the next company (%.0f-%.0fs)", lo, hi)
                    random_sleep(lo, hi, "between companies")
        print(f"\nDone. Rows completed this run: {completed}/{len(eligible)}")
        if self.dry_run:
            print("DRY RUN: No actions submitted.")
        return completed

    # ---------- single row ----------
    def process_row(self, browser: BrowserSession, row: JobRow, idx: int, total: int, attempt: int = 1) -> bool:
        r = row.excel_row
        n = self.settings.networking
        run = self.state.get_or_create_run(r, row.job_link, row.company_link)
        if not self.dry_run:
            self.excel.mark_in_progress(r)
            self.state.update_run(r, status=STATUS_IN_PROGRESS, last_error="")
        log.info("Starting row %d (%d/%d)%s", r, idx, total, " [DRY RUN]" if self.dry_run else "")
        if self.dry_run:
            self._print_dry_run_plan(row)

        status_ctx = {"Processing": f"row {idx}/{total} (Excel row {r})"}
        log.info("Messages: using hr_message/developer_message type '%s' (resume_name=%s)", row.message_key, row.resume_name)
        company_name = ""
        current_step = run.current_step
        try:
            # ---- application ----
            if sm.STEP_ORDER.index(current_step) <= sm.STEP_ORDER.index(sm.STEP_APPLICATION):
                self._set_step(r, sm.STEP_APPLICATION)
                print_status_block(**status_ctx, Step="Job application", Status="DRY RUN" if self.dry_run else "RUNNING")
                app = JobApplication(browser, self.settings, r, row.job_link, row.resume_name)
                app_status = app.apply(dry_run=self.dry_run)
                log.info("Application status: %s", app_status)
                if not self.dry_run:
                    self.state.update_run(r, application_status=app_status)
                    self.excel.update_row(r, application_status=app_status)
                self._set_step(r, sm.STEP_HR_SEARCH)
            else:
                log.info("Application already done (%s) - resuming at %s", run.application_status, current_step)

            # ---- company ----
            people = CompanyPeople(browser, self.settings, r, row.company_link)
            company_name = people.open_company()
            status_ctx["Company"] = company_name

            # ---- HR outreach ----
            run = self.state.get_run(r) or run
            if sm.STEP_ORDER.index(run.current_step) <= sm.STEP_ORDER.index(sm.STEP_HR_SEARCH):
                log.info("HR search started")
                net = Networker(browser, self.settings, self.state, r, row.company_link, company_name)
                if n.hr_max > 0:
                    hr_candidates = people.search_hr()
                    net.process(hr_candidates, CATEGORY_HR, row.hr_message, n.hr_min, n.hr_max, self.dry_run, status_ctx)
                self._set_step(r, sm.STEP_DEVELOPER_SEARCH)
            else:
                log.info("HR outreach already done (%d sent) - resuming at developer outreach", run.hr_successful)

            # ---- developer outreach ----
            run = self.state.get_run(r) or run
            if sm.STEP_ORDER.index(run.current_step) <= sm.STEP_ORDER.index(sm.STEP_DEVELOPER_SEARCH):
                log.info("Developer search started")
                net = Networker(browser, self.settings, self.state, r, row.company_link, company_name)
                if n.developer_max > 0:
                    dev_candidates = people.search_developers()
                    net.process(
                        dev_candidates, CATEGORY_DEVELOPER, row.developer_message,
                        n.developer_min, n.developer_max, self.dry_run, status_ctx,
                    )
                self._set_step(r, sm.STEP_DONE)

            # ---- completion ----
            if self.dry_run:
                log.info("Row %d dry run finished - nothing was submitted", r)
                return True
            run = self.state.get_run(r) or run
            self._validate_completion(run)
            self.state.update_run(r, status=STATUS_COMPLETED, current_step=sm.STEP_DONE, completed_at=now_iso(), last_error="")
            self.excel.mark_completed(
                r,
                application_status=run.application_status,
                hr_connections_sent=run.hr_successful,
                developer_connections_sent=run.developer_successful,
            )
            log.info("Row %d COMPLETED", r)
            return True

        except (CaptchaDetectedError, LoginRequiredError) as exc:
            self._pause(r, exc.step, str(exc))
            if attempt > MAX_INTERRUPTION_RETRIES:
                log.error("Row %d: too many interruptions - leaving it PAUSED", r)
                return False
            try:
                browser.handle_interruption(exc, r)
            except UserAbortError as abort:
                self.stop_requested = True
                self._pause(r, exc.step, str(abort))
                return False
            except (CaptchaDetectedError, LoginRequiredError) as again:
                log.error("Still blocked after intervention: %s", again)
                return False
            log.info("Resuming row %d after intervention", r)
            return self.process_row(browser, row, idx, total, attempt + 1)
        except JobClosedError as exc:
            log.info("Row %d: %s - marking FAILED (closed) and moving on", r, exc)
            if not self.dry_run:
                self.state.update_run(r, status=STATUS_FAILED, application_status=sm.APP_CLOSED, last_error=str(exc))
                self.excel.mark_failed(r, f"[APPLICATION] Job closed - {exc}", application_status=sm.APP_CLOSED)
            return None  # neither a success nor an agent failure
        except UserAbortError as exc:
            self.stop_requested = True
            self._pause(r, self._current_step(r), str(exc))
            return False
        except InvitationLimitError as exc:
            self.stop_requested = True
            self._pause(r, self._current_step(r), str(exc))
            log.error("%s - stopping the run", exc)
            return False
        except AgentError as exc:
            browser.screenshot(r, f"{exc.step.lower()}_error")
            self._pause(r, exc.step if exc.step != "UNKNOWN" else self._current_step(r), str(exc))
            return False
        except Exception as exc:  # noqa: BLE001 - browser crash or unexpected UI
            log.error("Unexpected error on row %d: %s\n%s", r, exc, traceback.format_exc())
            try:
                browser.screenshot(r, "unexpected_error")
            except Exception:  # noqa: BLE001
                pass
            self._pause(r, self._current_step(r), f"Unexpected error: {exc}")
            return False

    # ---------- helpers ----------
    def _set_step(self, excel_row: int, step: str) -> None:
        # In dry-run mode self.state is an in-memory DB, so this is harmless.
        self.state.update_run(excel_row, current_step=step)

    def _current_step(self, excel_row: int) -> str:
        run = self.state.get_run(excel_row)
        return run.current_step if run else sm.STEP_START

    def _pause(self, excel_row: int, step: str, error: str) -> None:
        log.warning("Row %d PAUSED at %s: %s", excel_row, step, error)
        if self.dry_run:
            return
        run = self.state.get_run(excel_row)
        self.state.update_run(excel_row, status=STATUS_PAUSED, last_error=error[:500])
        self.excel.mark_paused(
            excel_row,
            f"[{step}] {error}",
            application_status=run.application_status if run else "",
            hr_connections_sent=run.hr_successful if run else 0,
            developer_connections_sent=run.developer_successful if run else 0,
        )

    def _validate_completion(self, run: sm.JobRun) -> None:
        n = self.settings.networking
        problems = []
        if run.application_status not in sm.APP_DONE_STATES:
            problems.append(f"application_status={run.application_status}")
        if run.hr_successful < n.hr_min:
            problems.append(f"hr_successful={run.hr_successful} < hr_min={n.hr_min}")
        if run.developer_successful < n.developer_min:
            problems.append(f"developer_successful={run.developer_successful} < developer_min={n.developer_min}")
        if run.current_step != sm.STEP_DONE:
            problems.append(f"current_step={run.current_step}")
        if problems:
            raise AgentError("Refusing to mark COMPLETED: " + ", ".join(problems), "COMPLETION_CHECK")

    def _print_dry_run_plan(self, row: JobRow) -> None:
        n = self.settings.networking
        print(f"\nROW {row.excel_row}\n")
        print(f"Job:\n{row.job_link}\n")
        print(f"Resume:\n{row.resume_name}\n")
        print(f"Company:\n{row.company_link}\n")
        print("Would perform:\n")
        print("[1] Apply to job")
        print(f"[2] Select {row.resume_name}")
        print("[3] Open company page")
        print("[4] Find HR/Talent Acquisition")
        print(f"[5] Process up to {n.hr_max} HR profiles (min {n.hr_min}) with hr_message ({len(row.hr_message)} chars)")
        print("[6] Find software developers")
        print(f"[7] Process up to {n.developer_max} developers (min {n.developer_min}) with developer_message ({len(row.developer_message)} chars)")
        print("\nDRY RUN: navigating and validating only - no submissions.\n")


def print_status(settings: Settings) -> None:
    """--status: show Excel + SQLite state without opening a browser."""
    excel = ExcelManager(settings.paths.excel)
    rows = excel.load_rows()
    state = StateManager(settings.paths.db)
    print(f"\nExcel: {settings.paths.excel}")
    print(f"DB:    {settings.paths.db}\n")
    header = f"{'row':>4}  {'status':<12} {'application':<18} {'step':<17} {'HR':>5} {'DEV':>5}  last_error"
    print(header)
    print("-" * len(header))
    for row in rows:
        run = state.get_run(row.excel_row)
        app = run.application_status if run else row.application_status or "-"
        step = run.current_step if run else "-"
        hr = run.hr_successful if run else row.hr_connections_sent
        dev = run.developer_successful if run else row.developer_connections_sent
        err = (row.last_error or (run.last_error if run else "") or "")[:60]
        if not row.is_valid:
            err = "INVALID: " + "; ".join(row.problems)[:50]
        print(f"{row.excel_row:>4}  {row.status:<12} {app:<18} {step:<17} {hr:>5} {dev:>5}  {err}")
    counts = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    print("\nTotals: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) if counts else "\nNo rows.")
    conns = state.list_connections()
    if conns:
        sent = sum(1 for c in conns if c["result"] in sm.CONN_SUCCESS_STATES)
        print(f"Connection log: {len(conns)} attempts, {sent} requests sent")
    state.close()


def print_connections(settings: Settings, only_sent: bool = False) -> None:
    """--connections: who was contacted, with the note that was sent."""
    state = StateManager(settings.paths.db)
    rows = state.list_connections()
    if only_sent:
        rows = [r for r in rows if r["result"] in sm.CONN_SUCCESS_STATES]
    if not rows:
        print("No connection attempts recorded yet.")
        state.close()
        return
    print(f"\n{len(rows)} connection record(s)  (DB: {settings.paths.db})\n")
    for r in rows:
        print(f"[{r['created_at']}] row {r['excel_row']} | {r['category']:<9} | {r['result']}")
        print(f"   {r['profile_name'] or '?'} - {(r['headline'] or '')[:80]}")
        print(f"   {r['profile_url']}")
        if r["note"]:
            print(f"   note: {r['note']}")
        print()
    sent = sum(1 for r in rows if r["result"] in sm.CONN_SUCCESS_STATES)
    print(f"Total requests sent: {sent}")
    state.close()
