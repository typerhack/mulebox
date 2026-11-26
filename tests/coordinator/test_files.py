"""Files a job keeps for `mulebox fetch` on the coordinator (files.py, retention.py, rpc.py)."""

import hashlib
import io

import pytest

from mulebox.common.protocol import MessageType
from mulebox.coordinator import files, retention, rpc
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import Conflict, NotFound
from mulebox.coordinator.worker_keys import GateRefused, gate_command

from .test_attendance import T0, call, running

KEEP = {"keep": ["test-results/", "coverage/lcov.info"]}
PACK = b"a tar.gz, as far as the coordinator cares"
SHA = hashlib.sha256(PACK).hexdigest()


def finish(store, staging, job, now=T0 + 50, **body):
    return call(store, staging, "result", now, outcome="failed", exit_code=1, duration_s=1.0,
                **job, **body)


def test_the_entries_go_with_the_job_to_its_claim(store, staging):
    job = running(store, staging, **KEEP)
    with store.read() as conn:
        assert st.require_job(conn, job["job_id"])["keep_files"] == KEEP["keep"]
    status = call(store, staging, "status", T0 + 1, job_id=job["job_id"]).body
    assert status["keep"] == KEEP["keep"] and "files" not in status


def test_a_bad_entry_is_refused_at_submit(store, staging):
    from .helpers import submit_body
    reply = call(store, staging, "submit", T0, **submit_body(keep=["../outside"]))
    assert reply.type is MessageType.ERROR and "inside the project" in reply.body["message"]


def test_a_pack_is_taken_while_the_job_runs_and_handed_out_once_it_ended(store, staging):
    job = running(store, staging, **KEEP)
    assert files.receive(store, staging, job["job_id"], SHA, io.BytesIO(PACK))["bytes"] == len(PACK)
    said = {"count": 3, "bytes": 120, "left_out": ["big.zip: past keep_files_max (200.0 MB)"],
            "left_out_count": 1, "packed": True}
    status = finish(store, staging, job, files=said).body
    assert status["files"] == said
    out = io.BytesIO()
    assert files.send(store, staging, job["job_id"], out) == len(PACK) and out.getvalue() == PACK


def test_a_pack_is_refused_for_a_job_that_keeps_nothing_or_ended(store, staging):
    plain = running(store, staging)
    with pytest.raises(Conflict, match="keeps no files"):
        files.receive(store, staging, plain["job_id"], SHA, io.BytesIO(PACK))
    job = running(store, staging, T0 + 1, **KEEP)
    finish(store, staging, job)
    with pytest.raises(Conflict, match="before its result"):
        files.receive(store, staging, job["job_id"], SHA, io.BytesIO(PACK))


def test_a_pack_that_does_not_match_its_sha_is_not_kept(store, staging):
    job = running(store, staging, **KEEP)
    with pytest.raises(Exception, match="sha256 mismatch"):
        files.receive(store, staging, job["job_id"], SHA, io.BytesIO(PACK + b"x"))
    assert files.job_ids(staging) == []


def test_fetching_a_job_with_nothing_kept_names_the_code(store, staging):
    job = running(store, staging, **KEEP)
    finish(store, staging, job)
    with pytest.raises(NotFound) as caught:
        files.send(store, staging, job["job_id"], io.BytesIO())
    assert caught.value.error_code == "job.no_files"


def test_packs_go_after_files_days_and_logs_stay(store, staging):
    job = running(store, staging, **KEEP)
    files.receive(store, staging, job["job_id"], SHA, io.BytesIO(PACK))
    finish(store, staging, job, files={"count": 1, "bytes": 5, "packed": True})
    day = 86400.0
    retention.sweep(store, staging, T0 + 6 * day, 30, 365, files_days=7)
    assert files.job_ids(staging) == [job["job_id"]]
    retention.sweep(store, staging, T0 + 8 * day, 30, 365, files_days=7)
    assert files.job_ids(staging) == []


def test_the_download_writes_the_pack_or_an_error_on_stderr(store, staging):
    job = running(store, staging, **KEEP)
    files.receive(store, staging, job["job_id"], SHA, io.BytesIO(PACK))
    finish(store, staging, job, files={"count": 1, "bytes": 5, "packed": True})
    out, err = io.BytesIO(), io.StringIO()
    assert rpc.run_download(store, staging, job["job_id"], out, err, kept=True) == 0
    assert out.getvalue() == PACK
    other = running(store, staging, T0 + 2)
    assert rpc.run_download(store, staging, other["job_id"], io.BytesIO(), err, kept=True) == 4
    assert "no kept files" in err.getvalue() or "still" in err.getvalue()


def test_a_worker_key_may_send_a_pack_and_nothing_like_it():
    job = "job-01HZZZZZZZZZZZZZZZZZZZZZZZ"
    assert gate_command(f"mulebox rpc-upload-files {job} {SHA}") == ("rpc-upload-files",
                                                                     f"{job} {SHA}")
    for bad in (f"mulebox rpc-upload-files {job} notasha", f"mulebox rpc-upload-files ../x {SHA}",
                f"mulebox rpc-download-files {job}", f"mulebox rpc-upload {job} {SHA}"):
        with pytest.raises(GateRefused):
            gate_command(bad)
