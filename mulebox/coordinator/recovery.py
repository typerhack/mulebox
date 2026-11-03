"""Coordinator start-up recovery (docs/design.md, Leases and failure handling).

Jobs left in `starting|running|cleaning` whose worker lease has run out are marked
`finished/interrupted`; they are never replayed. Jobs whose lease is still valid are left
alone: their worker may still be running them. Snapshot uploads of finished or unknown
jobs, and temp uploads no longer being written, are removed.
"""

from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import ACTIVE_STATES, Store

_log = get_logger(__name__)
_ACTIVE = tuple(state.value for state in ACTIVE_STATES)


def recover(store: Store, now: float, staging: Staging | None = None) -> list[str]:
    """Interrupt active jobs with an expired (or missing) worker lease; return their ids."""
    interrupted: list[str] = []
    with store.write() as conn:
        marks = ", ".join("?" for _ in _ACTIVE)
        for job in st.select_jobs(
            conn, f"state IN ({marks}) AND (worker_lease_until IS NULL OR "
            "worker_lease_until < ?)", (*_ACTIVE, now),
        ):
            st.finish(conn, job, Outcome.INTERRUPTED, now)
            interrupted.append(job["job_id"])
    for job_id in interrupted:
        _log.warning("job %s interrupted: worker lease expired before restart", job_id)
    if staging is not None:
        cleanup_uploads(store, staging)
    return interrupted


def cleanup_uploads(store: Store, staging: Staging) -> list[str]:
    """Remove uploads nobody needs any more; return the job ids they belonged to."""
    removed: list[str] = []
    for job_id, is_temp in staging.upload_entries():
        try:
            job = store.get_job(job_id)
        except BadRequest:
            continue
        if job is None or job["state"] == JobState.FINISHED or (
            is_temp and job["state"] != JobState.UPLOADING
        ):
            try:
                staging.remove_upload_entry(job_id, is_temp)
            except BadRequest:
                _log.warning("leaving unexpected upload file for %r", job_id)
                continue
            removed.append(job_id)
    return removed
