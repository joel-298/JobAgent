from pathlib import Path

import pytest

import config
from src import utils


def test_default_settings_load():
    s = config.load_settings()
    assert s.networking.hr_max >= s.networking.hr_min
    assert s.delays.page_timeout > 0
    assert isinstance(s.application.answers, dict)


def test_invalid_settings_rejected(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("networking:\n  hr_min: 5\n  hr_max: 2\nrun:\n  retry_failed: maybe\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        config.load_settings(bad)
    assert "hr_min" in str(exc.value)
    assert "retry_failed" in str(exc.value)


@pytest.mark.parametrize(
    "requested,candidate,expected",
    [
        ("Java Developer Resume", "Java Developer Resume", True),
        ("Java Developer Resume", "Java Developer Resume.pdf", True),
        ("Java Developer Resume", "java developer resume.PDF", True),
        ("Java Developer Resume", "Java Developer", True),
        ("Java Developer", "Java Developer Resume.pdf", True),
        ("Java Developer Resume", "Python Developer Resume", False),
        ("Java Developer Resume", "Resume", False),
        ("", "Resume", False),
    ],
)
def test_resume_matches(requested, candidate, expected):
    assert utils.resume_matches(requested, candidate) is expected


def test_url_helpers():
    assert utils.is_linkedin_url("https://www.linkedin.com/jobs/view/1/", "/jobs/")
    assert not utils.is_linkedin_url("https://evil.com/linkedin.com/jobs/", "/jobs/")
    assert not utils.is_linkedin_url("linkedin.com/jobs/view/1", "/jobs/")
    assert utils.company_people_url("https://www.linkedin.com/company/acme/about/") == (
        "https://www.linkedin.com/company/acme/people/"
    )
    assert utils.company_people_url("https://www.linkedin.com/company/acme", "Talent Acquisition").endswith(
        "?keywords=Talent%20Acquisition"
    )
    assert utils.clean_profile_url("http://linkedin.com/in/x-y/?q=1#z") == "https://www.linkedin.com/in/x-y"


def test_contains_any_is_case_insensitive():
    assert utils.contains_any("Senior TALENT Partner", ["talent"])
    assert not utils.contains_any("Software Engineer", ["recruit", "talent"])
    assert utils.screenshot_name(4, "hr search error") == "row_004_hr_search_error.png"


def test_pick_resume():
    names = ["Joel_Matthew_Java_2.pdf", "Joel_Matthew_Mern_3.pdf", "Joel_Matthew_Multi_3.pdf"]
    assert utils.pick_resume("Joel_Matthew_Java_2.pdf", names) == (0, "exact")
    assert utils.pick_resume("joel_matthew_java_2", names) == (0, "exact")
    assert utils.pick_resume("Java", names) == (0, "substring")
    assert utils.pick_resume("Mern_3", names) == (1, "substring")
    assert utils.pick_resume("Joel_Matthew", names) == (None, "ambiguous")
    assert utils.pick_resume("Python", names) == (None, "no match")
    assert utils.pick_resume("", names) == (None, "empty resume_name")
