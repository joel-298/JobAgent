"""LinkedIn Job Application & Networking Automation Agent - CLI entry point.

    python app.py                 process every eligible row in data/jobs.xlsx
    python app.py --test-one      process only the first eligible row (MVP test)
    python app.py --dry-run       open pages and validate, submit/send nothing
    python app.py --resume        resume PAUSED / IN_PROGRESS rows without asking
    python app.py --status        show Excel + SQLite progress, no browser
    python app.py --connections   who was contacted + the note sent (--sent: only sent ones)
    python app.py --init-excel    create data/jobs.xlsx with the expected columns

The agent never handles your LinkedIn password: log in manually in the browser
window it opens the first time; the session is kept in browser_profile/.
It stops and waits for you whenever LinkedIn asks for verification.
"""
from __future__ import annotations

import argparse
import sys

from config import load_settings
from src.logger import setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="app.py",
        description="Automates LinkedIn Easy Apply + HR/developer connection requests from an Excel file.",
    )
    p.add_argument("--test-one", action="store_true", help="process only the first eligible row")
    p.add_argument("--dry-run", action="store_true", help="navigate and validate only; submit nothing")
    p.add_argument("--resume", action="store_true", help="resume PAUSED/IN_PROGRESS rows without asking")
    p.add_argument("--status", action="store_true", help="print progress and exit")
    p.add_argument("--connections", action="store_true", help="list everyone contacted, with the note sent")
    p.add_argument("--sent", action="store_true", help="with --connections: only successfully sent requests")
    p.add_argument("--init-excel", action="store_true", help="create the Excel template and exit")
    p.add_argument("--excel", help="path to the jobs Excel file (default: data/jobs.xlsx or JOBS_EXCEL in .env)")
    p.add_argument("--verbose", "-v", action="store_true", help="debug logging in the console")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.excel:
        from pathlib import Path

        settings.paths.excel = Path(args.excel).resolve()
    settings.paths.ensure_dirs()

    import logging

    log = setup_logging(settings.paths.logs, logging.DEBUG if args.verbose else logging.INFO)

    if args.init_excel:
        from src.excel_manager import ExcelManager

        if settings.paths.excel.exists():
            print(f"Excel already exists: {settings.paths.excel} (not overwritten)")
            return 0
        path = ExcelManager.create_template(settings.paths.excel)
        print(f"Created {path}")
        print("Fill in job_link, resume_name, company_link, hr_message, developer_message, then run:")
        print("  python app.py --dry-run     (validate)")
        print("  python app.py --test-one    (one job end to end)")
        return 0

    if args.connections:
        from src.runner import print_connections

        print_connections(settings, only_sent=args.sent)
        return 0

    if args.status:
        from src.runner import print_status

        try:
            print_status(settings)
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    from src.exceptions import AgentError, UserAbortError
    from src.runner import AgentRunner

    log.info("=" * 50)
    log.info(
        "Agent starting | mode=%s | excel=%s",
        "dry-run" if args.dry_run else ("test-one" if args.test_one else "run"),
        settings.paths.excel,
    )
    log.info(
        "Targets: HR %d-%d, developers %d-%d",
        settings.networking.hr_min,
        settings.networking.hr_max,
        settings.networking.developer_min,
        settings.networking.developer_max,
    )
    runner = AgentRunner(settings, dry_run=args.dry_run, test_one=args.test_one, resume=args.resume)
    try:
        runner.run()
    except UserAbortError as exc:
        log.warning("Run stopped by user: %s", exc)
        return 130
    except AgentError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("Interrupted (Ctrl+C). Rows in progress stay PAUSED/IN_PROGRESS and can be resumed.")
        return 130
    finally:
        runner.state.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
