# LinkedIn Job Application & Networking Automation Agent

## 1. Problem Statement

Applying for jobs and doing targeted networking manually is consuming a large portion of my day.

For each selected job, I currently need to:

1. Open the LinkedIn job posting.
2. Complete the LinkedIn application / Easy Apply flow.
3. Select the appropriate resume.
4. Open the company's LinkedIn page.
5. Find relevant HR / Talent Acquisition / Recruiting professionals.
6. Send connection requests with a prepared note.
7. Find software developers/engineers at the same company.
8. Send connection requests with a separate referral-oriented message.
9. Track which companies have been completed.

The goal of this project is to automate this repetitive browser work so I can spend my time on interview preparation, DSA, system design, learning, and other productive tasks.

This is a personal productivity tool. It is **not intended to bypass LinkedIn security systems, CAPTCHAs, rate limits, authentication, or other platform safeguards**. The automation should stop and request human intervention whenever LinkedIn requires verification or presents a flow the agent cannot safely handle.

---

## 2. Primary Objective

Build a Python-based browser automation agent that:

- Reads a user-prepared Excel file.
- Processes selected LinkedIn jobs sequentially.
- Opens each job URL in a real browser session.
- Completes the LinkedIn application flow where possible.
- Selects the resume specified in the Excel row.
- Opens the company LinkedIn profile specified in the same row.
- Searches for HR / Talent Acquisition / Recruiting people.
- Sends connection requests with the HR message from the Excel row.
- Searches for software developers/engineers.
- Sends connection requests with the referral message from the Excel row.
- Marks the row as `COMPLETED` only after the complete workflow succeeds.
- Saves progress so an interrupted run can be resumed.
- Uses configurable delays between actions and jobs.
- Stops for human intervention when CAPTCHA, verification, login problems, or an unexpected UI state occurs.

The first version must be tested on **ONE JOB ONLY** before being used for multiple jobs.

---

# 3. Technology Stack

Recommended stack:

- Python 3.11+
- Playwright for browser automation
- pandas + openpyxl for Excel handling
- SQLite for persistent execution state
- python-dotenv for configuration
- logging module for logs
- Optional: Pydantic for configuration validation

Suggested project structure:

```text
linkedin-job-agent/
│
├── app.py
├── config.py
├── requirements.txt
├── .env.example
├── README.md
│
├── config/
│   └── settings.yaml
│
├── data/
│   ├── jobs.xlsx
│   └── agent.db
│
├── logs/
│   └── agent.log
│
├── screenshots/
│
├── src/
│   ├── browser.py
│   ├── excel_manager.py
│   ├── state_manager.py
│   ├── job_application.py
│   ├── company_people.py
│   ├── networking.py
│   ├── selectors.py
│   ├── human_intervention.py
│   └── utils.py
│
└── tests/
    └── test_excel.py
```

---

# 4. Excel Input Format

The user will manually prepare and review the Excel file before execution.

Each row represents one job/company workflow.

The Excel file will contain exactly five primary input columns:

| Column | Name | Purpose |
|---|---|---|
| 1 | `job_link` | LinkedIn job/application URL |
| 2 | `resume_name` | Name of the resume that must be selected during the LinkedIn application |
| 3 | `company_link` | LinkedIn company profile URL |
| 4 | `hr_message` | Connection note/message for HR, Talent Acquisition, Recruiters |
| 5 | `developer_message` | Connection note/message for software developers/engineers |

The implementation may add tracking columns without changing the five required input fields.

Recommended tracking columns:

| Column | Purpose |
|---|---|
| `status` | PENDING / IN_PROGRESS / COMPLETED / PAUSED / FAILED |
| `application_status` | Application-specific result |
| `hr_connections_sent` | Number of HR/recruiter requests attempted |
| `developer_connections_sent` | Number of developer requests attempted |
| `last_error` | Last error encountered |
| `completed_at` | Completion timestamp |

