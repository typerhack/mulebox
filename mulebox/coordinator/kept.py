"""Failed jobs a node keeps for a rerun (docs/design.md, Rerun from the failed stage).

A worker says what it keeps with every claim and heartbeat (`kept`: the job id, how many
seconds are left, the memory its containers held), and that list replaces the one stored in
`workers.kept` (schema 35), on this machine's clock. What a node no longer lists is gone, so a
worker that restarted, or an older one that keeps nothing, reads as keeping nothing. Kept jobs
hold no slot; their memory counts as used room (sizes.py).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

MAX_KEPT = 64  # a list longer than any node's slots is not a worker's


def _entry(item: Any, now: float) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not isinstance(item.get("job_id"), str):
        return None
    left, memory = item.get("left_s"), item.get("memory")
    if not isinstance(left, (int, float)) or isinstance(left, bool) or left <= 0:
        return None
    if not isinstance(memory, int) or isinstance(memory, bool) or memory < 0:
        memory = 0
    return {"job_id": item["job_id"], "until": round(now + float(left), 3), "memory": memory}


def save(conn: sqlite3.Connection, worker: str, body: dict[str, Any], now: float) -> None:
    """Keep a claim's or heartbeat's `kept`; a body without it leaves the stored list alone,
    as a runner slot's heartbeat comes from the runner supervisor, which keeps nothing."""
    items = body.get("kept")
    if not isinstance(items, list):
        return
    entries = [e for e in (_entry(item, now) for item in items[:MAX_KEPT]) if e is not None]
    conn.execute("UPDATE workers SET kept = ? WHERE worker = ?",
                 (json.dumps(entries, sort_keys=True), worker))


def add(conn: sqlite3.Connection, worker: str, job_id: str, said: Any, now: float) -> None:
    """A result's `kept` (left_s, memory): the job is kept from now, before the worker's next
    claim lists it, so the client hears it with the result."""
    entry = _entry({**said, "job_id": job_id}, now) if isinstance(said, dict) else None
    if entry is None:
        return
    row = conn.execute("SELECT kept FROM workers WHERE worker = ?", (worker,)).fetchone()
    entries = [e for e in of_worker(dict(row) if row else None, now) if e["job_id"] != job_id]
    conn.execute("UPDATE workers SET kept = ? WHERE worker = ?",
                 (json.dumps([*entries, entry][-MAX_KEPT:], sort_keys=True), worker))


def of_worker(worker: dict[str, Any] | None, now: float) -> list[dict[str, Any]]:
    """What `worker` (a workers row) keeps now, its own expired entries left out."""
    text = (worker or {}).get("kept")
    if not text:
        return []
    try:
        entries = json.loads(text) if isinstance(text, str) else text
    except ValueError:
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("until", 0) > now]


def memory(conn: sqlite3.Connection, worker: str) -> int:
    """Bytes of memory the kept containers on `worker` hold, as it last said: its list is
    replaced with each report, and one past its time stays until the worker has removed it."""
    row = conn.execute("SELECT kept FROM workers WHERE worker = ?", (worker,)).fetchone()
    return sum(int(e.get("memory") or 0) for e in of_worker(dict(row) if row else None, 0.0))


def find(conn: sqlite3.Connection, job_id: str, now: float) -> tuple[str, dict[str, Any]] | None:
    """(the node, its entry) that keeps `job_id`, or None."""
    for row in conn.execute("SELECT worker, kept FROM workers WHERE kept IS NOT NULL"):
        for entry in of_worker(dict(row), now):
            if entry["job_id"] == job_id:
                return row["worker"], entry
    return None


def every(conn: sqlite3.Connection, now: float) -> dict[str, tuple[str, dict[str, Any]]]:
    """Every kept job id, to (its node, its entry)."""
    found: dict[str, tuple[str, dict[str, Any]]] = {}
    for row in conn.execute("SELECT worker, kept FROM workers WHERE kept IS NOT NULL"):
        for entry in of_worker(dict(row), now):
            found[entry["job_id"]] = (row["worker"], entry)
    return found
