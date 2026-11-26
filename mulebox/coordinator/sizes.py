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
from mulebox.coordinator import kept, needs, workers
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


def with_kept(conn: sqlite3.Connection, worker: str, on_it: list[Size | None],
              size: Size | None) -> list[Size | None]:
    """`on_it` and, for a job that declares a size, the memory of the failed jobs kept there
    for a rerun (kept.py): they hold no slot, so a job with no size, which counts as a slot's
    share, is not held back by them."""
    memory = kept.memory(conn, worker) if size else 0
    return [*on_it, {"cores": 0.0, "memory": float(memory)}] if memory else on_it


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


def _kept_for(conn: sqlite3.Connection, job: dict[str, Any], worker: dict[str, Any],
              budget: Budget, on_it: list[Size | None], order: Any) -> dict[str, Any] | None:
    """The job ahead of `job` in line that `worker` keeps its room for (queue.py), or None."""
    have = set(worker["capabilities"])
    for row in order.rows:
        if row["job_id"] == job["job_id"]:
            return None
        if (row["kind"] == "job" and set(row["needs"]) <= have and not row["paused"]
                and row["pinned_worker"] in (None, worker["worker"])
                and budget.holds(row["size"] or None)
                and not job_size.fits(budget, on_it, row["size"] or None)):
            return row
    return None


def waiting(conn: sqlite3.Connection, job: dict[str, Any], fleet: list[dict[str, Any]],
            now: float, order: Any = None) -> str | None:
    """`waiting_for` of a queued job that only sizes hold back, its own or that of the job
    ahead its node keeps room for, or None."""
    nodes = [w for w in needs.capable(needs.fleet_for(fleet, job), job["needs"])
             if workers.is_online(w, now) and not w.get("draining")]
    short, kept = [], []
    for worker in nodes:
        budget = budget_of(worker)
        if budget is None:
            return None
        on_it = running(conn, worker["worker"])
        if len(on_it) >= budget.slots:
            return None  # simply busy: the queue working
        if job_size.fits(budget, on_it, job.get("size") or None):
            ahead = _kept_for(conn, job, worker, budget, on_it, order) if order else None
            if ahead is None:
                return None
            kept.append(f"{worker['worker']} keeps its room for {ahead['job_id']} ahead of it, "
                        f"which needs {_need(ahead)}")
            continue
        short.append(f"{worker['worker']} has {job_size.room_words(budget, on_it)}")
    if kept and not short:
        return "waiting for room: " + "; ".join(kept)
    if not short:
        return None
    return f"waiting for room: it needs {_need(job)}; {', '.join(short + kept)}"


def _need(job: dict[str, Any]) -> str:
    return job_size.words(job["size"]) if job.get("size") else "one slot's share of a node"