The original five user-input columns must never be overwritten.

---

# 5. Example Excel

```text
job_link | resume_name | company_link | hr_message | developer_message
https://www.linkedin.com/jobs/view/123 | Java Developer Resume | https://www.linkedin.com/company/example | Hi, I recently applied... | Hi, I recently applied for...
```

The user should review and approve every row before the agent processes it.

---

# 6. Browser Session

The agent should use a persistent browser profile so that the user does not need to log into LinkedIn every time.

Example concept:

```text
browser_profile/
```

The first execution can allow the user to manually log in.

After login, the persistent session should be reused.

Do NOT store the LinkedIn password in source code, Excel, `.env`, or logs.

---

# 7. High-Level Workflow

For every Excel row:

```text
READ ROW
   ↓
Validate required fields
   ↓
Open job_link
   ↓
Verify job/application page
   ↓
Start LinkedIn application
   ↓
Select resume specified by resume_name
   ↓
Fill supported application fields
   ↓
Review application
   ↓
Submit application where appropriate
   ↓
Open company_link
   ↓
Open company's People section
   ↓
Find HR / Talent Acquisition / Recruiting people
   ↓
Send configured number of connection requests with hr_message
   ↓
Clear HR-related filters
   ↓
Search software developers/engineers
   ↓
Send configured number of connection requests with developer_message
   ↓
Validate workflow completion
   ↓
Mark Excel row COMPLETED
   ↓
Persist state to SQLite
   ↓
Wait configured delay
   ↓
Process next row
```

---

# 8. Job Application Workflow

## Step 1 — Read Excel

Load the next row whose status is:

```text
PENDING
```

Do not process rows already marked:

```text
COMPLETED
```

If a row is `PAUSED` or `FAILED`, behavior should be configurable.

---

## Step 2 — Open Job URL

Launch the persistent browser.

Navigate to:

```text
job_link
```

Wait for the page to load.

The agent should verify that it is on a LinkedIn job/application page before continuing.

If the page cannot be recognized:

```text
PAUSE
SAVE ERROR
REQUEST HUMAN INTERVENTION
```

---

# 9. LinkedIn Application

The agent should attempt to use the normal LinkedIn browser UI.

It should NOT call undocumented/private LinkedIn APIs.

The automation should:

1. Find the applicable application button.
2. Open the application form.
3. Navigate through the form.
4. Select the resume specified in `resume_name`.
5. Fill only fields that the agent has been explicitly configured to handle.
6. Preserve user-defined answers/configuration.
7. Review the final application screen.
8. Submit only when the workflow is recognized as valid.

---

# 10. Resume Selection

The Excel `resume_name` field determines which resume must be selected.

Example:

```text
resume_name = Java Developer Resume
```

The agent should search the visible LinkedIn resume-selection UI for that resume.

The matching should be robust to minor UI variations such as:

```text
Java Developer Resume
Java Developer Resume.pdf
Java Developer
```

However, the agent must NOT silently select a different resume if the requested resume cannot be confidently identified.

If the requested resume cannot be found:

```text
PAUSE
STATUS = PAUSED
SAVE ERROR
ASK USER
```

---

# 11. Application Questions

The initial version should not attempt to intelligently answer every possible custom question.

Support should initially focus on predictable UI operations.

For unknown questions:

```text
Take screenshot
Save current URL
Save visible question text where possible
Pause
Request human intervention
```

This makes the first version safer and easier to test.

A future version can add a configurable question/answer profile.

---

# 12. CAPTCHA / Verification Handling

This is critical.

If the agent encounters:

- CAPTCHA
- security verification
- unusual login challenge
- identity verification
- suspicious activity warning
- two-factor authentication
- unexpected account verification

the agent must:

```text
STOP AUTOMATION
SAVE CURRENT STATE
SAVE SCREENSHOT
LOG EVENT
WAIT FOR USER
```

