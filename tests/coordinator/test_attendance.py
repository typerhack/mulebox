"""Who is watching a job, and what happens to a job nobody watches."""

import io
import json

import pytest

from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import STOP_IDLE, STOP_LIMIT, STOP_QUEUED
from mulebox.coordinator import api, attendance, daemon, leases
from mulebox.coordinator import store as st
from mulebox.coordinator.attendance import Limits
from mulebox.coordinator.watch import watch

from .helpers import claimed, queued, request

T0 = 1000.0
LEASE = leases.CLIENT_LEASE_S
LIMITS = Limits(idle_s=900.0, max_s=86400.0)
GONE = T0 + LEASE  # the moment nobody has been watching


def call(store, staging, kind, now, **body):
    return api.handle(store, staging, request(kind, **body), now, cluster_slots=10)


def running(store, staging, now=T0, **extra):
    claim = claimed(store, staging, now, detached=True, **extra)
    job = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    call(store, staging, "job_update", now, state="running", **job)
    return job


def beat(store, staging, job, now, **activity):
    return call(store, staging, "heartbeat", now, lease="worker", activity=activity, **job)


def sweep(store, staging, now):
    # Keep the workers' leases out of it: these tests are about the client's.
    with store.write() as conn:
        conn.execute("UPDATE jobs SET worker_lease_until = ?", (now + 120.0,))
    return leases.expire(store, now, staging)


def job_of(store, job):
    return store.get_job(job["job_id"])


def view(store, job, now):
    row = job_of(store, job)
    with store.read() as conn:
        return attendance.unattended(row, now, attendance.read_limits(conn))


def test_a_detached_job_is_watched_until_its_lease_runs_out(store, staging):
    job = running(store, staging)
    assert view(store, job, GONE - 1) is None
    assert view(store, job, GONE)["since"] == GONE


def test_unknown_activity_never_counts_as_idle(store, staging):
    """An older worker reports nothing: only the long limit applies."""
    job = running(store, staging)
    call(store, staging, "heartbeat", GONE, lease="worker", **job)
    assert view(store, job, GONE + 3600)["stop_reason"] == STOP_LIMIT
    sweep(store, staging, GONE + 3600)
    assert job_of(store, job)["cancel_requested"] is False


def test_a_report_that_cannot_tell_clears_what_was_known(store, staging):
    job = running(store, staging)
    beat(store, staging, job, GONE, idle_s=5.0, output_idle_s=5.0)
    assert view(store, job, GONE + 1)["stop_reason"] == STOP_IDLE
    beat(store, staging, job, GONE + 2, idle_s=None, output_idle_s=9.0)
    assert view(store, job, GONE + 3)["stop_reason"] == STOP_LIMIT


def test_a_quiet_unattended_job_is_stopped_with_the_reason_recorded(store, staging):
    job = running(store, staging)
    beat(store, staging, job, GONE + 10, idle_s=60.0, output_idle_s=60.0)
    assert view(store, job, GONE + 10)["left_s"] == pytest.approx(890.0)  # from GONE
    sweep(store, staging, GONE + 899)
    assert job_of(store, job)["cancel_requested"] is False
    sweep(store, staging, GONE + 901)
    row = job_of(store, job)
    assert row["cancel_requested"] is True and row["stop_reason"] == STOP_IDLE
    reply = beat(store, staging, job, GONE + 902, idle_s=1.0)
    assert reply.body["cancel"] is True


def test_a_silent_but_busy_job_is_not_stopped(store, staging):
    """Output stopped long ago, the machine is working: idle_s stays low."""
    job = running(store, staging)
    for minute in range(0, 120, 5):
        now = GONE + minute * 60
        beat(store, staging, job, now, output_idle_s=minute * 60.0, idle_s=3.0, cpu_pct=390.0)
        sweep(store, staging, now)
    assert job_of(store, job)["cancel_requested"] is False


def test_an_active_job_stops_at_the_long_limit(store, staging):
    job = running(store, staging)
    now = GONE + LIMITS.max_s + 1
    beat(store, staging, job, now, idle_s=0.0, output_idle_s=0.0)
    sweep(store, staging, now)
    assert job_of(store, job)["stop_reason"] == STOP_LIMIT


def test_the_worker_cancel_comes_back_as_a_stop(store, staging):
    job = running(store, staging)
    sweep(store, staging, GONE + LIMITS.max_s + 1)
    now = GONE + LIMITS.max_s + 5
    call(store, staging, "job_update", now, state="cleaning", **job)
    reply = call(store, staging, "result", now, outcome="cancelled", exit_code=None,
                 duration_s=5.0, **job)
    assert reply.body["outcome"] == "cancelled" and reply.body["stop_reason"] == STOP_LIMIT


def test_a_job_that_beat_its_stop_keeps_its_result(store, staging):
    job = running(store, staging)
    sweep(store, staging, GONE + LIMITS.max_s + 1)
    now = GONE + LIMITS.max_s + 2
    call(store, staging, "job_update", now, state="cleaning", **job)
    call(store, staging, "result", now, outcome="passed", exit_code=0, duration_s=5.0, **job)
    assert job_of(store, job)["stop_reason"] is None


def test_a_detached_queued_job_warns_and_stops_at_the_long_limit(store, staging):
    job = {"job_id": queued(store, staging, T0, detached=True)}
    assert view(store, job, GONE + 3600)["stop_reason"] == STOP_QUEUED
    finished = sweep(store, staging, GONE + LIMITS.max_s - 1)
    assert not finished
    assert sweep(store, staging, GONE + LIMITS.max_s + 1) == [job["job_id"]]
    row = job_of(store, job)
    assert row["outcome"] == "cancelled" and row["stop_reason"] == STOP_QUEUED


