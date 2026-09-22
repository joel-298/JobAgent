"""Jarvis server: chat/voice UI + orchestration of agent1 and agent2.

    python frontend/server.py            -> http://localhost:8000

Uses your Claude Code login for the conversation (see brain.py).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import state as st  # noqa: E402
from brain import Brain  # noqa: E402
from runner import AgentRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("jarvis")

app = FastAPI(title="Jarvis")
clients: set[WebSocket] = set()
history: list[dict] = []  # {"role": "user"|"jarvis", "text": ...}
brain = Brain()
runner: AgentRunner | None = None
brain_lock = asyncio.Lock()
run_context: dict = {}  # what we captured before a run started, to summarise after
prefs: dict = {"reply_language": "en"}  # "en" or "hi" (subtitles are always Latin alphabet)

GREETING = "Hi Joel, Jarvis here. Say \"run a job search\" and I'll find today's LinkedIn jobs, or ask me about the ones already in your sheet."


async def broadcast(event: dict) -> None:
    dead = []
    for ws in list(clients):
        try:
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        clients.discard(ws)


def full_state() -> dict:
    s = st.snapshot()
    s["run"] = runner.status() if runner else {"running": False}
    s["brain"] = {"available": brain.available, "model": brain.model}
    s["prefs"] = dict(prefs)
    return s


def brain_state() -> dict:
    s = st.snapshot(for_brain=True)
    s["run"] = runner.status() if runner else {"running": False}
    s["preferred_reply_language"] = prefs["reply_language"]
    return s


async def say(text: str, action: str | None = None, speak: str = "", lang: str = "en") -> None:
    history.append({"role": "jarvis", "text": text})
    await broadcast({"type": "reply", "text": text, "speak": speak or text, "lang": lang, "action": action})


async def apply_reply(reply: dict) -> None:
    if reply.get("set_language") and reply["set_language"] != prefs["reply_language"]:
        prefs["reply_language"] = reply["set_language"]
        await push_state()
    await say(reply["say"], reply.get("action"), reply.get("speak", ""), reply.get("lang", "en"))


async def push_state() -> None:
    await broadcast({"type": "state", "state": full_state()})


# ---------- run lifecycle ----------
async def start_run(agent: str) -> bool:
    assert runner is not None
    if runner.running:
        await say(f"A {runner.agent.replace('_', ' ')} run is already in progress.")
        return False
    if not st._settings().paths.excel.exists() and agent == "apply":
        await say("There is no jobs sheet yet. Run a job search first.")
        return False
    run_context.clear()
    run_context["started"] = time.time()
    run_context["job_ids_before"] = set(st.jobs_found().keys())
    run_context["rows_before"] = {r["excel_row"]: r for r in st.excel_rows() if "error" not in r}
    run_context["conns_before"] = len(st.connections(1000))
    ok = runner.start(agent, on_finished)
    if ok:
        await broadcast({"type": "run_started", "agent": agent})
        await push_state()
    return ok


async def on_finished(agent: str, code: int, lines: list[str]) -> None:
    await push_state()
    summary = build_summary(agent, code, lines)
    await broadcast({"type": "run_finished", "agent": agent, "code": code, "summary": summary})
    event_text = (
        f"[EVENT] The {agent.replace('_', ' ')} run finished (exit code {code}). Summary data: "
        f"{json.dumps(summary, ensure_ascii=False)}. Tell the user what happened"
        + (" and ask whether you should start applying now." if agent == "job_search" and summary.get("new_jobs") else ".")
    )
    async with brain_lock:
        reply = await asyncio.get_event_loop().run_in_executor(None, brain.ask, event_text, brain_state())
    reply["action"] = None
    await apply_reply(reply)


def build_summary(agent: str, code: int, lines: list[str]) -> dict:
    summary: dict = {"agent": agent, "exit_code": code}
    if agent == "job_search":
        found = st.jobs_found()
        new_ids = [i for i in found if i not in run_context.get("job_ids_before", set())]
        summary["new_jobs"] = [
            {k: found[i].get(k, "") for k in ("title", "company", "location", "resume_name", "type")}
            | {"description": (found[i].get("description") or "")[:300]}
            for i in new_ids
        ]
        if not new_ids:  # dry run: nothing saved, read the log instead
            import re

            for ln in lines:
                m = re.search(r"would add: (.*) @ (.*) -> (\S+)", ln)
                if m:
                    summary["new_jobs"].append({"title": m.group(1), "company": m.group(2), "resume_name": m.group(3), "dry_run": True})
        skipped = [ln for ln in lines if ln.startswith("Skipped:")]
        summary["skipped"] = skipped[-1] if skipped else ""
    else:
        before = run_context.get("rows_before", {})
        after = {r["excel_row"]: r for r in st.excel_rows() if "error" not in r}
        found = st.jobs_found()
        changed = []
        for row_id, r in after.items():
            b = before.get(row_id)
            if not b or b["status"] != r["status"] or b["hr_sent"] != r["hr_sent"] or b["dev_sent"] != r["dev_sent"]:
                f = found.get(st._job_id(r["job_link"]), {})
                changed.append({"company": f.get("company", ""), "title": f.get("title", ""), "status": r["status"],
                                "application": r["application_status"], "hr_sent": r["hr_sent"], "dev_sent": r["dev_sent"],
                                "error": r["last_error"]})
        summary["rows_changed"] = changed
        summary["connections_sent_this_run"] = len(st.connections(1000)) - run_context.get("conns_before", 0)
        summary["totals"] = st.snapshot(for_brain=True)["totals"]
    return summary


# ---------- chat ----------
async def handle_chat(text: str) -> None:
    text = text.strip()
    if not text:
        return
    history.append({"role": "user", "text": text})
    await broadcast({"type": "user", "text": text})
    await broadcast({"type": "thinking"})
    async with brain_lock:
        reply = await asyncio.get_event_loop().run_in_executor(None, brain.ask, text, brain_state())
    await apply_reply(reply)
    await do_action(reply.get("action"))


async def do_action(action: str | None) -> None:
    if not action or runner is None:
        return
    if action == "run_job_search":
        await start_run("job_search")
    elif action == "start_applying":
        await start_run("apply")
    elif action == "continue_run":
        if runner.continue_run():
            await say("Continuing.")
        await push_state()
    elif action == "stop_run":
        if runner.stop():
            await say("Stopping the current run.")
        await push_state()


# ---------- routes ----------
@app.get("/")
async def index():
    return FileResponse(HERE / "web" / "index.html")


@app.get("/api/state")
async def api_state():
    return full_state()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "hello", "state": full_state(), "history": history[-40:], "greeting": GREETING if not history else None}, ensure_ascii=False))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            t = msg.get("type")
            if t == "chat":
                asyncio.create_task(handle_chat(str(msg.get("text", ""))))
            elif t == "action":
                name = msg.get("name")
                if name in ("run_job_search", "start_applying", "continue_run", "stop_run"):
                    await do_action(name)
            elif t == "state":
                await ws.send_text(json.dumps({"type": "state", "state": full_state()}, ensure_ascii=False))
            elif t == "set_language" and msg.get("lang") in ("en", "hi"):
                prefs["reply_language"] = msg["lang"]
                await push_state()
            elif t == "reset_brain":
                brain.reset()
                history.clear()
                await ws.send_text(json.dumps({"type": "reply", "text": "Memory cleared. " + GREETING}))
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)


app.mount("/static", StaticFiles(directory=str(HERE / "web")), name="static")


from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global runner
    runner = AgentRunner(broadcast, asyncio.get_event_loop())
    if not brain.available:
        log.error("Claude Code CLI not found - set CLAUDE_CLI=<path to claude.exe>")
    else:
        log.info("Brain: %s (model %s)", brain.cli, brain.model)
    log.info("Jarvis ready: open http://localhost:8000")
    yield


app.router.lifespan_context = lifespan


def _port_free(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


if __name__ == "__main__":
    port = int(os.environ.get("JARVIS_PORT", "8000"))
    if not _port_free(port):
        print(f"\nJarvis is already running (port {port} is in use).")
        print(f"  -> just open http://localhost:{port}")
        print("  -> or stop the old one first:  Get-Process python | Stop-Process   (PowerShell)")
        sys.exit(1)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
