"""What the dashboard reads from the coordinator: queue, job detail, history, log chunks.

Only reads (the store is opened read-only, see store.py). Job dicts are the wire shapes
from coordinator/views.py (`reservation_dict`, so runner reservations carry `kind`,
`runner` and `run_url`), log chunks come from `api.log_chunk_body` exactly as the `watch`
stream sends them. Never returned: the job's `env`, leases, attempt ids or upload hashes.
Calls are blocking (SQLite); the server runs them in a thread.
"""

from __future__ import annotations

import shlex
import time
from typing import Any

from mulebox.common.protocol import JobState
from mulebox.common.redact import Redactor
from mulebox.common.status import STOP_TEXT, shown_state, snapshot
from mulebox.coordinator import api, attendance, queue, steps, usual, workers
from mulebox.coordinator import store as st
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.validate import check_job_id
from mulebox.coordinator.views import placement, reservation_dict
from mulebox.dashboard import machines

QUEUE_FINISHED = 20
HISTORY_DEFAULT = 50
HISTORY_MAX = 200
DETAIL_FIELDS = ("base_commit", "timeout_min", "needs", "toolchain", "duration_s", "setup")


class DashboardData:
    def __init__(self, store: Store, staging: Staging) -> None:
        self.store, self.staging = store, staging
        self._redactor = Redactor()

    def queue_jobs(self, now: float | None = None,
                   finished_limit: int = QUEUE_FINISHED) -> list[dict[str, Any]]:
        """The queue rows, each waiting agent job with where it may go (views.placement)."""
        now = time.time() if now is None else now
        with self.store.read() as conn:
            rows = queue.listing(conn, finished_limit)
            fleet = workers.listing(conn)
            limits = attendance.read_limits(conn)
        return [{**reservation_dict(job, pos), **placement(fleet, job, now),
                 **attendance.fields(job, now, limits)} for job, pos in rows]

    def queue_snapshot(self, now: float) -> dict[str, Any]:
        return snapshot(self.queue_jobs(now), now)

    def machines(self, now: float) -> dict[str, Any]:
        with self.store.read() as conn:
            limits = attendance.read_limits(conn)
            active = [{**job, **attendance.fields(job, now, limits)}
                      for job in queue.active_jobs(conn)]
            return machines.snapshot(workers.listing(conn), active, now)

    def job(self, job_id: str, now: float | None = None) -> dict[str, Any] | None:
        """The detail view of one job, or None when the id is malformed or unknown."""
        raw = self._raw(job_id)
        if raw is None:
            return None
        job, place = raw
        with self.store.read() as conn:
            limits = attendance.read_limits(conn)
            rows = steps.for_job(conn, job["job_id"])
            typical = usual.for_job(conn, job)
            failed = steps.failed_stage(conn, job).get("stage")
        detail = {**reservation_dict(job, place), **{n: job[n] for n in DETAIL_FIELDS},
                  "steps": rows, "usual": typical, "failed_stage": failed,
                  **attendance.fields(job, time.time() if now is None else now, limits)}
        detail["shown_state"] = shown_state(detail)
        detail["stop_text"] = STOP_TEXT.get(detail.get("stop_reason"))
        detail["command"] = self._redactor.redact(shlex.join(job["argv"])) if job["argv"] else ""
        detail["log_size"] = self.staging.log_size(job["job_id"])
        return detail

    def history(self, limit: int = HISTORY_DEFAULT, before: float | None = None,
                project: str | None = None) -> dict[str, Any]:
        """Finished jobs, newest first; page with `before` = the last `finished_at` seen."""
        where, params = "state = ?", [JobState.FINISHED.value]
        if before is not None:
            where += " AND finished_at < ?"
            params.append(before)
        if project:
            where += " AND project = ?"
            params.append(project)
        limit = max(1, min(HISTORY_MAX, limit))
        with self.store.read() as conn:
            jobs = st.select_jobs(conn, where, tuple(params), "finished_at DESC, seq DESC",
                                  limit=limit)
        rows = [{**reservation_dict(job), "duration_s": job["duration_s"]} for job in jobs]
        rows = [{**row, "shown_state": shown_state(row)} for row in rows]
        more = len(rows) == limit
        return {"jobs": rows, "next_before": rows[-1]["finished_at"] if more else None}

    def log_chunk(self, job_id: str, offset: int) -> dict[str, Any] | None:
        """A `log_chunk` body from `offset` (state read first, as watch.py does)."""
        raw = self._raw(job_id)
        if raw is None:
            return None
        return api.log_chunk_body(self.staging, raw[0], offset)

    def log_size(self, job_id: str) -> int:
        return self.staging.log_size(check_job_id(job_id))

    def _raw(self, job_id: str) -> tuple[dict[str, Any], int | None] | None:
        try:
            check_job_id(job_id)
        except Exception:  # noqa: BLE001 - a malformed id is simply not found
            return None
        with self.store.read() as conn:
            job = st.fetch_job(conn, job_id)
            return (job, queue.position(conn, job)) if job is not None else None
