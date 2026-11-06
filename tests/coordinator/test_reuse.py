"""`check` does not repeat itself, and results wait for an agent that went away."""

import pytest

from mulebox.common.protocol import MessageType
from mulebox.coordinator import queue
from mulebox.coordinator import store as st
from mulebox.coordinator import watch as stream
from mulebox.coordinator.reuse import REUSE_S
from mulebox.version import get_version

from .helpers import queued, submit_body
from .test_attendance import T0, call, running

LATER = T0 + 100.0


def finish(store, staging, job, outcome="passed", code=0, now=T0 + 50):
    call(store, staging, "result", now, outcome=outcome, exit_code=code, duration_s=1.0, **job)


def again(store, staging, now=LATER, **extra):
    return call(store, staging, "submit", now, **submit_body(**{"reuse": True, **extra}))


def test_the_same_files_get_the_earlier_result(store, staging):
    job = running(store, staging)
    finish(store, staging, job)
    reply = again(store, staging)
    assert reply.type is MessageType.SUBMIT_OK
    assert reply.body["job_id"] == job["job_id"] and reply.body["state"] == "finished"
    assert reply.body["already"]["outcome"] == "passed"


def ran_on(store, job, version):
    with store.write() as conn:
        st.update_job(conn, job["job_id"], worker_version=version)


def test_a_failure_counts_too_with_its_exit_code(store, staging):
    job = running(store, staging)
    ran_on(store, job, get_version())
    finish(store, staging, job, "failed", 2)
    assert again(store, staging).body["already"]["exit_code"] == 2


@pytest.mark.parametrize("version", ["0.0.1", None])
def test_a_failure_from_another_mulebox_runs_again(store, staging, version):
    job = running(store, staging)
    ran_on(store, job, version)
    finish(store, staging, job, "failed", 2)
    reply = again(store, staging)
    assert "already" not in reply.body and reply.body["job_id"] != job["job_id"]


def test_a_pass_from_another_mulebox_still_counts(store, staging):
    job = running(store, staging)
    ran_on(store, job, "0.0.1")
    finish(store, staging, job)
    assert again(store, staging).body["job_id"] == job["job_id"]


def test_a_claim_records_the_workers_version(store, staging):
    queued(store, staging, T0)
    queue.claim(store, "wrk-a", ["node", "docker"], 1, 10, now=T0, version="1.2.3")
    with store.read() as conn:
        assert st.select_jobs(conn)[0]["worker_version"] == "1.2.3"


def test_the_same_job_running_is_joined(store, staging):
    job = running(store, staging)
    reply = again(store, staging)
    assert reply.body["job_id"] == job["job_id"] and reply.body["state"] == "running"


def test_changed_files_run(store, staging):
    finish(store, staging, running(store, staging))
    assert "already" not in again(store, staging, fingerprint="other-files").body


def test_changed_settings_run(store, staging):
    finish(store, staging, running(store, staging))
    assert "already" not in again(store, staging, setup="pnpm install").body
    assert "already" not in again(store, staging, env={"CI": "2"}).body


def test_another_job_runs(store, staging):
    finish(store, staging, running(store, staging))
    assert "already" not in again(store, staging, job="lint").body


def test_again_runs(store, staging):
    finish(store, staging, running(store, staging))
    body = call(store, staging, "submit", LATER, **submit_body()).body
    assert "already" not in body and body["state"] == "uploading"


def test_an_old_result_runs(store, staging):
    finish(store, staging, running(store, staging))
    assert "already" not in again(store, staging, now=T0 + 50 + REUSE_S + 1).body


def test_a_job_that_did_not_really_run_does_not_count(store, staging):
    job = running(store, staging)
    call(store, staging, "cancel", T0 + 10, job_id=job["job_id"])
    finish(store, staging, job, "cancelled", None)
    assert "already" not in again(store, staging).body


def test_a_job_that_never_started_does_not_count(store, staging):
    finish(store, staging, running(store, staging), "failed", None)
    assert "already" not in again(store, staging).body


def test_a_result_nobody_received_is_told_once(store, staging):
    job = running(store, staging)
    finish(store, staging, job)
    first = call(store, staging, "queue", LATER, limit=0, news_for="example-app").body
    assert [j["job_id"] for j in first["finished_away"]] == [job["job_id"]]
    second = call(store, staging, "queue", LATER, limit=0, news_for="example-app").body
    assert second["finished_away"] == []


def test_another_project_hears_nothing(store, staging):
    finish(store, staging, running(store, staging))
    body = call(store, staging, "queue", LATER, limit=0, news_for="other-app").body
    assert body["finished_away"] == []


def test_a_plain_queue_marks_nothing_told(store, staging):
    finish(store, staging, running(store, staging))
    call(store, staging, "queue", LATER)
    assert call(store, staging, "queue", LATER, limit=0,
                news_for="example-app").body["finished_away"]


def test_a_result_taken_by_reuse_is_not_told_again(store, staging):
    finish(store, staging, running(store, staging))
    assert again(store, staging).body["finished_away"] == []


def told_at(store, job):
    return store.get_job(job["job_id"])["told_at"]


def test_a_client_there_is_told_before_it_gets_the_result(store, staging):
    job = running(store, staging)
    seen = []
    stream._send_result(store, {"job_id": job["job_id"]}, True,
                        lambda: seen.append(told_at(store, job)), LATER)
    assert seen == [LATER]


def test_a_client_that_went_away_is_told_later(store, staging):
    job = running(store, staging)
    stream._send_result(store, {"job_id": job["job_id"]}, False, lambda: None, LATER)
    assert told_at(store, job) is None


def test_a_result_that_could_not_be_sent_is_told_later(store, staging):
    job = running(store, staging)

    def lost():
        raise BrokenPipeError

    with pytest.raises(BrokenPipeError):
        stream._send_result(store, {"job_id": job["job_id"]}, True, lost, LATER)
    assert told_at(store, job) is None
