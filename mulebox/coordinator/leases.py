"""Client and worker leases, and the sweep that acts on expired ones.

Clock: the coordinator's `time.time()`, passed in as `now` so tests control it.

- Client lease (300 s, renewed by `heartbeat lease=client` and the watch stream): when it
  runs out the job gets a cancel request; a `queued` job finishes `cancelled` at once,
  an active job is stopped by its worker (heartbeat replies `cancel: true`).
- A detached job (`check --detach`) has no client to lose, so the sweep never cancels it for
  that. Its lease says whether anyone is watching, and when nobody is it runs under the limits
  of attendance.py, which `stop` applies. Everything else still applies to it: the worker lease,
  the 10 minute upload timeout and `cancel`.
- Worker lease (120 s per job, renewed by every message of the current attempt): when it
  runs out the job finishes `interrupted`, or `cancelled` with its reason if an unattended stop
  was due or asked for: the stop decided the job's end, the lost worker only means nobody
  answered. It is never handed to another worker. A worker that comes back hears the job is
  over from its next heartbeat, stops it and cleans up; its result is refused. One that never
  answers stops the job itself after a lease without replies, and a restart clears the rest.
- An `uploading` job older than 10 minutes finishes `interrupted`. Uploading jobs are not
  subject to the client lease: a client cannot heartbeat while it streams a large upload.
- Runner reservations (`kind = 'runner'`) ignore the client lease; their worker lease is
  renewed by the worker's supervision heartbeats and expires like any other.
"""

import sqlite3
from typing import Any

from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import attendance
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import ACTIVE_STATES, Store

CLIENT_LEASE_S = 300.0  # survives a few minutes of laptop Wi-Fi loss
WORKER_LEASE_S = 120.0
UPLOAD_TIMEOUT_S = 600.0

_ACTIVE = tuple(state.value for state in ACTIVE_STATES)
_ACTIVE_SQL = f"state IN ({', '.join('?' for _ in _ACTIVE)})"


def check_attempt(job: dict[str, Any], attempt_id: Any) -> None:
    """Conflict unless `attempt_id` is the job's current attempt."""
    if not isinstance(attempt_id, str) or not attempt_id:
        raise BadRequest("field 'attempt_id' is required for worker messages")
    if attempt_id != job["attempt_id"]:
        raise Conflict(f"stale attempt {attempt_id} for job {job['job_id']}")


def renew_client(store: Store, job_id: str, now: float) -> dict[str, Any]:
    """Extend the client lease of an unfinished job; return the job."""
    with store.write() as conn:
        job = st.require_job(conn, job_id)
        if job["state"] != JobState.FINISHED:
            st.update_job(conn, job_id, client_lease_until=now + CLIENT_LEASE_S)
            job = st.require_job(conn, job_id)
    return job


def renew_worker(store: Store, job_id: str, attempt_id: str, now: float) -> dict[str, Any]:
    """Extend the worker lease for the current attempt; Conflict for a stale one."""
    with store.write() as conn:
        job = st.require_job(conn, job_id)
        check_attempt(job, attempt_id)
        return renew_worker_in(conn, job, now)


def renew_worker_in(conn: sqlite3.Connection, job: dict[str, Any], now: float
                    ) -> dict[str, Any]:
    """Same as renew_worker inside an open write transaction (attempt already checked)."""
    if job["state"] in _ACTIVE:
        st.update_job(conn, job["job_id"], worker_lease_until=now + WORKER_LEASE_S)
        job = st.require_job(conn, job["job_id"])
    return job


def expire(store: Store, now: float, staging: Staging | None = None) -> list[str]:
    """Apply every expired lease and upload timeout; return the ids of finished jobs.

    With `staging`, the snapshot uploads of those jobs are removed after the commit.
    """
    finished: list[str] = []
    with store.write() as conn:
        finished += _stop_unattended(conn, now)  # first: a stop that is due keeps its reason
        for job in st.select_jobs(conn, f"{_ACTIVE_SQL} AND worker_lease_until < ?",
                                  (*_ACTIVE, now)):
            lost = Outcome.CANCELLED if job["stop_reason"] else Outcome.INTERRUPTED
            st.finish(conn, job, lost, now)
            finished.append(job["job_id"])
        for job in st.select_jobs(conn, "state = ? AND created_at < ?",
                                  (JobState.UPLOADING.value, now - UPLOAD_TIMEOUT_S)):
            st.finish(conn, job, Outcome.INTERRUPTED, now)
            finished.append(job["job_id"])
        for job in st.select_jobs(
            conn, f"(state = ? OR {_ACTIVE_SQL}) AND cancel_requested = 0 "
            "AND kind = 'job' AND detached = 0 AND client_lease_until < ?",
            (JobState.QUEUED.value, *_ACTIVE, now),
        ):
            if request_cancel(conn, job, now)["state"] == JobState.FINISHED:
                finished.append(job["job_id"])
    if staging is not None:
        for job_id in finished:
            staging.remove_upload(job_id)
    return finished


def _stop_unattended(conn: sqlite3.Connection, now: float) -> list[str]:
    """Stop the unattended jobs that have run out of time; return those finished at once."""
    limits = attendance.read_limits(conn)
    finished = []
    for job in st.select_jobs(
        conn, f"(state = ? OR {_ACTIVE_SQL}) AND cancel_requested = 0 AND kind = 'job' "
        "AND detached = 1 AND client_lease_until <= ?", (JobState.QUEUED.value, *_ACTIVE, now),
    ):
        view = attendance.unattended(job, now, limits)
        if view is not None and now >= view["stop_at"]:
            if stop(conn, job, view["stop_reason"], now)["state"] == JobState.FINISHED:
                finished.append(job["job_id"])
    return finished


def stop(conn: sqlite3.Connection, job: dict[str, Any], reason: str, now: float
         ) -> dict[str, Any]:
    """`request_cancel` with the reason recorded. A running job's worker sees an ordinary cancel
    and reports `cancelled`, the reason turns that into a stop, so any worker can do this."""
    st.update_job(conn, job["job_id"], stop_reason=reason)
    return request_cancel(conn, st.require_job(conn, job["job_id"]), now)


def request_cancel(conn: sqlite3.Connection, job: dict[str, Any], now: float
                   ) -> dict[str, Any]:
    """Cancel a job: uploading/queued finish `cancelled` now, active ones get a request.

    Finished jobs are returned unchanged. The caller removes the upload of a job that
    this call finished.
    """
    if job["state"] in (JobState.UPLOADING, JobState.QUEUED):
        return st.finish(conn, job, Outcome.CANCELLED, now, cancel_requested=True)
    if job["state"] in _ACTIVE and not job["cancel_requested"]:
        st.update_job(conn, job["job_id"], cancel_requested=True)
        return st.require_job(conn, job["job_id"])
    return job
