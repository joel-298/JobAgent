"""Runs agent1 / agent2 as subprocesses, streams their output, relays prompts."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger("jarvis")

ROOT = Path(__file__).resolve().parent.parent
AGENTS = {
    "job_search": [sys.executable, "-u", str(ROOT / "agent1" / "app.py")],
    "apply": [sys.executable, "-u", str(ROOT / "agent2" / "app.py"), "--resume"],
}
HUMAN_MARKER = "HUMAN INTERVENTION REQUIRED"
PROMPT_MARKERS = ("> ", "[y/N]", "[Y/n]")


class AgentRunner:
    """One run at a time. Emits events through an async callback."""

    def __init__(self, emit: Callable[[dict], Awaitable[None]], loop: asyncio.AbstractEventLoop):
        self._emit = emit
        self._loop = loop
        self.proc: subprocess.Popen | None = None
        self.agent: str | None = None
        self.waiting_for_human = False
        self.human_reason = ""
        self.lines: list[str] = []
        self.exit_code: int | None = None
        self._finished_cb: Callable[[str, int, list[str]], Awaitable[None]] | None = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> dict:
        return {
            "running": self.running,
            "agent": self.agent if self.running else None,
            "waiting_for_human": self.waiting_for_human,
            "human_reason": self.human_reason,
            "last_lines": self.lines[-15:],
        }

    def _post(self, event: dict) -> None:
        asyncio.run_coroutine_threadsafe(self._emit(event), self._loop)

    def start(self, agent: str, on_finished: Callable[[str, int, list[str]], Awaitable[None]]) -> bool:
        if self.running:
            return False
        cmd = list(AGENTS[agent])
        if os.environ.get("JARVIS_DRY_RUN"):  # testing: agents navigate but submit/write nothing
            cmd.append("--dry-run")
        cmd += os.environ.get(f"JARVIS_{agent.upper()}_ARGS", "").split()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        log.info("Starting %s: %s", agent, " ".join(cmd))
        self.proc = subprocess.Popen(
            cmd, cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=env, bufsize=1,
        )
        self.agent = agent
        self.lines = []
        self.exit_code = None
        self.waiting_for_human = False
        self.human_reason = ""
        self._finished_cb = on_finished
        threading.Thread(target=self._pump, daemon=True).start()
        return True

    def _pump(self) -> None:
        assert self.proc and self.proc.stdout
        buf = ""
        block: list[str] = []
        in_block = False
        while True:
            ch = self.proc.stdout.read(1)
            if not ch:
                break
            buf += ch
            # Prompts ("> ") do not end with a newline: flush them too.
            if ch == "\n" or buf.endswith(PROMPT_MARKERS):
                line = buf.rstrip("\n")
                buf = ""
                if not line.strip():
                    continue
                self.lines.append(line)
                self._post({"type": "log", "line": line})
                if HUMAN_MARKER in line:
                    in_block, block = True, []
                elif in_block:
                    if line.strip().startswith("==="):
                        pass
                    elif line.strip() == ">":
                        in_block = False
                    else:
                        block.append(line.strip())
                if line.strip() == ">" or line.strip().endswith("> "):
                    self.waiting_for_human = True
                    self.human_reason = " ".join(x for x in block if x)[:400]
                    self._post({"type": "needs_human", "reason": self.human_reason})
                elif line.strip().endswith("[y/N]") or line.strip().endswith("[Y/n]"):
                    # any y/n prompt: answer yes so the run continues without a human
                    self.send("y")
        if buf.strip():
            self.lines.append(buf)
            self._post({"type": "log", "line": buf})
        self.exit_code = self.proc.wait()
        self.waiting_for_human = False
        agent, lines = self.agent or "", list(self.lines)
        log.info("%s finished with exit code %s", agent, self.exit_code)
        if self._finished_cb:
            asyncio.run_coroutine_threadsafe(self._finished_cb(agent, self.exit_code, lines), self._loop)

    def send(self, text: str) -> bool:
        if not self.running or not self.proc or not self.proc.stdin:
            return False
        try:
            self.proc.stdin.write(text + "\n")
            self.proc.stdin.flush()
        except OSError:
            return False
        self.waiting_for_human = False
        self.human_reason = ""
        return True

    def continue_run(self) -> bool:
        return self.send("")

    def stop(self) -> bool:
        if not self.running or not self.proc:
            return False
        if self.waiting_for_human:
            return self.send("q")
        try:
            self.proc.terminate()
        except OSError:
            return False
        return True
