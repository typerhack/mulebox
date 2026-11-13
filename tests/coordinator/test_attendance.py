"""A long job asks if all is well, and only a stuck one with no answer stops."""

import io
import json

import pytest

from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import STOP_STUCK, STOP_UNKNOWN
from mulebox.coordinator import api, attendance, daemon, leases
from mulebox.coordinator import store as st
from mulebox.coordinator.attendance import Limits
from mulebox.coordinator.watch import watch

from .helpers import claimed, queued, request

T0 = 1000.0
ASKED = T0 + 600.0  # with timeout_min=10
STUCK = ASKED + 600.0  # no answer for a timeout_min, and quiet since ASKED
LIMITS = Limits(idle_s=900.0, max_s=86400.0)


def call(store, staging, kind, now, **body):
    return api.handle(store, staging, request(kind, **body), now, cluster_slots=10)


def running(store, staging, now=T0, **extra):
    claim = claimed(store, staging, now, timeout_min=10, **extra)
    job = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    call(store, staging, "job_update", now, state="running", **job)
    return job


def beat(store, staging, job, now, **activity):
    return call(store, staging, "heartbeat", now, lease="worker", activity=activity, **job)


def active(store, staging, job, now):
    return beat(store, staging, job, now, idle_s=0.0, output_idle_s=0.0)


def sweep(store, staging, now):
    # Keep the workers' leases out of it.
    with store.write() as conn:
        conn.execute("UPDATE jobs SET worker_lease_until = ?", (now + 120.0,))
    return leases.expire(store, now, staging)


def job_of(store, job):
    return store.get_job(job["job_id"])


def view(store, job, now):
    row = job_of(store, job)
    with store.read() as conn:
        return attendance.question(row, now, attendance.read_limits(conn))


def test_nothing_is_asked_before_timeout_min(store, staging):
    job = running(store, staging)
    assert view(store, job, ASKED - 1) is None
    assert view(store, job, ASKED)["number"] == 1


def test_a_stuck_job_with_no_answer_stops_with_the_reason_recorded(store, staging):
    job = running(store, staging)
    active(store, staging, job, ASKED)
    sweep(store, staging, STUCK - 1)
    assert job_of(store, job)["cancel_requested"] is False
    sweep(store, staging, STUCK)
    row = job_of(store, job)
    assert row["cancel_requested"] is True and row["stop_reason"] == STOP_STUCK


@pytest.mark.parametrize("left_alone_for", [3600.0, 86400.0, 30 * 86400.0])
def test_a_working_job_is_never_stopped_with_nobody_there(store, staging, left_alone_for):
    job = running(store, staging)
    step = left_alone_for / 40
    for tick in range(1, 41):
        active(store, staging, job, T0 + tick * step)
        assert sweep(store, staging, T0 + tick * step) == []
    assert job_of(store, job)["cancel_requested"] is False


def test_a_silent_job_using_cpu_is_working(store, staging):
    job = running(store, staging)
    beat(store, staging, job, STUCK, idle_s=0.0, output_idle_s=5000.0)
    sweep(store, staging, STUCK)
    assert job_of(store, job)["cancel_requested"] is False


def test_an_answer_starts_the_count_over(store, staging):
    job = running(store, staging)
    active(store, staging, job, ASKED)
    call(store, staging, "job_ok", ASKED + 60, job_id=job["job_id"])
    assert view(store, job, ASKED + 60) is None
    sweep(store, staging, STUCK)
    assert job_of(store, job)["cancel_requested"] is False
    assert view(store, job, T0 + 1200.0)["number"] == 2


def test_an_answer_settles_every_question_so_far(store, staging):
    job = running(store, staging)
    active(store, staging, job, T0 + 1900.0)
    call(store, staging, "job_ok", T0 + 1900.0, job_id=job["job_id"])
    assert job_of(store, job)["check_in_ok"] == 3


def test_unknown_activity_never_counts_as_idle(store, staging):
    job = running(store, staging)
    sweep(store, staging, T0 + LIMITS.max_s - 1)
    assert job_of(store, job)["cancel_requested"] is False
    sweep(store, staging, T0 + LIMITS.max_s)
    assert job_of(store, job)["stop_reason"] == STOP_UNKNOWN


def test_a_queued_job_is_never_stopped_or_asked(store, staging):
    job_id = queued(store, staging, T0, timeout_min=1)
    assert sweep(store, staging, T0 + 30 * 86400.0) == []
    row = store.get_job(job_id)
    assert row["state"] == "queued" and row["cancel_requested"] is False


