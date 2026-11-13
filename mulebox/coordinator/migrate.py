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
- 6 -> 7: `jobs.env_order` (JSON list, default '[]'): the order of `env:` in the file, which a
  JSON object sorted on the wire and in the store loses.
- 7 -> 8: `jobs.stop_reason`, `jobs.activity` (JSON, default '{}') and `jobs.active_at`
  (attendance.py). An open detached job gets a new client lease: nothing renewed it before, so
  it would count as unattended since the day it started and could stop at the first sweep.
- 8 -> 9: `jobs.check_in_ok` (default 0, the last check-in the agent answered, attendance.py) and
  `jobs.told_at` (reuse.py). Jobs that already finished count as told, or a first command after
  an upgrade would report the whole history.
- 9 -> 10: `workers.disk_free` (bytes on its fullest disk, common/disk.py), NULL until reported.
- 10 -> 11: `jobs.install`, the job's `install` line (worker/install_step.py).
- 11 -> 12: `jobs.worker_version`, the mulebox that ran the job (reuse.py); NULL on older jobs.
- 12 -> 13: `job_steps.network_lost`, a stage that printed a lost connection (usual.py).
- 13 -> 14: `jobs.client_os`, the dev machine's system, for the dashboard; NULL on older jobs and CI.
- 14 -> 15: `workers.draining` (default 0): a draining worker claims no new job (machine_api.py).
- 15 -> 16: `workers.load`, JSON of the machine's `cpu_pct`, `cores` and `mem_pct` as the worker
  last reported them (common/proc.py HostLoad); NULL until it does.
- 16 -> 17: `jobs.ci_result` (JSON, default '{}'): how a GitHub job went, read by the runner's
  completed hook (runners/diary.py). Empty on agent jobs and on reservations released before it,
  whose `passed` only meant the slot was given back.
- 17 -> 18: `jobs.take` (JSON list, default '[]'): files `mulebox run --take` brings back
  (coordinator/taken.py).
- 18 -> 19: the `clients` table: each dev machine's mulebox and skill state (clients.py).
- 19 -> 20: `jobs.paused`, `jobs.priority` and `jobs.boost` (default 0): the owner's controls on
  a job (job_control.py).
- 20 -> 21: `workers.settings` (JSON: the `slots` and `priority` a worker last reported, and why a
  change could not be written), `workers.wanted` (JSON, a change its owner asked for that the
  worker has yet to apply) and `workers.wanted_at` (node_settings.py); NULL until set.
- 21 -> 22: `jobs.pin_side`, `jobs.pin_job` and `jobs.pin_order`: a job moved by hand, at the
  front or just ahead of or behind another job's place (line.py), NULL for the others; and
  `jobs.workflow`, a GitHub run's workflow name from its runner's hook, for the order rules.
"""

import sqlite3

from mulebox.coordinator import clients

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
    6: ("ALTER TABLE jobs ADD COLUMN env_order TEXT NOT NULL DEFAULT '[]'",),
    7: ("ALTER TABLE jobs ADD COLUMN stop_reason TEXT",
        "ALTER TABLE jobs ADD COLUMN activity TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE jobs ADD COLUMN active_at REAL",
        "UPDATE jobs SET client_lease_until = CAST(strftime('%s', 'now') AS REAL) + 300 "
        "WHERE detached = 1 AND state != 'finished'"),
    8: ("ALTER TABLE jobs ADD COLUMN check_in_ok INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE jobs ADD COLUMN told_at REAL",
        "UPDATE jobs SET told_at = finished_at WHERE state = 'finished'"),
    9: ("ALTER TABLE workers ADD COLUMN disk_free INTEGER",),
    10: ("ALTER TABLE jobs ADD COLUMN install TEXT",),
    11: ("ALTER TABLE jobs ADD COLUMN worker_version TEXT",),
    12: ("ALTER TABLE job_steps ADD COLUMN network_lost INTEGER NOT NULL DEFAULT 0",),
    13: ("ALTER TABLE jobs ADD COLUMN client_os TEXT",),
    14: ("ALTER TABLE workers ADD COLUMN draining INTEGER NOT NULL DEFAULT 0",),
    15: ("ALTER TABLE workers ADD COLUMN load TEXT",),
    16: ("ALTER TABLE jobs ADD COLUMN ci_result TEXT NOT NULL DEFAULT '{}'",),
    17: ("ALTER TABLE jobs ADD COLUMN take TEXT NOT NULL DEFAULT '[]'",),
    18: (clients.TABLE,),
    19: ("ALTER TABLE jobs ADD COLUMN paused INTEGER NOT NULL DEFAULT 0",
         "ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
         "ALTER TABLE jobs ADD COLUMN boost INTEGER NOT NULL DEFAULT 0"),
    20: ("ALTER TABLE workers ADD COLUMN settings TEXT",
         "ALTER TABLE workers ADD COLUMN wanted TEXT",
         "ALTER TABLE workers ADD COLUMN wanted_at REAL"),
    21: ("ALTER TABLE jobs ADD COLUMN pin_side TEXT",
         "ALTER TABLE jobs ADD COLUMN pin_job TEXT",
         "ALTER TABLE jobs ADD COLUMN pin_order REAL",
         "ALTER TABLE jobs ADD COLUMN workflow TEXT"),
}
# Indexes on columns that older schemas lack; created once the columns exist.
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS jobs_kind ON jobs (kind, state, pinned_worker)",
    "CREATE INDEX IF NOT EXISTS jobs_project ON jobs (project, job, seq)",
    # The recent finished jobs, read every second by the dashboard: without it SQLite sorted
    # every finished job to keep 20 (9.7 ms on 1273 jobs, 1.5 ms with it).
    "CREATE INDEX IF NOT EXISTS jobs_finished ON jobs (state, finished_at, seq)",
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
            f"{target}; upgrade mulebox on this machine: `mulebox setup <host>` from a dev machine "
            "on the newer mulebox"
        )
    for version in range(found, target):
        for statement in _STEPS[version]:
            conn.execute(statement)
        conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'",
                     (str(version + 1),))
    for statement in _INDEXES:
        conn.execute(statement)
    return found
