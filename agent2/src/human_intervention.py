"""Human-in-the-loop prompts.

The agent never tries to solve or bypass CAPTCHAs / verification. It stops,
leaves the browser open, and waits for the user.
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.exceptions import UserAbortError

log = logging.getLogger("agent")

BANNER = "=" * 50


def request_intervention(reason: str, screenshot: Path | None = None, instructions: str = "") -> None:
    """Block until the user presses ENTER. Typing 'q' aborts the run safely."""
    log.warning("HUMAN INTERVENTION REQUIRED: %s", reason)
    print()
    print(BANNER)
    print("HUMAN INTERVENTION REQUIRED")
    print(BANNER)
    print()
    print(f"Reason: {reason}")
    print()
    print("The browser has been left open.")
    if screenshot:
        print(f"Screenshot: {screenshot}")
    print()
    print(instructions or "Resolve the situation in the browser manually, then press ENTER\nto allow the agent to continue.")
    print("Type q + ENTER to stop the run.")
    print()
    print(BANNER)
    try:
        answer = input("> ").strip().lower()
    except EOFError:
        raise UserAbortError("No interactive terminal available to continue")
    if answer in ("q", "quit", "exit", "stop"):
        raise UserAbortError("User stopped the run at an intervention prompt")
    log.info("User signalled to continue")


def ask_yes_no(question: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{question} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")
