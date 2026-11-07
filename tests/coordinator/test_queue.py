import threading

from mulebox.common.protocol import JobState
from mulebox.coordinator import queue, views, workers
from mulebox.coordinator import store as st
from mulebox.coordinator.store import Store

from .helpers import claimed, queued, submit


def test_claim_oldest_first(store, staging):
    first = queued(store, staging, now=10.0)
    queued(store, staging, now=20.0)
    job = queue.claim(store, "wrk-a", ["node"], 1, cluster_slots=5, now=30.0)
    assert job["job_id"] == first
    assert job["state"] == JobState.STARTING
    assert job["worker"] == "wrk-a" and job["attempt_id"].startswith("att-")
    assert job["worker_lease_until"] == 30.0 + queue.WORKER_LEASE_S


def test_claim_respects_needs(store, staging):
    docker_job = queued(store, staging, now=10.0, needs=["docker"])
    plain = queued(store, staging, now=20.0, needs=["node"])
    assert queue.claim(store, "wrk-a", ["node"], 1, 5, now=30.0)["job_id"] == plain
    assert queue.claim(store, "wrk-a", ["node"], 1, 5, now=30.0) is None
    assert queue.claim(store, "wrk-b", ["node", "docker"], 1, 5, now=30.0)["job_id"] == docker_job


def test_claim_respects_cluster_slots_and_free_slots(store, staging):
    queued(store, staging)
    queued(store, staging)
    assert queue.claim(store, "wrk-a", [], 0, 5, now=1.0) is None
    assert queue.claim(store, "wrk-a", [], 1, 1, now=1.0) is not None
    assert queue.claim(store, "wrk-a", [], 0, 1, now=1.0) is None  # its one slot is taken


def test_cluster_limit_counts_every_online_worker(store, staging):
    for _ in range(3):
        queued(store, staging)
    assert queue.claim(store, "wrk-a", [], 1, 1, now=1.0) is not None
    assert queue.claim(store, "wrk-b", [], 1, 1, now=1.0) is not None  # a second machine adds its slot
    with store.read() as conn:
        assert workers.cluster_limit(conn, 1.0, 1) == 2
        assert workers.cluster_limit(conn, 1.0 + workers.OFFLINE_AFTER_S + 1, 1) == 1
        assert workers.cluster_limit(conn, 1.0, 5) == 5


def test_claim_skips_uploading(store, staging):
    submit(store, staging)
    assert queue.claim(store, "wrk-a", [], 1, 5, now=1.0) is None


def test_claim_records_worker(store, staging):
    queue.claim(store, "wrk-a", ["node"], 2, now=1.0)
    with store.read() as conn:
        row = conn.execute("SELECT * FROM workers WHERE worker = 'wrk-a'").fetchone()
    assert row["free_slots"] == 2 and row["last_seen"] == 1.0


def test_positions_and_listing(store, staging):
    ids = [queued(store, staging, now=float(t)) for t in (10, 20, 30)]
    queue.claim(store, "wrk-a", [], 1, now=40.0)
    with store.read() as conn:
        assert queue.position(conn, st.require_job(conn, ids[0])) is None
        assert queue.position(conn, st.require_job(conn, ids[1])) == 1
        assert queue.position(conn, st.require_job(conn, ids[2])) == 2
        rows = queue.listing(conn)
    assert [(job["job_id"], pos) for job, pos in rows] == [(ids[0], None), (ids[1], 1), (ids[2], 2)]


def test_threads_never_claim_twice(store, staging):
    for t in range(30):
        queued(store, staging, now=float(t))
    claimed, errors = [], []
    barrier = threading.Barrier(8)

    def worker(index):
        own = Store(store.path).open()
        try:
            barrier.wait()
            while (job := queue.claim(own, f"wrk-{index}", [], 1, 100, now=99.0)) is not None:
                claimed.append(job["job_id"])
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            own.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(claimed) == 30 and len(set(claimed)) == 30


def test_a_branch_runs_one_job_at_a_time(store, staging):
    first = queued(store, staging, branch="main")
    waits = queued(store, staging, branch="main")
    other = queued(store, staging, branch="feature")
    elsewhere = queued(store, staging, branch="main", project="other-app")
    got = [queue.claim(store, "wrk-a", ["node"], 4, 4)["job_id"] for _ in range(3)]
    assert got == [first, other, elsewhere]
    assert queue.claim(store, "wrk-a", ["node"], 1, 4) is None
    assert store.get_job(waits)["state"] == "queued"


def test_a_queued_job_names_the_job_on_its_branch(store, staging):
    first = claimed(store, staging, branch="main")["job_id"]
    other = queued(store, staging, branch="feature/a")
    behind = queued(store, staging, branch="main")
    waiting, free = store.get_job(behind), store.get_job(other)
    with store.read() as conn:
        assert views.running_ahead(conn, waiting)["branch_busy"] == first
        assert "branch_busy" not in views.running_ahead(conn, free)
