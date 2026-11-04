import os
from unittest import mock

import pytest

from mulebox.common.protocol import JobState, MessageType, Outcome
from mulebox.coordinator import api, leases

from .helpers import claimed, queued, request, submit, submit_body

T0 = 1000.0


def call(store, staging, type_, now=T0, **body):
    return api.handle(store, staging, request(type_, **body), now)


def test_submit_creates_uploading_job(store, staging):
    reply = call(store, staging, "submit", **submit_body(needs=["node"], timeout_min=20,
                                                         toolchain={"node": "22.0.0"}))
    assert reply.type is MessageType.SUBMIT_OK
    job = store.get_job(reply.body["job_id"])
    assert job["state"] == JobState.UPLOADING and job["needs"] == ["node"]
    assert job["timeout_min"] == 20 and job["toolchain"] == {"node": "22.0.0"}


def test_submit_repeat_key_returns_same_job(store, staging):
    body = submit_body(idempotency_key="sub-fixed")
    first = call(store, staging, "submit", **body)
    second = call(store, staging, "submit", **body)
    assert first.body["job_id"] == second.body["job_id"]
    assert second.request_id != first.request_id  # replies reuse each request's id


@pytest.mark.parametrize("bad", [
    {"argv": []}, {"argv": "pnpm check"}, {"timeout_min": 0}, {"timeout_min": True},
    {"needs": "docker"}, {"toolchain": {"node": 22}}, {"project": ""},
])
def test_submit_rejects_bad_fields(store, staging, bad):
    reply = call(store, staging, "submit", **submit_body(**bad))
    assert reply.type is MessageType.ERROR and reply.body["code"] == "bad_request"


def test_status_and_position(store, staging):
    first = queued(store, staging)
    second = queued(store, staging)
    reply = call(store, staging, "status", job_id=second)
    assert reply.body["position"] == 2 and reply.body["state"] == "queued"
    assert call(store, staging, "status", job_id=first).body["position"] == 1


def test_status_errors(store, staging):
    missing = call(store, staging, "status", job_id="job-01JC3X0000000000000000000Z")
    assert missing.body["code"] == "not_found"
    assert call(store, staging, "status", job_id="../etc").body["code"] == "bad_request"


def test_cancel_queued_finishes_and_removes_upload(store, staging):
    job_id = queued(store, staging)
    assert os.path.exists(staging.upload_path(job_id))
    reply = call(store, staging, "cancel", job_id=job_id)
    assert reply.body["state"] == "finished" and reply.body["outcome"] == "cancelled"
    assert not os.path.exists(staging.upload_path(job_id))
    again = call(store, staging, "cancel", job_id=job_id)
    assert again.type is MessageType.STATUS_OK


def test_cancel_running_sets_request(store, staging):
    claim = claimed(store, staging)
    reply = call(store, staging, "cancel", job_id=claim["job_id"])
    assert reply.body["state"] == "starting" and reply.body["cancel_requested"] is True


def test_client_heartbeat(store, staging):
    job_id = submit(store, staging)
    reply = call(store, staging, "heartbeat", now=T0 + 50, job_id=job_id, lease="client")
    assert reply.type is MessageType.STATUS_OK
    assert store.get_job(job_id)["client_lease_until"] == T0 + 50 + leases.CLIENT_LEASE_S
    bad = call(store, staging, "heartbeat", job_id=job_id, lease="other")
    assert bad.body["code"] == "bad_request"


def test_queue_listing(store, staging):
    claim = claimed(store, staging)
    waiting = queued(store, staging)
    done = queued(store, staging)
    call(store, staging, "cancel", job_id=done)
    reply = call(store, staging, "queue")
    jobs = reply.body["jobs"]
    assert [j["job_id"] for j in jobs] == [claim["job_id"], waiting, done]
    assert jobs[1]["position"] == 1 and jobs[0]["position"] is None
    expected = {"job_id", "project", "job", "branch", "client", "state", "outcome",
                "exit_code", "worker", "position", "created_at", "started_at", "finished_at",
                "kind", "detached"}
    assert set(jobs[0]) == expected
    assert len(call(store, staging, "queue", limit=0).body["jobs"]) == 2


def test_logs_from_offset(store, staging):
    claim = claimed(store, staging)
    staging.append_log(claim["job_id"], 0, b"line one\nline two\n")
    reply = call(store, staging, "logs", job_id=claim["job_id"], offset=9)
    assert reply.type is MessageType.LOG_CHUNK
    assert reply.body["data"] == "line two\n" and reply.body["next_offset"] == 18
    assert reply.body["eof"] is False


def test_logs_eof_when_finished(store, staging):
    job_id = queued(store, staging)
    call(store, staging, "cancel", job_id=job_id)
    reply = call(store, staging, "logs", job_id=job_id, offset=0)
    assert reply.body["eof"] is True and reply.body["data"] == ""


def test_non_request_types_are_bad_requests(store, staging):
    reply = call(store, staging, "claim_none")
    assert reply.body["code"] == "bad_request"
    reply = call(store, staging, "watch", job_id="job-01JC3X0000000000000000000Z", offset=0)
    assert reply.body["code"] == "bad_request"


def test_internal_errors_become_error_replies(store, staging):
    job_id = queued(store, staging)
    with mock.patch.object(api.queue, "position", side_effect=RuntimeError("boom")):
        reply = call(store, staging, "status", job_id=job_id)
    assert reply.body == {"code": "internal", "message": "internal error: RuntimeError"}


def test_outcome_values_on_finished_status(store, staging):
    job_id = queued(store, staging)
    call(store, staging, "cancel", job_id=job_id)
    body = call(store, staging, "status", job_id=job_id).body
    assert body["outcome"] == Outcome.CANCELLED and body["exit_code"] is None
