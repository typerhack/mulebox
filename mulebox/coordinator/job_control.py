"""The owner's controls on one job (`mulebox pause|resume|first|up|down|last|boost|normal`).

mulebox runs on its owner's own network, so whoever reaches the queue may steer it.

- `pause`: a queued job is skipped and keeps its place; a running one is frozen on its machine,
  its processes and its containers (worker/controls.py), and is not asked or stopped as stuck.
- `resume`: undoes it. For a running job it answers every check-in so far and counts as
  activity (attendance.py), so the time it spent paused is not held against it.
- `first`, `up`, `down`, `last`: a queued job moves to the front of the line, one place ahead,
  one place back, or to the end (line_moves.py). Only the moved job is pinned, at the front or
  just ahead of or behind another job's place; the others stay where the order rules put them
  (line.py), so a later rule change still applies to them.
- `boost`: the job gets the machine's CPU and disk before anything else there, and its machine
  takes no new job until it ends (queue.boosted_on). A queued job is also moved first.
- `normal`: ends the boost; the job keeps its place in line.

A GitHub run's slot moves in line while it waits. Once its run holds the slot, it can be
paused (frozen) and boosted like a job: the worker applies both to the runner's service and the
run's Compose containers (runners/supervise.py). A long freeze can make GitHub give up on the
runner and fail the run; the owner chose to have it anyway. A waiting upgrade only moves in line,
and a finished or cancelled job has nothing to steer.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.protocol import JobState, Message, MessageType
from mulebox.coordinator import attendance, line, line_moves, queue
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.views import status_body

ACTIONS = ("pause", "resume", "first", "up", "down", "last", "boost", "normal")
MOVES = line_moves.MOVES
_STEERABLE = (JobState.UPLOADING, JobState.QUEUED, JobState.STARTING, JobState.RUNNING)


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
    if action in MOVES:
        if not waiting:
            raise Conflict(f"job {job['job_id']} is {job['state']}; only a waiting job moves in line")
        if job["state"] == JobState.UPLOADING:
            if action != "first":
                raise Conflict(f"job {job['job_id']} is still uploading; it has no place in line yet")
            return line_moves.front(line.read(conn, now), job)
        return line_moves.move(line.read(conn, now), job, action)
    if action == "boost":
        return {"boost": 1, **(line_moves.front(line.read(conn, now), job) if waiting else {})}
    return {"boost": 0} if job["boost"] else {}  # normal


def _allowed(job: dict[str, Any], action: str) -> bool:
    """Whether `action` applies to a job of this kind in this state (the docstring's rules)."""
    if job["kind"] == queue.JOB_KIND:
        return True
    if action in MOVES:
        return job["state"] == JobState.QUEUED
    return job["kind"] == queue.RUNNER_KIND and job["state"] in (JobState.STARTING, JobState.RUNNING)


def control(req: Request) -> Message:
    action = v.text(req.body, "action")
    if action not in ACTIONS:
        raise BadRequest(f"field 'action' must be one of {', '.join(ACTIONS)}")
    with req.store.write() as conn:
        job = st.require_job(conn, v.job_id(req.body))
        if not _allowed(job, action):
            what = ("holds a slot for a GitHub run; while it waits it can only move in line, "
                    "and once it runs it can be paused or boosted" if job["kind"] == queue.RUNNER_KIND
                    else "is an upgrade; it can only move in line while it waits, or be cancelled")
            raise Conflict(f"job {job['job_id']} {what}")
        if job["state"] not in _STEERABLE or job["cancel_requested"]:
            raise Conflict(f"job {job['job_id']} is "
                           f"{'being cancelled' if job['cancel_requested'] else job['state']}; "
                           "there is nothing to " + action)
        fields = changes(conn, job, action, req.now)
        if fields:
            st.update_job(conn, job["job_id"], **fields)
            job = st.require_job(conn, job["job_id"])
        order = line.read(conn, req.now)
        place, why = order.position(job), order.explain(job)
    return req.reply(MessageType.STATUS_OK, status_body(job, place, action=action, **why))
