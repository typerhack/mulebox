"""Runner reservations in the coordinator: reserve, acquire, release, runner_jobs, FIFO."""

import pytest

from mulebox.common.protocol import JobState, MessageType, Outcome
from mulebox.coordinator import api, leases

from .helpers import queued, request

T0 = 1000.0
REPO = "example-org/example-app"


def call(store, staging, type_, now=T0, slots=1, **body):
    return api.handle(store, staging, request(type_, **body), now, cluster_slots=slots)


def reserve(store, staging, now=T0, run_id="100", worker="build-1", **extra):
    body = {"worker": worker, "repository": REPO, "job": "test", "run_id": run_id,
            "run_attempt": "1", "runner": "build-1-example-app", **extra}
    reply = call(store, staging, "reserve", now=now, **body)
    assert reply.type is MessageType.SUBMIT_OK, reply.body
    return reply.body["job_id"]


def acquire(store, staging, job_id, now=T0, slots=1):
    reply = call(store, staging, "acquire", now=now, slots=slots, job_id=job_id)
    assert reply.type is MessageType.STATUS_OK, reply.body
    return reply.body


def claim(store, staging, now=T0, slots=1, worker="build-1", free_slots=1):
    return call(store, staging, "claim", now=now, slots=slots, worker=worker,
                capabilities=["node", "docker"], free_slots=free_slots)


def finish_claimed(store, staging, body, now=T0):
    reply = call(store, staging, "result", now=now, job_id=body["job_id"],
                 attempt_id=body["attempt_id"], outcome="passed", exit_code=0, duration_s=1)
    assert reply.body["state"] == "finished"


def test_reserve_creates_queued_reservation(store, staging):
    job_id = reserve(store, staging, branch="main", run_url="https://github.example/run/1")
    job = store.get_job(job_id)
    assert job["state"] == JobState.QUEUED and job["queued_at"] == T0
    assert (job["kind"], job["project"], job["client"]) == ("runner", "example-org__example-app",
                                                            "github")
    assert (job["pinned_worker"], job["runner"], job["job"]) == (
        "build-1", "build-1-example-app", "test")
    assert job["argv"] == [] and job["client_lease_until"] is None
    assert job["idempotency_key"] == "gh-example-org/example-app-100-1-test-build-1-example-app"
    assert job["branch"] == "main" and job["run_url"] == "https://github.example/run/1"


def test_reserve_is_idempotent(store, staging):
    first = reserve(store, staging)
    assert reserve(store, staging, now=T0 + 5) == first
    assert reserve(store, staging, run_id=101) != first  # integer run ids are accepted
    keyed = reserve(store, staging, run_id="102", idempotency_key="gh-fixed")
    assert reserve(store, staging, run_id="103", idempotency_key="gh-fixed") == keyed


@pytest.mark.parametrize("field,value", [
    ("repository", "no-slash"), ("repository", "a/b/c"), ("worker", "../x"),
    ("runner", "a b"), ("run_id", ""),
])
def test_reserve_rejects_bad_fields(store, staging, field, value):
    body = {"worker": "build-1", "repository": REPO, "job": "test", "run_id": "1",
            "run_attempt": "1", "runner": "r1", field: value}
    assert call(store, staging, "reserve", **body).body["code"] == "bad_request"


def test_reservation_waits_behind_older_agent_job(store, staging):
    queued(store, staging, now=T0)
    res = reserve(store, staging, now=T0 + 1)
    assert acquire(store, staging, res) == {"job_id": res, "state": "queued", "position": 2}
    agent_job = claim(store, staging, now=T0 + 2).body  # the older agent job goes first
    assert agent_job["job_id"] != res
    assert acquire(store, staging, res, now=T0 + 3)["state"] == "queued"  # slot busy
    finish_claimed(store, staging, agent_job, now=T0 + 4)
    granted = acquire(store, staging, res, now=T0 + 5)
    assert granted["state"] == "running"
    job = store.get_job(res)
    assert job["worker"] == "build-1" and job["started_at"] == T0 + 5
    assert job["worker_lease_until"] == T0 + 5 + leases.WORKER_LEASE_S


def test_agent_job_waits_behind_older_reservation(store, staging):
    res = reserve(store, staging, now=T0)
    queued(store, staging, now=T0 + 1)
    assert claim(store, staging, now=T0 + 2).type is MessageType.CLAIM_NONE
    assert acquire(store, staging, res, now=T0 + 3)["state"] == "running"
    assert claim(store, staging, now=T0 + 4).type is MessageType.CLAIM_NONE  # slot held
    call(store, staging, "release", now=T0 + 5, job_id=res, outcome="passed")
    assert claim(store, staging, now=T0 + 6).type is MessageType.CLAIM_OK


def control(store, staging, job_id, action, now=T0):
    return call(store, staging, "job_control", now=now, job_id=job_id, action=action)


