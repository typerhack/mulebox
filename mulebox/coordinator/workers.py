"""The coordinator's record of workers, kept apart from jobs (store.py).

`last_seen` is refreshed by a worker's claims, which only happen while it has a free slot,
and by its job heartbeats, every 3 s while it does not. So a busy worker stays seen.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

OFFLINE_AFTER_S = 15.0  # workers poll every 1 s, or heartbeat every 3 s while busy


def upsert(conn: sqlite3.Connection, worker: str, capabilities: list[str],
           free_slots: int, now: float, slots: int | None = None) -> None:
    """Record a worker seen at `now`; `slots` is its total slot count when known."""
    conn.execute(
        "INSERT INTO workers (worker, capabilities, free_slots, last_seen, slots) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (worker) DO UPDATE SET capabilities = excluded.capabilities, "
        "free_slots = excluded.free_slots, last_seen = excluded.last_seen, "
        "slots = COALESCE(excluded.slots, workers.slots)",
        (worker, json.dumps(sorted(capabilities)), free_slots, now, slots),
    )


def touch(conn: sqlite3.Connection, worker: str | None, now: float) -> None:
    """Note that `worker` is alive; a name the store does not know changes nothing."""
    conn.execute("UPDATE workers SET last_seen = ? WHERE worker = ?", (now, worker))


def is_online(worker: dict[str, Any], now: float) -> bool:
    return now - worker["last_seen"] <= OFFLINE_AFTER_S


def _decoded(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["capabilities"] = json.loads(data["capabilities"])
    return data


def get(conn: sqlite3.Connection, worker: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM workers WHERE worker = ?", (worker,)).fetchone()
    return _decoded(row) if row is not None else None


def listing(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every known worker, by name."""
    return [_decoded(row) for row in conn.execute("SELECT * FROM workers ORDER BY worker")]
