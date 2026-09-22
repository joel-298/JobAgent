"""Minimal HTML pages that imitate the LinkedIn UI structure the agent relies on.

Used by the Playwright-based tests so the application / networking logic can
be exercised offline. They mirror the selectors in src/selectors.py.
"""

JOB_PAGE = """
<html><body>
<nav class="global-nav"><a href="/mynetwork/">My Network</a></nav>
<main>
  <h1 class="t-24">Software Engineer</h1>
  <div class="job-details-jobs-unified-top-card__company-name"><a href="/company/acme/">Acme Corp</a></div>
  {apply_area}
</main>
<script>
const answers = {{}};
function openModal() {{
  document.getElementById('modal').style.display = 'block';
  showStep(1);
}}
function showStep(n) {{
  document.querySelectorAll('.step').forEach(s => s.style.display = 'none');
  document.getElementById('step' + n).style.display = 'block';
  document.getElementById('modal').dataset.step = n;
}}
function next() {{
  const n = parseInt(document.getElementById('modal').dataset.step);
  const r = document.querySelector('input[name=resume]:checked'); if (r) window.__checkedResume = r.value;
  if (n === 3) {{
    const v = document.getElementById('q1').value.trim();
    const err = document.getElementById('q1err');
    if (!v) {{ err.style.display = 'block'; return; }}
    err.style.display = 'none';
  }}
  showStep(n + 1);
}}
function selectResume(el) {{
  document.querySelectorAll('.jobs-document-upload-redesign-card__container').forEach(c => c.classList.remove('jobs-document-upload-redesign-card__container--selected'));
  el.closest('.jobs-document-upload-redesign-card__container').classList.add('jobs-document-upload-redesign-card__container--selected');
}}
function submit() {{
  document.getElementById('modal').innerHTML = '<h2>Your application was sent to Acme Corp!</h2><button aria-label="Dismiss">X</button>';
  window.__submitted = true;
}}
</script>
<div id="modal" class="jobs-easy-apply-modal" role="dialog" style="display:none" data-step="0">
  <button aria-label="Dismiss" onclick="document.getElementById('modal').style.display='none'">X</button>
  <div id="step1" class="step">
    <h3>Contact info</h3>
    <div class="fb-dash-form-element"><label for="phone">Mobile phone number</label><input id="phone" type="text" value="123"></div>
    <footer><button aria-label="Continue to next step" onclick="next()">Next</button></footer>
  </div>
  <div id="step2" class="step" style="display:none">
    <h3>Resume</h3>
    <div class="jobs-document-upload-redesign-card__container">
      <h3 class="jobs-document-upload-redesign-card__file-name">Python Backend Resume.pdf</h3>
      <button onclick="selectResume(this)">Select</button>
    </div>
    <div class="jobs-document-upload-redesign-card__container">
      <h3 class="jobs-document-upload-redesign-card__file-name">Java Developer Resume.pdf</h3>
      <button onclick="selectResume(this)">Select</button>
    </div>
    <footer><button aria-label="Continue to next step" onclick="next()">Next</button></footer>
  </div>
  <div id="step3" class="step" style="display:none">
    <h3>Additional Questions</h3>
    <div class="fb-dash-form-element">
      <label for="q1">How many years of experience do you have with Java?</label>
      <input id="q1" type="text" value="">
      <div id="q1err" class="artdeco-inline-feedback--error" style="display:none">Please enter a valid answer</div>
    </div>
    <footer><button aria-label="Review your application" onclick="next()">Review</button></footer>
  </div>
  <div id="step4" class="step" style="display:none">
    <h3>Review your application</h3>
    <footer><button aria-label="Submit application" onclick="submit()">Submit application</button></footer>
  </div>
</div>
</body></html>
"""

# Resume step shaped like the 2026 LinkedIn UI: no LinkedIn class names,
# "<PDF badge> <file name> <date> <download icon> <radio>".
RESUME_STEP_RADIO_STYLE = """
  <div id="step2" class="step" style="display:none">
    <h3>Apply to Quik Hire Staffing</h3>
    <p>Top choice job</p>
    <h4>Resume</h4>
    <p>Select or upload a resume in DOC, DOCX, or PDF format that is less than 2MB</p>
    <div class="cardlist">
      <label class="rcard"><span class="badge">PDF</span><span>Joel_Matthew_Java_2.pdf</span><span>9/17/2026</span><input type="radio" name="resume" value="1"></label>
      <label class="rcard"><span class="badge">PDF</span><span>Joel_Matthew_Mern_3.pdf</span><span>9/16/2026</span><input type="radio" name="resume" value="2"></label>
      <label class="rcard"><span class="badge">PDF</span><span>Joel_Matthew_Multi_3.pdf</span><span></span><input type="radio" name="resume" value="3"></label>
    </div>
    <button>Upload resume</button>
    <footer><button aria-label="Continue to next step" onclick="next()">Next</button></footer>
  </div>
"""


