"""Upgrades that wait their turn in the queue (M16.5; docs/install.md, Upgrading).

`mulebox setup <machine> --queued` leaves the new version on the machine and goes. There it is
a row of kind `upgrade` in the line, pinned to that machine, and a waiter on the machine
(worker/upgrade_wait.py) asks for its turn every few seconds:

- Nothing in line behind the upgrade starts on its machine (`blocks`): jobs and GitHub slots
  wait, as they do for a job ahead of them. Other machines go on.
- Its turn comes when the machine runs nothing and nothing ahead of it in line could start
  there (`_due`). By default it goes first in line, so that is as soon as the running jobs end;
  `--behind` leaves it behind the jobs already waiting.
- It then holds the machine while the waiter installs, and ends `passed` or `failed` with the
  installer's output as its log. The line goes on after it.

A waiting upgrade can be cancelled, moved and paused like a job. A waiter that stops asking
(the machine rebooted, the unit was stopped) lets its row go after TURN_LEASE_S, and one that
dies mid-install after INSTALL_LEASE_S, so a lost upgrade never holds a machine for good.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.coordinator import queue, workers
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.store import ACTIVE_STATES
from mulebox.coordinator.views import status_body

UPGRADE_KIND = "upgrade"
TURN_LEASE_S = 90.0  # the waiter asks every few seconds
INSTALL_LEASE_S = 1800.0  # past the installer's own limit
MAX_LOG = 64 * 1024
_WAITING = (JobState.QUEUED.value,)
_PENDING = (JobState.QUEUED.value, *(s.value for s in ACTIVE_STATES))


def _key(row: dict[str, Any]) -> tuple[int, float, int]:
    return (-row["priority"], row["queued_at"], row["seq"])


def pending(conn: sqlite3.Connection, worker: str) -> list[dict[str, Any]]:
    """Upgrades of `worker` that are waiting or installing, in line order."""
    marks = ", ".join("?" * len(_PENDING))
    return st.select_jobs(conn, f"kind = ? AND pinned_worker = ? AND state IN ({marks})",
                          (UPGRADE_KIND, worker, *_PENDING), queue.QUEUE_ORDER)


def blocks(conn: sqlite3.Connection, worker: str, row: dict[str, Any]) -> bool:
    """Whether an upgrade keeps `row` (a waiting job or GitHub slot) from starting on `worker`:
    one is installing there, or one waits ahead of `row` in line."""
    for upgrade in pending(conn, worker):
        if upgrade["state"] != JobState.QUEUED or _key(upgrade) < _key(row):
            return True
    return False


def _due(conn: sqlite3.Connection, upgrade: dict[str, Any]) -> bool:
    """The machine runs nothing, and nothing ahead in line could start there first."""
    worker = upgrade["pinned_worker"]
    if queue.active_on(conn, worker) > 0:
        return False
    if workers.is_draining(conn, worker):
        return True  # paused: nothing ahead will start there anyway
    known = workers.get(conn, worker)
    have = set(known["capabilities"]) if known else set()
    for row in st.select_jobs(conn, "state = ?", _WAITING, queue.QUEUE_ORDER):
        if _key(row) >= _key(upgrade):
            return True
        if row["kind"] == queue.JOB_KIND and not row["paused"] and set(row["needs"]) <= have:
            return False
        if row["kind"] == queue.RUNNER_KIND and row["pinned_worker"] == worker:
            return False
    return True


def _create(req: Request) -> dict[str, Any]:
    worker = v.text(req.body, "worker")
    version = v.text(req.body, "version")
    first = req.body.get("first", True) is not False
    with req.store.write() as conn:
        for found in pending(conn, worker):
            raise Conflict(f"an upgrade of {worker} to {found['branch']} is already in line "
                           f"({found['job_id']}); cancel it first: mulebox cancel {found['job_id']}")
        top = conn.execute("SELECT MAX(priority) FROM jobs WHERE state = ?", _WAITING).fetchone()[0]
        return st.insert_job(conn, {
            "job_id": new_id("job"), "kind": UPGRADE_KIND, "pinned_worker": worker,
            "project": "mulebox", "job": "upgrade", "branch": version,
            "client": v.text(req.body, "client", "upgrade"), "argv": ["upgrade", version],
            "fingerprint": "", "base_commit": "", "timeout_min": 0, "detached": True,
            "idempotency_key": f"upgrade-{new_id('key')}", "priority": (top or 0) + 1 if first else 0,
            "state": JobState.QUEUED, "created_at": req.now, "queued_at": req.now,
            "client_lease_until": req.now + TURN_LEASE_S,
        })


def _turn(req: Request) -> dict[str, Any]:
    with req.store.write() as conn:
        job = _require(conn, req)
        if job["state"] == JobState.QUEUED:
            if not job["paused"] and _due(conn, job):
                job = st.transition(conn, job, JobState.STARTING, worker=job["pinned_worker"],
                                    started_at=req.now, worker_lease_until=req.now + INSTALL_LEASE_S)
                job = st.transition(conn, job, JobState.RUNNING)
            else:
                st.update_job(conn, job["job_id"], client_lease_until=req.now + TURN_LEASE_S)
                job = st.require_job(conn, job["job_id"])
        return {**status_body(job, queue.position(conn, job)),
                "go": job["state"] in ACTIVE_STATES}


def _done(req: Request) -> dict[str, Any]:
    outcome = Outcome.PASSED if req.body.get("passed") is True else Outcome.FAILED
    text = str(req.body.get("log", ""))[-MAX_LOG:]
    with req.store.write() as conn:
        job = _require(conn, req)
        if job["state"] not in ACTIVE_STATES:
            raise Conflict(f"upgrade {job['job_id']} is {job['state']}, not installing")
        duration = round(max(0.0, req.now - (job["started_at"] or req.now)), 3)
        job = st.finish(conn, job, outcome, req.now, duration_s=duration,
                        exit_code=0 if outcome == Outcome.PASSED else 1)
    if text:
        req.staging.append_log(job["job_id"], 0, text.encode())
    return status_body(job)


def _require(conn: sqlite3.Connection, req: Request) -> dict[str, Any]:
    job = st.require_job(conn, v.job_id(req.body))
    if job["kind"] != UPGRADE_KIND:
        raise BadRequest(f"job {job['job_id']} is not an upgrade")
    return job


def expire(conn: sqlite3.Connection, now: float) -> list[str]:
    """Waiting upgrades whose waiter stopped asking; their ids. Installing ones go with the
    ordinary worker lease (leases.expire)."""
    gone = st.select_jobs(conn, "kind = ? AND state = ? AND client_lease_until < ?",
                          (UPGRADE_KIND, JobState.QUEUED.value, now))
    for job in gone:
        st.finish(conn, job, Outcome.INTERRUPTED, now)
    return [job["job_id"] for job in gone]


_ACTIONS = {"queue": _create, "turn": _turn, "done": _done}


def upgrade(req: Request) -> Message:
    action = v.text(req.body, "action")
    if action not in _ACTIONS:
        raise BadRequest(f"field 'action' must be one of {', '.join(_ACTIONS)}")
    made = _ACTIONS[action](req)
    if action == "queue":
        with req.store.read() as conn:
            made = status_body(made, queue.position(conn, made))
    return req.reply(MessageType.STATUS_OK, made)
