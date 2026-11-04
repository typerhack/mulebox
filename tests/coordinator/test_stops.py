"""How an unattended stop ends when a worker is lost or somebody cancels at the same moment."""

from mulebox.client import report
from mulebox.common.protocol import MessageType
from mulebox.common.status import STOP_IDLE, STOP_LIMIT, STOP_QUEUED, shown_state
from mulebox.coordinator import leases

from .helpers import queued
from .test_attendance import GONE, LIMITS, T0, beat, call, job_of, running, sweep


def stopped_view(store, job):
    row = job_of(store, job)
    return row["outcome"], row["stop_reason"], report.exit_code_for(row), shown_state(row)


STOPPED_IDLE = ("cancelled", STOP_IDLE, 76, "stopped: unattended")


def test_a_stop_the_worker_never_answered_keeps_its_reason(store, staging):
    job = running(store, staging)
    beat(store, staging, job, GONE, idle_s=0.0, output_idle_s=0.0)
    sweep(store, staging, GONE + 901)
    assert job_of(store, job)["cancel_requested"] is True
    assert leases.expire(store, GONE + 901 + leases.WORKER_LEASE_S + 1, staging) == [job["job_id"]]
    assert stopped_view(store, job) == STOPPED_IDLE


def test_a_stop_due_as_the_worker_lease_runs_out_keeps_its_reason(store, staging):
    job = running(store, staging)
    beat(store, staging, job, GONE, idle_s=0.0, output_idle_s=0.0)
    with store.write() as conn:
        conn.execute("UPDATE jobs SET worker_lease_until = ?", (GONE + 900.0,))
    assert leases.expire(store, GONE + 901, staging) == [job["job_id"]]
    assert stopped_view(store, job) == STOPPED_IDLE


def test_a_lost_worker_with_no_stop_is_still_interrupted(store, staging):
    job = running(store, staging)
    assert leases.expire(store, T0 + leases.WORKER_LEASE_S + 1, staging) == [job["job_id"]]
    assert job_of(store, job)["outcome"] == "interrupted"


def test_a_worker_back_after_a_stop_is_told_to_end_and_cannot_change_the_result(store, staging):
    job = running(store, staging)
    beat(store, staging, job, GONE, idle_s=0.0, output_idle_s=0.0)
    sweep(store, staging, GONE + 901)
    leases.expire(store, GONE + 1100, staging)
    assert beat(store, staging, job, GONE + 1200).body["cancel"] is True
    reply = call(store, staging, "result", GONE + 1201, outcome="interrupted", exit_code=None,
                 duration_s=1.0, **job)
    assert reply.type is MessageType.ERROR
    assert stopped_view(store, job) == STOPPED_IDLE


def cancel_then_report(store, staging, job, now, state=None):
    """Somebody cancels after the stop was asked for, and the worker ends the job."""
    if state:
        call(store, staging, "job_update", now, state=state, **job)
    call(store, staging, "cancel", now, job_id=job["job_id"])
    call(store, staging, "result", now, outcome="cancelled", exit_code=None, duration_s=1.0, **job)


def test_a_persons_cancel_outranks_a_stop_that_has_not_taken_effect(store, staging):
    job = running(store, staging)
    sweep(store, staging, GONE + LIMITS.max_s + 1)
    assert job_of(store, job)["stop_reason"] == STOP_LIMIT
    cancel_then_report(store, staging, job, GONE + LIMITS.max_s + 2)
    row = job_of(store, job)
    assert row["stop_reason"] is None and shown_state(row) == "cancelled"
    assert report.exit_code_for(row) == 130


def test_a_cancel_after_the_worker_acted_on_the_stop_changes_nothing(store, staging):
    job = running(store, staging)
    sweep(store, staging, GONE + LIMITS.max_s + 1)
    cancel_then_report(store, staging, job, GONE + LIMITS.max_s + 2, state="cleaning")
    row = job_of(store, job)
    assert row["stop_reason"] == STOP_LIMIT and report.exit_code_for(row) == 76


def test_a_cancel_of_a_stopped_queued_job_changes_nothing(store, staging):
    job_id = queued(store, staging, T0, detached=True)
    sweep(store, staging, GONE + LIMITS.max_s + 1)
    call(store, staging, "cancel", GONE + LIMITS.max_s + 2, job_id=job_id)
    assert store.get_job(job_id)["stop_reason"] == STOP_QUEUED
