"""A person's hold on a node, waiting in line like a job (docs/design.md, Holding a node, M23.10).

`mulebox hold <node>` makes a row of kind `hold`, pinned to the node, with no snapshot; the worker
runs nothing for it. Its slots, `hold_slots` or all of the node's for 0, count as taken
(queue.held_slots), so no job or GitHub run starts in them, and an upgrade waits for it.

- `make`: in line behind the jobs waiting, or first with `next`.
- `turn`: the dev machine asks every few seconds while it waits, and every 30 s once held. Its
  turn comes when nothing ahead in line could start on its node (reservations.ahead), no upgrade
  of the node comes first, and enough slots are free. Each ask renews its lease: a waiting hold
  ends after LEASE_S without one (`expire`), a held one through the worker lease, which `turn`
  renews (leases.expire).
- `release`: let go. `mulebox cancel` lets go too (api.cancel). Past `for_s` (timeout_min) a
  held node goes back whatever the dev machine does.
"""

from __future__ import annotations

import sqlite3
import time
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.coordinator import line, line_moves, queue, reservations, upgrades, workers
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, NotFound
from mulebox.coordinator.store import ACTIVE_STATES
from mulebox.coordinator import views
from mulebox.coordinator.views import status_body

HOLD_KIND = queue.HOLD_KIND
LEASE_S = 120.0  # the dev machine renews every 30 s
DEFAULT_FOR_S = 2 * 3600.0
MAX_FOR_S = 24 * 3600.0
PROJECT, JOB = "mulebox", "hold"


def what(job: dict[str, Any]) -> str:
    """"the whole node" or "2 slots", as the hold's branch reads."""
    n = int(job.get("hold_slots") or 0)
    return "the whole node" if n == 0 else f"{n} slot{'s' if n != 1 else ''}"


def _make(req: Request) -> dict[str, Any]:
    node = v.text(req.body, "node")
    slots = v.integer(req.body, "slots", 0, 0, 1024)
    for_s = float(v.integer(req.body, "for_s", int(DEFAULT_FOR_S), 60, int(MAX_FOR_S)))
    with req.store.write() as conn:
        known = workers.get(conn, node)
        if known is None:
            raise NotFound(f"no node called {node!r}", error_code="node.unknown")
        if slots and known.get("slots") and slots > known["slots"]:
            raise BadRequest(f"{node} has {known['slots']} slots; ask for at most that, or "
                             "leave out --slots for the whole node")
        ahead = line_moves.front(line.read(conn, req.now), {"job_id": ""}) \
            if req.body.get("next") is True else {}
        job = st.insert_job(conn, {
            "job_id": new_id("job"), "kind": HOLD_KIND, "pinned_worker": node,
            "project": PROJECT, "job": JOB, "branch": "", "hold_slots": slots,
            "client": v.text(req.body, "client", "hold"), "argv": ["hold"],
            "fingerprint": "", "base_commit": "", "timeout_min": round(for_s / 60),
            "detached": True, "idempotency_key": f"hold-{new_id('key')}", **ahead,
            "state": JobState.QUEUED, "created_at": req.now, "queued_at": req.now,
            "client_lease_until": req.now + LEASE_S,
        })
        st.update_job(conn, job["job_id"], branch=what(job))
        return st.require_job(conn, job["job_id"])


def due(conn: sqlite3.Connection, job: dict[str, Any], now: float,
        order: line.Line | None = None) -> bool:
    """Whether a waiting hold may take its node now."""
    order = order or line.read(conn, now)
    worker = job["pinned_worker"]
    if job["paused"] or reservations.ahead(conn, job, now, order) > 0:
        return False
    if upgrades.blocks(conn, worker, job, order):
        return False
    total = reservations.worker_slots(conn, worker, 1)
    need = int(job["hold_slots"] or 0) or total
    return queue.active_on(conn, worker) + need <= total


def _turn(req: Request) -> dict[str, Any]:
    with req.store.write() as conn:
        job = _require(conn, req)
        if job["state"] == JobState.QUEUED:
            if due(conn, job, req.now):
                job = st.transition(conn, job, JobState.STARTING, worker=job["pinned_worker"],
                                    started_at=req.now, worker_lease_until=req.now + LEASE_S)
                job = st.transition(conn, job, JobState.RUNNING)
            else:
                st.update_job(conn, job["job_id"], client_lease_until=req.now + LEASE_S)
                job = st.require_job(conn, job["job_id"])
        elif job["state"] in ACTIVE_STATES:
            if req.now >= until(job):
                job = _end(conn, job, Outcome.PASSED, req.now, "its time was up")
            else:
                st.update_job(conn, job["job_id"], worker_lease_until=req.now + LEASE_S)
                job = st.require_job(conn, job["job_id"])
        return _view(conn, job, req.now)


