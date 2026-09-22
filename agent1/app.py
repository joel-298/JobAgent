"""Agent 1 - LinkedIn job finder. Fills agent2/data/jobs.xlsx with PENDING rows.

    python agent1/app.py               search and append new jobs
    python agent1/app.py --dry-run     search and show what would be added, write nothing
    python agent1/app.py --max 10      stop after 10 new jobs
    python agent1/app.py --keywords "Java Developer,Node.js Developer"

Filters, exclusions, resume rules and message texts: agent1/config/search.yaml.
Uses agent2's browser login (agent2/browser_profile) and settings.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

AGENT1_DIR = Path(__file__).resolve().parent
AGENT2_DIR = AGENT1_DIR.parent / "agent2"
sys.path.insert(0, str(AGENT2_DIR))  # reuse agent2's config / src packages
sys.path.insert(0, str(AGENT1_DIR))

from config import load_settings  # noqa: E402  (agent2)
from src.exceptions import AgentError, UserAbortError  # noqa: E402  (agent2)
from src.logger import setup_logging  # noqa: E402  (agent2)

from agent1_src.finder import JobFinder, SearchConfig  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="agent1/app.py", description="Find LinkedIn Easy Apply jobs and add them to agent2's Excel.")
    p.add_argument("--dry-run", action="store_true", help="show what would be added; write nothing")
    p.add_argument("--max", type=int, help="maximum new rows to add (overrides config)")
    p.add_argument("--keywords", help="comma-separated search keywords (overrides config)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args(argv)

    settings = load_settings()
    settings.paths.ensure_dirs()
    log = setup_logging(settings.paths.logs, logging.DEBUG if args.verbose else logging.INFO)

    cfg = SearchConfig.load(AGENT1_DIR / "config" / "search.yaml")
    if args.max:
        cfg.max_new_jobs = args.max
    if args.keywords:
        cfg.keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    missing = [t for t in ("java", "mern") if "<PASTE" in ((cfg.messages.get(t) or {}).get("hr") or "") + ((cfg.messages.get(t) or {}).get("developer") or "")]
    if missing:
        log.warning("agent1/config/search.yaml: messages for %s still contain a placeholder drive link - fill them in", missing)

    log.info("=" * 50)
    log.info("Agent1 starting | %s | keywords=%s | max=%d | excel=%s",
             "DRY RUN" if args.dry_run else "run", cfg.keywords, cfg.max_new_jobs, settings.paths.excel)
    finder = JobFinder(settings, cfg, dry_run=args.dry_run)
    try:
        added = finder.run()
    except UserAbortError as exc:
        log.warning("Stopped by user: %s", exc)
        return 130
    except AgentError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.warning("Interrupted (Ctrl+C). Rows already added are kept.")
        return 130

    print()
    print(f"{'Would add' if args.dry_run else 'Added'} {len(added)} job(s):")
    for e in added:
        print(f"  [{e['type']:<4}] {e['title'][:55]:<55} | {e['company'][:30]:<30} | {e['job_link']}")
    if finder.skipped:
        print("\nSkipped: " + ", ".join(f"{k}: {v}" for k, v in sorted(finder.skipped.items(), key=lambda kv: -kv[1])))
    if not args.dry_run and added:
        print(f"\nReview {settings.paths.excel} (delete rows you don't want), then run:  python agent2/app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