def test_a_job_with_a_client_gone_is_treated_the_same(store, staging):
    job = running(store, staging)  # attached: no `detached`
    active(store, staging, job, T0 + 500)
    assert sweep(store, staging, T0 + 500 + leases.CLIENT_LEASE_S) == []
    assert job_of(store, job)["cancel_requested"] is False


def test_a_runner_reservation_is_never_asked(store, staging):
    job = running(store, staging)
    with store.write() as conn:
        conn.execute("UPDATE jobs SET kind = 'runner'")
    assert view(store, job, STUCK * 10) is None


def test_a_cancelled_job_is_not_asked(store, staging):
    job = running(store, staging)
    call(store, staging, "cancel", ASKED + 1, job_id=job["job_id"])
    assert view(store, job, ASKED + 2) is None


def test_limits_come_from_what_the_service_saved(store, staging, node):
    attendance.save_limits(store, daemon.limits_of(node))
    with store.read() as conn:
        assert attendance.read_limits(conn) == daemon.limits_of(node)


def test_status_has_the_activity_and_the_question(store, staging):
    job = running(store, staging)
    beat(store, staging, job, T0 + 40, output_idle_s=12.5, idle_s=2.0, cpu_pct=180.0, net_kib_s=1.5)
    body = call(store, staging, "status", T0 + 42, job_id=job["job_id"]).body
    assert body["question"] is None
    assert body["activity"] == {"elapsed_s": 42.0, "stage": None, "output_idle_s": 12.5,
                                "idle_s": 2.0, "job_cpu_pct": None, "cpu_pct": 180.0,
                                "net_kib_s": 1.5, "last_line": None, "download": None}
    assert call(store, staging, "status", ASKED, job_id=job["job_id"]).body["question"]["reason"]


def test_queue_and_submit_name_waiting_questions(store, staging):
    from .helpers import submit_body
    job = running(store, staging)
    assert "question" not in call(store, staging, "queue", T0 + 1).body["jobs"][0]
    assert call(store, staging, "queue", ASKED).body["jobs"][0]["question"]["left_s"] > 0
    reply = call(store, staging, "submit", ASKED, **submit_body())
    assert [j["job_id"] for j in reply.body["questions"]] == [job["job_id"]]
    assert not call(store, staging, "submit", ASKED,
                    **submit_body(project="other-app")).body["questions"]


def stream(store, staging, job_id, clock, **body):
    out = io.BytesIO()
    msg = Message(MessageType.WATCH, "req-w", {"job_id": job_id, "offset": 0, **body})

    class Done(Exception):
        pass

    def sleep(_):
        raise Done

    try:
        watch(store, staging, msg, io.BytesIO(), out, clock=lambda: clock, sleep=sleep)
    except Done:
        pass
    return [json.loads(line)["body"] for line in out.getvalue().splitlines()]


def test_a_running_job_checks_in_every_timeout_min(store, staging):
    job = running(store, staging)
    assert not [b for b in stream(store, staging, job["job_id"], T0 + 599, lease=True)
                if "check_in" in b]
    beat(store, staging, job, T0 + 1500, output_idle_s=30.0, idle_s=1.0, cpu_pct=99.0, net_kib_s=2.0)
    found = [b["check_in"] for b in stream(store, staging, job["job_id"], T0 + 1500, lease=True)
             if "check_in" in b]
    assert found == [{"number": 2, "elapsed_s": 1500.0, "stage": None, "output_idle_s": 30.0,
                      "idle_s": 1.0, "job_cpu_pct": None, "cpu_pct": 99.0,
                      "net_kib_s": 2.0, "last_line": None, "download": None}]


def test_status_gives_the_download_with_only_its_known_keys(store, staging):
    job = running(store, staging)
    beat(store, staging, job, T0 + 40, download={
        "what": "cache", "name": "pip cache", "done_bytes": 1418315, "total_bytes": 9806923.0,
        "stalled": "yes", "net_scope": "elsewhere", "extra": 1})
    found = call(store, staging, "status", T0 + 42, job_id=job["job_id"]).body["activity"]
    assert found["download"]["done_bytes"] == 1418315
    assert found["download"]["total_bytes"] == 9806923 and found["download"]["stalled"] is None
    assert found["download"]["net_scope"] is None and "extra" not in found["download"]


def test_a_queued_job_does_not_check_in(store, staging):
    job_id = queued(store, staging, T0, timeout_min=1)
    assert not any("check_in" in b for b in stream(store, staging, job_id, T0 + 9000, lease=True))