def test_a_waiting_slot_moves_in_line_and_its_new_place_holds(store, staging):
    older = queued(store, staging, now=T0)
    res = reserve(store, staging, now=T0 + 1)
    assert control(store, staging, res, "first").body["position"] == 1
    assert claim(store, staging, now=T0 + 2).type is MessageType.CLAIM_NONE  # the slot leads
    assert acquire(store, staging, res, now=T0 + 3)["state"] == "running"
    call(store, staging, "release", now=T0 + 4, job_id=res, outcome="passed")
    assert claim(store, staging, now=T0 + 5).body["job_id"] == older


def test_a_job_moved_ahead_of_a_slot_goes_first(store, staging):
    res = reserve(store, staging, now=T0)
    later = queued(store, staging, now=T0 + 1)
    control(store, staging, later, "first")
    waiting = acquire(store, staging, res, now=T0 + 2)
    assert (waiting["state"], waiting["position"]) == ("queued", 2)
    assert claim(store, staging, now=T0 + 3).body["job_id"] == later


def test_a_paused_job_does_not_hold_a_slot_back(store, staging):
    paused = queued(store, staging, now=T0)
    control(store, staging, paused, "pause")
    res = reserve(store, staging, now=T0 + 1)
    assert acquire(store, staging, res, now=T0 + 2)["state"] == "running"


def test_a_slot_only_moves(store, staging):
    res = reserve(store, staging, now=T0)
    for action in ("pause", "boost"):
        reply = control(store, staging, res, action)
        assert reply.type is MessageType.ERROR and "only move in line" in reply.body["message"]
    acquire(store, staging, res, now=T0 + 1)
    assert "only move in line" in control(store, staging, res, "first").body["message"]


def test_other_workers_are_not_blocked_by_a_pinned_reservation(store, staging):
    reserve(store, staging, now=T0, worker="build-2")
    queued(store, staging, now=T0 + 1)
    assert claim(store, staging, now=T0 + 2, slots=2).type is MessageType.CLAIM_OK


def test_two_reservations_one_slot_one_at_a_time(store, staging):
    first = reserve(store, staging, now=T0, run_id="1")
    second = reserve(store, staging, now=T0 + 1, run_id="2")
    assert acquire(store, staging, second)["position"] == 2  # the first is older
    assert acquire(store, staging, first)["state"] == "running"
    assert acquire(store, staging, second, now=T0 + 2) == {
        "job_id": second, "state": "queued", "position": 1}
    call(store, staging, "release", now=T0 + 3, job_id=first, outcome="passed")
    assert acquire(store, staging, second, now=T0 + 4)["state"] == "running"
    assert acquire(store, staging, second, now=T0 + 5)["state"] == "running"  # idempotent


def test_worker_slot_limit_applies_beside_cluster_slots(store, staging):
    queued(store, staging, now=T0)
    assert claim(store, staging, now=T0 + 1, slots=2).type is MessageType.CLAIM_OK
    res = reserve(store, staging, now=T0 + 2)
    # The cluster has two slots, but build-1 reported one slot and uses it.
    assert acquire(store, staging, res, now=T0 + 3, slots=2)["state"] == "queued"


def test_running_reservation_takes_the_agents_slot(store, staging):
    res = reserve(store, staging, now=T0)
    assert acquire(store, staging, res, slots=2)["state"] == "running"
    queued(store, staging, now=T0 + 1)
    # The agent has no job of its own, so it reports one free slot; the reservation holds it.
    assert claim(store, staging, now=T0 + 2, slots=2).type is MessageType.CLAIM_NONE


def test_release_and_release_when_finished(store, staging):
    res = reserve(store, staging, now=T0)
    acquire(store, staging, res, now=T0 + 1)
    reply = call(store, staging, "release", now=T0 + 31, job_id=res, outcome="failed")
    assert reply.body["state"] == "finished" and reply.body["outcome"] == "failed"
    assert store.get_job(res)["duration_s"] == 30
    again = call(store, staging, "release", now=T0 + 40, job_id=res, outcome="passed")
    assert again.type is MessageType.STATUS_OK and again.body["outcome"] == "failed"
    assert store.get_job(res)["finished_at"] == T0 + 31


def test_a_release_keeps_how_the_github_job_went_and_drops_what_it_does_not_know(store, staging):
    res = reserve(store, staging)
    acquire(store, staging, res, now=T0 + 1)
    said = {"outcome": "failed", "step": "Full backend test suite", "message": "x" * 900,
            "extra": "dropped", "exit": 1}
    call(store, staging, "release", now=T0 + 31, job_id=res, outcome="failed", ci_result=said)
    stored = store.get_job(res)["ci_result"]
    assert stored == {"outcome": "failed", "step": "Full backend test suite", "message": "x" * 500}
    old = reserve(store, staging, run_id="101")
    call(store, staging, "release", job_id=old, outcome="passed", ci_result="not a mapping")
    assert store.get_job(old)["ci_result"] == {}  # unknown, as from an older hook
    reply = call(store, staging, "queue")
    shown = {j["job_id"]: j.get("ci_result") for j in reply.body["jobs"]}
    assert shown[res]["step"] == "Full backend test suite"