def until(job: dict[str, Any]) -> float:
    return float(job["started_at"] or 0) + 60.0 * float(job["timeout_min"] or 0)


def _release(req: Request) -> dict[str, Any]:
    with req.store.write() as conn:
        job = _require(conn, req)
        job = release(conn, job, req.now, "let go")
        return _view(conn, job, req.now)


def release(conn: sqlite3.Connection, job: dict[str, Any], now: float, why: str
            ) -> dict[str, Any]:
    """Let go of a hold, waiting or held; a finished one is returned as it is."""
    if job["state"] == JobState.FINISHED:
        return job
    outcome = Outcome.PASSED if job["state"] in ACTIVE_STATES else Outcome.CANCELLED
    return _end(conn, job, outcome, now, why)


def _end(conn: sqlite3.Connection, job: dict[str, Any], outcome: Outcome, now: float,
         why: str) -> dict[str, Any]:
    started = job["started_at"]
    duration = round(max(0.0, now - started), 3) if started is not None else None
    return st.finish(conn, job, outcome, now, duration_s=duration, stop_reason=why,
                     exit_code=0)


def _view(conn: sqlite3.Connection, job: dict[str, Any], now: float) -> dict[str, Any]:
    held = job["state"] in ACTIVE_STATES
    return {**status_body(job, queue.position(conn, job, now), views.waiting_for(conn, job, now)),
            "go": held, "node": job["pinned_worker"], "holds": what(job), **({"until": until(job)} if held else {}),
            **({"ended": job.get("stop_reason") or job.get("outcome")}
               if job["state"] == JobState.FINISHED else {})}


def in_the_way(conn: sqlite3.Connection, job: dict[str, Any], now: float,
               order: line.Line | None = None) -> str | None:
    """Why a waiting job waits for a hold, if it does: one holds a node it could run on, or
    waits ahead of it in line (queue.oldest_reservation). None when no hold is in its way."""
    marks = ", ".join("?" for _ in ACTIVE_STATES)
    found = st.select_jobs(conn, f"kind = ? AND (state = ? OR state IN ({marks}))",
                           (HOLD_KIND, JobState.QUEUED.value, *(s.value for s in ACTIVE_STATES)),
                           queue.QUEUE_ORDER)
    if job["pinned_worker"]:
        found = [h for h in found if h["pinned_worker"] == job["pinned_worker"]]
    if found and order is None:
        order = line.read(conn, now)
    for row in found:
        node = row["pinned_worker"]
        if row["state"] in ACTIVE_STATES:
            ends = time.strftime("%H:%M", time.localtime(until(row)))
            return (f"{node} is held ({what(row)}) by {row['client']} until {ends} at most "
                    f"({row['job_id']})")
        if order.before(row, job):
            return (f"a hold of {node} is ahead of it in line ({row['job_id']}): nothing behind "
                    "it starts there until it ends")
    return None


def _require(conn: sqlite3.Connection, req: Request) -> dict[str, Any]:
    job = st.require_job(conn, v.job_id(req.body))
    if job["kind"] != HOLD_KIND:
        raise BadRequest(f"job {job['job_id']} is not a hold; `mulebox cancel` stops a job")
    return job


def expire(conn: sqlite3.Connection, now: float) -> list[str]:
    """Holds whose dev machine stopped asking while they waited, and held ones past their time;
    their ids. A held one whose dev machine went quiet goes with the worker lease."""
    gone = st.select_jobs(conn, "kind = ? AND state = ? AND client_lease_until < ?",
                          (HOLD_KIND, JobState.QUEUED.value, now))
    for job in gone:
        _end(conn, job, Outcome.INTERRUPTED, now, "its dev machine went quiet")
    marks = ", ".join("?" for _ in ACTIVE_STATES)
    for job in st.select_jobs(conn, f"kind = ? AND state IN ({marks})",
                              (HOLD_KIND, *(s.value for s in ACTIVE_STATES))):
        if now >= until(job):
            _end(conn, job, Outcome.PASSED, now, "its time was up")
            gone.append(job)
    return [job["job_id"] for job in gone]


_ACTIONS = {"make": _make, "turn": _turn, "release": _release}


def hold(req: Request) -> Message:
    action = v.text(req.body, "action")
    if action not in _ACTIONS:
        raise BadRequest(f"field 'action' must be one of {', '.join(_ACTIONS)}")
    made = _ACTIONS[action](req)
    if action == "make":
        with req.store.read() as conn:
            made = _view(conn, made, req.now)
    return req.reply(MessageType.STATUS_OK, made)
