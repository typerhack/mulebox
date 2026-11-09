"""Removing old job logs, files runs brought back (a day after), and, much later, old stage
rows. Nothing else.

Nothing removed logs before this, and one job can write a lot. A log goes `log_days` after its
job finished, found by listing the logs folder and looking each name up in the store: a file
there that is no finished job's log, or a job still running, is left alone. Each file is a
regular file directly in that folder, named after a valid job id, and is removed through
safepath. Stage rows stay `step_days`, longer than logs, because they are small and are
what `usual` is worked out from. Job rows are never removed.
"""

from __future__ import annotations

from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState
from mulebox.coordinator import taken
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store

_log = get_logger(__name__)
DAY_S = 86400.0
TAKEN_DAYS = 1  # files a run brought back: the client fetched them at its end
_FINISHED_BEFORE = "SELECT job_id FROM jobs WHERE state = ? AND finished_at < ?"


def _old(store: Store, job_ids: set[str] | list[str], before: float) -> list[str]:
    with store.read() as conn:
        old = {row["job_id"] for row in conn.execute(
            _FINISHED_BEFORE, (JobState.FINISHED.value, before))}
    return sorted(job_id for job_id in job_ids if job_id in old)


def _old_logs(store: Store, staging: Staging, before: float) -> list[str]:
    return _old(store, staging.log_job_ids(), before)


def sweep(store: Store, staging: Staging, now: float, log_days: int,
          step_days: int) -> tuple[int, int]:
    """(logs removed, stage rows removed). A log that cannot go is tried again next time."""
    removed = 0
    for job_id in _old_logs(store, staging, now - log_days * DAY_S):
        try:
            staging.remove_log(job_id)
            removed += 1
        except MuleboxError as exc:
            _log.warning("could not remove the log of %s: %s", job_id, exc)
    for job_id in _old(store, taken.job_ids(staging), now - TAKEN_DAYS * DAY_S):
        try:
            taken.remove(staging, job_id)
        except MuleboxError as exc:
            _log.warning("could not remove the files %s brought back: %s", job_id, exc)
    with store.write() as conn:
        cursor = conn.execute(f"DELETE FROM job_steps WHERE job_id IN ({_FINISHED_BEFORE})",
                              (JobState.FINISHED.value, now - step_days * DAY_S))
    return removed, cursor.rowcount