def test_release_of_a_queued_reservation(store, staging):
    res = reserve(store, staging)
    reply = call(store, staging, "release", job_id=res, outcome="cancelled")
    assert reply.body["outcome"] == "cancelled" and store.get_job(res)["duration_s"] is None


def test_release_rejects_agent_jobs_and_timed_out(store, staging):
    agent_job = queued(store, staging)
    assert call(store, staging, "release", job_id=agent_job,
                outcome="passed").body["code"] == "bad_request"
    res = reserve(store, staging)
    assert call(store, staging, "release", job_id=res,
                outcome="timed_out").body["code"] == "bad_request"
    assert call(store, staging, "acquire", job_id=agent_job).body["code"] == "bad_request"


def test_heartbeat_without_attempt_renews_reservation(store, staging):
    res = reserve(store, staging)
    acquire(store, staging, res)
    reply = call(store, staging, "heartbeat", now=T0 + 50, job_id=res, lease="worker")
    assert reply.body["state"] == "running" and reply.body["cancel"] is False
    assert store.get_job(res)["worker_lease_until"] == T0 + 50 + leases.WORKER_LEASE_S
    update = call(store, staging, "job_update", job_id=res, state="cleaning", attempt_id="x")
    assert update.body["code"] == "bad_request"


def test_runner_jobs_lists_unfinished_reservations_of_the_worker(store, staging):
    running = reserve(store, staging, run_id="1")
    acquire(store, staging, running)
    waiting = reserve(store, staging, now=T0 + 1, run_id="2")
    done = reserve(store, staging, now=T0 + 2, run_id="3")
    call(store, staging, "release", job_id=done, outcome="cancelled")
    reserve(store, staging, run_id="4", worker="build-2")
    queued(store, staging)
    reply = call(store, staging, "runner_jobs", worker="build-1")
    assert reply.type is MessageType.QUEUE_OK
    assert [(j["job_id"], j["state"]) for j in reply.body["jobs"]] == [
        (running, "running"), (waiting, "queued")]
    assert reply.body["jobs"][0]["runner"] == "build-1-example-app"
    assert reply.body["jobs"][0]["kind"] == "runner"


def test_expire_interrupts_reservation_and_ignores_client_lease(store, staging):
    res = reserve(store, staging, now=T0)
    waiting = reserve(store, staging, now=T0, run_id="2")
    acquire(store, staging, res, now=T0)
    with store.write() as conn:  # a client lease must not matter for reservations
        conn.execute("UPDATE jobs SET client_lease_until = ? WHERE kind = 'runner'", (T0,))
    assert leases.expire(store, T0 + 60) == []
    assert store.get_job(waiting)["cancel_requested"] is False
    assert leases.expire(store, T0 + leases.WORKER_LEASE_S + 1) == [res]
    job = store.get_job(res)
    assert job["state"] == JobState.FINISHED and job["outcome"] == Outcome.INTERRUPTED
    assert store.get_job(waiting)["state"] == JobState.QUEUED


def test_worker_restart_keeps_reservations(store, staging):
    res = reserve(store, staging)
    acquire(store, staging, res)
    reply = call(store, staging, "claim", worker="build-1", capabilities=[], free_slots=1,
                 restarted=True)
    assert reply.type is MessageType.CLAIM_NONE
    assert store.get_job(res)["state"] == JobState.RUNNING


def test_a_ci_slot_usually_takes_what_past_slots_of_its_repository_took(store, staging):
    from mulebox.coordinator import usual
    for run_id, held in (("1", 100), ("2", 300), ("3", 200)):
        res = reserve(store, staging, run_id=run_id)
        acquire(store, staging, res)
        call(store, staging, "release", now=T0 + held, job_id=res, outcome="passed")
    waiting = reserve(store, staging, run_id="4")
    job = store.get_job(waiting)
    with store.read() as conn:
        assert usual.job_seconds(conn, job) == 200


def test_a_granted_slot_takes_its_runner_log_until_a_minute_after_its_release(store, staging):
    from mulebox.coordinator.reservations import LATE_LOG_S
    res = reserve(store, staging)
    acquire(store, staging, res)
    reply = call(store, staging, "log_chunk", job_id=res, offset=0, data="mulebox: step: Tests\n")
    assert reply.type is MessageType.STATUS_OK, reply.body
    assert staging.log_size(res) == len("mulebox: step: Tests\n")
    call(store, staging, "release", now=T0 + 5, job_id=res, outcome="passed")
    last = call(store, staging, "log_chunk", now=T0 + 15, job_id=res, offset=21, data="last\n")
    assert last.type is MessageType.STATUS_OK, last.body  # the last step, read after the hook
    late = call(store, staging, "log_chunk", now=T0 + 5 + LATE_LOG_S, job_id=res, offset=26,
                data="late\n")
    assert late.type is MessageType.ERROR
    assert store.get_job(res)["state"] == JobState.FINISHED