The agent must NOT attempt to solve, evade, bypass, or defeat the verification.

After the user completes the required verification manually, the agent may resume from the saved state.

---

# 13. Company Page Workflow

After the job application is successfully completed:

```text
OPEN company_link
```

The agent should navigate to the company's LinkedIn page.

Then:

```text
People
```

The agent should locate the company's people/member discovery section using visible UI.

---

# 14. HR / Talent Acquisition Search

The first networking phase searches for people associated with:

- HR
- Human Resources
- Talent Acquisition
- Talent
- Recruiter
- Recruiting
- Technical Recruiter
- Talent Partner
- People Operations

Search/filter terms should be configurable.

The agent should NOT assume that every profile returned is actually responsible for hiring.

It should use the visible title/headline information.

---

# 15. HR Connection Requests

The agent should process a configurable number of relevant profiles.

Default target:

```text
minimum = 5
maximum = 10
```

The exact number should be configurable in:

```text
config/settings.yaml
```

For each suitable profile:

1. Open the profile.
2. Determine whether already connected.
3. If already connected, do not send another connection request.
4. If not connected, open the connection flow.
5. Select `Add a note` when available.
6. Paste the `hr_message` from the Excel row.
7. Send the connection request.
8. Log the result.
9. Continue to the next profile.

The same message from the row may be reused for the HR targets.

---

# 16. Already Connected Users

If the person is already connected:

```text
DO NOT SEND DUPLICATE CONNECTION REQUEST
```

The agent should log:

```text
ALREADY_CONNECTED
```

Whether to send a separate direct message to existing connections should be disabled in the MVP.

---

# 17. Developer Search

After completing the HR/recruiter phase:

```text
CLEAR HR/TALENT FILTERS
```

Then search for:

- Software Engineer
- Software Developer
- Backend Engineer
- Frontend Engineer
- Full Stack Engineer
- SDE
- Developer
- Engineering

The exact search terms should be configurable.

---

# 18. Developer Referral Outreach

Default target:

```text
minimum = 10
maximum = 15
```

For each relevant developer:

1. Open profile.
2. Check connection status.
3. If already connected, do not send a duplicate connection request.
4. If not connected, click Connect.
5. Click `Add a note` where available.
6. Paste `developer_message`.
7. Send request.
8. Log result.
9. Continue.

The developer message is intended to be the user's pre-written referral-oriented message.

Example concept:

```text
Hi, I recently applied for a Software Engineer role at your company.
If you feel my profile is relevant, I would really appreciate it if you
could refer me or share my resume with the appropriate HR/recruiting team.
Thank you!
```

The actual message must come from Excel, not be hardcoded.

---

# 19. Important Networking Rules

The agent should:

- Never send duplicate connection requests.
- Never message someone who is already connected in the MVP.
- Never invent a person's name.
- Never alter the user's message unless explicitly configured to do so.
- Never send messages to people outside the configured target categories.
- Never continue if the LinkedIn UI becomes ambiguous.
- Log every attempted connection.

---

# 20. Configurable Limits

Create:

```text
config/settings.yaml
```

Example:

```yaml
networking:
  hr_min: 5
  hr_max: 10

  developer_min: 10
  developer_max: 15

delays:
  between_profiles_min: 20
  between_profiles_max: 60

  between_actions_min: 2
  between_actions_max: 8

  between_companies_min: 120
  between_companies_max: 300
```

These are normal pacing controls for reliability and user workflow management.

They are NOT intended to circumvent LinkedIn safeguards.

---

# 21. Randomized Delays

The agent should avoid executing every action with exactly the same fixed delay.

For reliability, configurable delays may use a random value inside a user-defined range.

Example:

```python
sleep(random.uniform(20, 60))
```

The goal is to prevent brittle automation caused by clicking faster than the page/UI can respond.

It must NOT be represented as a method for defeating platform detection.

---

