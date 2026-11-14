"""Which free node takes a job (coordinator/node_choice.py) and `--on <node>` (api.py, queue.py)."""

import io

from mulebox.common.protocol import MessageType
from mulebox.coordinator import api, node_choice, uploads
from mulebox.coordinator import store as st

from .helpers import queued, request, snapshot, submit_body


def claim(store, staging, worker, now, *, slots=2, free=None, priority="normal", caps=("node",)):
    body = {"worker": worker, "capabilities": list(caps),
            "free_slots": slots if free is None else free,
            "settings": {"slots": slots, "priority": priority}}
    return api.handle(store, staging, request("claim", **body), now, cluster_slots=1)


def seen(store, staging, now=1.0, **nodes):
    """Make each node known and online with its free slots, taking nothing."""
    for name, free in nodes.items():
        claim(store, staging, name, now, slots=max(free, 1), free=free)


def old_job(store, worker, branch, now=5.0, **extra):
    """A finished job of `branch` that ran on `worker`."""
    body = submit_body(branch=branch)
    with store.write() as conn:
        st.insert_job(conn, {
            **{k: body[k] for k in ("project", "job", "argv", "idempotency_key", "fingerprint",
                                    "base_commit", "client", "branch")},
            "job_id": f"job-old-{worker}-{now}", "state": "finished", "created_at": now,
            "started_at": now, "finished_at": now + 1, "worker": worker, "timeout_min": 30,
            "outcome": "passed", "exit_code": 0, **extra})


def ran_on(store, worker, branch, now=5.0):
    old_job(store, worker, branch, now)


def test_the_node_holding_the_branch_goes_first(store, staging):
    seen(store, staging, **{"build-1": 1, "build-2": 1})
    ran_on(store, "build-2", "main")
    queued(store, staging, now=10.0, branch="main")
    assert claim(store, staging, "build-1", 11.0, slots=1).type is MessageType.CLAIM_NONE
    reply = claim(store, staging, "build-2", 12.0, slots=1)
    assert reply.type is MessageType.CLAIM_OK


def test_a_node_waits_for_the_branchs_node_only_a_while(store, staging):
    """The branch's node is free but never asks (an upgrade ahead of it there, say)."""
    seen(store, staging, now=10.0, **{"build-1": 1, "build-2": 1})
    ran_on(store, "build-2", "main")
    queued(store, staging, now=10.0, branch="main")
    assert claim(store, staging, "build-1", 11.0, slots=1).type is MessageType.CLAIM_NONE
    assert claim(store, staging, "build-1", 11.0 + node_choice.HOLD_S - 1,
                 slots=1).type is MessageType.CLAIM_NONE
    reply = claim(store, staging, "build-1", 11.0 + node_choice.HOLD_S, slots=1)
    assert reply.type is MessageType.CLAIM_OK


def test_with_no_branch_node_the_one_with_more_room_goes_first(store, staging):
    seen(store, staging, **{"build-1": 1, "build-2": 3})
    queued(store, staging, now=10.0)
    assert claim(store, staging, "build-1", 11.0, slots=1).type is MessageType.CLAIM_NONE
    assert claim(store, staging, "build-2", 12.0, slots=3).type is MessageType.CLAIM_OK


def test_a_tie_is_no_reason_to_wait(store, staging):
    seen(store, staging, **{"build-1": 2, "build-2": 2})
    queued(store, staging, now=10.0)
    assert claim(store, staging, "build-1", 11.0).type is MessageType.CLAIM_OK


def test_priority_still_comes_before_the_branch(store, staging):
    claim(store, staging, "spare-1", 1.0, priority="preferred")
    claim(store, staging, "desk-1", 1.0)
    ran_on(store, "desk-1", "main")
    queued(store, staging, now=10.0, branch="main")
    assert claim(store, staging, "desk-1", 11.0).type is MessageType.CLAIM_NONE
    assert claim(store, staging, "spare-1", 12.0, priority="preferred").type is MessageType.CLAIM_OK


def test_the_wait_counts_from_the_first_time_a_job_was_left(store, staging):
    """A job that sat in a busy line still gets the branch's node once it is free."""
    seen(store, staging, **{"build-1": 1, "build-2": 1})
    ran_on(store, "build-2", "main")
    queued(store, staging, now=10.0, branch="main")
    late = 10.0 + 10 * node_choice.HOLD_S
    claim(store, staging, "build-2", late, slots=1)  # online again, free, but asks after
    seen_now = claim(store, staging, "build-1", late + 1, slots=1)
    assert seen_now.type is MessageType.CLAIM_NONE


def test_a_job_sent_on_a_node_waits_for_that_node_alone(store, staging):
    seen(store, staging, **{"build-1": 2, "build-2": 2})
    job_id = queued(store, staging, now=10.0, on="build-2")
    assert claim(store, staging, "build-1", 10_000.0).type is MessageType.CLAIM_NONE
    reply = claim(store, staging, "build-2", 10_001.0)
    assert reply.type is MessageType.CLAIM_OK and reply.body["job_id"] == job_id


def test_on_is_echoed_and_shown(store, staging):
    seen(store, staging, **{"build-1": 1})
    reply = api.handle(store, staging, request("submit", **submit_body(on="build-1")), 10.0)
    assert reply.type is MessageType.SUBMIT_OK and reply.body["on"] == "build-1"
    status = api.handle(store, staging, request("queue"), 11.0)
    assert any(row.get("on") == "build-1" for row in status.body["jobs"])
    claim(store, staging, "build-1", 12.0, slots=1, free=0)  # busy
    job_id = reply.body["job_id"]
    data, digest = snapshot()
    uploads.accept_upload(store, staging, job_id, digest, io.BytesIO(data), 12.0)
    body = api.handle(store, staging, request("status", job_id=job_id), 13.0).body
    assert body["waiting_for"] == "sent with --on build-1: it waits for that node alone"


def test_on_an_unknown_node_or_one_without_the_needs_is_refused(store, staging):
    seen(store, staging, **{"build-1": 1})
    reply = api.handle(store, staging, request("submit", **submit_body(on="build-9")), 10.0)
    assert reply.type is MessageType.ERROR and "no node is named build-9" in reply.body["message"]
    assert "build-1" in reply.body["message"]
    reply = api.handle(store, staging, request(
        "submit", **submit_body(on="build-1", needs=["docker"])), 10.0)
    assert reply.type is MessageType.ERROR and "docker" in reply.body["message"]
    with store.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_with_on_only_a_result_from_that_node_counts(store, staging):
    seen(store, staging, **{"build-1": 1, "build-2": 1})
    old_job(store, "build-1", "main")
    body = submit_body(reuse=True, branch="main")
    assert api.handle(store, staging, request("submit", **body), 10.0).body.get("already")
    body = submit_body(reuse=True, branch="main", on="build-2")
    reply = api.handle(store, staging, request("submit", **body), 10.0)
    assert reply.type is MessageType.SUBMIT_OK and not reply.body.get("already")
    with store.read() as conn:
        job = st.select_jobs(conn, "job_id = ?", (reply.body["job_id"],))[0]
    assert job["pinned_worker"] == "build-2"
