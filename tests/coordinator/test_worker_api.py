import os

from mulebox.common.protocol import MessageType

from .helpers import claimed, queued
from .test_api import T0, call


def test_claim_ok_body(store, staging):
    queued(store, staging, setup="pnpm install", toolchain={"node": "22.0.0"}, needs=["node"])
    reply = call(store, staging, "claim", worker="wrk-a", capabilities=["node"], free_slots=1)
    assert reply.type is MessageType.CLAIM_OK
    assert set(reply.body) == {"job_id", "attempt_id", "project", "job", "branch", "argv",
                               "fingerprint",
                               "base_commit", "timeout_min", "setup", "install", "toolchain", "needs", "env",
                               "env_order", "limits"}
    assert reply.body["setup"] == "pnpm install" and reply.body["argv"] == ["pnpm", "check"]


def test_claim_none(store, staging):
    reply = call(store, staging, "claim", worker="wrk-a", capabilities=[], free_slots=1)
    assert reply.type is MessageType.CLAIM_NONE
    bad = call(store, staging, "claim", worker="wrk-a", capabilities=[], free_slots=-1)
    assert bad.body["code"] == "bad_request"


def test_full_worker_flow(store, staging):
    claim = claimed(store, staging)
    ids = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    reply = call(store, staging, "job_update", now=T0 + 10, state="running", **ids)
    assert reply.body["state"] == "running" and reply.body["cancel"] is False
    assert store.get_job(claim["job_id"])["worker_lease_until"] == T0 + 10 + 120
    reply = call(store, staging, "log_chunk", offset=0, data="hello\n", **ids)
    assert reply.body["log_size"] == 6
    call(store, staging, "log_chunk", offset=0, data="hello\n", **ids)  # resend: no-op
    assert store.get_job(claim["job_id"])["log_size"] == 6
    reply = call(store, staging, "heartbeat", lease="worker", **ids)
    assert reply.body["cancel"] is False
    call(store, staging, "job_update", state="cleaning", **ids)
    reply = call(store, staging, "result", now=T0 + 99, outcome="passed", exit_code=0,
                 duration_s=12.5, **ids)
    assert reply.body["state"] == "finished" and reply.body["outcome"] == "passed"
    job = store.get_job(claim["job_id"])
    assert job["exit_code"] == 0 and job["duration_s"] == 12.5 and job["finished_at"] == T0 + 99
    assert not os.path.exists(staging.upload_path(claim["job_id"]))
    again = call(store, staging, "result", outcome="passed", exit_code=0, duration_s=1, **ids)
    assert again.body["code"] == "conflict"
    late = call(store, staging, "log_chunk", offset=6, data="late", **ids)
    assert late.body["code"] == "conflict"


def test_stale_attempt_is_conflict_everywhere(store, staging):
    claim = claimed(store, staging)
    stale = {"job_id": claim["job_id"], "attempt_id": "att-01JC3X0000000000000000000Z"}
    replies = [
        call(store, staging, "job_update", state="running", **stale),
        call(store, staging, "log_chunk", offset=0, data="x", **stale),
        call(store, staging, "result", outcome="passed", exit_code=0, duration_s=1, **stale),
        call(store, staging, "heartbeat", lease="worker", **stale),
    ]
    assert [r.body["code"] for r in replies] == ["conflict"] * 4
    missing = call(store, staging, "job_update", state="running", job_id=claim["job_id"])
    assert missing.body["code"] == "bad_request"


def test_cancel_reaches_worker_heartbeat(store, staging):
    claim = claimed(store, staging)
    call(store, staging, "cancel", job_id=claim["job_id"])
    reply = call(store, staging, "heartbeat", lease="worker", job_id=claim["job_id"],
                 attempt_id=claim["attempt_id"])
    assert reply.body["cancel"] is True


def test_invalid_transition_and_finished_update(store, staging):
    claim = claimed(store, staging)
    ids = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    assert call(store, staging, "job_update", state="queued", **ids).body["code"] == "conflict"
    assert call(store, staging, "job_update", state="finished", **ids).body["code"] == "bad_request"


def test_log_gap_is_conflict(store, staging):
    claim = claimed(store, staging)
    reply = call(store, staging, "log_chunk", offset=5, data="x", job_id=claim["job_id"],
                 attempt_id=claim["attempt_id"])
    assert reply.body["code"] == "conflict"


def test_first_claim_after_restart_interrupts_the_old_jobs(store, staging):
    old = claimed(store, staging, worker="wrk-a")
    reply = call(store, staging, "claim", worker="wrk-a", capabilities=[], free_slots=1,
                 restarted=True)
    assert reply.type is MessageType.CLAIM_NONE
    assert store.get_job(old["job_id"])["outcome"] == "interrupted"
