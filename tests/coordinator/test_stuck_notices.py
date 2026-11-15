"""A job that looks stuck, as `status` and the watch stream tell it (attendance.py `looks`,
stuck_notices.py), with the real coordinator code."""

from mulebox.common.stuck import STUCK_AFTER_MIN
from mulebox.coordinator import attendance
from mulebox.coordinator.stuck_notices import LOOK_S, Teller

from .test_attendance import T0, beat, call, job_of, running, stream

QUIET = {"idle_s": 200.0, "compute_idle_s": 200.0, "io_kib_s": 0.0, "output_idle_s": 200.0,
         "last_line": "Running migrations..."}


def looks(store, staging, job, now):
    return call(store, staging, "status", now, job_id=job["job_id"]).body["looks"]


def test_status_says_a_quiet_job_looks_stuck_and_a_busy_one_works(store, staging):
    job = running(store, staging)
    beat(store, staging, job, T0 + 30, idle_s=1.0, compute_idle_s=1.0, output_idle_s=1.0)
    assert looks(store, staging, job, T0 + 31)["verdict"] == "working"
    beat(store, staging, job, T0 + 250, **QUIET)
    seen = looks(store, staging, job, T0 + 260)
    assert seen["verdict"] == "stuck" and seen["quiet_s"] == 210.0
    assert seen["limit_s"] == STUCK_AFTER_MIN * 60.0 and seen["since"] == T0 + 50.0


def test_a_project_can_raise_the_limit_but_not_lower_it(store, staging):
    job = running(store, staging, stuck_after_min=10)
    assert job_of(store, job)["stuck_after_min"] == 10
    beat(store, staging, job, T0 + 250, **QUIET)
    assert looks(store, staging, job, T0 + 260)["verdict"] == "working"
    row = {**job_of(store, job), "stuck_after_min": 1}
    assert attendance.stuck_limit_s(row, attendance.Limits()) == STUCK_AFTER_MIN * 60.0


def test_the_stream_tells_stuck_once_then_moving(store, staging):
    job = running(store, staging)
    beat(store, staging, job, T0 + 250, **QUIET)
    body = [b["stuck"] for b in stream(store, staging, job["job_id"], T0 + 260) if "stuck" in b]
    assert [(b["verdict"], b["number"]) for b in body] == [("stuck", 1)]
    assert "Looks stuck" in body[0]["text"]


def test_the_teller_says_each_change_once(store, staging):
    job = running(store, staging)
    teller = Teller(attendance.Limits())
    beat(store, staging, job, T0 + 250, **QUIET)
    first = teller.notices(job_of(store, job), [], T0 + 260)
    again = teller.notices(job_of(store, job), [], T0 + 260 + LOOK_S)
    beat(store, staging, job, T0 + 270, idle_s=0.0, compute_idle_s=0.0, output_idle_s=0.0)
    back = teller.notices(job_of(store, job), [], T0 + 270 + LOOK_S)
    assert [name for name, _ in first] == ["stuck"] and again == []
    assert back == [("moving", {"number": 1, "since": T0 + 270 + LOOK_S, "stage": None})]
