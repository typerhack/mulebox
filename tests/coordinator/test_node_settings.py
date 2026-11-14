"""A node's settings from afar, and node priority in claims (coordinator/node_settings.py)."""

import pytest

from mulebox.common.protocol import MessageType
from mulebox.coordinator import api, node_choice, node_settings, queue, workers

from .helpers import queued, request

GB = 1 << 30


def claim(store, staging, worker, now, *, slots=2, priority="normal", free=None, caps=("node",),
          error=None, load=None):
    settings = {"slots": slots, "priority": priority, **({"error": error} if error else {})}
    body = {"worker": worker, "capabilities": list(caps),
            "free_slots": slots if free is None else free, "settings": settings,
            **({"load": load} if load else {})}
    return api.handle(store, staging, request("claim", **body), now, cluster_slots=1)


def ask(store, staging, worker="build-1", now=10.0, **body):
    reply = api.handle(store, staging, request("node_settings", worker=worker, **body), now)
    return reply.type, reply.body


def test_a_change_waits_goes_back_in_a_claim_and_clears_once_reported(store, staging):
    claim(store, staging, "build-1", 1.0, load={"cores": 16, "memory": {
        "total": 32 * GB, "available": 16 * GB, "used": 16 * GB}})
    kind, view = ask(store, staging)
    assert kind is MessageType.NODE_SETTINGS_OK
    assert view["current"] == {"slots": 2, "priority": "normal"} and view["pending"] is None
    assert view["suggested"]["slots"] == 4 and "16 cores" in view["suggested"]["reason"]
    assert view["choices"] == {"slots": {"min": 1, "max": 64},
                               "priority": ["preferred", "normal", "fallback"]}
    _, view = ask(store, staging, slots=3, now=11.0)
    assert view["pending"] == {"slots": 3} and view["pending_since"] == 11.0
    reply = claim(store, staging, "build-1", 12.0)  # not applied yet: it is sent again
    assert reply.body["node_settings"] == {"slots": 3} and reply.body["node_settings_at"] == 11.0
    reply = claim(store, staging, "build-1", 13.0, slots=3)
    assert "node_settings" not in reply.body
    _, view = ask(store, staging, now=14.0)
    assert view["current"]["slots"] == 3 and view["pending"] is None
    with store.read() as conn:
        assert workers.get(conn, "build-1")["slots"] == 3


def test_a_heartbeat_carries_the_change_too(store, staging):
    queued(store, staging)
    job = claim(store, staging, "build-1", 1.0).body
    ask(store, staging, priority="preferred")
    beat = {"job_id": job["job_id"], "lease": "worker", "attempt_id": job["attempt_id"],
            "settings": {"slots": 2, "priority": "normal"}}
    reply = api.handle(store, staging, request("heartbeat", **beat), 2.0)
    assert reply.body["node_settings"] == {"priority": "preferred"}
    beat["settings"]["priority"] = "preferred"
    reply = api.handle(store, staging, request("heartbeat", **beat), 3.0)
    assert "node_settings" not in reply.body


def test_asking_for_what_it_has_or_cancelling_leaves_nothing_waiting(store, staging):
    claim(store, staging, "build-1", 1.0)
    assert ask(store, staging, slots=2)[1]["pending"] is None
    assert ask(store, staging, slots=5, priority="fallback")[1]["pending"] == {
        "slots": 5, "priority": "fallback"}
    assert ask(store, staging, slots=4)[1]["pending"] == {"slots": 4, "priority": "fallback"}
    assert ask(store, staging, cancel=True)[1]["pending"] is None


def test_a_change_that_could_not_be_written_says_why_until_asked_again(store, staging):
    claim(store, staging, "build-1", 1.0)
    ask(store, staging, slots=3)
    claim(store, staging, "build-1", 2.0, error="node.toml is a symlink")
    assert ask(store, staging)[1]["error"] == "node.toml is a symlink"
    assert ask(store, staging, slots=4)[1]["error"] is None


@pytest.mark.parametrize("body, words", [
    ({"slots": 0}, "from 1 to 64"), ({"slots": 65}, "from 1 to 64"), ({"slots": "3"}, "whole"),
    ({"slots": True}, "whole"), ({"priority": "first"}, "one of")])
def test_bad_values_are_refused(store, staging, body, words):
    claim(store, staging, "build-1", 1.0)
    kind, reply = ask(store, staging, **body)
    assert kind is MessageType.ERROR and reply["code"] == "bad_request" and words in reply["message"]


def test_an_unknown_machine_or_one_that_never_reported_is_refused(store, staging):
    assert ask(store, staging, worker="nobody")[1]["code"] == "not_found"
    queue.claim(store, "old-1", [], 1, 1, now=1.0)  # an older worker: no settings
    _, view = ask(store, staging, worker="old-1")
    assert view["applies"] is False and view["current"] is None
    kind, reply = ask(store, staging, worker="old-1", slots=3)
    assert reply["code"] == "conflict" and "upgrade it first" in reply["message"]


