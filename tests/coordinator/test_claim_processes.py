"""Claims from several processes at once: no job twice, the cluster limit holds."""

import multiprocessing

import pytest

from mulebox.coordinator import queue
from mulebox.coordinator.store import Store

from .helpers import queued

PROCESSES = 6


def _claim_loop(path, index, cluster_slots, barrier, results):
    store = Store(path).open()
    try:
        barrier.wait()
        while (job := queue.claim(store, f"wrk-{index}", [], 1, cluster_slots, now=99.0)):
            results.put(job["job_id"])
            if cluster_slots < 100:
                break
    finally:
        store.close()
    results.put(None)


def _run(path, cluster_slots):
    ctx = multiprocessing.get_context("spawn")
    barrier, results = ctx.Barrier(PROCESSES), ctx.Queue()
    procs = [ctx.Process(target=_claim_loop, args=(path, i, cluster_slots, barrier, results))
             for i in range(PROCESSES)]
    for proc in procs:
        proc.start()
    claimed, done = [], 0
    while done < PROCESSES:
        item = results.get(timeout=60)
        if item is None:
            done += 1
        else:
            claimed.append(item)
    for proc in procs:
        proc.join(timeout=60)
        assert proc.exitcode == 0
    return claimed


# six one-slot workers: the cluster holds their six slots even when the coordinator's own is 3
@pytest.mark.parametrize("cluster_slots, expected", [(100, 24), (3, PROCESSES)])
def test_processes_claim_atomically(store, staging, cluster_slots, expected):
    for t in range(24):
        queued(store, staging, now=float(t))
    claimed = _run(str(store.path), cluster_slots)
    assert len(claimed) == expected
    assert len(set(claimed)) == expected
    with store.read() as conn:
        assert queue.active_count(conn) == expected