def test_watching_takes_a_job_back_and_the_count_starts_over(store, staging):
    job = running(store, staging)
    assert view(store, job, GONE + 600) is not None
    leases.renew_client(store, job["job_id"], GONE + 600)
    assert view(store, job, GONE + 601) is None
    assert view(store, job, GONE + 600 + LEASE)["since"] == GONE + 600 + LEASE


def test_a_job_with_a_client_is_never_unattended_and_is_cancelled_as_before(store, staging):
    claim = claimed(store, staging)
    job = {"job_id": claim["job_id"]}
    assert view(store, job, GONE) is None
    sweep(store, staging, GONE + 1)
    row = job_of(store, job)
    assert row["cancel_requested"] is True and row["stop_reason"] is None


def test_a_runner_reservation_is_never_unattended(store, staging):
    reply = call(store, staging, "reserve", T0, worker="wrk-a", repository="example/app",
                 job="ci", run_id="1", run_attempt="1", runner="r1")
    job = {"job_id": reply.body["job_id"]}
    with store.write() as conn:
        conn.execute("UPDATE jobs SET detached = 1, client_lease_until = 1")
    assert view(store, job, T0 + LIMITS.max_s * 2) is None
    sweep(store, staging, T0 + LIMITS.max_s * 2)
    assert job_of(store, job)["stop_reason"] is None


def test_a_cancelled_job_is_not_shown_as_unattended(store, staging):
    job = running(store, staging)
    call(store, staging, "cancel", GONE + 1, job_id=job["job_id"])
    assert view(store, job, GONE + 2) is None


def test_limits_come_from_what_the_service_saved(store, staging, node):
    with store.read() as conn:
        assert attendance.read_limits(conn) == Limits()
    attendance.save_limits(store, Limits(idle_s=60.0, max_s=7200.0))
    with store.read() as conn:
        assert attendance.read_limits(conn) == Limits(idle_s=60.0, max_s=7200.0)
    job = running(store, staging)
    beat(store, staging, job, GONE, idle_s=0.0)
    assert view(store, job, GONE)["left_s"] == pytest.approx(60.0)
    assert daemon.limits_of(node) == Limits()


def test_status_is_the_activity_view(store, staging):
    job = running(store, staging)
    beat(store, staging, job, T0 + 40, output_idle_s=12.5, idle_s=2.0, cpu_pct=180.0, net_kib_s=1.5)
    body = call(store, staging, "status", T0 + 42, job_id=job["job_id"]).body
    assert body["attended"] is True and body["unattended"] is None
    assert body["activity"] == {"elapsed_s": 42.0, "stage": None, "output_idle_s": 12.5,
                                "idle_s": 2.0, "job_cpu_pct": None, "cpu_pct": 180.0,
                                "net_kib_s": 1.5}
    away = call(store, staging, "status", GONE + 1, job_id=job["job_id"]).body
    assert away["attended"] is False and away["unattended"]["reason"]


def test_queue_and_submit_name_unattended_jobs(store, staging):
    job = running(store, staging)
    rows = call(store, staging, "queue", GONE + 1).body["jobs"]
    assert rows[0]["unattended"]["left_s"] > 0
    assert "unattended" not in call(store, staging, "queue", T0 + 1).body["jobs"][0]
    other = claimed_body()
    reply = call(store, staging, "submit", GONE + 2, **other)
    assert [j["job_id"] for j in reply.body["unattended"]] == [job["job_id"]]
    assert not call(store, staging, "submit", GONE + 2,
                    **claimed_body(project="other-app")).body["unattended"]


def claimed_body(**extra):
    from .helpers import submit_body
    return submit_body(**extra)


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


def test_a_watcher_takes_a_job_back_and_hears_that_it_was_unattended(store, staging):
    job = running(store, staging)
    bodies = stream(store, staging, job["job_id"], GONE + 60, lease=False, log=False)
    notices = [b["unattended"] for b in bodies if "unattended" in b]
    assert len(notices) == 1 and notices[0]["taken_back"] is True
    assert notices[0]["left_s"] > 0
    assert view(store, job, GONE + 61) is None


def test_watching_never_holds_the_lease_of_a_job_with_a_client(store, staging):
    claim = claimed(store, staging)
    stream(store, staging, claim["job_id"], T0 + 100, lease=False, log=False)
    assert store.get_job(claim["job_id"])["client_lease_until"] == GONE


def test_a_running_job_checks_in_every_timeout_min(store, staging):
    job = running(store, staging, timeout_min=10)
    assert not [b for b in stream(store, staging, job["job_id"], T0 + 599, lease=True)
                if "check_in" in b]
    beat(store, staging, job, T0 + 1500, output_idle_s=30.0, idle_s=1.0, cpu_pct=99.0, net_kib_s=2.0)
    found = [b["check_in"] for b in stream(store, staging, job["job_id"], T0 + 1500, lease=True)
             if "check_in" in b]
    assert found == [{"number": 2, "elapsed_s": 1500.0, "stage": None, "output_idle_s": 30.0,
                      "idle_s": 1.0, "job_cpu_pct": None, "cpu_pct": 99.0,
                      "net_kib_s": 2.0}]


def test_a_queued_job_does_not_check_in(store, staging):
    job_id = queued(store, staging, T0, detached=True, timeout_min=1)
    assert not any("check_in" in b for b in stream(store, staging, job_id, T0 + 9000, lease=True))


def test_store_keeps_the_report_as_given(store, staging):
    job = running(store, staging)
    beat(store, staging, job, T0 + 5, idle_s=2.0, output_idle_s=4.0)
    with store.read() as conn:
        row = st.fetch_job(conn, job["job_id"])
    assert row["activity"] == {"idle_s": 2.0, "output_idle_s": 4.0}
    assert row["active_at"] == T0 + 3
