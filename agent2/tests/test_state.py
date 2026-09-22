import pytest

from src import state_manager as sm


@pytest.fixture
def state() -> sm.StateManager:
    s = sm.StateManager(":memory:")
    yield s
    s.close()


def test_create_and_update_run(state: sm.StateManager):
    run = state.get_or_create_run(2, "https://www.linkedin.com/jobs/view/1", "https://www.linkedin.com/company/x")
    assert run.status == "PENDING"
    assert run.current_step == sm.STEP_START
    state.update_run(2, status="IN_PROGRESS", current_step=sm.STEP_HR_SEARCH, hr_successful=3)
    run = state.get_run(2)
    assert run.status == "IN_PROGRESS"
    assert run.current_step == sm.STEP_HR_SEARCH
    assert run.hr_successful == 3
    assert run.updated_at


def test_changed_links_reset_state(state: sm.StateManager):
    state.get_or_create_run(2, "https://www.linkedin.com/jobs/view/1", "https://www.linkedin.com/company/x")
    state.update_run(2, status="PAUSED", hr_successful=5)
    run = state.get_or_create_run(2, "https://www.linkedin.com/jobs/view/999", "https://www.linkedin.com/company/x")
    assert run.status == "PENDING"
    assert run.hr_successful == 0


def test_unknown_field_rejected(state: sm.StateManager):
    state.get_or_create_run(2, "j", "c")
    with pytest.raises(ValueError):
        state.update_run(2, job_link="changed")


def test_connections_dedupe_and_counts(state: sm.StateManager):
    state.get_or_create_run(2, "j", "c")
    url = "https://www.linkedin.com/in/alice"
    assert not state.already_contacted(url)
    state.record_connection(2, "c", url, "HR", sm.CONN_SENT, "Alice", "Recruiter")
    assert state.already_contacted(url)
    state.record_connection(2, "c", "https://www.linkedin.com/in/bob", "HR", sm.CONN_ALREADY_CONNECTED)
    state.record_connection(2, "c", "https://www.linkedin.com/in/carol", "HR", sm.CONN_NOTE_UNAVAILABLE)
    state.record_connection(2, "c", "https://www.linkedin.com/in/dave", "DEVELOPER", sm.CONN_SENT_NO_NOTE)
    assert state.count_successful(2, "HR") == 1
    assert state.count_successful(2, "DEVELOPER") == 1
    assert state.seen_profiles(2, "HR") == {url, "https://www.linkedin.com/in/bob", "https://www.linkedin.com/in/carol"}
    # a skipped-for-note profile may be retried; an already-connected one may not
    assert not state.already_contacted("https://www.linkedin.com/in/carol")
    assert state.already_contacted("https://www.linkedin.com/in/bob")


def test_unfinished_runs(state: sm.StateManager):
    state.get_or_create_run(2, "j", "c")
    state.get_or_create_run(3, "j2", "c2")
    state.get_or_create_run(4, "j3", "c3")
    state.update_run(2, status="COMPLETED")
    state.update_run(3, status="PAUSED")
    state.update_run(4, status="IN_PROGRESS")
    assert [r.excel_row for r in state.unfinished_runs()] == [3, 4]
