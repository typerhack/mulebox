"""The owner's controls on one job (`mulebox pause|resume|first|boost|normal`, the dashboard).

mulebox runs on its owner's own network, so whoever reaches the queue may steer it.

- `pause`: a queued job is skipped and keeps its place; a running one is frozen on its machine,
  its processes and its containers (worker/controls.py), and is not asked or stopped as stuck.
- `resume`: undoes it. For a running job it answers every check-in so far and counts as
  activity (attendance.py), so the time it spent paused is not held against it.
- `first`: a queued job goes before every other waiting job.
- `boost`: the job gets the machine's CPU and disk before anything else there, and its machine
  takes no new job until it ends (queue.boosted_on). A queued job is also moved first.
- `normal`: back to its own place in line, without the boost.

A GitHub run's slot is GitHub's, and a finished or cancelled job has nothing to steer.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.protocol import JobState, Message, MessageType
from mulebox.coordinator import attendance
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.views import status_body

ACTIONS = ("pause", "resume", "first", "boost", "normal")
_STEERABLE = (JobState.UPLOADING, JobState.QUEUED, JobState.STARTING, JobState.RUNNING)


def _first(conn: sqlite3.Connection, job: dict[str, Any]) -> int:
    """A priority above every other waiting job's, or the job's own if it already leads."""
    top = conn.execute("SELECT MAX(priority) FROM jobs WHERE state IN (?, ?) AND job_id != ?",
                       (JobState.UPLOADING.value, JobState.QUEUED.value, job["job_id"])
                       ).fetchone()[0] or 0
    return max(job["priority"], top + 1)


def changes(conn: sqlite3.Connection, job: dict[str, Any], action: str,
            now: float) -> dict[str, Any]:
    """The columns `action` sets on `job`; nothing when it is already so."""
    waiting = job["state"] in (JobState.UPLOADING, JobState.QUEUED)
    if action == "pause":
        return {"paused": 1}
    if action == "resume":
        if not job["paused"]:
            return {}
        if waiting:
            return {"paused": 0}
        return {"paused": 0, "check_in_ok": attendance.answer(job, now), "active_at": now}
    if action == "first":
        if not waiting:
            raise Conflict(f"job {job['job_id']} is {job['state']}; only a waiting job can go first")
        return {"priority": _first(conn, job)}
    if action == "boost":
        return {"boost": 1, **({"priority": _first(conn, job)} if waiting else {})}
    return {"priority": 0, "boost": 0}  # normal


def control(req: Request) -> Message:
    action = v.text(req.body, "action")
    if action not in ACTIONS:
        raise BadRequest(f"field 'action' must be one of {', '.join(ACTIONS)}")
    with req.store.write() as conn:
        job = st.require_job(conn, v.job_id(req.body))
        if job["kind"] != "job":
            raise Conflict(f"job {job['job_id']} holds a slot for a GitHub run; "
                           "steer that run on GitHub")
        if job["state"] not in _STEERABLE or job["cancel_requested"]:
            raise Conflict(f"job {job['job_id']} is "
                           f"{'being cancelled' if job['cancel_requested'] else job['state']}; "
                           "there is nothing to " + action)
        fields = changes(conn, job, action, req.now)
        if fields:
            st.update_job(conn, job["job_id"], **fields)
            job = st.require_job(conn, job["job_id"])
    return req.reply(MessageType.STATUS_OK, status_body(job, action=action))
