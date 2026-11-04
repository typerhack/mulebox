"""An unattended job in what the dashboard reads, and a stopped job in its history."""

from mulebox.coordinator import attendance, leases
from mulebox.coordinator import store as st
from mulebox.coordinator.attendance import Limits
from mulebox.dashboard import machines

from .conftest import NOW

GONE = NOW + 10.0


def leave(store, job_id):
    """The job is detached, and its lease ran out at GONE."""
    with store.write() as conn:
        st.update_job(conn, job_id, detached=1, client_lease_until=GONE)


def test_the_queue_row_and_the_machine_row_both_say_it(data, store, run_job):
    job_id, _ = run_job()
    leave(store, job_id)
    row = data.queue_snapshot(GONE + 100.0)["running"][0]
    assert row["unattended"]["stop_reason"] == "unattended_limit"
    assert row["unattended"]["left_s"] == Limits().max_s - 100.0
    panel = data.machines(GONE + 100.0)
    assert panel["machines"][0]["jobs"][0]["unattended"] == row["unattended"]


def test_a_watched_job_carries_nothing(data, store, run_job):
    job_id, _ = run_job()
    leave(store, job_id)
    row = data.queue_snapshot(GONE - 1.0)["running"][0]
    assert "unattended" not in row
    assert "unattended" not in data.machines(GONE - 1.0)["machines"][0]["jobs"][0]


def test_the_limits_come_from_what_the_service_saved(data, store, run_job):
    job_id, _ = run_job()
    leave(store, job_id)
    attendance.save_limits(store, Limits(idle_s=60.0, max_s=7200.0))
    row = data.queue_snapshot(GONE)["running"][0]
    assert row["unattended"]["left_s"] == 7200.0


def test_the_job_page_has_it_too(data, store, run_job):
    job_id, _ = run_job()
    leave(store, job_id)
    assert data.job(job_id, GONE + 1.0)["unattended"]["since"] == GONE
    assert "unattended" not in data.job(job_id, GONE - 1.0)


def test_panels_change_with_the_minutes_left_not_with_the_seconds(data, store, run_job):
    job_id, _ = run_job()
    leave(store, job_id)
    mark = machines.fingerprint(data.machines(GONE + 1.0))
    assert machines.fingerprint(data.machines(GONE + 1.5)) == mark
    assert machines.fingerprint(data.machines(GONE + 90.0)) != mark


def test_taking_a_job_back_changes_the_panel(data, store, run_job):
    job_id, _ = run_job()
    leave(store, job_id)
    gone = machines.fingerprint(data.machines(GONE + 1.0))
    with store.write() as conn:
        st.update_job(conn, job_id, client_lease_until=GONE + 300.0)
    assert machines.fingerprint(data.machines(GONE + 1.0)) != gone


def test_a_stopped_job_reads_stopped_in_every_place(data, store, staging, run_job, finish_job):
    job_id, state = run_job()
    leave(store, job_id)
    with store.write() as conn:
        st.update_job(conn, job_id, active_at=NOW, worker_lease_until=GONE + 5000.0)
    leases.expire(store, GONE + Limits().idle_s + 1.0, staging)
    finish_job(state, "cancelled", None, now=GONE + 1000.0)
    expected = "stopped: unattended"
    assert data.job(job_id)["shown_state"] == expected
    assert data.job(job_id)["stop_text"] == "no activity while nobody watched"
    assert data.queue_snapshot(GONE + 2000.0)["recent"][0]["shown_state"] == expected
    assert data.history()["jobs"][0]["shown_state"] == expected
