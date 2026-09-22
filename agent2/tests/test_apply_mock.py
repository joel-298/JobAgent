"""Easy Apply flow exercised against the offline mock job page."""
import pytest

from src import state_manager as sm
from src.exceptions import ResumeNotFoundError
from src.job_application import JobApplication
from tests import mock_pages as M

JOB_URL = "https://www.linkedin.com/jobs/view/123456/"


def test_inspect_modes(browser, settings, site):
    site.add(JOB_URL, M.job_page(M.EASY_APPLY_AREA))
    assert JobApplication(browser, settings, 2, JOB_URL, "x").open_and_inspect().mode == "easy_apply"
    site.add(JOB_URL, M.job_page(M.EXTERNAL_APPLY_AREA))
    assert JobApplication(browser, settings, 2, JOB_URL, "x").open_and_inspect().mode == "external"
    site.add(JOB_URL, M.job_page(M.APPLIED_AREA))
    info = JobApplication(browser, settings, 2, JOB_URL, "x").open_and_inspect()
    assert info.mode == "applied"
    assert info.title == "Software Engineer"
    assert info.company == "Acme Corp"


def test_full_apply_with_configured_answer(browser, settings, site):
    site.add(JOB_URL, M.job_page())
    settings.application.answers = {"years of experience": "4"}
    try:
        app = JobApplication(browser, settings, 2, JOB_URL, "Java Developer Resume")
        assert app.apply() == sm.APP_COMPLETED
        assert browser.page.evaluate("window.__submitted") is True
        assert browser.page.evaluate("document.getElementById('q1') === null") is True  # modal replaced
    finally:
        settings.application.answers = {}


def test_wrong_resume_never_selected(browser, settings, site):
    site.add(JOB_URL, M.job_page())
    app = JobApplication(browser, settings, 2, JOB_URL, "Golang Resume")
    with pytest.raises(ResumeNotFoundError) as exc:
        app.apply()
    assert "Golang Resume" in str(exc.value)
    assert browser.page.evaluate("!!window.__submitted") is False
    selected = browser.page.locator(".jobs-document-upload-redesign-card__container--selected").count()
    assert selected == 0


def test_dry_run_never_submits(browser, settings, site):
    site.add(JOB_URL, M.job_page())
    settings.application.answers = {"years of experience": "4"}
    try:
        app = JobApplication(browser, settings, 2, JOB_URL, "Java Developer Resume")
        assert app.apply(dry_run=True) == sm.APP_DRY_RUN
        assert browser.page.evaluate("!!window.__submitted") is False
    finally:
        settings.application.answers = {}


def test_unknown_question_pauses_for_user(browser, settings, site, monkeypatch):
    """With no configured answer the agent must pause; simulate the user typing the answer."""
    site.add(JOB_URL, M.job_page())
    calls = []

    def fake_intervention(reason, screenshot=None, instructions=""):
        calls.append(reason)
        browser.page.fill("#q1", "5")

    monkeypatch.setattr("src.job_application.request_intervention", fake_intervention)
    from src.answers import AnswerProfile

    monkeypatch.setattr(AnswerProfile, "load", classmethod(lambda cls, *a, **k: cls(experience_years_with_tech="", total_experience_years="")))  # no profile
    app = JobApplication(browser, settings, 2, JOB_URL, "Java Developer Resume")
    assert app.apply() == sm.APP_COMPLETED
    assert len(calls) == 1
    assert "years of experience" in calls[0]


def test_external_apply_skip_and_pause(browser, settings, site, monkeypatch):
    site.add(JOB_URL, M.job_page(M.EXTERNAL_APPLY_AREA))
    settings.application.external_apply = "skip"
    try:
        assert JobApplication(browser, settings, 2, JOB_URL, "x").apply() == sm.APP_SKIPPED_EXTERNAL
        settings.application.external_apply = "pause"
        monkeypatch.setattr("src.job_application.request_intervention", lambda *a, **k: None)
        assert JobApplication(browser, settings, 2, JOB_URL, "x").apply() == sm.APP_MANUAL
    finally:
        settings.application.external_apply = "pause"


def test_already_applied(browser, settings, site):
    site.add(JOB_URL, M.job_page(M.APPLIED_AREA))
    assert JobApplication(browser, settings, 2, JOB_URL, "x").apply() == sm.APP_ALREADY_APPLIED


@pytest.mark.parametrize("requested,expected_value", [
    ("Joel_Matthew_Java_2.pdf", "1"),
    ("Joel_Matthew_Java_2", "1"),
    ("Java", "1"),
    ("mern", "2"),
    ("Multi_3", "3"),
])
def test_radio_style_resume_step(browser, settings, site, requested, expected_value):
    site.add(JOB_URL, M.job_page_radio_resumes())
    settings.application.answers = {"years of experience": "4"}
    try:
        app = JobApplication(browser, settings, 2, JOB_URL, requested)
        assert app.apply() == sm.APP_COMPLETED
        checked = browser.page.evaluate("window.__checkedResume")
        assert checked == expected_value
    finally:
        settings.application.answers = {}


def test_radio_style_ambiguous_or_missing_pauses(browser, settings, site):
    site.add(JOB_URL, M.job_page_radio_resumes())
    for bad in ("Joel_Matthew", "Python Resume"):
        with pytest.raises(ResumeNotFoundError):
            JobApplication(browser, settings, 2, JOB_URL, bad).apply()
        assert browser.page.evaluate("!!window.__submitted") is False
