"""SQLite execution state (data/agent.db).

Tables
  job_runs     one record per Excel row; the reliable source of progress.
  connections  every connection attempt (profile URL, category, result), used
               to never send a duplicate request and for resume/recovery.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.utils import now_iso

log = logging.getLogger("agent")

# Workflow steps in order. current_step records the *next* thing to do.
STEP_START = "START"
STEP_APPLICATION = "APPLICATION"
STEP_HR_SEARCH = "HR_SEARCH"
STEP_DEVELOPER_SEARCH = "DEVELOPER_SEARCH"
STEP_DONE = "DONE"
STEP_ORDER = [STEP_START, STEP_APPLICATION, STEP_HR_SEARCH, STEP_DEVELOPER_SEARCH, STEP_DONE]

# application_status values
APP_PENDING = "PENDING"
APP_COMPLETED = "COMPLETED"
APP_ALREADY_APPLIED = "ALREADY_APPLIED"
APP_MANUAL = "MANUAL"  # user completed it by hand during a pause
APP_SKIPPED_EXTERNAL = "SKIPPED_EXTERNAL"
APP_DRY_RUN = "DRY_RUN"
APP_CLOSED = "CLOSED"  # job no longer accepting applications
APP_DONE_STATES = {APP_COMPLETED, APP_ALREADY_APPLIED, APP_MANUAL, APP_SKIPPED_EXTERNAL}

# connection results
CONN_SENT = "SENT"
CONN_SENT_NO_NOTE = "SENT_NO_NOTE"
CONN_ALREADY_CONNECTED = "ALREADY_CONNECTED"
CONN_PENDING = "PENDING_REQUEST"
CONN_NOTE_UNAVAILABLE = "NOTE_UNAVAILABLE"
CONN_NO_CONNECT_BUTTON = "NO_CONNECT_BUTTON"
CONN_ERROR = "ERROR"
CONN_DRY_RUN = "DRY_RUN"
CONN_SUCCESS_STATES = {CONN_SENT, CONN_SENT_NO_NOTE}

SCHEMA = """
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    excel_row INTEGER NOT NULL UNIQUE,
    job_link TEXT NOT NULL,
    company_link TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    application_status TEXT NOT NULL DEFAULT 'PENDING',
    hr_attempted INTEGER NOT NULL DEFAULT 0,
    hr_successful INTEGER NOT NULL DEFAULT 0,
    developer_attempted INTEGER NOT NULL DEFAULT 0,
    developer_successful INTEGER NOT NULL DEFAULT 0,
    current_step TEXT NOT NULL DEFAULT 'START',
    last_error TEXT,
    started_at TEXT,
    updated_at TEXT,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    excel_row INTEGER NOT NULL,
    company_link TEXT NOT NULL,
    profile_url TEXT NOT NULL,
    profile_name TEXT,
    headline TEXT,
    category TEXT NOT NULL,
    result TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_connections_profile ON connections(profile_url);
"""


@dataclass
class JobRun:
    id: int
    excel_row: int
    job_link: str
    company_link: str
    status: str
    application_status: str
    hr_attempted: int
    hr_successful: int
    developer_attempted: int
    developer_successful: int
    current_step: str
    last_error: str | None
    started_at: str | None
    updated_at: str | None
    completed_at: str | None


class StateManager:
    def __init__(self, db_path: Path | str):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(connections)")}
        if "note" not in cols:  # migrate older databases
            self.conn.execute("ALTER TABLE connections ADD COLUMN note TEXT")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- job_runs ----------
    def _row_to_run(self, row) -> JobRun | None:
        return JobRun(**dict(row)) if row else None

    def get_run(self, excel_row: int) -> JobRun | None:
        cur = self.conn.execute("SELECT * FROM job_runs WHERE excel_row = ?", (excel_row,))
        return self._row_to_run(cur.fetchone())

    def get_or_create_run(self, excel_row: int, job_link: str, company_link: str) -> JobRun:
        run = self.get_run(excel_row)
        if run:
            if run.job_link != job_link or run.company_link != company_link:
                # The user changed the row -> old progress no longer applies.
                log.warning("Row %s links changed since last run; resetting its state", excel_row)
                self.conn.execute("DELETE FROM job_runs WHERE excel_row = ?", (excel_row,))
                self.conn.commit()
            else:
                return run
        ts = now_iso()
        self.conn.execute(
            "INSERT INTO job_runs (excel_row, job_link, company_link, status, started_at, updated_at)"
            " VALUES (?, ?, ?, 'PENDING', ?, ?)",
            (excel_row, job_link, company_link, ts, ts),
        )
        self.conn.commit()
        return self.get_run(excel_row)  # type: ignore[return-value]

    def update_run(self, excel_row: int, **fields) -> None:
        allowed = {
            "status",
            "application_status",
            "hr_attempted",
            "hr_successful",
            "developer_attempted",
            "developer_successful",
            "current_step",
            "last_error",
            "completed_at",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"Unknown job_runs fields: {bad}")
        fields["updated_at"] = now_iso()
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(
            f"UPDATE job_runs SET {sets} WHERE excel_row = ?", (*fields.values(), excel_row)
        )
        self.conn.commit()

    def list_runs(self) -> list[JobRun]:
        cur = self.conn.execute("SELECT * FROM job_runs ORDER BY excel_row")
        return [self._row_to_run(r) for r in cur.fetchall()]  # type: ignore[misc]

    def unfinished_runs(self) -> list[JobRun]:
        cur = self.conn.execute(
            "SELECT * FROM job_runs WHERE status IN ('IN_PROGRESS', 'PAUSED') ORDER BY excel_row"
        )
        return [self._row_to_run(r) for r in cur.fetchall()]  # type: ignore[misc]

    # ---------- connections ----------
    def record_connection(
        self,
        excel_row: int,
        company_link: str,
        profile_url: str,
        category: str,
        result: str,
        profile_name: str = "",
        headline: str = "",
        note: str = "",
    ) -> None:
        self.conn.execute(
            "INSERT INTO connections (excel_row, company_link, profile_url, profile_name, headline,"
            " category, result, note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (excel_row, company_link, profile_url, profile_name, headline, category, result,
             note if result in (CONN_SENT,) else "", now_iso()),
        )
        self.conn.commit()

    def already_contacted(self, profile_url: str) -> bool:
        """True if a request was ever sent (or is pending) to this profile, any row."""
        cur = self.conn.execute(
            "SELECT 1 FROM connections WHERE profile_url = ? AND result IN (?, ?, ?, ?) LIMIT 1",
            (profile_url, CONN_SENT, CONN_SENT_NO_NOTE, CONN_PENDING, CONN_ALREADY_CONNECTED),
        )
        return cur.fetchone() is not None

    def seen_profiles(self, excel_row: int, category: str) -> set[str]:
        cur = self.conn.execute(
            "SELECT profile_url FROM connections WHERE excel_row = ? AND category = ?",
            (excel_row, category),
        )
        return {r[0] for r in cur.fetchall()}

    def count_successful(self, excel_row: int, category: str) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM connections WHERE excel_row = ? AND category = ? AND result IN (?, ?)",
            (excel_row, category, CONN_SENT, CONN_SENT_NO_NOTE),
        )
        return int(cur.fetchone()[0])

    def list_connections(self, excel_row: int | None = None) -> list[sqlite3.Row]:
        if excel_row is None:
            cur = self.conn.execute("SELECT * FROM connections ORDER BY id")
        else:
            cur = self.conn.execute(
                "SELECT * FROM connections WHERE excel_row = ? ORDER BY id", (excel_row,)
            )
        return cur.fetchall()
