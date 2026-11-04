"""The coordinator's SQLite store: jobs, workers and the schema version.

One file, opened by every `mulebox rpc` process and by the coordinator service at once.
WAL mode lets readers run beside a writer; `busy_timeout` makes writers wait for each
other; every write runs in `BEGIN IMMEDIATE`, so read-check-update sequences (claim,
transition) are atomic across processes. A Store may be shared between threads (the watch
loop's heartbeat reader); a lock serialises use of its one connection.

Every state change goes through `transition`, which calls `protocol.check_transition`.
The store never reads the clock: callers pass `now` (epoch seconds).
"""

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mulebox.common.protocol import JobState, Outcome, ProtocolError, check_transition
from mulebox.coordinator import migrate
from mulebox.coordinator.errors import Conflict, NotFound

# 2: reservations for GitHub runners; 3: job env; 4: worker reports; 5: detached (migrate.py)
SCHEMA_VERSION = 5
BUSY_TIMEOUT_MS = 10_000
ACTIVE_STATES = (JobState.STARTING, JobState.RUNNING, JobState.CLEANING)

_JSON_COLUMNS = frozenset({"argv", "toolchain", "needs", "capabilities", "env"})
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    project TEXT NOT NULL,
    job TEXT NOT NULL,
    argv TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    base_commit TEXT NOT NULL,
    client TEXT NOT NULL,
    branch TEXT,
    setup TEXT,
    toolchain TEXT NOT NULL DEFAULT '{}',
    env TEXT NOT NULL DEFAULT '{}',
    needs TEXT NOT NULL DEFAULT '[]',
    timeout_min INTEGER NOT NULL,
    state TEXT NOT NULL,
    outcome TEXT,
    exit_code INTEGER,
    duration_s REAL,
    worker TEXT,
    attempt_id TEXT,
    upload_sha256 TEXT,
    client_lease_until REAL,
    worker_lease_until REAL,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    log_size INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    queued_at REAL,
    started_at REAL,
    finished_at REAL,
    kind TEXT NOT NULL DEFAULT 'job',
    pinned_worker TEXT,
    runner TEXT,
    run_url TEXT,
    detached INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS jobs_state ON jobs (state, queued_at, seq);
