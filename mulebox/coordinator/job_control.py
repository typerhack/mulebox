"""The owner's controls on one job (`mulebox pause|resume|first|up|down|last|boost|normal`).

mulebox runs on its owner's own network, so whoever reaches the queue may steer it.

- `pause`: a queued job is skipped and keeps its place; a running one is frozen on its machine,
  its processes and its containers (worker/controls.py), and is not asked or stopped as stuck.
- `resume`: undoes it. For a running job it answers every check-in so far and counts as
  activity (attendance.py), so the time it spent paused is not held against it.
- `first`, `up`, `down`, `last`: a queued job moves to the front of the line, one place ahead,
  one place back, or to the end (`_move`). The line is the queue's own order, priority first
  (queue.QUEUE_ORDER), so a move writes the new order into every waiting job's priority; a
  job sent later comes after all of them, as it would anyway.
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
from mulebox.coordinator import attendance, queue
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.views import status_body

ACTIONS = ("pause", "resume", "first", "up", "down", "last", "boost", "normal")
MOVES = ("first", "up", "down", "last")
_STEERABLE = (JobState.UPLOADING, JobState.QUEUED, JobState.STARTING, JobState.RUNNING)


def _first(conn: sqlite3.Connection, job: dict[str, Any]) -> int:
    """A priority above every other waiting job's, or the job's own if it already leads."""
    top = conn.execute("SELECT MAX(priority) FROM jobs WHERE state IN (?, ?) AND job_id != ?",
                       (JobState.UPLOADING.value, JobState.QUEUED.value, job["job_id"])
                       ).fetchone()[0] or 0
    return max(job["priority"], top + 1)


def _move(conn: sqlite3.Connection, job: dict[str, Any], to: str) -> dict[str, Any]:
    """Reorder the line with `job` moved `to`; the job's own new columns."""
    # Every queued row, GitHub's slots too, so they keep their place among the jobs shown.
    line = st.select_jobs(conn, "state = ?", (JobState.QUEUED.value,), queue.QUEUE_ORDER)
    ids = [row["job_id"] for row in line]
    at = ids.index(job["job_id"])
    ids.pop(at)
    place = {"first": 0, "last": len(ids), "up": max(at - 1, 0), "down": min(at + 1, len(ids))}[to]
    ids.insert(place, job["job_id"])
    if place == at:
        return {}
    priority = {row["job_id"]: row["priority"] for row in line}
    for index, job_id in enumerate(ids):
        wanted = len(ids) - index  # the last in line keeps 1, ahead of jobs sent later
        if priority[job_id] != wanted and job_id != job["job_id"]:
            st.update_job(conn, job_id, priority=wanted)
    return {"priority": len(ids) - place}


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
            return {"priority": _first(conn, job)}
        return _move(conn, job, action)
    if action == "boost":
        return {"boost": 1, **({"priority": _first(conn, job)} if waiting else {})}
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
        place = queue.position(conn, job)
    return req.reply(MessageType.STATUS_OK, status_body(job, place, action=action))
