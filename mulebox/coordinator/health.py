"""A node that rests, on the coordinator's side (design.md, A node that rests).

The worker decides: a resting one claims with no free slot, and leaves a withheld capability out
of its claims (worker/agent_health.py). The coordinator keeps what it reports (`workers.health`,
schema 33) for `mulebox machine list`, a waiting job's reason and node choice; counts a withheld
capability as offered at submit, so a passing fault refuses no job; puts back in line, once, a
job its node could not set up; and hands `mulebox machine check` to the node.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.common import node_health, versions
from mulebox.common.protocol import JobState, Outcome

MAX_RETRIES = 1
RETRY_SINCE = "1.41.0"  # a worker that continues a retried job's log at its offset
CHECK_WAIT_S = 120.0  # an ask not taken by then is dropped (the node went away)


def save(conn: sqlite3.Connection, worker: str | None, body: dict[str, Any]) -> None:
    """Keep the `health` of a claim or heartbeat; a body without the field (an older worker, a
    runner supervisor's heartbeat) changes nothing."""
    if worker is None or "health" not in body:
        return
    report = node_health.checked(body["health"])
    conn.execute("UPDATE workers SET health = ? WHERE worker = ?",
                 (None if report is None else json.dumps(report, sort_keys=True), worker))


def withheld(body: dict[str, Any] | None) -> list[str]:
    """The capabilities a claim's `health` says it leaves out for now."""
    report = node_health.checked((body or {}).get("health"))
    return list((report or {}).get("withheld") or ())


def of(row: dict[str, Any]) -> dict[str, Any] | None:
    """A worker row's health, decoded; None for a healthy or older worker."""
    value = row.get("health")
    if isinstance(value, dict):
        return value
    try:
        return node_health.checked(json.loads(value)) if value else None
    except ValueError:
        return None


def offers(row: dict[str, Any]) -> set[str]:
    """What a node can take jobs for now: its capabilities but those withheld."""
    report = of(row)
    return set(row["capabilities"]) - set((report or {}).get("withheld") or ())


def resting(row: dict[str, Any]) -> bool:
    return bool((of(row) or {}).get("resting"))


def may_take(job: dict[str, Any], version: str | None) -> bool:
    """A job back in line goes only to a worker that continues its log (claim's `log_offset`)."""
    return not job.get("retries") or versions.compare(version, RETRY_SINCE) in (0, 1)


def claim_fields(job: dict[str, Any]) -> dict[str, Any]:
    return {"log_offset": job["log_size"]} if job.get("retries") and job.get("log_size") else {}


def retry(conn: sqlite3.Connection, job: dict[str, Any], body: dict[str, Any],
          outcome: Outcome, exit_code: int | None) -> str | None:
    """Put back in line a job its node could not set up (`node_fault`), once; the note for its
    log, or None when it ends as it is."""
    fault = body.get("node_fault")
    if (not isinstance(fault, str) or not fault or outcome is not Outcome.FAILED
            or exit_code is not None or job["kind"] != "job" or job["cancel_requested"]
            or (job.get("retries") or 0) >= MAX_RETRIES):
        return None
    # Not a transition a worker may ask for (protocol.py): only this path, for this reason.
    moved = conn.execute(
        "UPDATE jobs SET state = ?, worker = NULL, attempt_id = NULL, started_at = NULL, "
        "worker_lease_until = NULL, retries = retries + 1, activity = '{}', active_at = NULL "
        "WHERE job_id = ? AND state = ?", (JobState.QUEUED.value, job["job_id"], job["state"]))
    if moved.rowcount != 1:
        return None
    return (f"mulebox: {fault[:node_health.MAX_TEXT]}. The job goes back in line for another "
            "node, or this one once it is well again; it is not your code\n")


def ask_check(conn: sqlite3.Connection, worker: str, now: float) -> None:
    conn.execute("UPDATE workers SET check_asked = ? WHERE worker = ?", (now, worker))


def hand_out(conn: sqlite3.Connection, worker: str | None, now: float) -> dict[str, Any]:
    """`health_check: true` for a reply to a node asked to check itself, once."""
    row = conn.execute("SELECT check_asked FROM workers WHERE worker = ?", (worker,)).fetchone()
    if row is None or row[0] is None:
        return {}
    conn.execute("UPDATE workers SET check_asked = NULL WHERE worker = ?", (worker,))
    return {"health_check": True} if now - row[0] <= CHECK_WAIT_S else {}


def reason(rows: list[dict[str, Any]], needs: list[str]) -> str | None:
    """Why the nodes for a job take none now, from their health, or None."""
    found = [node_health.reason(row["worker"], of(row)) for row in rows
             if node_health.blocks(of(row), needs)]
    found = [line for line in found if line]
    if not found:
        return None
    names = " ".join(row["worker"] for row in rows)
    return ("; ".join(found) + f". After a fix, `mulebox machine check <node>` ({names}) "
            "lets it take jobs at once")