# 22. State Management

Excel alone should not be the only state store.

Use SQLite as the reliable execution state.

Example:

```text
agent.db
```

Suggested table:

```text
job_runs
```

Fields:

```text
id
excel_row
job_link
company_link
status
application_status
hr_attempted
hr_successful
developer_attempted
developer_successful
current_step
last_error
started_at
updated_at
completed_at
```

---

# 23. Excel Completion

The Excel row should be marked:

```text
COMPLETED
```

ONLY after:

1. Application workflow completed successfully.
2. HR/Talent outreach completed according to configured target rules.
3. Developer outreach completed according to configured target rules.
4. Results were persisted.
5. No unresolved critical error exists.

Then write:

```text
status = COMPLETED
```

and:

```text
completed_at = current timestamp
```

---

# 24. Partial Failure

The agent must NOT mark a row completed if only part of the workflow succeeded.

Examples:

### Application succeeds, HR search fails

```text
status = PAUSED
current_step = HR_SEARCH
```

### HR outreach succeeds, developer search fails

```text
status = PAUSED
current_step = DEVELOPER_SEARCH
```

### Browser crashes

```text
status = PAUSED
current_step = last known step
```

The user should be able to resume the row later.

---

# 25. Resume / Recovery

On startup:

```text
Load SQLite state
↓
Find PENDING / PAUSED / IN_PROGRESS rows
↓
Ask user whether to resume interrupted work
```

The agent should avoid repeating already completed actions.

For example, if:

```text
application_status = COMPLETED
hr_successful = 7
developer_successful = 0
```

the agent should resume from developer outreach rather than re-applying to the job.

---

# 26. Logging

Every important action should be logged.

Example:

```text
[21:05:10] Starting row 4
[21:05:15] Opening job URL
[21:05:29] Application form detected
[21:05:35] Resume selected: Java Developer Resume
[21:06:20] Application submitted
[21:06:35] Opening company page
[21:07:10] HR search started
[21:07:45] Connection request sent: Profile A
[21:08:30] Already connected: Profile B
[21:12:10] HR target reached: 7
[21:12:25] Developer search started
...
[21:20:40] Developer target reached: 12
[21:20:45] Row 4 COMPLETED
```

Logs should never contain passwords, cookies, session tokens, or other secrets.

---

# 27. Screenshots

Take screenshots when:

- An unexpected page appears.
- CAPTCHA/verification appears.
- Application cannot be recognized.
- Resume cannot be found.
- Connection UI cannot be recognized.
- A critical exception occurs.

Store them under:

```text
screenshots/
```

Use meaningful filenames:

```text
row_004_application_error.png
row_004_captcha.png
row_004_hr_search_error.png
```

---

# 28. Human-in-the-Loop Design

The agent should have a visible terminal status such as:

```text
Processing row 4/20

Company: Example Company
Step: HR outreach

HR connections:
7 / 10

Developer connections:
0 / 15

Status: RUNNING
```

When intervention is required:

```text
==================================================
HUMAN INTERVENTION REQUIRED
==================================================

Reason: CAPTCHA / verification detected

The browser has been left open.

Complete the verification manually, then press ENTER
to allow the agent to continue.

==================================================
```

---

# 29. One-Job MVP

Do NOT immediately process 15–20 jobs.

First create an MVP that supports exactly one Excel row.

MVP test:

```text
1 job
1 resume
1 company
HR target: 2
Developer target: 2
```

This allows the complete flow to be tested without processing a large number of jobs.

Only after the complete workflow works reliably should configurable larger limits be enabled.

---

# 30. MVP Acceptance Criteria

The one-job test is successful if:

