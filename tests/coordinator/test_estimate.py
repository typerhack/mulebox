"""The estimate for a queued job, from past runs of the same project, job and command."""

import io

from mulebox.coordinator import api, usual
from mulebox.coordinator.watch import watch

from .helpers import queued, request, submit


def past_run(store, staging, duration, outcome="passed", **extra):
    job_id = queued(store, staging, **extra)
    claim = api.handle(store, staging, request(
        "claim", worker="wrk-a", capabilities=[], free_slots=1), 1000.0, cluster_slots=10).body
    assert claim["job_id"] == job_id
    ids = {"job_id": job_id, "attempt_id": claim["attempt_id"]}
    row = {"seq": 0, "stage": "command", "started_at": 100.0, "finished_at": 100.0 + duration}
    api.handle(store, staging, request("steps", steps=[row], **ids), 1000.0)
    api.handle(store, staging, request("result", outcome=outcome, exit_code=0,
                                       duration_s=duration, **ids), 1000.0)


def estimate_of(store, job_id):
    job = store.get_job(job_id)
    with store.read() as conn:
        return usual.estimate(job, usual.for_job(conn, job))


def test_median_of_past_passed_runs(store, staging):
    for duration in (100.0, 300.0, 120.0):
        past_run(store, staging, duration)
    assert estimate_of(store, queued(store, staging)) == {"estimate_s": 120.0, "estimate_runs": 3}


def test_too_few_runs_give_no_estimate(store, staging):
    for _ in range(usual.MIN_RUNS - 1):
        past_run(store, staging, 100.0)
    assert estimate_of(store, queued(store, staging)) == {}


def test_failed_runs_do_not_count(store, staging):
    for _ in range(3):
        past_run(store, staging, 5.0, outcome="failed")
    assert estimate_of(store, queued(store, staging)) == {}


def test_only_the_last_runs_count(store, staging):
    for _ in range(3):
        past_run(store, staging, 900.0)
    for _ in range(usual.RUNS):
        past_run(store, staging, 60.0)
    assert estimate_of(store, queued(store, staging))["estimate_s"] == 60.0


def test_another_job_or_command_or_project_does_not_count(store, staging):
    for _ in range(3):
        past_run(store, staging, 100.0)
    assert estimate_of(store, queued(store, staging, job="test")) == {}
    assert estimate_of(store, queued(store, staging, project="other")) == {}
    assert estimate_of(store, queued(store, staging, argv=["pnpm", "other"])) == {}


def test_the_usual_of_a_job_is_kept_apart_by_command_as_well(store, staging):
    for _ in range(3):
        past_run(store, staging, 100.0)
    job_id = queued(store, staging, argv=["pnpm", "other"])
    assert api.handle(store, staging, request("status", job_id=job_id), 1000.0).body["usual"] is None


def test_a_job_that_is_not_queued_has_no_estimate(store, staging):
    for _ in range(3):
        past_run(store, staging, 100.0)
    assert estimate_of(store, submit(store, staging)) == {}  # still uploading


def test_a_status_reply_carries_it(store, staging):
    for _ in range(3):
        past_run(store, staging, 100.0)
    job_id = queued(store, staging)
    body = api.handle(store, staging, request("status", job_id=job_id), 1000.0).body
    assert body["estimate_s"] == 100.0 and body["estimate_runs"] == 3


def test_the_watch_stream_carries_it(store, staging):
    for _ in range(3):
        past_run(store, staging, 100.0)
    job_id = queued(store, staging)

    class Stop(Exception):
        pass

    def stop(_):
        raise Stop

    out = io.BytesIO()
    try:
        watch(store, staging, request("watch", job_id=job_id, offset=0), io.BytesIO(), out,
              sleep=stop)
    except Stop:
        pass
    assert b'"estimate_s":100.0' in out.getvalue()

