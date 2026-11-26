"""`mulebox check --from-stage`: kept failed jobs, and the rerun that takes one over (kept.py,
rerun.py)."""

import io

from mulebox.common.protocol import MessageType
from mulebox.coordinator import kept, sizes, uploads, usual
from mulebox.coordinator import store as st

from .helpers import snapshot, submit_body
from .test_attendance import T0, call, running

MAIN = {"branch": "main"}


def failed_and_kept(store, staging, left_s=900.0, memory=2 * 10**9, worker="wrk-a"):
    job = running(store, staging, **MAIN)
    call(store, staging, "result", T0 + 50, outcome="failed", exit_code=7, duration_s=1.0, **job)
    claim(store, staging, T0 + 51, worker,
          kept=[{"job_id": job["job_id"], "left_s": left_s, "memory": memory}])
    return job["job_id"]


def claim(store, staging, now, worker="wrk-a", **extra):
    return call(store, staging, "claim", now, worker=worker, capabilities=["node", "docker"],
                free_slots=1, **extra)


def rerun(store, staging, now=T0 + 60, **extra):
    return call(store, staging, "submit", now,
                **submit_body(**{**MAIN, "from_stage": "command", **extra}))


def test_a_rerun_goes_to_the_node_that_keeps_the_job(store, staging):
    first = failed_and_kept(store, staging)
    reply = rerun(store, staging)
    assert reply.type is MessageType.SUBMIT_OK, reply.body
    assert reply.body["rerun"] == {"from_stage": "command", "reuses": first, "node": "wrk-a",
                                   "kept_until": T0 + 51 + 900.0}
    assert reply.body["on"] == "wrk-a"
    with store.read() as conn:
        job = st.require_job(conn, reply.body["job_id"])
    assert (job["reuses"], job["from_stage"], job["pinned_worker"]) == (first, "command", "wrk-a")


def test_its_claim_names_the_kept_job(store, staging):
    first = failed_and_kept(store, staging)
    data = rerun(store, staging).body
    blob, digest = snapshot()
    uploads.accept_upload(store, staging, data["job_id"], digest, io.BytesIO(blob), T0 + 61)
    other = claim(store, staging, T0 + 62, worker="wrk-b")
    assert other.type is MessageType.CLAIM_NONE  # pinned to the node that keeps it
    reply = claim(store, staging, T0 + 63, kept=[])
    assert reply.type is MessageType.CLAIM_OK
    assert (reply.body["reuses"], reply.body["from_stage"]) == (first, "command")


def test_a_waiting_rerun_says_which_node_keeps_its_containers(store, staging):
    first = failed_and_kept(store, staging)
    later = rerun(store, staging).body["job_id"]
    blob, digest = snapshot()
    uploads.accept_upload(store, staging, later, digest, io.BytesIO(blob), T0 + 61)
    body = call(store, staging, "status", T0 + 62, job_id=later).body
    assert body["waiting_for"] == f"a rerun: it waits for wrk-a, which keeps the containers of {first}"


def test_nothing_kept_runs_from_the_start_and_says_why(store, staging):
    reply = rerun(store, staging)
    assert reply.body["rerun"]["note"].startswith("no failed job of this name and branch is kept")
    with store.read() as conn:
        job = st.require_job(conn, reply.body["job_id"])
    assert job["reuses"] is None and job["from_stage"] is None and job["pinned_worker"] is None


def test_an_expired_or_unlisted_kept_job_is_not_used(store, staging):
    failed_and_kept(store, staging, left_s=5.0)  # until T0 + 56
    assert "note" in rerun(store, staging, now=T0 + 60).body["rerun"]
    failed_and_kept(store, staging)
    claim(store, staging, T0 + 55, kept=[])  # the worker removed it
    assert "note" in rerun(store, staging).body["rerun"]


def test_another_branch_finds_nothing(store, staging):
    failed_and_kept(store, staging)
    assert "note" in rerun(store, staging, branch="other").body["rerun"]


def test_on_another_node_says_where_it_is_kept(store, staging):
    first = failed_and_kept(store, staging)
    claim(store, staging, T0 + 52, worker="wrk-b")
    note = rerun(store, staging, on="wrk-b").body["rerun"]["note"]
    assert note == f"{first} is kept on wrk-a, not on wrk-b, so this job runs from the start"


def test_a_job_kept_on_a_node_gone_offline_runs_from_the_start(store, staging):
    first = failed_and_kept(store, staging, left_s=3600.0)
    note = rerun(store, staging, now=T0 + 600).body["rerun"]["note"]
    assert note.startswith(f"{first} is kept on wrk-a, which is offline")


def test_a_stage_that_runs_before_the_containers_is_refused(store, staging):
    reply = rerun(store, staging, from_stage="images")
    assert reply.type is MessageType.ERROR and "from_stage" in reply.body["message"]


def test_status_says_how_long_a_failed_job_is_kept(store, staging):
    first = failed_and_kept(store, staging)
    body = call(store, staging, "status", T0 + 60, job_id=first).body
    assert (body["kept_on"], body["kept_until"]) == ("wrk-a", T0 + 51 + 900.0)
    later = rerun(store, staging).body["job_id"]
    body = call(store, staging, "status", T0 + 61, job_id=later).body
    assert (body["reuses"], body["from_stage"]) == (first, "command")


def test_kept_memory_counts_as_used_room(store, staging):
    failed_and_kept(store, staging, memory=3 * 10**9)
    with store.read() as conn:
        assert kept.memory(conn, "wrk-a") == 3 * 10**9
        assert sizes.with_kept(conn, "wrk-a", [], {"cores": 1.0}) == [
            {"cores": 0.0, "memory": 3e9}]
        assert sizes.with_kept(conn, "wrk-a", [], None) == []  # a job with no size: slots only


def test_a_runner_heartbeat_without_kept_leaves_the_list(store, staging):
    first = failed_and_kept(store, staging)
    job = running(store, staging)
    call(store, staging, "heartbeat", T0 + 70, lease="worker", **job)
    with store.read() as conn:
        assert kept.find(conn, first, T0 + 71) is not None


def test_a_rerun_is_not_given_back_to_a_plain_check(store, staging):
    job = running(store, staging, **MAIN)
    call(store, staging, "result", T0 + 50, outcome="passed", exit_code=0, duration_s=1.0, **job)
    with store.write() as conn:
        st.update_job(conn, job["job_id"], reuses="job-01ABCDEFGHJKMNPQRSTVWXYZ0")
    again = call(store, staging, "submit", T0 + 80, **submit_body(**MAIN, reuse=True))
    assert again.type is MessageType.SUBMIT_OK and "already" not in again.body


def test_a_rerun_does_not_count_towards_usual():
    assert "r.reuses IS NULL" in usual._JOB_RUNS and "j.reuses IS NULL" in usual._RECENT
