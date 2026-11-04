"""Opening a store written by an older mulebox brings its schema forward."""

import sqlite3

import pytest

from mulebox.common.protocol import JobState
from mulebox.coordinator import store as st
from mulebox.coordinator import workers
from mulebox.coordinator.migrate import SchemaTooNew
from mulebox.coordinator.store import Store

from .helpers import submit

# The schema of mulebox 0.5.x (schema version 1), as it was written to disk.
V1_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE jobs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE, project TEXT NOT NULL, job TEXT NOT NULL,
    argv TEXT NOT NULL, fingerprint TEXT NOT NULL, base_commit TEXT NOT NULL,
    client TEXT NOT NULL, branch TEXT, setup TEXT, toolchain TEXT NOT NULL DEFAULT '{}',
    needs TEXT NOT NULL DEFAULT '[]', timeout_min INTEGER NOT NULL, state TEXT NOT NULL,
    outcome TEXT, exit_code INTEGER, duration_s REAL, worker TEXT, attempt_id TEXT,
    upload_sha256 TEXT, client_lease_until REAL, worker_lease_until REAL,
    cancel_requested INTEGER NOT NULL DEFAULT 0, log_size INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, queued_at REAL, started_at REAL, finished_at REAL
);
CREATE INDEX jobs_state ON jobs (state, queued_at, seq);
CREATE TABLE workers (
    worker TEXT PRIMARY KEY, capabilities TEXT NOT NULL, free_slots INTEGER NOT NULL,
    last_seen REAL NOT NULL
);
INSERT INTO meta VALUES ('schema_version', '1');
INSERT INTO jobs (job_id, idempotency_key, project, job, argv, fingerprint, base_commit,
    client, timeout_min, state, created_at, queued_at)
    VALUES ('job-01JC3X0000000000000000000', 'sub-old', 'example-app', 'check',
            '["pnpm", "check"]', 'f', 'a', 'alice@laptop', 30, 'queued', 900.0, 900.0);
INSERT INTO workers VALUES ('build-1', '["node"]', 1, 900.0);
"""


def columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


@pytest.fixture
def old_db(staging):
    conn = sqlite3.connect(staging.db_path)
    conn.executescript(V1_SCHEMA)
    conn.close()
    return staging.db_path


def test_version_one_store_is_migrated(old_db, staging):
    with Store(old_db).open() as store:
        assert store.schema_version() == st.SCHEMA_VERSION == 4
        with store.read() as conn:
            assert {"kind", "pinned_worker", "runner", "run_url"} <= columns(conn, "jobs")
            assert "slots" in columns(conn, "workers")
            indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master "
                                                  "WHERE type = 'index'")}
            assert "jobs_kind" in indexes
            assert workers.get(conn, "build-1")["slots"] is None
        old = store.get_job("job-01JC3X0000000000000000000")
        assert old["kind"] == "job" and old["state"] == JobState.QUEUED
        assert old["pinned_worker"] is None and old["argv"] == ["pnpm", "check"]
        new_id = submit(store, staging)
        assert store.get_job(new_id)["kind"] == "job"


def test_migration_runs_once(old_db):
    Store(old_db).open().close()
    with Store(old_db).open() as store:  # a second open must not add the columns again
        assert store.schema_version() == st.SCHEMA_VERSION


def test_new_store_needs_no_migration(store):
    with store.read() as conn:
        assert "kind" in columns(conn, "jobs") and "slots" in columns(conn, "workers")
    assert store.schema_version() == st.SCHEMA_VERSION


def test_newer_store_is_refused(staging):
    conn = sqlite3.connect(staging.db_path)
    conn.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
                       "INSERT INTO meta VALUES ('schema_version', '99');")
    conn.close()
    with pytest.raises(SchemaTooNew, match="upgrade mulebox"):
        Store(staging.db_path).open()


def test_version_three_store_gets_the_steps_table_and_keeps_its_jobs(old_db, staging):
    with Store(old_db).open() as store:
        job = store.get_job("job-01JC3X0000000000000000000")
        with store.write() as conn:
            conn.execute("DROP TABLE job_steps")
            conn.execute("UPDATE meta SET value = '3' WHERE key = 'schema_version'")
    with Store(old_db).open() as store:
        assert store.schema_version() == 4
        assert store.get_job(job["job_id"])["project"] == "example-app"
        with store.read() as conn:
            assert {"stage", "started_at", "finished_at", "exit_code", "bytes_downloaded",
                    "failing_line"} <= columns(conn, "job_steps")
