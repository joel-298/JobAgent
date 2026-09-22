"""Jarvis's brain: Claude via the Claude Code CLI in headless mode.

Uses your Claude subscription login (no API key). Set ANTHROPIC_API_KEY in the
environment to use the API instead - the CLI picks it up automatically.
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

log = logging.getLogger("jarvis")

ACTIONS = {"run_job_search", "start_applying", "stop_run", "continue_run"}
LANGS = {"en", "hi"}
_NON_LATIN = re.compile("[\u0900-\u097F\u0600-\u06FF]")  # Devanagari, Arabic/Urdu

SYSTEM_PROMPT = """You are Jarvis, the user's personal job-application assistant. You control two local agents:
- agent1 "job search": finds LinkedIn Easy Apply jobs (India, last 24h) and adds them to an Excel sheet with the resume to use (Java or MERN).
- agent2 "apply": applies to every PENDING row with the chosen resume, then sends connection notes to 1 HR person and 1 developer per company.

Every user message comes with a STATE block (current run status, jobs found with short job descriptions, Excel statuses, connection log). Answer questions from that data; be specific (company names, roles, locations, which resume). If something is not in the data, say so.

Rules:
1. Reply ONLY with one JSON object:
   {"say": "<subtitle text>", "speak": "<text for text-to-speech>", "lang": "en"|"hi", "action": <"run_job_search"|"start_applying"|"stop_run"|"continue_run"|null>, "set_language": "en"|"hi"|null}
2. "say" is shown as subtitles and "speak" is read aloud: conversational, concise, no markdown, no bullet symbols, no URLs. Summaries: name each company, the role, and a one-sentence gist of the JD, plus the resume chosen.

LANGUAGE RULES (very important):
- You understand English, Hindi and Hinglish, written in any script.
- STATE.preferred_reply_language tells you which language to answer in: "en" = English (default), "hi" = Hindi.
- If the user asks you to switch ("reply in Hindi", "Hindi mein bolo", "English please"), set "set_language" to the new code and answer in that language from then on.
- English mode: "say" and "speak" are both plain English, "lang": "en".
- Hindi mode: talk in natural conversational Hindi (Hinglish is fine). "say" (the subtitle) MUST use ONLY the Latin/English alphabet - romanised Hindi such as "Aaj maine 20 jobs dhoondhi hain" - NEVER Devanagari, Urdu, Sanskrit or any other script. "speak" is the same sentence in Devanagari script so the Hindi voice pronounces it well, "lang": "hi". Company names, roles and technical words stay in English.
- Never mix scripts inside "say".
3. Only set action "run_job_search" when the user asks to search/find jobs. Only set "start_applying" when the user clearly confirms (e.g. "yes", "start applying", "go ahead") after applying was offered or requested. Never start applying on your own initiative.
4. If a run is already in progress, do not start another; tell the user what is running.
5. When a run needs human help (captcha, login, unknown form question), the state says so: explain what to do in the browser and tell them to say "continue" or press Continue when done -> then use action "continue_run".
6. After a job search finishes, summarise the results and ask: "Should I start applying to these now?"
7. After an apply run finishes, report what completed, what paused and why, and how many connection requests were sent.
8. Keep it friendly and brief. The user's name is Joel.

CANDIDATE PROFILE (Joel's resume - use it to answer questions about his background):
{resume}"""


def _resume_text() -> str:
    try:
        import yaml

        cfg = Path(__file__).resolve().parent.parent / "agent2" / "config" / "answers.yaml"
        raw = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return str(raw.get("resume_text") or "").strip() or "(no resume configured)"
    except Exception:  # noqa: BLE001
        return "(no resume configured)"


def find_claude_cli() -> str | None:
    env = os.environ.get("CLAUDE_CLI")
    if env and Path(env).exists():
        return env
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    home = Path.home()
    candidates = glob.glob(str(home / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude.exe"))
    candidates += glob.glob(str(home / ".vscode" / "extensions" / "anthropic.claude-code-*" / "resources" / "native-binary" / "claude"))
    if candidates:
        # highest version last
        def ver(p: str):
            m = re.search(r"claude-code-(\d+)\.(\d+)\.(\d+)", p)
            return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
        return sorted(candidates, key=ver)[-1]
    return None


class Brain:
    def __init__(self, model: str | None = None, timeout: int = 120):
        self.cli = find_claude_cli()
        self.model = model or os.environ.get("JARVIS_MODEL", "sonnet")
        self.timeout = timeout
        self.session_id: str | None = None
        if not self.cli:
            log.error("Claude Code CLI not found. Install Claude Code or set CLAUDE_CLI=<path to claude.exe>")

    @property
    def available(self) -> bool:
        return bool(self.cli)

    def reset(self) -> None:
        self.session_id = None

    def ask(self, user_text: str, state: dict) -> dict:
        """Return {"say": str, "action": str|None}. Never raises."""
        if not self.cli:
            return {"say": "My brain is offline: I couldn't find the Claude Code CLI on this computer.", "speak": "", "lang": "en", "action": None, "set_language": None}
        prompt = f"STATE:\n{json.dumps(state, ensure_ascii=False)}\n\nUSER: {user_text}"
        cmd = [self.cli, "-p", prompt, "--output-format", "json", "--tools", "", "--model", self.model]
        if self.session_id:
            cmd += ["--resume", self.session_id]
        else:
            cmd += ["--system-prompt", SYSTEM_PROMPT.replace("{resume}", _resume_text())]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return {"say": "Sorry, thinking took too long. Please try again.", "speak": "", "lang": "en", "action": None, "set_language": None}
        except OSError as exc:
            log.error("CLI launch failed: %s", exc)
            return {"say": "I couldn't start my brain process.", "speak": "", "lang": "en", "action": None, "set_language": None}
        if proc.returncode != 0:
            log.error("claude CLI failed (%s): %s", proc.returncode, (proc.stderr or proc.stdout)[:500])
            if self.session_id:  # a stale session can fail to resume; retry fresh once
                self.session_id = None
                return self.ask(user_text, state)
            return {"say": "Something went wrong while thinking. Please try again.", "speak": "", "lang": "en", "action": None, "set_language": None}
        try:
            data = json.loads(proc.stdout)
        except ValueError:
            data = {"result": proc.stdout}
        self.session_id = data.get("session_id") or self.session_id
        return self._parse(data.get("result") or "")

    @staticmethod
    def _parse(text: str) -> dict:
        text = text.strip()
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                obj = json.loads(m.group(0))
                say = str(obj.get("say") or "").strip()
                speak = str(obj.get("speak") or "").strip() or say
                lang = obj.get("lang") if obj.get("lang") in LANGS else "en"
                action = obj.get("action")
                action = action if action in ACTIONS else None
                set_language = obj.get("set_language") if obj.get("set_language") in LANGS else None
                if say and _NON_LATIN.search(say):
                    # Subtitles must stay in the Latin alphabet: strip any other script.
                    say = _NON_LATIN.sub("", say).strip() or "(reply given by voice)"
                if say:
                    return {"say": say, "speak": speak, "lang": lang, "action": action, "set_language": set_language}
            except ValueError:
                pass
        return {"say": text or "Sorry, I didn't catch that.", "speak": text, "lang": "en", "action": None, "set_language": None}
