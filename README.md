# LinkedIn Job Application Automation

## Jarvis (voice / chat control)

```bash
python -m pip install -r frontend/requirements.txt     # once
python frontend/server.py                              # then open http://localhost:8000
```

Talk or type: "Jarvis, run a job search" -> it runs agent1, then tells you every
company, role and a one-line JD, and asks "Should I start applying?" -> say
"yes" -> it runs agent2 and reports what completed / paused and how many
connection requests went out. Ask anything about the jobs in between.

* **Language rule:** Jarvis understands English, Hindi and Hinglish (spoken or typed,
  any script). It replies in English by default; say "Hindi mein bolo" / pick
  "Reply in: Hindi" to get Hindi. Subtitles (the chat text) are ALWAYS written
  in the English/Latin alphabet - Hinglish like "Aaj 20 jobs mili hain" - never
  Devanagari, Urdu or Sanskrit script; only the voice speaks in Hindi.
  "Mic hears" sets the speech-recognition language (English / Hindi).
* **Voice chat mode** (switch in the sidebar) keeps the mic listening all the time and pauses while Jarvis speaks; off = mic button is push-to-talk and you type prompts. Settings tab: reply language, mic language, voice selection (Edge "Natural" voices sound best), speech rate, optional wake word.
* Views: Command Center (stats, AI core, conversation, agents, latest jobs), Jobs Sheet (full Excel table with search/filters), Connections, Live Log, Settings.
* Mic button = push to talk; "Hands-free" keeps listening (say "Jarvis ..." first).
* When LinkedIn needs you (captcha, unknown form question) a yellow banner appears:
  fix it in the browser window, then say "continue" or press the button.
* The brain runs on your Claude Code login (no API key). Set `JARVIS_MODEL=opus`
  for a stronger model, or add `ANTHROPIC_API_KEY` to switch to the API.
* Windows Firewall asks once because the server also listens for your phone on
  the same Wi-Fi; declining keeps it PC-only (localhost still works).

## Manual mode

Two agents, run manually one after the other:

| step | command | what it does |
|---|---|---|
| 1 | `python agent1/app.py` | searches LinkedIn Jobs (India, past 24 h, Easy Apply only), picks the Java or MERN resume from each job description and appends `PENDING` rows to `agent2/data/jobs.xlsx` |
| 2 | review `agent2/data/jobs.xlsx` | delete rows you don't want |
| 3 | `python agent2/app.py` | applies with the chosen resume, connects with HR + developers, marks rows `COMPLETED` |

Useful extras: `python agent1/app.py --dry-run`, `python agent2/app.py --status`,
`python agent2/app.py --connections`.

Config: `agent1/config/search.yaml` (keywords, filters, message texts),
`agent2/config/settings.yaml` (limits, delays), `agent2/config/answers.yaml`
(application question answers). Details in each agent's README.

Setup once: `python -m pip install -r agent2/requirements.txt` and
`python -m playwright install chromium`. Log in to LinkedIn in the browser
window on the first run; the session is kept in `agent2/browser_profile/`.
