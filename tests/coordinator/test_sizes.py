"""Job sizes in the queue (coordinator/sizes.py, queue.py): fit, kept room, refusal, reason."""

from mulebox.coordinator import queue
from mulebox.coordinator.views import waiting_for

from .helpers import queued
from .test_api import call

GB = 10**9
LOAD = {"cores": 8, "memory": {"total": 16 * GB}}


def take(store, worker="build-1", free=2, now=1000.0, load=LOAD):
    return queue.claim(store, worker, ["linux"], free, 10, now=now, load=load)


def test_no_size_anywhere_is_slots_as_before(store, staging):
    for _ in range(3):
        queued(store, staging)
    assert take(store, free=2) and take(store, free=1)
    assert take(store, free=0) is None


def test_a_big_job_waits_for_room_and_keeps_it(store, staging):
    first = queued(store, staging, size={"cores": 6})
    big = queued(store, staging, size={"cores": 6, "memory": "4GB"})
    small = queued(store, staging, size={"cores": 1})
    assert take(store)["job_id"] == first
    assert take(store, free=1) is None  # 2 cores left: the big job keeps them, the small waits
    job = store.get_job(big)
    with store.read() as conn:
        assert "waiting for room: it needs 6 cores and 4.0 GB; build-1 has 2 cores" in (
            waiting_for(conn, job, 1000.0) or "")
    assert store.get_job(small)["state"] == "queued"
    job = store.get_job(small)
    with store.read() as conn:  # it would fit, but the room is kept for the big job
        assert waiting_for(conn, job, 1000.0) == (
            f"waiting for room: build-1 keeps its room for {big} ahead of it, which needs "
            "6 cores and 4.0 GB")


def test_a_job_too_big_for_this_node_is_passed_over(store, staging):
    queued(store, staging, size={"cores": 6})
    big = queued(store, staging, size={"cores": 12})  # fits the other node only
    small = queued(store, staging, size={"cores": 2})
    take(store, worker="build-2", load={"cores": 16, "memory": {"total": 32 * GB}}, free=0)
    assert take(store)  # the 6-core job
    assert take(store, free=1)["job_id"] == small  # 12 cores never fit here
    assert take(store, worker="build-2", load={"cores": 16, "memory": {"total": 32 * GB}},
                free=1)["job_id"] == big


def test_a_node_whose_size_is_not_known_counts_slots_only(store, staging):
    queued(store, staging, size={"cores": 64})
    assert take(store, load=None)


def test_the_owners_room_is_kept(store, staging):
    queued(store, staging, size={"cores": 8})
    take(store, free=0)  # the node reports itself, with nothing free
    with store.write() as conn:
        conn.execute("UPDATE workers SET settings = ? WHERE worker = 'build-1'", ('{"keep_cores": 2}',))
    assert queue.claim(store, "build-1", ["linux"], 2, 10, now=1000.0, load=LOAD) is None


def test_a_job_no_node_can_ever_hold_is_refused_at_submit(store, staging):
    take(store, free=2)  # build-1 reports 8 cores, 16 GB and 2 slots, with nothing to take
    reply = call(store, staging, "submit", project="example-app", job="check", argv=["x"],
                 idempotency_key="k-big", fingerprint="f" * 64, base_commit="a" * 40,
                 client="alice", size={"cores": 12})
    assert reply.body["code"] == "no_worker" and "asks for 12 cores" in reply.body["message"]
    bad = call(store, staging, "submit", project="example-app", job="check", argv=["x"],
               idempotency_key="k-bad", fingerprint="f" * 64, base_commit="a" * 40,
               client="alice", size={"cores": "many"})
    assert bad.body["code"] == "bad_request"


def test_a_sized_github_run_waits_for_room(store, staging):
    from mulebox.coordinator import reservations as rs

    queued(store, staging, size={"cores": 6})
    take(store)  # 6 of 8 cores held
    with store.write() as conn:
        run = rs.create(conn, {"pinned_worker": "build-1", "project": "example-app", "job": "ci",
                               "runner": "build-1-app", "idempotency_key": "gh-1",
                               "size": {"cores": 4}}, 1000.0)
        assert rs.try_grant(conn, run, 1000.0, 10)["state"] == "queued"
        small = rs.create(conn, {"pinned_worker": "build-1", "project": "example-app",
                                 "job": "lint", "runner": "build-1-app2",
                                 "idempotency_key": "gh-2", "size": {"cores": 2}}, 1000.0)
    with store.write() as conn:
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (run["job_id"],))
        assert rs.try_grant(conn, small, 1000.0, 10)["state"] == "running"
