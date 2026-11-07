"""The FIFO queue: atomic claims, slot accounting, queue positions and the listing.

A claim runs in one `BEGIN IMMEDIATE` transaction, so two workers (threads or processes)
claiming at once can never get the same job, and the cluster-wide slot limit holds.

Agent jobs (`kind = 'job'`) and runner reservations (`kind = 'runner'`, reservations.py)
share one line: slots count `starting|running|cleaning` rows of both kinds, `claim` only
hands out agent jobs, and it never passes an older reservation pinned to the claiming
worker.
"""

import sqlite3
import time
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.protocol import JobState
from mulebox.coordinator import holds, workers
from mulebox.coordinator import store as st
from mulebox.coordinator.attendance import LIMITS_BY_COORDINATOR
from mulebox.coordinator.leases import WORKER_LEASE_S
from mulebox.coordinator.store import ACTIVE_STATES, Store

DEFAULT_FINISHED_LIMIT = 20

_ACTIVE_SQL = "state IN ({})".format(", ".join(f"'{s.value}'" for s in ACTIVE_STATES))
_QUEUE_ORDER = "queued_at, seq"
JOB_KIND = "job"
RUNNER_KIND = "runner"


def claim(store: Store, worker: str, capabilities: list[str] | tuple[str, ...],
          free_slots: int, cluster_slots: int = 1, *, now: float | None = None,
          toolchains: dict[str, list[str]] | None = None, version: str | None = None,
          disk_free: int | None = None) -> dict[str, Any] | None:
    """Give `worker` the oldest queued job whose needs it meets, or None.

    None when the worker has no free slot, when the cluster's slots (workers.cluster_limit, at
    least `cluster_slots`) are all held by jobs in
    `starting|running|cleaning`, or when no queued job fits. The claimed job moves to
    `starting` with a fresh attempt id and worker lease.
    """
    now = time.time() if now is None else now
    have = set(capabilities)
    with store.write() as conn:
        held = active_on(conn, worker, JOB_KIND)
        workers.upsert(conn, worker, list(capabilities), free_slots, now,
                       slots=free_slots + held, toolchains=toolchains, version=version,
                       disk_free=disk_free)
        free = free_slots - active_on(conn, worker, RUNNER_KIND)
        if (free < 1 or workers.is_draining(conn, worker)
                or active_count(conn) >= workers.cluster_limit(conn, now, cluster_slots)
                or holds.draining(conn, now)):
            return None
        blocker = oldest_reservation(conn, worker)
        on_hold = holds.held(conn, now)
        busy = {(job["project"], job["branch"]) for job in active_jobs(conn)
                if job["kind"] == JOB_KIND}  # a branch's worktree holds one job at a time
        for job in st.select_jobs(conn, "state = ? AND kind = ?",
                                  (JobState.QUEUED.value, JOB_KIND), _QUEUE_ORDER):
            if blocker is not None and _key(blocker) < _key(job):
                return None  # FIFO: the older reservation goes first
            if (set(job["needs"]) <= have and (job["project"], job["branch"]) not in busy
                    and job["project"] not in on_hold):
                return st.transition(
                    conn, job, JobState.STARTING, worker=worker, attempt_id=new_id("att"),
                    worker_lease_until=now + WORKER_LEASE_S, started_at=now,
                    worker_version=version,
                )
    return None


def active_count(conn: sqlite3.Connection) -> int:
    """Rows of both kinds holding a slot anywhere in the cluster."""
    return conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {_ACTIVE_SQL}").fetchone()[0]


def active_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every row holding a slot, of both kinds."""
    return st.select_jobs(conn, _ACTIVE_SQL)


def active_on(conn: sqlite3.Connection, worker: str, kind: str | None = None) -> int:
    """Rows holding a slot on `worker` (of `kind`, or of both kinds)."""
    sql = f"SELECT COUNT(*) FROM jobs WHERE {_ACTIVE_SQL} AND worker = ?"
    params: tuple = (worker,)
    if kind is not None:
        sql += " AND kind = ?"
        params += (kind,)
    return conn.execute(sql, params).fetchone()[0]


def oldest_reservation(conn: sqlite3.Connection, worker: str) -> dict[str, Any] | None:
    """The oldest queued reservation pinned to `worker`, or None."""
    rows = st.select_jobs(conn, "state = ? AND kind = ? AND pinned_worker = ?",
                          (JobState.QUEUED.value, RUNNER_KIND, worker), _QUEUE_ORDER, limit=1)
    return rows[0] if rows else None


def _key(job: dict[str, Any]) -> tuple[float, int]:
    return (job["queued_at"], job["seq"])


def position(conn: sqlite3.Connection, job: dict[str, Any]) -> int | None:
    """1-based place of a queued job in the line; None for any other state."""
    if job["state"] != JobState.QUEUED:
        return None
    ahead = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE state = ? AND (queued_at < ? OR "
        "(queued_at = ? AND seq < ?))",
        (JobState.QUEUED.value, job["queued_at"], job["queued_at"], job["seq"]),
    ).fetchone()[0]
    return ahead + 1


def listing(conn: sqlite3.Connection, finished_limit: int = DEFAULT_FINISHED_LIMIT
            ) -> list[tuple[dict[str, Any], int | None]]:
    """(job, position) pairs: active jobs, then queued in order, uploading, recent finished."""
    active = st.select_jobs(conn, _ACTIVE_SQL, (), "started_at, seq")
    queued = st.select_jobs(conn, "state = ?", (JobState.QUEUED.value,), _QUEUE_ORDER)
    uploading = st.select_jobs(conn, "state = ?", (JobState.UPLOADING.value,), "seq")
    finished = st.select_jobs(
        conn, "state = ?", (JobState.FINISHED.value,), "finished_at DESC, seq DESC",
        limit=finished_limit,
    )
    rows: list[tuple[dict[str, Any], int | None]] = [(job, None) for job in active]
    rows += [(job, index + 1) for index, job in enumerate(queued)]
    rows += [(job, None) for job in uploading + finished]
    return rows


def claim_body(job: dict[str, Any]) -> dict[str, Any]:
    """claim_ok body (docs/interfaces-m1.md, Wire usage)."""
    names = ("job_id", "attempt_id", "project", "job", "branch", "argv", "fingerprint",
             "base_commit",
             "timeout_min", "setup", "install", "toolchain", "needs", "env", "env_order")
    return {**{name: job[name] for name in names}, "limits": LIMITS_BY_COORDINATOR}
