"""A waiting question in what the dashboard reads, and a stopped job in its history."""

from mulebox.coordinator import attendance, leases
from mulebox.coordinator import store as st
from mulebox.coordinator.attendance import ANSWER_S, Limits
from mulebox.dashboard import machines

from .conftest import NOW

ASKED = NOW + 600.0


def ask(store, job_id):
    with store.write() as conn:
        st.update_job(conn, job_id, started_at=NOW, timeout_min=10)


def test_the_queue_row_and_the_machine_row_both_say_it(data, store, run_job):
    job_id, _ = run_job()
    ask(store, job_id)
    row = data.queue_snapshot(ASKED + 100.0)["running"][0]
    assert row["question"]["stop_reason"] == "stuck_unknown"
    assert row["question"]["left_s"] == NOW + Limits().max_s - ASKED - 100.0
    panel = data.machines(ASKED + 100.0)
    assert panel["machines"][0]["jobs"][0]["question"] == row["question"]


def test_nothing_is_carried_before_it_is_asked(data, store, run_job):
    job_id, _ = run_job()
    ask(store, job_id)
    row = data.queue_snapshot(ASKED - 1.0)["running"][0]
    assert "question" not in row
    assert "question" not in data.machines(ASKED - 1.0)["machines"][0]["jobs"][0]


def test_the_job_page_has_it_too(data, store, run_job):
    job_id, _ = run_job()
    ask(store, job_id)
    assert data.job(job_id, ASKED + 1.0)["question"]["since"] == ASKED
    assert "question" not in data.job(job_id, ASKED - 1.0)


def test_panels_change_with_the_minutes_left_not_with_the_seconds(data, store, run_job):
    job_id, _ = run_job()
    ask(store, job_id)
    mark = machines.fingerprint(data.machines(ASKED + 1.0))
    assert machines.fingerprint(data.machines(ASKED + 1.5)) == mark
    assert machines.fingerprint(data.machines(ASKED + 90.0)) != mark


def test_an_answer_changes_the_panel(data, store, run_job):
    job_id, _ = run_job()
    ask(store, job_id)
    waiting = machines.fingerprint(data.machines(ASKED + 1.0))
    with store.write() as conn:
        st.update_job(conn, job_id, check_in_ok=1)
    assert machines.fingerprint(data.machines(ASKED + 1.0)) != waiting


def test_a_stopped_job_reads_stopped_in_every_place(data, store, staging, run_job, finish_job):
    job_id, state = run_job()
    ask(store, job_id)
    stuck = ASKED + ANSWER_S
    with store.write() as conn:
        st.update_job(conn, job_id, active_at=ASKED, worker_lease_until=stuck + 5000.0)
    leases.expire(store, stuck, staging)
    finish_job(state, "cancelled", None, now=stuck + 10.0)
    expected = "stopped: stuck"
    assert data.job(job_id)["shown_state"] == expected
    assert data.job(job_id)["stop_text"] == "no activity and no answer from the agent"
    assert data.queue_snapshot(stuck + 20.0)["recent"][0]["shown_state"] == expected
    assert data.history()["jobs"][0]["shown_state"] == expected


def test_the_limits_come_from_what_the_service_saved(data, store, run_job):
    job_id, _ = run_job()
    ask(store, job_id)
    attendance.save_limits(store, Limits(idle_s=60.0, max_s=7200.0))
    assert data.queue_snapshot(ASKED)["running"][0]["question"]["left_s"] == 6600.0
