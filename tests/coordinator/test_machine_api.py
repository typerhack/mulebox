"""`machine` requests: a drained worker claims nothing, a removed one is forgotten."""

import pytest

from mulebox.coordinator import api, queue, workers
from mulebox.coordinator.errors import Conflict, NotFound

from .helpers import queued, request


def act(store, staging, name, action, now=1.0):
    reply = api.handle(store, staging, request("machine", worker=name, action=action), now)
    if reply.type == "error":
        raise {"conflict": Conflict, "not_found": NotFound}.get(reply.body["code"], RuntimeError)(
            reply.body["message"])
    return reply.body


def test_drained_worker_claims_nothing_until_resumed(store, staging):
    queued(store, staging)
    queue.claim(store, "wrk-a", [], 0, 5, now=1.0)  # registers, no slot free
    assert act(store, staging, "wrk-a", "drain")["running"] == []
    assert queue.claim(store, "wrk-a", [], 2, 5, now=2.0) is None
    assert queue.claim(store, "wrk-b", [], 2, 5, now=2.0) is not None  # others still claim
    queued(store, staging)
    act(store, staging, "wrk-a", "resume")
    assert queue.claim(store, "wrk-a", [], 2, 5, now=3.0) is not None


def test_drain_lists_what_still_runs(store, staging):
    queued(store, staging)
    job = queue.claim(store, "wrk-a", [], 1, 5, now=1.0)
    assert act(store, staging, "wrk-a", "drain")["running"] == [job["job_id"]]


def test_remove_is_refused_while_online_or_busy(store, staging):
    queued(store, staging)
    queue.claim(store, "wrk-a", [], 1, 5, now=1.0)
    with pytest.raises(Conflict, match="online"):
        act(store, staging, "wrk-a", "remove", now=2.0)
    with pytest.raises(Conflict, match="still has 1 job"):
        act(store, staging, "wrk-a", "remove", now=1.0 + workers.OFFLINE_AFTER_S + 1)


def test_remove_forgets_a_stopped_worker(store, staging):
    queue.claim(store, "wrk-a", [], 1, 5, now=1.0)
    act(store, staging, "wrk-a", "remove", now=100.0)
    with store.read() as conn:
        assert workers.get(conn, "wrk-a") is None
    with pytest.raises(NotFound):
        act(store, staging, "wrk-a", "drain", now=100.0)


def test_unknown_action_is_refused(store, staging):
    queue.claim(store, "wrk-a", [], 1, 5, now=1.0)
    with pytest.raises(RuntimeError, match="action"):
        act(store, staging, "wrk-a", "explode")
