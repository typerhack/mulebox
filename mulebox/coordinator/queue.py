"""The queue: atomic claims, slot accounting, queue positions and the listing.

In the order of the line (line.py): the owner's moves, then the order rules, then arrival.
A paused job is skipped and keeps its place; a machine running a boosted job takes no new one
until it ends. A job sent `--on <node>` goes to that node only. A job another free node should
take (ranked above, holding its branch, or with more room) is left to it for a while
(node_choice.py).

A claim runs in one `BEGIN IMMEDIATE` transaction, so two workers (threads or processes)
claiming at once can never get the same job, and the cluster-wide slot limit holds.

Agent jobs (`kind = 'job'`) and runner reservations (`kind = 'runner'`, reservations.py)
share one line: slots count `starting|running|cleaning` rows of both kinds, `claim` only
hands out agent jobs, and it never passes a reservation pinned to the claiming worker
that is ahead of it in line. Paused rows wait without holding back the rows behind them.
"""

import sqlite3
import time
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.protocol import JobState
from mulebox.coordinator import holds, line, node_choice, project_pause, upgrades, workers
from mulebox.coordinator import store as st
from mulebox.coordinator.attendance import LIMITS_BY_COORDINATOR
from mulebox.coordinator.leases import WORKER_LEASE_S
from mulebox.coordinator.store import ACTIVE_STATES, Store

DEFAULT_FINISHED_LIMIT = 20

_ACTIVE_SQL = "state IN ({})".format(", ".join(f"'{s.value}'" for s in ACTIVE_STATES))
QUEUE_ORDER = line.ARRIVAL_ORDER  # with no order rule on (line.py)
JOB_KIND = "job"
RUNNER_KIND = "runner"


def claim(store: Store, worker: str, capabilities: list[str] | tuple[str, ...],
          free_slots: int, cluster_slots: int = 1, *, now: float | None = None,
          toolchains: dict[str, list[str]] | None = None, version: str | None = None,
          disk_free: int | None = None,
          load: dict[str, Any] | None = None,
          priority: str | None = None) -> dict[str, Any] | None:
    """Give `worker` the first queued job in line (line.py) whose needs it meets, or None.

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
                       disk_free=disk_free, load=load)
        free = free_slots - active_on(conn, worker, RUNNER_KIND)
        if (free < 1 or workers.is_draining(conn, worker)
                or active_count(conn) >= workers.cluster_limit(conn, now, cluster_slots)
                or holds.draining(conn, now) or boosted_on(conn, worker)):
            return None
        order = line.read(conn, now)
        blocker = oldest_reservation(conn, worker, order)
        on_hold = holds.held(conn, now) | set(project_pause.paused(conn, now))
        upgrading = upgrades.pending(conn, worker)
        busy = {(job["project"], job["branch"]) for job in active_jobs(conn)
                if job["kind"] == JOB_KIND}  # a branch's worktree holds one job at a time
        choice = node_choice.read(conn, worker, now, priority, free)  # who else is free
        for job in (row for row in order.rows if row["kind"] == JOB_KIND):
            if blocker is not None and order.before(blocker, job):
                return None  # the reservation ahead in line goes first
            if upgrades.blocks(conn, worker, job, order, upgrading):
                return None  # an upgrade of this machine is ahead in line (upgrades.py)
            if (set(job["needs"]) <= have and (job["project"], job["branch"]) not in busy
                    and job["project"] not in on_hold and not job["paused"]
                    and job["pinned_worker"] in (None, worker)  # `--on`
                    and node_choice.leave_to(conn, choice, job, now) is None):
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


def boosted_on(conn: sqlite3.Connection, worker: str) -> bool:
    """Whether `worker` runs a job its owner gave the whole machine (job_control.py)."""
    return conn.execute(f"SELECT 1 FROM jobs WHERE {_ACTIVE_SQL} AND worker = ? AND boost = 1",
                        (worker,)).fetchone() is not None


def oldest_reservation(conn: sqlite3.Connection, worker: str,
                       order: line.Line | None = None) -> dict[str, Any] | None:
    """The queued reservation pinned to `worker` that is first in line, or None."""
    order = order or line.read(conn)
    return next((row for row in order.rows
                 if row["kind"] == RUNNER_KIND and row["pinned_worker"] == worker), None)


def position(conn: sqlite3.Connection, job: dict[str, Any], now: float | None = None) -> int | None:
    """1-based place of a queued job in the line; None for any other state."""
    if job["state"] != JobState.QUEUED:
        return None
    return line.read(conn, now).position(job)


def listing(conn: sqlite3.Connection, finished_limit: int = DEFAULT_FINISHED_LIMIT,
            order: line.Line | None = None) -> list[tuple[dict[str, Any], int | None]]:
    """(job, position) pairs: active jobs, then queued in order, uploading, recent finished."""
    active = st.select_jobs(conn, _ACTIVE_SQL, (), "started_at, seq")
    queued = (order or line.read(conn)).rows
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
             "timeout_min", "setup", "install", "toolchain", "needs", "env", "env_order", "take")
    return {**{name: job[name] for name in names}, "limits": LIMITS_BY_COORDINATOR}