def test_a_bad_report_never_fails_a_claim(store, staging):
    body = {"worker": "build-1", "capabilities": [], "free_slots": 1,
            "settings": {"slots": 999, "priority": "x"}}
    reply = api.handle(store, staging, request("claim", **body), 1.0)
    assert reply.type is MessageType.CLAIM_NONE
    assert ask(store, staging)[1]["current"] is None


# -- priority ---------------------------------------------------------------------------

def test_a_fallback_node_leaves_a_job_to_a_free_preferred_one(store, staging):
    claim(store, staging, "spare-1", 1.0, priority="preferred", free=0)  # registers
    claim(store, staging, "mac-1", 1.0, priority="fallback", free=0)
    claim(store, staging, "spare-1", 1.0, priority="preferred", free=0)  # now with its settings
    queued(store, staging, now=1.0)
    assert claim(store, staging, "mac-1", 2.0, priority="fallback").type is MessageType.CLAIM_NONE
    assert claim(store, staging, "spare-1", 2.0, priority="preferred").type is MessageType.CLAIM_OK


def test_a_fallback_node_takes_it_when_the_better_one_is_full_or_gone(store, staging):
    claim(store, staging, "spare-1", 1.0, slots=1, priority="preferred", free=0)
    claim(store, staging, "spare-1", 1.0, slots=1, priority="preferred", free=0)
    claim(store, staging, "mac-1", 1.0, priority="fallback", free=0)
    queued(store, staging, now=1.0)
    assert claim(store, staging, "spare-1", 2.0, slots=1, priority="preferred").type \
        is MessageType.CLAIM_OK  # its one slot is now taken
    queued(store, staging, now=2.0)
    assert claim(store, staging, "mac-1", 3.0, priority="fallback").type is MessageType.CLAIM_OK
    queued(store, staging, now=3.0)  # the preferred one goes offline
    late = 3.0 + workers.OFFLINE_AFTER_S + 1
    claim(store, staging, "mac-1", late - 1, priority="fallback", free=0)
    assert claim(store, staging, "mac-1", late, priority="fallback").type is MessageType.CLAIM_OK


def test_a_job_only_the_lower_node_can_run_is_not_held(store, staging):
    claim(store, staging, "spare-1", 1.0, priority="preferred", free=0)
    claim(store, staging, "spare-1", 1.0, priority="preferred", free=0)
    claim(store, staging, "mac-1", 1.0, priority="fallback", caps=("node", "xcode"), free=0)
    queued(store, staging, now=1.0, needs=["xcode"])
    reply = claim(store, staging, "mac-1", 2.0, priority="fallback", caps=("node", "xcode"))
    assert reply.type is MessageType.CLAIM_OK


def test_a_job_held_too_long_goes_to_whoever_claims(store, staging):
    claim(store, staging, "spare-1", 1.0, priority="preferred", free=0)
    claim(store, staging, "spare-1", 1.0, priority="preferred", free=0)
    claim(store, staging, "mac-1", 1.0, priority="fallback", free=0)
    queued(store, staging, now=1.0)
    with store.read() as conn:
        queued_at = conn.execute("SELECT queued_at FROM jobs").fetchone()[0]
    claim(store, staging, "spare-1", queued_at + 25, priority="preferred", free=0)  # online, idle
    assert claim(store, staging, "mac-1", queued_at + 26, priority="fallback").type \
        is MessageType.CLAIM_NONE
    held = queued_at + 26  # the first time it was left: the wait counts from here
    claim(store, staging, "spare-1", held + node_choice.GRACE_S - 2, priority="preferred", free=0)
    assert claim(store, staging, "mac-1", held + node_choice.GRACE_S - 1,
                 priority="fallback").type is MessageType.CLAIM_NONE
    claim(store, staging, "spare-1", held + node_choice.GRACE_S, priority="preferred", free=0)
    reply = claim(store, staging, "mac-1", held + node_choice.GRACE_S + 1, priority="fallback")
    assert reply.type is MessageType.CLAIM_OK


def test_a_hand_edit_past_what_can_be_asked_is_still_reported(store, staging):
    claim(store, staging, "big-1", 1.0, slots=100)
    assert ask(store, staging, worker="big-1")[1]["current"]["slots"] == 100


def test_machine_list_shows_priority_and_what_waits(store, staging):
    claim(store, staging, "build-1", 1.0, priority="preferred")
    ask(store, staging, slots=4, now=2.0)
    row = api.handle(store, staging, request("machines"), 3.0).body["workers"][0]
    assert row["priority"] == "preferred" and row["pending"] == {"slots": 4}
