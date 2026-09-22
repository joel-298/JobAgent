"""Read-only view of the agents' data for Jarvis (Excel, jobs_found.json, SQLite)."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT2 = ROOT / "agent2"
sys.path.insert(0, str(AGENT2))

from config import load_settings  # noqa: E402
from src.excel_manager import ExcelManager  # noqa: E402


def _settings():
    return load_settings()


def jobs_found() -> dict:
    f = _settings().paths.excel.parent / "jobs_found.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def excel_rows() -> list[dict]:
    s = _settings()
    if not s.paths.excel.exists():
        return []
    try:
        rows = ExcelManager(s.paths.excel).load_rows()
    except Exception as exc:  # noqa: BLE001
        return [{"error": str(exc)}]
    return [
        {
            "excel_row": r.excel_row,
            "job_link": r.job_link,
            "resume_name": r.resume_name,
            "company_link": r.company_link,
            "status": r.status,
            "application_status": r.application_status,
            "hr_sent": r.hr_connections_sent,
            "dev_sent": r.developer_connections_sent,
            "last_error": r.last_error,
            "completed_at": r.completed_at,
            "valid": r.is_valid,
            "problems": r.problems,
        }
        for r in rows
    ]


def connections(limit: int = 50) -> list[dict]:
    db = _settings().paths.db
    if not db.exists():
        return []
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM connections ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    except sqlite3.Error:
        return []
    finally:
        conn.close()
    return [
        {"row": r["excel_row"], "category": r["category"], "result": r["result"], "name": r["profile_name"],
         "headline": r["headline"], "url": r["profile_url"], "at": r["created_at"]}
        for r in rows
    ]


def _job_id(link: str) -> str:
    import re

    m = re.search(r"/jobs/view/(\d+)", link or "")
    return m.group(1) if m else ""


def snapshot(for_brain: bool = False) -> dict:
    """Combined state. for_brain=True trims descriptions to keep prompts small."""
    found = jobs_found()
    rows = excel_rows()
    jobs = []
    for r in rows:
        if "error" in r:
            jobs.append(r)
            continue
        f = found.get(_job_id(r["job_link"]), {})
        jobs.append(
            {
                "excel_row": r["excel_row"],
                "title": f.get("title", ""),
                "company": f.get("company", ""),
                "location": f.get("location", ""),
                "resume": r["resume_name"],
                "status": r["status"],
                "application": r["application_status"],
                "hr_sent": r["hr_sent"],
                "dev_sent": r["dev_sent"],
                "error": r["last_error"],
                "job_link": r["job_link"],
                "company_link": r["company_link"],
                "description": (f.get("description", "") or "")[: 400 if for_brain else 2000],
                "valid": r["valid"],
                "problems": r["problems"],
            }
        )
    counts: dict[str, int] = {}
    for r in rows:
        if "error" not in r:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    conns = connections(30 if for_brain else 100)
    return {"jobs": jobs, "totals": counts, "connections": conns}