- Excel is loaded correctly.
- The correct job URL opens.
- The correct resume is selected.
- The application is completed successfully.
- The company URL opens.
- People search works.
- HR/Talent filters work.
- Two appropriate HR/recruiting profiles are processed.
- The correct HR message is used.
- Developer search works.
- Two appropriate developer profiles are processed.
- The correct developer message is used.
- Already-connected profiles are skipped.
- The row is marked `COMPLETED`.
- SQLite state is updated.
- Logs are generated.
- Errors cause safe pauses instead of incorrect actions.

---

# 31. Scaling After MVP

Once the one-job test is stable:

```text
1 job
↓
3 jobs
↓
5 jobs
↓
10 jobs
↓
15–20 jobs
```

Do not scale before validating the previous stage.

---

# 32. Browser Automation Design

Use Playwright.

Prefer:

- Accessible roles
- Visible text
- Stable DOM attributes
- Multiple selector fallbacks
- Explicit waits
- Page-state validation

Avoid:

- Blind coordinate clicking
- Fixed screen positions
- Extremely brittle CSS selectors
- Assuming a page always looks identical

LinkedIn's UI can change, so selectors should be centralized in:

```text
src/selectors.py
```

---

# 33. Page State Validation

Before performing a critical action, verify the expected state.

Example:

```text
Expected:
Application modal is open

If not:
PAUSE
SAVE SCREENSHOT
LOG ERROR
```

Similarly:

```text
Expected:
Company page loaded

Expected:
People section available

Expected:
Connection dialog open
```

The agent should never blindly continue after an unexpected UI state.

---

# 34. No Private API Requirement

The implementation should operate through the browser UI.

Do not build the system around:

- undocumented LinkedIn APIs
- private endpoints
- direct request replay
- session-token extraction
- CAPTCHA bypass
- security-control bypass

This keeps the architecture focused on browser-based personal productivity automation.

---

# 35. Security

Never hardcode:

- LinkedIn password
- cookies
- session tokens
- authentication headers
- API keys

Use the persistent browser profile for login.

Add:

```text
.env
```

to `.gitignore`.

Also add:

```text
browser_profile/
data/agent.db
logs/
screenshots/
.env
```

to `.gitignore` as appropriate.

---

# 36. CLI

The application should eventually support:

```bash
python app.py
```

Possible commands:

```bash
python app.py --test-one
python app.py --resume
python app.py --status
python app.py --dry-run
```

`--test-one` should process only the first eligible row.

`--dry-run` should navigate/read/validate without sending applications or connection requests.

---

# 37. Dry Run Mode

Before real execution, provide:

```bash
python app.py --dry-run
```

Dry run should:

- Read Excel.
- Validate URLs.
- Open pages.
- Identify expected UI.
- Show what actions would be performed.
- NOT submit applications.
- NOT send connection requests.

Example output:

```text
ROW 1

Job:
https://...

Resume:
Java Developer Resume

Company:
Example Company

Would perform:

[1] Apply to job
[2] Select Java Developer Resume
[3] Open company page
[4] Find HR/Talent Acquisition
[5] Process up to 5 HR profiles
[6] Find software developers
[7] Process up to 10 developers

DRY RUN: No actions submitted.
```

---

# 38. Future AI Layer

Do NOT make an LLM mandatory for the first MVP.

The first version should be deterministic browser automation.

Later, an AI layer can help with:

- Identifying whether a profile is relevant.
- Understanding unusual application questions.
- Classifying job titles.
- Selecting appropriate people from search results.
- Generating personalized messages if the user enables it.
- Recovering from minor UI changes.

The AI should never silently make high-impact decisions that the user has not configured.

---

# 39. Error Handling

Every module must use controlled exceptions.

Example categories:

```text
LoginRequiredError
CaptchaDetectedError
UnexpectedPageError
ResumeNotFoundError
ApplicationFailedError
CompanyPageError
PeopleSearchError
ConnectionError
UnknownUIError
```

Each critical error should:

1. Save state.
2. Log error.
3. Screenshot page.
4. Pause safely.
5. Allow resume.

---

# 40. Important Completion Rule

