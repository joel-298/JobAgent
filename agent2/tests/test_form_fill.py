"""Question filling on a dialog shaped like the 2026 Easy Apply form."""
from pathlib import Path

from src import selectors as S
from src.answers import AnswerProfile
from src.job_application import JobApplication

FORM = """
<html><body><main><h1>x</h1></main>
<dialog open>
  <h2>Apply to Acme</h2>
  <div><label for="e1">Email*</label><select id="e1"><option>a@b.com</option></select></div>
  <div><label for="q1">How many years of experience do you have with React.js?</label><input id="q1" type="number" value=""></div>
  <div><label for="q2">Where are you currently located?</label><input id="q2" type="text" value=""></div>
  <div><label for="q3">What is your current annual salary (INR)?</label><input id="q3" type="text" value=""></div>
  <div><label for="q4">Are you legally authorized to work in India?</label>
    <select id="q4"><option>Select an option</option><option>Yes</option><option>No</option></select></div>
  <fieldset role="radiogroup"><legend>Are you willing to relocate?</legend>
    <div role="radio" aria-label="Yes" aria-checked="false" onclick="this.setAttribute('aria-checked','true');this.nextElementSibling.setAttribute('aria-checked','false')">Yes</div>
    <div role="radio" aria-label="No" aria-checked="false" onclick="this.setAttribute('aria-checked','true');this.previousElementSibling.setAttribute('aria-checked','false')">No</div>
  </fieldset>
  <div><label for="q5">Describe yourself</label><textarea id="q5"></textarea></div>
  <div><label for="q6">Phone*</label><input id="q6" type="tel" value="12345"></div>
  <button>Submit application</button>
</dialog></body></html>
"""


def test_read_and_fill_fields(browser, settings):
    browser.page.set_content(FORM)
    app = JobApplication(browser, settings, 2, "https://www.linkedin.com/jobs/view/1/", "x")
    app.answers = AnswerProfile.load(Path(settings.paths.root) / "config" / "answers.yaml")
    modal = browser.find(S.APPLY_MODAL)
    fields = app._read_fields(modal)
    labels = {f["label"]: f for f in fields}
    assert "Are you willing to relocate?" in labels and labels["Are you willing to relocate?"]["options"] == ["Yes", "No"]
    assert labels["Phone*"]["value"] == "12345"

    app._fill_configured_fields(modal)
    p = browser.page
    assert p.input_value("#q1") == "1"
    assert p.input_value("#q2") == "Chandigarh"
    assert p.input_value("#q3") == "700000"
    assert p.input_value("#q4") == "Yes"
    assert p.get_attribute("[role=radio][aria-label='Yes']", "aria-checked") == "true"
    assert p.input_value("#q5") == ""  # unknown question left alone
    assert p.input_value("#q6") == "12345"  # pre-filled value untouched
    assert p.input_value("#e1") == "a@b.com"
    remaining = app._visible_questions(modal)
    assert remaining == ["Describe yourself"]
