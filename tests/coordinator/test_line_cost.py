"""The line's cost: a long line is read, claimed and explained in a fixed number of queries
(coordinator/line.py, usual.lengths), and one request reads it once."""

from mulebox.common.protocol import JobState
from mulebox.coordinator import api, line, queue
from mulebox.coordinator import store as st

from .helpers import queued, request, submit_body
from .test_line import control, rules
from .test_usual import run


def _fill(store, count, start=0):
    """`count` waiting jobs straight into the store, of a few projects and jobs."""
    with store.write() as conn:
        for n in range(start, start + count):
            body = submit_body(project=f"example-{n % 4}", job=f"check-{n % 3}", needs=["gpu"])
            st.insert_job(conn, {**body, "job_id": f"job-{n:026d}", "state": JobState.QUEUED,
                                 "created_at": float(n), "queued_at": float(n), "timeout_min": 20})


def _counted(store, work):
    seen = []
    store._conn.set_trace_callback(seen.append)
    try:
        work()
    finally:
        store._conn.set_trace_callback(None)
    return len(seen)


def test_a_long_line_is_read_and_claimed_in_a_fixed_number_of_queries(store, staging):
    run(store, staging, [("command", 30)], project="example-1", job="check-1")
    rules(store, staging, shortest_first=True, fair_turns=True, aging_min=30)
    _fill(store, 50)
    pinned = queued(store, staging, now=60.0, project="example-1")
    control(store, staging, pinned, "up")
    api.handle(store, staging, request("upgrade", action="queue", worker="wrk-a",
                                       version="9.9.9", first=False), 61.0)
    queue.claim(store, "wrk-b", ["node"], 1, 10, now=99.0)  # the node is known from here on
    counts = []
    for more in (0, 400):
        _fill(store, more, start=1000)

        def read():
            with store.read() as conn:
                line.read(conn, 100.0)

        # No node offers gpu: the claim looks at every row in line and takes none.
        counts.append((_counted(store, read),
                       _counted(store, lambda: queue.claim(store, "wrk-b", ["node"], 1, 10,
                                                           now=100.0))))
    assert counts[0] == counts[1], counts


def test_one_request_reads_the_line_once(store, staging, monkeypatch):
    _fill(store, 20)
    api.handle(store, staging, request("upgrade", action="queue", worker="wrk-a",
                                       version="9.9.9"), 30.0)
    rules(store, staging, shortest_first=True)
    reads = []
    real = line.read
    monkeypatch.setattr(line, "read", lambda *a, **k: reads.append(1) or real(*a, **k))
    for kind, body in (("queue", {"limit": 0}), ("status", {"job_id": f"job-{3:026d}"})):
        reads.clear()
        assert api.handle(store, staging, request(kind, **body), 40.0).type != "error"
        assert len(reads) == 1, kind
