# LinkedIn Job Application & Networking Agent

Personal productivity tool that works through an Excel list of jobs: applies
with **Easy Apply** using the resume you name, opens the company page, and
sends connection requests with your prepared notes to HR/recruiting people and
to software developers. Progress is tracked in the Excel file and in SQLite so
an interrupted run can be resumed.

It drives a real browser through LinkedIn's normal UI. It never touches your
password, never calls private APIs, and **stops and waits for you** whenever
LinkedIn shows a login, CAPTCHA or verification screen.

## Setup

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium        # once
python app.py --init-excel                   # creates data/jobs.xlsx
```

Fill `data/jobs.xlsx` (one row per job):

| column | meaning |
|---|---|
| `job_link` | LinkedIn job URL (`https://www.linkedin.com/jobs/view/...`) |
| `resume_name` | Name of the resume as shown in LinkedIn's Easy Apply resume picker |
| `company_link` | LinkedIn company URL (`https://www.linkedin.com/company/...`) |
| `hr_message_<type>` | Connection note for HR / recruiters, one column per resume type, e.g. `hr_message_java`, `hr_message_mern`, `hr_message_multi` (max 300 chars) |
| `developer_message_<type>` | Referral note for developers, same types, e.g. `developer_message_java` (max 300 chars) |

The `<type>` whose name appears in `resume_name` decides which pair is used:
`resume_name = Joel_Matthew_Mern_3.pdf` -> `hr_message_mern` + `developer_message_mern`.
Only that pair needs to be filled for the row. Add more types by adding
columns (`hr_message_python`, `developer_message_python`, ...). Plain
`hr_message` / `developer_message` columns act as a default pair.

Leave `status` empty or `PENDING`. The agent fills the tracking columns
(`status`, `application_status`, `hr_connections_sent`,
`developer_connections_sent`, `last_error`, `completed_at`) and never
overwrites your input columns.

## Run

```bash
python app.py --dry-run     # opens pages, validates, sends NOTHING
python app.py --test-one    # one row end-to-end (do this first)
python app.py               # all PENDING rows
python app.py --resume      # continue PAUSED / IN_PROGRESS rows without asking
python app.py --status      # progress table, no browser
```

First run: a browser window opens on LinkedIn. Log in there yourself, then
press ENTER in the terminal. The session is kept in `browser_profile/` so you
don't have to log in again.

While it runs the terminal shows the current row, step and counts. When it
needs you (CAPTCHA, unknown application question, resume not found, external
application site) it prints a `HUMAN INTERVENTION REQUIRED` box, leaves the
browser open, and waits for ENTER (`q` + ENTER stops the run).

## Configuration - `config/settings.yaml`

* `networking.hr_min/hr_max`, `developer_min/developer_max` - how many
  requests per company. Defaults are **2 / 2** for the one-job MVP test; raise
  them (spec suggests 5-10 HR, 10-15 developers) once a full run works.
* `networking.*_search_terms` / `*_title_keywords` - what to search and which
  headlines count. Developer phase also has `developer_exclude_keywords`.
* `networking.send_without_note_if_unavailable` - LinkedIn limits free notes;
  `false` (default) skips such profiles, `true` sends without a note.
* `application.external_apply` - `pause` (ask you to apply manually) or `skip`.
* Application questions are answered from **`config/answers.yaml`**:
  years of experience with any listed tech keyword, total experience, current
  location, willing to relocate, current / expected salary (auto-converted to
  LPA or per-month when the question asks for it), and Yes/No questions
  matching `yes_to`. Add your own `extra_rules` (question substring -> answer).
  Pre-filled fields are never changed; any other required question pauses
  for you.
* `delays.*` - random pacing ranges in seconds.
* `browser.channel` - `chromium` (bundled), `chrome` or `msedge` (installed).
* `run.resume_paused` - `ask` / `yes` / `no`; `run.retry_failed` - `retry` / `skip`.

## How a row is processed

```
open job_link -> Easy Apply -> select resume_name -> Next/Review -> Submit
open company_link -> People -> search HR terms -> connect with hr_message (x N)
                            -> search developer terms -> connect with developer_message (x M)
all phases OK -> status = COMPLETED
anything else -> status = PAUSED, last_error = [STEP] reason, screenshot saved
```

Rules the code enforces:

* the resume is selected only when it confidently matches `resume_name`;
  otherwise the row pauses - a different resume is never chosen
* profiles that are already connected, pending, or were contacted in any
  earlier run are skipped (`data/agent.db` keeps the log)
* notes are your Excel text, verbatim
* `COMPLETED` is written only after application + HR minimum + developer
  minimum are all satisfied

## Recovery

`PAUSED` rows keep their progress (`current_step`, sent counts) in
`data/agent.db`. Fix the cause (e.g. rename the resume in Excel, finish the
verification in the browser) and run `python app.py --resume`; finished phases
are not repeated. To restart a row from scratch delete its record from
`data/agent.db` (or delete the file to reset everything).

## Files

```
app.py                CLI
config.py             settings / paths
config/settings.yaml  all limits and keywords
data/jobs.xlsx        your input (created by --init-excel)
data/agent.db         SQLite state
logs/agent.log        full log
screenshots/          row_00N_<reason>.png on problems
browser_profile/      persistent browser login
src/                  browser, excel_manager, state_manager, job_application,
                      company_people, networking, runner, selectors, ...
tests/                pytest (offline, uses mock LinkedIn-like pages)
```

Run the tests with `python -m pytest`.

## Notes

* LinkedIn's markup changes; all selectors live in `src/selectors.py`.
* Keep `browser_profile/`, `data/agent.db`, `logs/`, `screenshots/` private
  (they are in `.gitignore`).
* Start with one job, then 3, 5, 10... as the spec recommends.
