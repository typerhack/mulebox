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


def _history(store, count, start=0):
    """`count` passed runs of example-app's check, run n taking n seconds."""
    with store.write() as conn:
        for n in range(start, start + count):
            job_id = f"job-run{n:023d}"
            st.insert_job(conn, {**submit_body(), "job_id": job_id, "state": JobState.FINISHED,
                                 "outcome": "passed", "created_at": float(n),
                                 "queued_at": float(n), "timeout_min": 20})
            conn.execute("INSERT INTO job_steps (job_id, seq, stage, started_at, finished_at) "
                         "VALUES (?, 0, 'command', 0, ?)", (job_id, float(n)))


def _steps(store, work):
    """SQLite's virtual machine steps `work` takes: the rows it looks at."""
    seen = [0]

    def tick():
        seen[0] += 1
        return 0

    store._conn.set_progress_handler(tick, 1)
    try:
        work()
    finally:
        store._conn.set_progress_handler(None, 1)
    return seen[0]


def test_a_jobs_usual_length_reads_only_its_last_runs_however_long_its_history(store, staging):
    from mulebox.coordinator import usual

    steps = []
    for start, count in ((0, 100), (100, 900)):
        _history(store, count, start)
        job_id = queued(store, staging, now=5000.0)
        with store.read() as conn:
            job = st.require_job(conn, job_id)
            assert usual.lengths(conn, [job])[job_id] == float(start + count - 11)  # last 20

            def read(conn=conn, job=job):
                usual.lengths(conn, [job])

            steps.append(_steps(store, read))
    assert steps[1] < steps[0] * 2, steps  # ten times the history, about the same work
