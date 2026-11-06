"""A stuck job's stop, against everything that can happen around it."""

from mulebox.client import report
from mulebox.common.protocol import MessageType
from mulebox.common.status import STOP_STUCK, shown_state
from mulebox.coordinator import leases

from .test_attendance import ASKED, STUCK, T0, active, beat, call, job_of, running, sweep


def stopped_view(store, job):
    row = job_of(store, job)
    return row["outcome"], row["stop_reason"], report.exit_code_for(row), shown_state(row)


STOPPED = ("cancelled", STOP_STUCK, 76, "stopped: stuck")


def stuck(store, staging):
    job = running(store, staging)
    active(store, staging, job, ASKED)
    sweep(store, staging, STUCK)
    return job


def test_the_worker_cancel_comes_back_as_a_stop(store, staging):
    job = stuck(store, staging)
    assert beat(store, staging, job, STUCK + 1).body["cancel"] is True
    call(store, staging, "result", STUCK + 2, outcome="cancelled", exit_code=None, duration_s=1.0,
         **job)
    assert stopped_view(store, job) == STOPPED


def test_a_stop_the_worker_never_answered_keeps_its_reason(store, staging):
    job = stuck(store, staging)
    assert leases.expire(store, STUCK + leases.WORKER_LEASE_S + 1, staging) == [job["job_id"]]
    assert stopped_view(store, job) == STOPPED


def test_a_lost_worker_with_no_stop_is_still_interrupted(store, staging):
    job = running(store, staging)
    assert leases.expire(store, T0 + leases.WORKER_LEASE_S + 1, staging) == [job["job_id"]]
    assert job_of(store, job)["outcome"] == "interrupted"


def test_a_worker_back_after_a_stop_cannot_change_the_result(store, staging):
    job = stuck(store, staging)
    leases.expire(store, STUCK + 200, staging)
    assert beat(store, staging, job, STUCK + 300).body["cancel"] is True
    reply = call(store, staging, "result", STUCK + 301, outcome="interrupted", exit_code=None,
                 duration_s=1.0, **job)
    assert reply.type is MessageType.ERROR
    assert stopped_view(store, job) == STOPPED


def cancel_then_report(store, staging, job, now, state=None):
    if state:
        call(store, staging, "job_update", now, state=state, **job)
    call(store, staging, "cancel", now, job_id=job["job_id"])
    call(store, staging, "result", now, outcome="cancelled", exit_code=None, duration_s=1.0, **job)


def test_a_persons_cancel_outranks_a_stop_that_has_not_taken_effect(store, staging):
    job = stuck(store, staging)
    cancel_then_report(store, staging, job, STUCK + 2)
    row = job_of(store, job)
    assert row["stop_reason"] is None and shown_state(row) == "cancelled"
    assert report.exit_code_for(row) == 130


def test_a_cancel_after_the_worker_acted_on_the_stop_changes_nothing(store, staging):
    job = stuck(store, staging)
    cancel_then_report(store, staging, job, STUCK + 2, state="cleaning")
    row = job_of(store, job)
    assert row["stop_reason"] == STOP_STUCK and report.exit_code_for(row) == 76


def test_a_job_that_beat_its_stop_keeps_its_result(store, staging):
    job = stuck(store, staging)
    call(store, staging, "result", STUCK + 1, outcome="passed", exit_code=0, duration_s=1.0, **job)
    row = job_of(store, job)
    assert row["outcome"] == "passed" and shown_state(row) != "stopped: stuck"
