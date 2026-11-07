"""Slot reservations for GitHub Actions runners (docs/interfaces-m3.md, Reservations).

A reservation is a job row with `kind = 'runner'`, pinned to one worker, with no snapshot.
It is created `queued`, granted (`queued -> starting -> running` in one transaction) when
it is the oldest queued row its worker could run and both a cluster slot and a worker slot
are free, and ended by `release`. Every function here runs inside the caller's write
transaction; the time comes in as `now`.
"""

import re
import sqlite3
from typing import Any

from mulebox.common.config_reader import NAME_RE
from mulebox.common.ids import new_id
from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import holds, queue, workers
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.leases import WORKER_LEASE_S
from mulebox.coordinator.queue import JOB_KIND, RUNNER_KIND

GITHUB_CLIENT = "github"
RELEASE_OUTCOMES = frozenset(
    {Outcome.PASSED, Outcome.FAILED, Outcome.CANCELLED, Outcome.INTERRUPTED}
)
_REPOSITORY_RE = re.compile(rf"({NAME_RE.pattern})/({NAME_RE.pattern})")


def project_name(repository: str) -> str:
    """`owner/repo` -> `owner__repo`, so it passes the project name rule."""
    if not isinstance(repository, str) or not _REPOSITORY_RE.fullmatch(repository):
        raise BadRequest(f"field 'repository' must look like owner/repo, got {repository!r}")
    return repository.replace("/", "__")


def default_key(repository: str, run_id: str, run_attempt: str, job: str, runner: str) -> str:
    """One key per GitHub job attempt on one runner, so a retried hook finds its row."""
    return f"gh-{repository}-{run_id}-{run_attempt}-{job}-{runner}"


def create(conn: sqlite3.Connection, fields: dict[str, Any], now: float) -> dict[str, Any]:
    """Insert a queued reservation, or return the one with the same idempotency key.

    `fields`: pinned_worker, project, job, runner, idempotency_key, + branch, run_url.
    """
    found = st.find_by_key(conn, fields["idempotency_key"])
    if found is not None:
        if found["kind"] != RUNNER_KIND:
            raise BadRequest("idempotency_key belongs to an agent job, not a reservation")
        return found
    return st.insert_job(conn, {
        **fields, "job_id": new_id("job"), "kind": RUNNER_KIND, "client": GITHUB_CLIENT,
        "argv": [], "fingerprint": "", "base_commit": "", "timeout_min": 0,
        "state": JobState.QUEUED, "created_at": now, "queued_at": now,
    })


def require(conn: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    job = st.require_job(conn, job_id)
    if job["kind"] != RUNNER_KIND:
        raise BadRequest(f"job {job_id} is not a runner reservation")
    return job


def ahead(conn: sqlite3.Connection, job: dict[str, Any]) -> int:
    """Queued rows older than `job` that its worker could run (agent jobs whose needs the
    worker meets, and reservations pinned to it)."""
    worker = job["pinned_worker"]
    known = workers.get(conn, worker)
    have = set(known["capabilities"]) if known else set()
    older = st.select_jobs(
        conn, "state = ? AND (queued_at < ? OR (queued_at = ? AND seq < ?))",
        (JobState.QUEUED.value, job["queued_at"], job["queued_at"], job["seq"]),
    )
    return sum(
        1 for row in older
        if (row["kind"] == JOB_KIND and set(row["needs"]) <= have)
        or (row["kind"] == RUNNER_KIND and row["pinned_worker"] == worker)
    )


def worker_slots(conn: sqlite3.Connection, worker: str, cluster_slots: int) -> int:
    """The worker's total slots as last reported by its claims; `cluster_slots` until the
    worker has claimed once (one node: both are the node's `slots`)."""
    known = workers.get(conn, worker)
    if known is None or known["slots"] is None:
        return cluster_slots
    return known["slots"]


def try_grant(conn: sqlite3.Connection, job: dict[str, Any], now: float,
              cluster_slots: int) -> dict[str, Any]:
    """Grant a queued reservation if it is first in line and slots are free.

    Returns the job, `running` when granted, unchanged otherwise.
    """
    if job["state"] != JobState.QUEUED or ahead(conn, job) > 0 or holds.draining(conn, now):
        return job
    worker = job["pinned_worker"]
    if queue.active_count(conn) >= workers.cluster_limit(conn, now, cluster_slots):
        return job
    if queue.active_on(conn, worker) >= worker_slots(conn, worker, cluster_slots):
        return job
    job = st.transition(conn, job, JobState.STARTING, worker=worker, started_at=now,
                        worker_lease_until=now + WORKER_LEASE_S)
    return st.transition(conn, job, JobState.RUNNING)


def release(conn: sqlite3.Connection, job: dict[str, Any], outcome: Outcome,
            now: float) -> dict[str, Any]:
    """End a reservation with `outcome`; a finished one is returned unchanged."""
    if outcome not in RELEASE_OUTCOMES:
        allowed = ", ".join(sorted(o.value for o in RELEASE_OUTCOMES))
        raise BadRequest(f"field 'outcome' must be one of {allowed}")
    if job["state"] == JobState.FINISHED:
        return job
    started = job["started_at"]
    duration = round(max(0.0, now - started), 3) if started is not None else None
    return st.finish(conn, job, outcome, now, duration_s=duration)


LATE_LOG_S = 60.0  # a released slot still takes its runner log's last lines this long


def takes_late_log(job: dict[str, Any], now: float) -> bool:
    """True for a reservation released less than LATE_LOG_S ago: the runner's last step is
    read after its completed hook released the slot (runners/live_log.py)."""
    finished = job.get("finished_at")
    return (job.get("kind") == RUNNER_KIND and job["state"] == JobState.FINISHED
            and isinstance(finished, (int, float)) and now - finished < LATE_LOG_S)


def unfinished(conn: sqlite3.Connection, worker: str) -> list[dict[str, Any]]:
    """Reservations pinned to `worker` that are not finished, oldest first."""
    return st.select_jobs(conn, "kind = ? AND pinned_worker = ? AND state != ?",
                          (RUNNER_KIND, worker, JobState.FINISHED.value), "queued_at, seq")


def check_name(value: Any, field: str) -> str:
    """A worker or runner name: it becomes part of folder names, so it is strict."""
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise BadRequest(f"field '{field}' must be a simple name, got {value!r}")
    return value
