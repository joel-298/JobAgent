# Agent 1 - job finder

Searches LinkedIn Jobs (India, past 24h, Easy Apply only) and appends PENDING
rows to `../agent2/data/jobs.xlsx`, choosing the Java or MERN resume from the
job description and filling the matching message columns.

    python agent1/app.py --dry-run   # preview
    python agent1/app.py             # add rows
    python agent2/app.py             # then apply

Settings: `config/search.yaml` (keywords, filters, excluded titles, resume
rules, message texts). It reuses agent2's browser login and settings.