The most important rule in the project is:

```text
NEVER MARK A ROW COMPLETED UNLESS THE ENTIRE
CONFIGURED WORKFLOW FOR THAT ROW HAS COMPLETED.
```

If something fails:

```text
PAUSED / FAILED
```

not:

```text
COMPLETED
```

---

# 41. Development Phases

## Phase 1 — Project Setup

Build:

- Python environment
- requirements.txt
- Playwright
- project structure
- configuration
- logging

## Phase 2 — Excel Manager

Build:

- Excel reader
- validation
- status columns
- row selection
- safe Excel updates

## Phase 3 — Browser Session

Build:

- persistent Playwright context
- manual login
- session reuse
- browser lifecycle

## Phase 4 — Job Application

Build:

- job URL navigation
- Easy Apply detection
- resume selection
- supported form fields
- submission
- application state

## Phase 5 — Company People Search

Build:

- company navigation
- People section
- HR/Talent filters
- profile collection

## Phase 6 — HR Networking

Build:

- connection-state detection
- Add a note
- HR message insertion
- configurable target count
- logging

## Phase 7 — Developer Networking

Build:

- clear HR filters
- developer filters
- profile collection
- developer message insertion
- configurable target count

## Phase 8 — State & Recovery

Build:

- SQLite
- resume capability
- partial workflow recovery
- failure states

## Phase 9 — Testing

Test with one job.

## Phase 10 — Scaling

Gradually increase the number of rows after the MVP passes.

---

# 42. Claude Code Instructions

Claude Code should NOT attempt to generate the entire project blindly without testing.

Work in milestones.

For every milestone:

1. Explain what will be implemented.
2. Create/update files.
3. Run relevant tests.
4. Check for errors.
5. Fix errors.
6. Do not move to the next milestone until the current milestone works.

The agent should inspect the existing project before modifying files.

Do not overwrite working code unnecessarily.

Keep modules small and maintainable.

---

# 43. First Task for Claude Code

The first task should be:

```text
Read this specification completely.

Do not build the entire system yet.

First:

1. Create the project structure.
2. Create requirements.txt.
3. Create configuration files.
4. Create Excel schema validation.
5. Create SQLite state schema.
6. Create logging.
7. Create a Playwright persistent browser setup.
8. Implement --dry-run.
9. Implement --test-one.
10. Add basic unit tests.

Do not implement real application submission or networking until
the foundation has been tested successfully.
```

---

# 44. Final Product Goal

The final workflow should feel like:

```text
User prepares jobs.xlsx
        ↓
User reviews all selected jobs
        ↓
User starts:

python app.py

        ↓
Agent opens browser
        ↓
Processes Job 1
        ↓
Applies
        ↓
Selects specified resume
        ↓
Opens company
        ↓
Contacts configured HR/Talent profiles
        ↓
Contacts configured software developers
        ↓
Marks Row 1 COMPLETED
        ↓
Waits configured interval
        ↓
Processes Job 2
        ↓
...
        ↓
Processes all eligible rows
```

The user should be able to leave the agent running while working on other tasks.

The system must prioritize:

1. Correctness
2. Safe stopping
3. Recoverability
4. Accurate Excel tracking
5. Clear logs
6. Maintainable code
7. Human intervention when required

rather than maximum speed.

---

# 45. Success Definition

The project is successful when I can prepare an Excel file containing my personally reviewed job opportunities, start the Python application, and have the browser agent process each row sequentially while:

- applying using the correct resume,
- visiting the specified company,
- performing the configured HR/Talent outreach,
- performing the configured developer/referral outreach,
- respecting configured limits and delays,
- stopping safely for verification or unexpected situations,
- preserving state,
- and accurately marking each fully completed row.

The first goal is NOT maximum automation.

The first goal is a reliable **one-job end-to-end proof of concept**.

Once that works, expand it gradually to the full 15–20 job daily workflow.