CREATE TABLE IF NOT EXISTS workers (
    worker TEXT PRIMARY KEY,
    capabilities TEXT NOT NULL,
    free_slots INTEGER NOT NULL,
    last_seen REAL NOT NULL,
    slots INTEGER,
    toolchains TEXT,
    version TEXT
);
"""
_JOB_COLUMNS = frozenset(
    "job_id idempotency_key project job argv fingerprint base_commit client branch setup "
    "toolchain needs timeout_min state outcome exit_code duration_s worker attempt_id "
    "upload_sha256 client_lease_until worker_lease_until cancel_requested log_size "
    "created_at queued_at started_at finished_at kind pinned_worker runner run_url env "
    "detached".split()
)


class Store:
    """Handle on the SQLite file at `path`. Call `open()` before use.

    `readonly=True` (the dashboard) opens an existing file with `mode=ro`: no schema
    setup, and every write fails in SQLite itself.
    """

    def __init__(self, path: Path, readonly: bool = False) -> None:
        self.path = Path(path)
        self.readonly = readonly
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    def open(self) -> "Store":
        target = f"{self.path.resolve().as_uri()}?mode=ro" if self.readonly else self.path
        conn = sqlite3.connect(
            target, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None,
            check_same_thread=False, uri=self.readonly,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        if self.readonly:
            self._conn = conn
            return self
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        self._conn = conn
        try:
            with self.write() as tx:
                for statement in _SCHEMA.split(";"):
                    if statement.strip():
                        tx.execute(statement)
                tx.execute(
                    "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                migrate.upgrade(tx, SCHEMA_VERSION)
        except BaseException:
            self.close()
            raise
        return self

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "Store":
        return self if self._conn is not None else self.open()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Store is not open; call open() first")
        return self._conn

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """A `BEGIN IMMEDIATE` transaction: committed on success, rolled back on error."""
        with self._lock:
            conn = self._connection()
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """A read transaction: one consistent snapshot of the database."""
        with self._lock:
            conn = self._connection()
            conn.execute("BEGIN")
            try:
                yield conn
            finally:
                conn.execute("COMMIT")

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.read() as conn:
            return fetch_job(conn, job_id)

    def schema_version(self) -> int:
        with self.read() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        return int(row["value"])


def _row_to_job(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    job = dict(row)
    for name in _JSON_COLUMNS & job.keys():
        job[name] = json.loads(job[name])
    job["cancel_requested"] = bool(job["cancel_requested"])
    job["detached"] = bool(job["detached"])
    return job


def _encode_columns(fields: dict[str, Any]) -> dict[str, Any]:
    unknown = fields.keys() - _JOB_COLUMNS
    if unknown:
        raise ValueError(f"unknown job column(s): {', '.join(sorted(unknown))}")
    encoded = {}
    for name, value in fields.items():
        if name in _JSON_COLUMNS:
            value = json.dumps(value, sort_keys=True)
        elif isinstance(value, (JobState, Outcome)):
            value = value.value
        elif isinstance(value, bool):
            value = int(value)
        encoded[name] = value
    return encoded


def fetch_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    return _row_to_job(conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone())


def require_job(conn: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    job = fetch_job(conn, job_id)
    if job is None:
        raise NotFound(f"no job {job_id}")
    return job


def find_by_key(conn: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (key,)).fetchone()
    return _row_to_job(row)


def select_jobs(conn: sqlite3.Connection, where: str = "1", params: tuple = (),
                order: str = "seq", limit: int | None = None) -> list[dict[str, Any]]:
    """Jobs matching a fixed SQL `where` clause (callers pass constants, values as params)."""
    sql = f"SELECT * FROM jobs WHERE {where} ORDER BY {order}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return [_row_to_job(row) for row in conn.execute(sql, params)]


def insert_job(conn: sqlite3.Connection, fields: dict[str, Any]) -> dict[str, Any]:
    encoded = _encode_columns(fields)
    names = ", ".join(encoded)
    marks = ", ".join("?" for _ in encoded)
    conn.execute(f"INSERT INTO jobs ({names}) VALUES ({marks})", tuple(encoded.values()))
    return require_job(conn, fields["job_id"])


def update_job(conn: sqlite3.Connection, job_id: str, **fields: Any) -> None:
    """Change non-state fields. State changes must use `transition`."""
    if "state" in fields:
        raise ValueError("use transition() to change a job's state")
    if not fields:
        return
    encoded = _encode_columns(fields)
    assignments = ", ".join(f"{name} = ?" for name in encoded)
    conn.execute(f"UPDATE jobs SET {assignments} WHERE job_id = ?", (*encoded.values(), job_id))


def transition(conn: sqlite3.Connection, job: dict[str, Any], new: JobState,
               **fields: Any) -> dict[str, Any]:
    """Move `job` to `new` (checked by protocol.check_transition) and set `fields`."""
    old = JobState(job["state"])
    try:
        check_transition(old, new)
    except ProtocolError as exc:
        raise Conflict(f"job {job['job_id']}: {exc}") from None
    encoded = _encode_columns({**fields, "state": new})
    assignments = ", ".join(f"{name} = ?" for name in encoded)
    cursor = conn.execute(
        f"UPDATE jobs SET {assignments} WHERE job_id = ? AND state = ?",
        (*encoded.values(), job["job_id"], old.value),
    )
    if cursor.rowcount != 1:
        raise Conflict(f"job {job['job_id']} changed state concurrently")
    return require_job(conn, job["job_id"])


def finish(conn: sqlite3.Connection, job: dict[str, Any], outcome: Outcome, now: float,
           **fields: Any) -> dict[str, Any]:
    """Move `job` to `finished` with `outcome`; clears both leases."""
    return transition(
        conn, job, JobState.FINISHED, outcome=outcome, finished_at=now,
        client_lease_until=None, worker_lease_until=None, **fields,
    )
