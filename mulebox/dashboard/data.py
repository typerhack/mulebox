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

from mulebox.common.download_watch import clean as clean_download
from mulebox.common.protocol import JobState
from mulebox.common.redact import Redactor
from mulebox.common.status import ACTIVE, STOP_TEXT, current_stage, shown_state, snapshot
from mulebox.coordinator import (api, attendance, clients, line, line_rules, node_settings, queue,
                                 stats, stats_api, steps, usual, workers)
from mulebox.coordinator import store as st
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.validate import check_job_id
from mulebox.coordinator.views import placement, reservation_dict, running_ahead, waiting_for
from mulebox.dashboard import history_query, machines, notices
from mulebox.version import get_version

QUEUE_FINISHED = 20
HISTORY_DEFAULT = 50
HISTORY_MAX = 200
DETAIL_FIELDS = ("base_commit", "timeout_min", "needs", "toolchain", "duration_s", "setup",
                 "cancel_requested")


class DashboardData:
    def __init__(self, store: Store, staging: Staging, local_name: str | None = None) -> None:
        """`local_name`: the worker on the dashboard's own machine, if one is (`host` rows)."""
        self.store, self.staging, self.local_name = store, staging, local_name
        self._redactor = Redactor()

    def queue_jobs(self, now: float | None = None,
                   finished_limit: int = QUEUE_FINISHED) -> list[dict[str, Any]]:
        """The queue rows, each waiting agent job with where it may go (views.placement)."""
        now = time.time() if now is None else now
        with self.store.read() as conn:
            order = line.read(conn, now)  # the order rules' reasons (line.py)
            rows = queue.listing(conn, finished_limit, order)
            fleet = workers.listing(conn)
            limits = attendance.read_limits(conn)
            typical = usual.lengths(conn, [job for job, _ in rows
                                           if job["state"] != JobState.FINISHED])
            doing = {job["job_id"]: _doing(job, steps.for_job(conn, job["job_id"]))
                     for job, _ in rows if job["state"] in ACTIVE}
            # The coordinator's own reason (paused, held, behind an upgrade, a paused project,
            # nothing fits), the one `mulebox status` and `queue` give.
            why = {job["job_id"]: reason for job, _ in rows
                   if (reason := waiting_for(conn, job, now, order))}
            # The job holding a queued job's branch, which it waits for even with a slot free.
            busy = {job["job_id"]: holder for job, _ in rows
                    if (holder := running_ahead(conn, job).get("branch_busy"))}
        return [{**reservation_dict(job, pos), **placement(fleet, job, now),
                 **attendance.fields(job, now, limits), **order.explain(job),
                 **({"usual_s": typical[job["job_id"]]} if typical.get(job["job_id"]) else {}),
                 **({"doing": doing[job["job_id"]]} if job["job_id"] in doing else {}),
                 **({"waiting_for": why[job["job_id"]]} if job["job_id"] in why else {}),
                 **({"branch_busy": busy[job["job_id"]]} if job["job_id"] in busy else {})}
                for job, pos in rows]

    def queue_snapshot(self, now: float) -> dict[str, Any]:
        return snapshot(self.queue_jobs(now), now)

    def queue_rules(self) -> dict[str, Any]:
        """The order rules and the projects to set them for (line_rules.body)."""
        with self.store.read() as conn:
            return line_rules.body(conn)

    def machines(self, now: float) -> dict[str, Any]:
        return self.fleet(now)[0]

    def fleet(self, now: float) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """The machines panel, and the workers as stored (with their full `load`) it came from."""
        with self.store.read() as conn:
            limits = attendance.read_limits(conn)
            active = [{**job, **attendance.fields(job, now, limits)}
                      for job in queue.active_jobs(conn)]
            found = workers.listing(conn)
            panel = machines.snapshot(found, active, now, self.local_name)
            panel["notices"] = notices.notices(get_version(), found, clients.recent(conn, now), now)
            return panel, found

    def node_settings(self, name: str, now: float) -> dict[str, Any] | None:
        """A machine's settings window (coordinator/node_settings.py `view`), or None if unknown."""
        with self.store.read() as conn:
            found = workers.get(conn, name)
            return None if found is None else node_settings.view(conn, found, now)

    def job(self, job_id: str, now: float | None = None) -> dict[str, Any] | None:
        """The detail view of one job, or None when the id is malformed or unknown."""
        raw = self._raw(job_id)
        if raw is None:
            return None
        job, place = raw
        now = time.time() if now is None else now
        with self.store.read() as conn:
            limits = attendance.read_limits(conn)
            rows = steps.for_job(conn, job["job_id"])
            typical = usual.for_job(conn, job)
            failed = steps.failed_stage(conn, job).get("stage")
            why = line.read(conn, now).explain(job)
        detail = {**reservation_dict(job, place), **{n: job[n] for n in DETAIL_FIELDS},
                  "steps": rows, "usual": typical, "failed_stage": failed,
                  **attendance.fields(job, now, limits), **why,
                  "activity": attendance.status_fields(job, rows, now, limits)["activity"]}
        detail["shown_state"] = shown_state(detail)
        detail["stop_text"] = STOP_TEXT.get(detail.get("stop_reason"))
        detail["command"] = self._redactor.redact(shlex.join(job["argv"])) if job["argv"] else ""
        detail["setup"] = self._redactor.redact(job["setup"]) if job["setup"] else job["setup"]
        detail["log_size"] = self.staging.log_size(job["job_id"])
        return detail

    def history(self, limit: int = HISTORY_DEFAULT, before: float | None = None,
                chosen: dict[str, str] | None = None) -> dict[str, Any]:
        """Finished jobs matching `chosen` (history_query.filters), newest first; page with
        `before` = the last `finished_at` seen. The first page also lists every value each
        filter can take, the Statistics page's list (coordinator/stats.py `choices`)."""
        where, params = history_query.where(chosen or {}, before)
        limit = max(1, min(HISTORY_MAX, limit))
        with self.store.read() as conn:
            jobs = st.select_jobs(conn, where, params, "finished_at DESC, seq DESC", limit=limit)
            options = stats.choices(conn) if before is None else None
        rows = [{**reservation_dict(job), "duration_s": job["duration_s"]} for job in jobs]
        rows = [{**row, "shown_state": shown_state(row)} for row in rows]
        more = len(rows) == limit
        return {"jobs": rows, "next_before": rows[-1]["finished_at"] if more else None,
                **({"choices": options} if options is not None else {})}

    def stats(self, body: dict[str, Any], now: float) -> dict[str, Any]:
        """Job minutes, as `mulebox stats` gets them (coordinator/stats_api.py)."""
        return stats_api.answer(self.store, body, now)

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



def _doing(job: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What a job in a slot is doing now, for its card: its stage (a runner job's GitHub step)
    and the CPU of the job alone in percent of one core, null when not measured, and what it is
    downloading (common/download_watch.py), null when nothing is."""
    report = job.get("activity") or {}
    cpu = report.get("job_cpu_pct")
    step = report.get("step")
    return {"stage": current_stage(job, rows),
            "step": step if isinstance(step, str) else None,
            "cpu_pct": cpu if isinstance(cpu, (int, float)) else None,
            "download": clean_download(report.get("download"))}
