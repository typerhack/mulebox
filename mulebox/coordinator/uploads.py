"""Snapshot transfer: `rpc-upload` (client -> coordinator) and `rpc-download` (-> worker).

An upload is accepted only while the job is `uploading`; once the file is verified and in
place, the job moves `uploading -> queued` and gets a fresh client lease (the client could
not heartbeat during a long upload).
"""

from typing import Any, BinaryIO

from mulebox.common.protocol import JobState
from mulebox.coordinator import queue
from mulebox.coordinator import store as st
from mulebox.coordinator.errors import Conflict, NotFound
from mulebox.coordinator.leases import CLIENT_LEASE_S
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.validate import check_job_id


def accept_upload(store: Store, staging: Staging, job_id: str, sha256: str,
                  stream: BinaryIO, now: float) -> tuple[dict[str, Any], int | None]:
    """Store the snapshot from `stream` and queue the job; return (job, position)."""
    check_job_id(job_id)
    _require_uploading(store.get_job(job_id), job_id)
    staging.write_upload(job_id, stream, sha256)
    try:
        with store.write() as conn:
            job = st.require_job(conn, job_id)
            _require_uploading(job, job_id)
            job = st.transition(
                conn, job, JobState.QUEUED, queued_at=now, upload_sha256=sha256,
                client_lease_until=now + CLIENT_LEASE_S,
            )
            return job, queue.position(conn, job)
    except (Conflict, NotFound):
        current = store.get_job(job_id)
        if current is None or current["state"] == JobState.FINISHED:
            staging.remove_upload(job_id)  # cancelled meanwhile; nobody needs the file
        raise


def send_snapshot(store: Store, staging: Staging, job_id: str, out: BinaryIO) -> int:
    """Write the job's snapshot to `out`; return the byte count."""
    check_job_id(job_id)
    if store.get_job(job_id) is None:
        raise NotFound(f"no job {job_id}")
    return staging.copy_upload(job_id, out)


def _require_uploading(job: dict[str, Any] | None, job_id: str) -> None:
    if job is None:
        raise NotFound(f"no job {job_id}")
    if job["state"] != JobState.UPLOADING:
        raise Conflict(f"job {job_id} is {job['state']}; uploads are accepted only while uploading")
