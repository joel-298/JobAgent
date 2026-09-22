"""AI fallback for application questions not covered by config/answers.yaml.

Asks Claude through the Claude Code CLI (your subscription login) to answer a
single form field from the resume text. Answers only when the information is
in the resume; otherwise returns None so the run pauses for the user.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("agent")

SYSTEM = """You fill in ONE job-application form field for a candidate, using ONLY the candidate profile given.
Reply with a single JSON object: {"answer": <string or null>, "reason": "<short>"}.
Rules: for a dropdown/radio field the answer must be EXACTLY one of the given options; for a number field reply digits only;
keep text answers short (max 300 characters) and in English; if the field needs information that is not in the profile
(document uploads, ID/passport numbers, references, signatures, exact dates you don't know) reply {"answer": null}.
Reasonable inferences are fine (e.g. years of experience with a listed skill = the candidate's total experience,
any Yes/No eligibility question the profile supports = "Yes")."""


def find_claude_cli() -> str | None:
    env = os.environ.get("CLAUDE_CLI")
    if env and Path(env).exists():
        return env
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    home = Path.home()
    cands = glob.glob(str(home / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude*"))
    cands = [c for c in cands if c.endswith("claude.exe") or c.endswith("claude")]

    def ver(p: str):
        m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)
        return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)

    return sorted(cands, key=ver)[-1] if cands else None


class AIAnswerer:
    def __init__(self, resume_text: str, model: str | None = None, timeout: int = 90):
        self.cli = find_claude_cli()
        self.resume_text = resume_text
        self.model = model or os.environ.get("JARVIS_MODEL", "sonnet")
        self.timeout = timeout
        self.cache: dict[str, str | None] = {}

    @property
    def available(self) -> bool:
        return bool(self.cli and self.resume_text)

    def answer(self, question: str, kind: str, options: list[str]) -> str | None:
        if not self.available:
            return None
        key = f"{kind}|{question}|{'|'.join(options)}"
        if key in self.cache:
            return self.cache[key]
        prompt = (
            f"CANDIDATE PROFILE:\n{self.resume_text}\n\nFIELD: {question}\nFIELD TYPE: {kind}\n"
            + (f"OPTIONS: {json.dumps(options, ensure_ascii=False)}\n" if options else "")
        )
        cmd = [self.cli, "-p", prompt, "--output-format", "json", "--tools", "", "--model", self.model, "--system-prompt", SYSTEM]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout)
            data = json.loads(proc.stdout)
            m = re.search(r"\{.*\}", str(data.get("result") or ""), re.S)
            obj = json.loads(m.group(0)) if m else {}
        except Exception as exc:  # noqa: BLE001
            log.warning("AI fallback failed for '%s': %s", question[:60], exc)
            return None
        ans = obj.get("answer")
        ans = str(ans).strip() if ans not in (None, "") else None
        if ans and options and ans not in options:
            low = {o.lower(): o for o in options}
            ans = low.get(ans.lower())
        if ans and re.search(r"\(in (days|years|months|lpa|lakhs|inr|rs)\)|in days|number of|how many", question.lower()):
            m = re.search(r"\d+(\.\d+)?", ans)
            ans = m.group(0) if m else ans
        if ans and kind == "number":
            m = re.search(r"\d+(\.\d+)?", ans)
            ans = m.group(0) if m else None
        log.info("AI fallback: '%s' -> %r (%s)", question[:60], ans, obj.get("reason", ""))
        self.cache[key] = ans
        return ans
