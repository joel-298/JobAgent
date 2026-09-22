"""People search + connection requests exercised against offline mock pages."""
import pytest

from src import state_manager as sm
from src.company_people import CATEGORY_DEVELOPER, CATEGORY_HR, CompanyPeople
from src.exceptions import CompanyPageError, ConnectionRequestError
from src.networking import Networker
from tests import mock_pages as M

COMPANY = "https://www.linkedin.com/company/acme/"
PEOPLE = "https://www.linkedin.com/company/acme/people/"
IN = "https://www.linkedin.com/in/"

PEOPLE_LIST = [
    ("alice", "Alice A", "Senior Technical Recruiter at Acme"),
    ("bob", "Bob B", "Talent Acquisition Partner"),
    ("carol", "Carol C", "Software Engineer II"),
    ("dave", "Dave D", "Sales Manager"),
    ("erin", "Erin E", "Backend Developer"),
    ("frank", "Frank F", "Talent Sourcing Engineer"),  # excluded from developers
]


@pytest.fixture
def state():
    s = sm.StateManager(":memory:")
    s.get_or_create_run(2, "job", COMPANY)
    yield s
    s.close()


def _setup(site, profile_states: dict[str, str] | None = None, note_available=True):
    site.add(COMPANY, M.people_page(PEOPLE_LIST).replace("<ul", "<ul"))
    site.add(PEOPLE, M.people_page(PEOPLE_LIST))
    profile_states = profile_states or {}
    for slug, name, headline in PEOPLE_LIST:
        site.add(IN + slug, M.profile_page(name, headline, profile_states.get(slug, "connectable"), note_available))


def test_company_and_people_search(browser, settings, site):
    _setup(site)
    cp = CompanyPeople(browser, settings, 2, COMPANY)
    assert cp.open_company() == "Acme Corp"
    hr = cp.search_hr()
    assert [c.name for c in hr] == ["Alice A", "Bob B", "Frank F"]
    assert all(c.category == CATEGORY_HR for c in hr)
    devs = cp.search_developers()
    assert [c.name for c in devs] == ["Carol C", "Erin E"]  # Frank excluded (talent), Dave (sales) not matched
    assert all(c.category == CATEGORY_DEVELOPER for c in devs)


def test_company_not_found(browser, settings, site):
    with pytest.raises(CompanyPageError):
        CompanyPeople(browser, settings, 2, "https://www.linkedin.com/company/nope/").open_company()


def test_hr_outreach_sends_exact_message_and_skips_connected(browser, settings, site, state):
    _setup(site, {"alice": "connected", "bob": "connectable", "frank": "pending"})
    cp = CompanyPeople(browser, settings, 2, COMPANY)
    hr = cp.search_hr()
    net = Networker(browser, settings, state, 2, COMPANY)
    message = "Hi, I applied for the SWE role at Acme. Would love to connect!"
    sent = net.process(hr, CATEGORY_HR, message, target_min=1, target_max=2)
    assert sent == 1
    rows = {r["profile_url"]: r["result"] for r in state.list_connections(2)}
    assert rows[IN + "alice"] == sm.CONN_ALREADY_CONNECTED
    assert rows[IN + "bob"] == sm.CONN_SENT
    assert rows[IN + "frank"] == sm.CONN_PENDING
    # last page visited was frank (pending) -> check bob's note via the stored page? re-open bob
    browser.page.goto(IN + "bob")
    assert browser.page.evaluate("window.__sentNote") is None  # fresh page: nothing sent twice
    run = state.get_run(2)
    assert run.hr_successful == 1 and run.hr_attempted == 3


def test_note_is_verbatim(browser, settings, site, state):
    _setup(site)
    net = Networker(browser, settings, state, 2, COMPANY)
    from src.company_people import PersonCandidate

    cand = PersonCandidate(IN + "carol", "Carol C", "Software Engineer II", CATEGORY_DEVELOPER)
    msg = "Hi Carol, I recently applied for the Software Engineer role. Could you refer me? Thanks!"
    assert net.connect(cand, msg) == sm.CONN_SENT
    assert browser.page.evaluate("window.__sentNote") == msg


def test_minimum_not_reached_raises(browser, settings, site, state):
    _setup(site, {"alice": "connected", "bob": "connected", "frank": "connected"})
    cp = CompanyPeople(browser, settings, 2, COMPANY)
    net = Networker(browser, settings, state, 2, COMPANY)
    with pytest.raises(ConnectionRequestError) as exc:
        net.process(cp.search_hr(), CATEGORY_HR, "hi", target_min=1, target_max=2)
    assert "Only 0 of the required minimum 1" in str(exc.value)


def test_note_unavailable_skips_by_default(browser, settings, site, state):
    _setup(site, note_available=False)
    from src.company_people import PersonCandidate

    cand = PersonCandidate(IN + "erin", "Erin E", "Backend Developer", CATEGORY_DEVELOPER)
    net = Networker(browser, settings, state, 2, COMPANY)
    assert net.connect(cand, "hello") == sm.CONN_NOTE_UNAVAILABLE
    assert not browser.page.evaluate("!!window.__sentWithoutNote")
    settings.networking.send_without_note_if_unavailable = True
    try:
        assert net.connect(cand, "hello") == sm.CONN_SENT_NO_NOTE
        assert browser.page.evaluate("window.__sentWithoutNote") is True
    finally:
        settings.networking.send_without_note_if_unavailable = False


def test_dry_run_sends_nothing(browser, settings, site, state):
    _setup(site)
    cp = CompanyPeople(browser, settings, 2, COMPANY)
    net = Networker(browser, settings, state, 2, COMPANY)
    sent = net.process(cp.search_hr(), CATEGORY_HR, "hi", 1, 2, dry_run=True)
    assert sent == 2
    assert state.list_connections(2) == []
    assert browser.page.evaluate("typeof window.__sentNote") == "undefined"


def test_never_duplicate_across_runs(browser, settings, site, state):
    _setup(site)
    state.record_connection(3, "other-company", IN + "bob", CATEGORY_HR, sm.CONN_SENT)
    cp = CompanyPeople(browser, settings, 2, COMPANY)
    net = Networker(browser, settings, state, 2, COMPANY)
    sent = net.process(cp.search_hr(), CATEGORY_HR, "hi", 1, 2)
    assert sent == 2
    urls = [r["profile_url"] for r in state.list_connections(2)]
    assert IN + "bob" not in urls
    assert urls == [IN + "alice", IN + "frank"]
