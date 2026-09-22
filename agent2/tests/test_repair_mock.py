"""The form rejects a text answer with a red 'Invalid input' (2026 UI style);
the agent must repair it with a numeric answer without human help."""
from src import state_manager as sm
from src.job_application import JobApplication
from tests import mock_pages as M

JOB_URL = "https://www.linkedin.com/jobs/view/777/"

STEP3 = """
  <div id="step3" class="step" style="display:none">
    <h3>Additional Questions</h3>
    <div><label for="ctc">What is your current CTC?*</label><input id="ctc" type="text" maxlength="20" value="7 LPA">
      <span id="ctcerr" style="display:none;color:red">Invalid input</span></div>
    <div><label for="q1">How many years of experience do you have with Java?</label><input id="q1" type="text" value=""></div>
    <footer><button aria-label="Review your application" onclick="validate3()">Review</button></footer>
  </div>
  <script>
  function validate3() {
    const v = document.getElementById('ctc').value.trim();
    const bad = !/^\\d+$/.test(v);
    document.getElementById('ctcerr').style.display = bad ? 'inline' : 'none';
    window.__reviewClicks = (window.__reviewClicks || 0) + 1;
    if (!bad && document.getElementById('q1').value.trim()) showStep(4);
  }
  </script>
"""


def _page():
    html = M.job_page()
    start = html.index('<div id="step3"')
    end = html.index('<div id="step4"')
    return html[:start] + STEP3 + html[end:]


def test_invalid_input_is_repaired_automatically(browser, settings, site, monkeypatch):
    site.add(JOB_URL, _page())
    calls = []
    monkeypatch.setattr("src.job_application.request_intervention", lambda *a, **k: calls.append(a))
    app = JobApplication(browser, settings, 2, JOB_URL, "Java Developer Resume")
    app.ai = None  # make sure the rule-based repair alone fixes it
    assert app.apply() == sm.APP_COMPLETED
    assert calls == []  # no human needed
    assert browser.page.evaluate("window.__submitted") is True
