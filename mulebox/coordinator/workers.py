"""The coordinator's record of workers, kept apart from jobs (store.py).

`last_seen` is refreshed by a worker's claims, which only happen while it has a free slot,
and by its job heartbeats, every 3 s while it does not. So a busy worker stays seen.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.common import disk

OFFLINE_AFTER_S = 15.0  # workers poll every 1 s, or heartbeat every 3 s while busy


def upsert(conn: sqlite3.Connection, worker: str, capabilities: list[str],
           free_slots: int, now: float, slots: int | None = None,
           toolchains: dict[str, list[str]] | None = None, version: str | None = None,
           disk_free: int | None = None) -> None:
    """Record a worker seen at `now`, and what it told of `slots`, `toolchains`, `version` and
    `disk_free`."""
    conn.execute(
        "INSERT INTO workers (worker, capabilities, free_slots, last_seen, slots, toolchains, "
        "version, disk_free) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (worker) DO UPDATE SET capabilities = excluded.capabilities, "
        "free_slots = excluded.free_slots, last_seen = excluded.last_seen, "
        "slots = COALESCE(excluded.slots, workers.slots), "
        "toolchains = COALESCE(excluded.toolchains, workers.toolchains), "
        "version = COALESCE(excluded.version, workers.version), "
        "disk_free = COALESCE(excluded.disk_free, workers.disk_free)",
        (worker, json.dumps(sorted(capabilities)), free_slots, now, slots,
         None if toolchains is None else json.dumps(toolchains, sort_keys=True), version,
         disk_free),
    )


def touch(conn: sqlite3.Connection, worker: str | None, now: float) -> None:
    """Note that `worker` is alive; a name the store does not know changes nothing."""
    conn.execute("UPDATE workers SET last_seen = ? WHERE worker = ?", (now, worker))


def is_online(worker: dict[str, Any], now: float) -> bool:
    return now - worker["last_seen"] <= OFFLINE_AFTER_S


def _decoded(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["capabilities"] = json.loads(data["capabilities"])
    tools = data.get("toolchains")  # absent in a read-only view of a store not yet upgraded
    data["toolchains"] = json.loads(tools) if tools else None
    return data


def get(conn: sqlite3.Connection, worker: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM workers WHERE worker = ?", (worker,)).fetchone()
    return _decoded(row) if row is not None else None


def listing(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Every known worker, by name."""
    return [_decoded(row) for row in conn.execute("SELECT * FROM workers ORDER BY worker")]


def report(worker: dict[str, Any], now: float) -> dict[str, Any]:
    """One entry of a `machines_ok` reply."""
    return {"worker": worker["worker"], "online": is_online(worker, now),
            "capabilities": worker["capabilities"], "toolchains": worker["toolchains"],
            "version": worker.get("version"), "slots": worker["slots"],
            "disk_free": worker.get("disk_free")}


def low_disks(conn: sqlite3.Connection, now: float) -> list[dict[str, Any]]:
    """Online workers short of space, for whoever is about to give them work."""
    return [{"worker": row["worker"], "free": row.get("disk_free")} for row in listing(conn)
            if is_online(row, now) and disk.is_low(row.get("disk_free"))]
