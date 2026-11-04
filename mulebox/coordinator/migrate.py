"""Schema upgrades for the coordinator store, run by `Store.open` in its write transaction.

A new database is created at the current version by store._SCHEMA. An older one is
brought forward one version at a time; each step only adds columns, so jobs written by an
older mulebox stay readable. A database from a newer mulebox is refused.

- 1 -> 2 (reservations for GitHub runners, docs/interfaces-m3.md): `jobs.kind` (default
  'job'), `jobs.pinned_worker`, `jobs.runner`, `jobs.run_url`, `workers.slots`.
- 2 -> 3: `jobs.env` (the project's `env:` values, JSON, default '{}').
- 3 -> 4: `workers.toolchains` (JSON, name to versions) and `workers.version`; NULL until a
  worker reports them.
- 4 -> 5: `jobs.detached` (default 0): the job does not depend on its client (leases.py).
- 5 -> 6: the `job_steps` table (steps.py). Only adds a table. The same statement is in
  store._SCHEMA, which runs first, so it says IF NOT EXISTS.
"""

import sqlite3

from mulebox.common.errors import MuleboxError

JOB_STEPS = """
CREATE TABLE IF NOT EXISTS job_steps (
    job_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    stage TEXT NOT NULL,
    started_at REAL NOT NULL,
    finished_at REAL,
    exit_code INTEGER,
    bytes_downloaded INTEGER,
    failing_line TEXT,
    PRIMARY KEY (job_id, seq)
)
"""
_STEPS: dict[int, tuple[str, ...]] = {
    1: (
        "ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'job'",
        "ALTER TABLE jobs ADD COLUMN pinned_worker TEXT",
        "ALTER TABLE jobs ADD COLUMN runner TEXT",
        "ALTER TABLE jobs ADD COLUMN run_url TEXT",
        "ALTER TABLE workers ADD COLUMN slots INTEGER",
    ),
    2: ("ALTER TABLE jobs ADD COLUMN env TEXT NOT NULL DEFAULT '{}'",),
    3: ("ALTER TABLE workers ADD COLUMN toolchains TEXT",
        "ALTER TABLE workers ADD COLUMN version TEXT"),
    4: ("ALTER TABLE jobs ADD COLUMN detached INTEGER NOT NULL DEFAULT 0",),
    5: (JOB_STEPS,),
}
# Indexes on columns that older schemas lack; created once the columns exist.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS jobs_kind ON jobs (kind, state, pinned_worker)",
    "CREATE INDEX IF NOT EXISTS jobs_project ON jobs (project, job, seq)",
)


class SchemaTooNew(MuleboxError):
    """The store was written by a newer mulebox."""


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return int(row[0])


def upgrade(conn: sqlite3.Connection, target: int) -> int:
    """Bring the schema to `target` inside the caller's transaction; return the old version."""
    found = current_version(conn)
    if found > target:
        raise SchemaTooNew(
            f"the mulebox store has schema version {found}, this mulebox knows up to "
            f"{target}; upgrade mulebox on this machine"
        )
    for version in range(found, target):
        for statement in _STEPS[version]:
            conn.execute(statement)
        conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'",
                     (str(version + 1),))
    for statement in _INDEXES:
        conn.execute(statement)
    return found
