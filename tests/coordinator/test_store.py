import sqlite3

import pytest

from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import Conflict, NotFound
from mulebox.coordinator.store import Store

from .helpers import submit


def test_open_creates_schema_with_wal(store):
    assert store.schema_version() == st.SCHEMA_VERSION
    with store.read() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 5000
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"jobs", "workers", "meta"} <= tables


def test_reopen_keeps_data(store, staging):
    job_id = submit(store, staging)
    store.close()
    with Store(staging.db_path).open() as again:
        assert again.get_job(job_id)["state"] == JobState.UPLOADING


def test_unopened_store_refuses(tmp_path):
    with pytest.raises(RuntimeError):
        Store(tmp_path / "x.db").get_job("job-x")


def test_transition_checks_state_machine(store, staging):
    job_id = submit(store, staging)
    with store.write() as conn:
        job = st.require_job(conn, job_id)
        with pytest.raises(Conflict):
            st.transition(conn, job, JobState.RUNNING)  # uploading -> running is not allowed
        job = st.transition(conn, job, JobState.QUEUED, queued_at=1.0)
        assert job["state"] == JobState.QUEUED


def test_transition_from_finished_refused(store, staging):
    job_id = submit(store, staging)
    with store.write() as conn:
        job = st.finish(conn, st.require_job(conn, job_id), Outcome.CANCELLED, 5.0)
        assert job["outcome"] == Outcome.CANCELLED and job["finished_at"] == 5.0
        with pytest.raises(Conflict):
            st.transition(conn, job, JobState.QUEUED)


def test_transition_detects_concurrent_change(store, staging):
    job_id = submit(store, staging)
    with store.write() as conn:
        stale = st.require_job(conn, job_id)
        st.transition(conn, stale, JobState.QUEUED, queued_at=1.0)
        with pytest.raises(Conflict):
            st.transition(conn, stale, JobState.FINISHED)


def test_update_job_refuses_state_and_unknown_columns(store, staging):
    job_id = submit(store, staging)
    with store.write() as conn:
        with pytest.raises(ValueError):
            st.update_job(conn, job_id, state="queued")
        with pytest.raises(ValueError):
            st.update_job(conn, job_id, **{"state = 'x'; --": 1})


def test_write_rolls_back_on_error(store, staging):
    job_id = submit(store, staging)
    with pytest.raises(RuntimeError):
        with store.write() as conn:
            st.update_job(conn, job_id, log_size=99)
            raise RuntimeError("boom")
    assert store.get_job(job_id)["log_size"] == 0


def test_idempotency_key_unique(store, staging):
    submit(store, staging, idempotency_key="sub-same")
    with store.write() as conn:
        job = st.find_by_key(conn, "sub-same")
        fields = {k: v for k, v in job.items() if k != "seq"}
        fields["job_id"] = "job-01JC3X0000000000000000000Z"
        with pytest.raises(sqlite3.IntegrityError):
            st.insert_job(conn, fields)


def test_require_job_not_found(store):
    with store.read() as conn:
        with pytest.raises(NotFound):
            st.require_job(conn, "job-01JC3X0000000000000000000Z")
