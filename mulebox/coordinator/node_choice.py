"""Which free node takes a job (design.md, Which node runs a job).

Nodes ask for work; the coordinator never assigns it. When a node asks, it may still leave a job
it could run to another node that is free now, for a short while:

1. Priority (M23.4): to a node ranked above it (`priority` in node.toml) that offers the job's
   needs, for `GRACE_S`.
2. The branch's node: of nodes on the same level, the one that ran the branch's last job keeps
   the branch's project folder and set-up dependencies, so it goes first, for `HOLD_S`.
3. Room: else, on the same level, a node with more free slots than this one goes first, for
   `HOLD_S`. A tie is no reason to wait.

Every wait counts from the first time a node left the job (`jobs.deferred_at`), not from its
arrival, so a job that sat behind a busy line still gets its preferred node, and a node that can
never take it (an upgrade ahead of it there, a GitHub slot) never strands it. A job sent with
`--on <node>` (`pinned_worker`) is for that node alone and none of this applies.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from mulebox.common import node_settings as ns
from mulebox.coordinator import store as st
from mulebox.coordinator import workers
from mulebox.coordinator.store import ACTIVE_STATES

GRACE_S = 30.0  # left to a better-ranked node at most this long
HOLD_S = 10.0  # left to a node of the same level at most this long
_ACTIVE = "state IN ({})".format(", ".join(f"'{s.value}'" for s in ACTIVE_STATES))


@dataclass(frozen=True)
class Peer:
    name: str
    offers: frozenset[str]
    free: int


@dataclass
class Choice:
    """What a claiming node knows of the others now (`read`)."""
    worker: str
    free: int
    better: list[Peer] = field(default_factory=list)  # free, ranked above
    peers: list[Peer] = field(default_factory=list)  # free, same level


def read(conn: sqlite3.Connection, worker: str, now: float, priority: str | None,
         free: int) -> Choice:
    """The nodes that could take a job now: online, not paused, running no boosted job, with
    a free slot; `priority` as this node's claim says it, else as stored."""
    rows = workers.listing(conn)
    if priority is None:
        priority = next(((r.get("settings") or {}).get("priority") for r in rows
                         if r["worker"] == worker), None)
    mine = ns.rank(priority)
    choice = Choice(worker, free)
    for row in rows:
        if row["worker"] == worker or not workers.is_online(row, now) or row.get("draining"):
            continue
        held, boosted = conn.execute(
            f"SELECT COUNT(*), MAX(boost) FROM jobs WHERE {_ACTIVE} AND worker = ?",
            (row["worker"],)).fetchone()
        room = (row["slots"] or 0) - held
        if boosted or room < 1:
            continue
        rank = ns.rank((row.get("settings") or {}).get("priority"))
        peer = Peer(row["worker"], frozenset(row["capabilities"]), room)
        if rank > mine:
            choice.better.append(peer)
        elif rank == mine:
            choice.peers.append(peer)
    return choice


def branch_node(conn: sqlite3.Connection, project: str, branch: str | None) -> str | None:
    """The node that ran this branch's last job, so holds its project folder."""
    row = conn.execute("SELECT worker FROM jobs WHERE kind = 'job' AND project = ? AND branch IS ? "
                       "AND worker IS NOT NULL AND started_at IS NOT NULL "
                       "ORDER BY started_at DESC LIMIT 1", (project, branch)).fetchone()
    return row[0] if row else None


def leave_to(conn: sqlite3.Connection, choice: Choice, job: dict[str, Any],
             now: float) -> str | None:
    """Why this node leaves `job` to another one now, or None when it takes it. The first time
    it is left, `deferred_at` is set."""
    if job.get("pinned_worker"):
        return None
    waited = now - (job.get("deferred_at") or now)
    needs = set(job["needs"])
    why = None
    if waited < GRACE_S and any(needs <= p.offers for p in choice.better):
        why = "a node ranked above"
    elif waited < HOLD_S and (fitting := [p for p in choice.peers if needs <= p.offers]):
        holder = branch_node(conn, job["project"], job["branch"])
        if holder != choice.worker:
            if any(p.name == holder for p in fitting):
                why = f"{holder}, which holds the branch"
            elif any(p.free > choice.free for p in fitting):
                why = "a node with more free slots"
    if why is not None and job.get("deferred_at") is None:
        st.update_job(conn, job["job_id"], deferred_at=now)
    return why
