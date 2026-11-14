"""Opening a store written by an older mulebox brings its schema forward."""

import sqlite3
import time

import pytest

from mulebox.common.protocol import JobState
from mulebox.coordinator import migrate, workers
from mulebox.coordinator import store as st
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
            '["pnpm", "check"]', 'f', 'a', 'alice@dev machine', 30, 'queued', 900.0, 900.0);
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
        assert store.schema_version() == st.SCHEMA_VERSION == 24
        with store.read() as conn:
            assert {"kind", "pinned_worker", "runner", "run_url", "detached", "pin_side",
                    "pin_job", "pin_order", "workflow"} <= columns(conn, "jobs")
            assert {"slots", "toolchains", "version", "draining", "load", "settings", "wanted",
                    "wanted_at"} <= columns(conn, "workers")
            indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master "
                                                  "WHERE type = 'index'")}
            assert {"jobs_kind", "jobs_finished"} <= indexes
            old_worker = workers.get(conn, "build-1")
            assert old_worker["slots"] is None and old_worker["toolchains"] is None
            assert old_worker["draining"] == 0
        old = store.get_job("job-01JC3X0000000000000000000")
        assert old["kind"] == "job" and old["state"] == JobState.QUEUED
        assert old["pinned_worker"] is None and old["argv"] == ["pnpm", "check"]
        assert old["detached"] is False
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


def shape(conn):
    """Every table's columns and every index, however the store got them."""
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                             "AND name NOT LIKE 'sqlite_%'")]
    indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' "
                                              "AND name NOT LIKE 'sqlite_%'")}
    return {table: columns(conn, table) for table in tables}, indexes


def store_at(path, version):
    """A database as a mulebox of that schema left it, with its job and worker."""
    conn = sqlite3.connect(path)
    conn.executescript(V1_SCHEMA)
    for step in range(1, version):
        for statement in migrate._STEPS[step]:
            conn.execute(statement)
    conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(version),))
    conn.commit()
    conn.close()


def test_one_sequence_with_no_gap():
    assert sorted(migrate._STEPS) == list(range(1, st.SCHEMA_VERSION))


@pytest.mark.parametrize("version", range(1, st.SCHEMA_VERSION + 1))
def test_every_old_schema_reaches_what_a_new_store_has(version, staging, tmp_path):
    with Store(tmp_path / "new.db").open() as store, store.read() as conn:
        fresh = shape(conn)
    store_at(staging.db_path, version)
    with Store(staging.db_path).open() as store:
        assert store.schema_version() == st.SCHEMA_VERSION
        with store.read() as conn:
            assert shape(conn) == fresh
        assert store.get_job("job-01JC3X0000000000000000000")["project"] == "example-app"


def test_the_schema_main_was_at_upgrades_with_its_jobs_and_workers(staging):
    """Schema 3 as mulebox 0.25.3 wrote it: before worker reports, detached jobs and steps."""
    store_at(staging.db_path, 3)
    conn = sqlite3.connect(staging.db_path)
    before = columns(conn, "jobs") | columns(conn, "workers")
    conn.close()
    assert not {"detached", "toolchains", "version"} & before
    with Store(staging.db_path).open() as store:
        with store.read() as conn:
            assert "detached" in columns(conn, "jobs")
            assert {"toolchains", "version"} <= columns(conn, "workers")
            assert {"stage", "started_at", "finished_at", "exit_code", "bytes_downloaded",
                    "failing_line"} <= columns(conn, "job_steps")
            assert "jobs_project" in shape(conn)[1]
            assert workers.get(conn, "build-1")["version"] is None
        assert store.get_job("job-01JC3X0000000000000000000")["detached"] is False


def test_a_store_without_steps_gets_the_table_and_keeps_its_jobs(staging):
    store_at(staging.db_path, 5)
    with Store(staging.db_path).open() as store:
        assert store.schema_version() == st.SCHEMA_VERSION
        assert store.get_job("job-01JC3X0000000000000000000")["project"] == "example-app"
        with store.read() as conn:
            assert {"stage", "started_at", "finished_at", "exit_code", "bytes_downloaded",
                    "failing_line"} <= columns(conn, "job_steps")


def test_an_open_detached_job_is_not_unattended_since_the_day_it_started(staging):
    store_at(staging.db_path, 7)
    conn = sqlite3.connect(staging.db_path)
    conn.execute("UPDATE jobs SET detached = 1, client_lease_until = 901.0")
    conn.execute("INSERT INTO jobs (job_id, idempotency_key, project, job, argv, fingerprint, "
                 "base_commit, client, timeout_min, state, outcome, created_at, detached, "
                 "client_lease_until) VALUES ('job-01JC3X0000000000000000001', 'sub-done', "
                 "'example-app', 'check', '[]', 'f', 'a', 'x', 30, 'finished', 'passed', 900.0, "
                 "1, NULL)")
    conn.commit()
    conn.close()
    with Store(staging.db_path).open() as store:
        job = store.get_job("job-01JC3X0000000000000000000")
        done = store.get_job("job-01JC3X0000000000000000001")
    assert job["client_lease_until"] > time.time()
    assert job["stop_reason"] is None and job["activity"] == {} and job["active_at"] is None
    assert done["client_lease_until"] is None
    assert job["check_in_ok"] == 0 and job["told_at"] is None


def test_recent_finished_jobs_need_no_sort(staging):
    """The dashboard reads them every second; a sort of every finished job cost 9.7 ms."""
    with Store(staging.db_path).open() as store, store.read() as conn:
        plan = " ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM jobs WHERE state = 'finished' "
            "ORDER BY finished_at DESC, seq DESC LIMIT 20"))
    assert "jobs_finished" in plan and "TEMP B-TREE" not in plan
