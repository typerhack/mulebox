"""What jobs really used (`usage`): kept from heartbeats and results, summed per job."""

from mulebox.common.protocol import MessageType
from mulebox.coordinator import usage_report
from mulebox.coordinator import store as st

from .helpers import claimed, queued
from .test_api import T0, call

GB = 1_000_000_000


def finished(store, staging, usage=None, outcome="passed", at=1.0, **fields):
    job_id = queued(store, staging, now=at)
    with store.write() as conn:
        conn.execute("UPDATE jobs SET state = 'finished' WHERE job_id = ?", (job_id,))
        st.update_job(conn, job_id, outcome=outcome, started_at=at, finished_at=at + 60,
                      duration_s=60.0, worker=fields.pop("worker", "build-1"),
                      **({"usage": usage} if usage else {}), **fields)
    return job_id


def peaks(cores, memory):
    return {"peak_cores": cores, "peak_memory": memory, "cpu_s": 10.0, "samples": 6}


def test_heartbeats_and_the_result_keep_the_runs_peaks(store, staging):
    claim = claimed(store, staging)
    ids = {"job_id": claim["job_id"], "attempt_id": claim["attempt_id"]}
    call(store, staging, "job_update", state="running", **ids)
    call(store, staging, "heartbeat", lease="worker", activity={
        "idle_s": 0, "usage": {**peaks(2.0, GB), "peak_cores_stage": "setup"}}, **ids)
    job = store.get_job(claim["job_id"])
    assert job["usage"]["peak_cores_stage"] == "setup"
    assert "usage" not in job["activity"]  # kept apart: it outlives the run
    call(store, staging, "heartbeat", lease="worker", activity={"idle_s": 0}, **ids)
    assert store.get_job(claim["job_id"])["usage"]["peak_cores"] == 2.0  # an older worker's beat
    call(store, staging, "job_update", state="cleaning", **ids)
    call(store, staging, "result", outcome="passed", exit_code=0, duration_s=60.0,
         usage=peaks(3.0, 2 * GB), **ids)
    assert store.get_job(claim["job_id"])["usage"]["peak_memory"] == 2 * GB
    reply = call(store, staging, "status", job_id=claim["job_id"])
    assert reply.body["usage"]["peak_cores"] == 3.0


def test_summary_per_job_median_peak_and_a_size_that_fits(store, staging):
    for n, (cores, memory) in enumerate([(1.2, 900_000_000), (3.4, 2_100_000_000),
                                         (2.0, 1_000_000_000)]):
        finished(store, staging, peaks(cores, memory), at=10.0 + n)
    finished(store, staging, None, at=20.0)  # an older node's run
    finished(store, staging, peaks(9.0, 9 * GB), outcome="failed", at=30.0)
    finished(store, staging, peaks(1.0, GB), kind="runner", job="test", at=40.0)
    with store.read() as conn:
        jobs = usage_report.summary(conn, {})
        every = usage_report.summary(conn, {}, every=True)
        last_two = usage_report.summary(conn, {"kind": "job"}, runs=2)
    runner, check = jobs
    assert runner["kind"] == "runner" and runner["fits"] == {"cores": 1, "memory": GB}
    assert (check["runs"], check["measured"], check["not_measured"]) == (4, 3, 1)
    assert check["cores"] == {"median": 2.0, "max": 3.4}
    assert check["memory"] == {"median": 1_000_000_000, "max": 2_100_000_000}
    assert check["fits"] == {"cores": 4, "memory": 2_500_000_000}  # rounded up, 0.5 GB steps
    assert check["machines"] == ["build-1"]
    assert [j for j in every if j["kind"] == "job"][0]["cores"]["max"] == 9.0
    assert last_two[0]["runs"] == 2


def test_one_run_and_the_machines_sizes(store, staging):
    job_id = finished(store, staging, peaks(2.0, GB))
    with store.write() as conn:
        conn.execute("INSERT INTO workers (worker, capabilities, free_slots, last_seen, load) "
                     "VALUES ('build-1', '[]', 1, 1, ?)",
                     ('{"cores": 8, "memory": {"total": 16000000000}}',))
    reply = call(store, staging, "usage", job_id=job_id)
    assert reply.type is MessageType.USAGE_OK
    assert reply.body["machines"] == {"build-1": {"cores": 8, "memory": 16_000_000_000}}
    assert reply.body["run"]["average_cores"] == round(10.0 / 60.0, 2)
    listed = call(store, staging, "usage", project="example-app", runs=5)
    assert listed.body["runs"] == 5 and listed.body["jobs"][0]["measured"] == 1
    bad = call(store, staging, "usage", kind="other")
    assert bad.body["code"] == "bad_request"
    assert call(store, staging, "usage", job_id="job-01JC3X0000000000000000000Q").body["code"] == "not_found"
