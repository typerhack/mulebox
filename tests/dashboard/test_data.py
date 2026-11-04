import sqlite3

import pytest

from mulebox.coordinator import store as st
from mulebox.coordinator.store import Store

from .conftest import NOW


def test_store_opened_read_only_refuses_writes(run_job, readonly_store):
    job_id, _ = run_job()
    with readonly_store.read() as conn:
        assert st.fetch_job(conn, job_id)["state"] == "running"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with readonly_store.write() as conn:
            st.update_job(conn, job_id, branch="other")


def test_read_only_store_does_not_create_a_database(tmp_path):
    with pytest.raises(sqlite3.OperationalError):
        Store(tmp_path / "missing.db", readonly=True).open().read().__enter__()


def test_queue_snapshot_uses_the_status_model(data, run_job, finish_job):
    _, state = run_job()
    finish_job(state, "failed", 2)
    running, _ = run_job(now=NOW + 10)
    snap = data.queue_snapshot(NOW + 20)
    assert [row["job_id"] for row in snap["running"]] == [running]
    assert snap["running"][0]["elapsed_s"] == 10.0
    assert snap["recent"][0]["shown_state"] == "failed"


def test_detail_redacts_the_command_and_never_returns_env(data, run_job):
    secret = "ghp_" + "a" * 36
    job_id, _ = run_job(argv=["deploy", f"--token={secret}"], env={"API_KEY": "hunter2"})
    detail = data.job(job_id)
    assert secret not in detail["command"]
    text = repr(detail)
    assert "env" not in detail and "hunter2" not in text and "attempt_id" not in text
    assert "lease" not in text


@pytest.mark.parametrize("job_id", ["nope", "../../etc/passwd", "job-" + "0" * 26])
def test_unknown_or_malformed_ids_are_not_found(data, job_id):
    assert data.job(job_id) is None
    assert data.log_chunk(job_id, 0) is None


def test_history_pages_and_filters(data, run_job, finish_job):
    for n in range(3):
        _, state = run_job(now=NOW + n, project="example-app" if n else "other-app")
        finish_job(state, now=NOW + 100 + n)
    first = data.history(limit=2)
    assert [j["finished_at"] for j in first["jobs"]] == [NOW + 102, NOW + 101]
    second = data.history(limit=2, before=first["next_before"])
    assert [j["project"] for j in second["jobs"]] == ["other-app"]
    assert second["next_before"] is None
    assert len(data.history(project="other-app")["jobs"]) == 1


def test_history_limit_is_bounded(data):
    assert data.history(limit=-5)["jobs"] == []