def job_page_radio_resumes() -> str:
    """Job page whose resume step uses the radio-style layout."""
    html = JOB_PAGE.format(apply_area=EASY_APPLY_AREA)
    start = html.index('<div id="step2"')
    end = html.index('<div id="step3"')
    return html[:start] + RESUME_STEP_RADIO_STYLE + html[end:]


EASY_APPLY_AREA = '<button class="jobs-apply-button" onclick="openModal()"><span>Easy Apply</span></button>'
EXTERNAL_APPLY_AREA = '<button class="jobs-apply-button" aria-label="Apply to Acme on company website"><span>Apply</span></button>'
APPLIED_AREA = '<div class="artdeco-inline-feedback"><span class="artdeco-inline-feedback__message">Applied 2 days ago</span></div>'


def job_page(area: str = EASY_APPLY_AREA) -> str:
    return JOB_PAGE.format(apply_area=area)


PEOPLE_PAGE = """
<html><body>
<nav class="global-nav"><a href="/mynetwork/">My Network</a></nav>
<main>
<h1 class="org-top-card-summary__title">Acme Corp</h1>
<ul class="display-flex">
{cards}
</ul>
</main></body></html>
"""

PEOPLE_CARD = """
<li class="org-people-profile-card__profile-card-spacing">
  <div class="artdeco-entity-lockup">
    <a href="/in/{slug}/"><div class="artdeco-entity-lockup__title">{name}</div></a>
    <div>&middot; 3rd+</div>
    <div class="artdeco-entity-lockup__subtitle">{headline}</div>
    <div>Pune, India</div>
  </div>
</li>
"""


def people_page(people: list[tuple[str, str, str]]) -> str:
    cards = "".join(PEOPLE_CARD.format(slug=s, name=n, headline=h) for s, n, h in people)
    return PEOPLE_PAGE.format(cards=cards)


PROFILE_PAGE = """
<html><body>
<nav class="global-nav"><a href="/mynetwork/">My Network</a></nav>
<main>
<section>
  <h1>{name}</h1>
  <div class="text-body-medium break-words">{headline}</div>
  <span class="dist-value">{distance}</span>
  <div class="pv-top-card-v2-ctas">{buttons}</div>
</section>
</main>
<script>
function openConnect() {{ document.getElementById('cdialog').style.display='block'; }}
function addNote() {{ document.getElementById('note').style.display='block'; document.getElementById('sendbtn').style.display='inline'; }}
function send() {{ window.__sentNote = document.getElementById('custom-message').value; document.getElementById('cdialog').style.display='none';
  const t = document.createElement('div'); t.className='artdeco-toast-item'; t.textContent='Invitation sent'; document.body.appendChild(t); }}
function sendNoNote() {{ window.__sentNote = null; window.__sentWithoutNote = true; document.getElementById('cdialog').style.display='none';
  const t = document.createElement('div'); t.className='artdeco-toast-item'; t.textContent='Invitation sent'; document.body.appendChild(t); }}
</script>
<div id="cdialog" role="dialog" style="display:none">
  <button aria-label="Dismiss" onclick="document.getElementById('cdialog').style.display='none'">X</button>
  {note_button}
  <div id="note" style="display:none"><textarea id="custom-message" name="message"></textarea></div>
  <button aria-label="Send without a note" onclick="sendNoNote()">Send without a note</button>
  <button id="sendbtn" aria-label="Send invitation" style="display:none" onclick="send()">Send</button>
</div>
</body></html>
"""

CONNECT_BUTTON = '<button aria-label="Invite {name} to connect" onclick="openConnect()"><span>Connect</span></button>'
MESSAGE_BUTTON = '<button aria-label="Message {name}"><span>Message</span></button>'
PENDING_BUTTON = '<button aria-label="Pending, click to withdraw invitation sent to {name}"><span>Pending</span></button>'
ADD_NOTE_BUTTON = '<button aria-label="Add a note" onclick="addNote()">Add a note</button>'


def profile_page(name: str, headline: str, state: str = "connectable", note_available: bool = True) -> str:
    if state == "connectable":
        buttons, distance = CONNECT_BUTTON.format(name=name), "2nd"
    elif state == "connected":
        buttons, distance = MESSAGE_BUTTON.format(name=name), "1st"
    elif state == "pending":
        buttons, distance = PENDING_BUTTON.format(name=name), "2nd"
    else:
        buttons, distance = "", "3rd"
    return PROFILE_PAGE.format(
        name=name,
        headline=headline,
        distance=distance,
        buttons=buttons,
        note_button=ADD_NOTE_BUTTON if note_available else "",
    )
