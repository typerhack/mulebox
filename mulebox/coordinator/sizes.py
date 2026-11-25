"""Job sizes in the queue (docs/design.md, Job sizes; common/job_size.py has the rules).

- At submit, a job whose `size` no node for it could ever give (its budget, with nothing else
  running) is refused at once, with the sizes, as a job nobody can run is (needs.py). A node
  whose size is not known yet does not refuse anything.
- At a claim, a node takes a job only when its size fits in what the jobs running there leave
  of its budget. When the first job in line that the node could take does not fit yet, the node
  keeps that room for it and takes no job behind it (queue.py), so small jobs cannot keep a big
  one waiting for ever. A job too big for this node ever is passed over: another takes it.
- A GitHub run's reservation is granted only when its size fits too (reservations.py); while
  it waits first in line, no job behind it starts on its node, so its room is kept the same way.
- A waiting job that a node with a free slot could take but for its size says so.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.common import job_size, units
from mulebox.common.job_size import Budget, Size
from mulebox.coordinator import needs, workers
from mulebox.coordinator.errors import BadRequest

HOW_TO_FIT = ("lower `size:` in .mulebox.yml (`mulebox usage` shows what the job really used), "
              "or lower `keep_cores` and `keep_memory` on a node")


def asked(body: dict[str, Any]) -> Size:
    """`size` of a submit, checked; {} for none (older clients, or not set)."""
    try:
        return job_size.checked(body.get("size")) or {}
    except ValueError as exc:
        raise BadRequest(str(exc)) from None


def budget_of(worker: dict[str, Any]) -> Budget | None:
    return job_size.budget(worker.get("load"), worker.get("settings"), worker.get("slots"))


def running(conn: sqlite3.Connection, worker: str) -> list[Size | None]:
    """The sizes of what holds a slot on `worker`, agent jobs and GitHub runs (runner_size.py);
    None for one with no size. Upgrades hold no slot."""
    rows = conn.execute("SELECT size FROM jobs WHERE worker = ? AND kind IN ('job', 'runner') "
                        "AND state IN ('starting', 'running', 'cleaning')", (worker,)).fetchall()
    return [json.loads(row["size"] or "{}") or None for row in rows]


def room_for(conn: sqlite3.Connection, worker: str, size: Size | None) -> bool:
    """Whether a job or run of `size` fits on `worker` now; True on a node of unknown size."""
    budget = budget_of(workers.get(conn, worker) or {})
    return budget is None or job_size.fits(budget, running(conn, worker), size)


def refusal(fleet: list[dict[str, Any]], wanted: list[str], size: Size,
            on: str | None = None) -> str | None:
    """Why a job of this size must not be queued at all, or None."""
    if not size:
        return None
    nodes = needs.capable(needs.fleet_for(fleet, {"pinned_worker": on}), wanted)
    known = [(w, budget_of(w)) for w in nodes]
    if not nodes or any(b is None or b.holds(size) for _, b in known):
        return None
    room = "; ".join(f"{w['worker']} {b.cores:g} cores and {units.size(b.memory)}"
                     for w, b in known if b is not None)
    return (f"this job asks for {job_size.words(size)}, more than any node for it can give a "
            f"job (what each has after what it keeps for its owner: {room}): {HOW_TO_FIT}")


def waiting(conn: sqlite3.Connection, job: dict[str, Any], fleet: list[dict[str, Any]],
            now: float) -> str | None:
    """`waiting_for` of a queued job that only its size holds back, or None."""
    nodes = [w for w in needs.capable(needs.fleet_for(fleet, job), job["needs"])
             if workers.is_online(w, now) and not w.get("draining")]
    short = []
    for worker in nodes:
        budget = budget_of(worker)
        if budget is None:
            return None
        on_it = running(conn, worker["worker"])
        if len(on_it) >= budget.slots:
            return None  # simply busy: the queue working
        if job_size.fits(budget, on_it, job.get("size") or None):
            return None
        short.append(f"{worker['worker']} has {job_size.room_words(budget, on_it)}")
    if not short:
        return None
    need = job_size.words(job["size"]) if job.get("size") else "one slot's share of a node"
    return f"waiting for room: it needs {need}; {', '.join(short)}"
