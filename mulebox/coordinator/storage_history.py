"""Every node's cleanups, kept for the user to read back (design.md, Disk use and cleanup on its
own): when each ran and why, what it removed and how much it freed.

A worker's storage report carries its last sweep as `sweep` (worker/storage_sweep.py); `add`
keeps each one once in `storage_sweeps` (schema 26, its table in migrate.py), the newest
`KEEP` per node.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

KEEP = 1000
MAX_ROWS = 500


def add(conn: sqlite3.Connection, worker: str, report: dict[str, Any]) -> None:
    sweep = report.get("sweep")
    if not isinstance(sweep, dict) or not isinstance(sweep.get("started"), (int, float)):
        return
    conn.execute("INSERT OR IGNORE INTO storage_sweeps (worker, started, body) VALUES (?, ?, ?)",
                 (worker, float(sweep["started"]), json.dumps(sweep, sort_keys=True)))
    conn.execute("DELETE FROM storage_sweeps WHERE worker = ? AND started NOT IN (SELECT started "
                 "FROM storage_sweeps WHERE worker = ? ORDER BY started DESC LIMIT ?)",
                 (worker, worker, KEEP))


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """The newest cleanups of every node, newest first."""
    rows = conn.execute("SELECT worker, body FROM storage_sweeps ORDER BY started DESC LIMIT ?",
                        (max(1, min(limit, MAX_ROWS)),)).fetchall()
    return [{"node": row["worker"], **json.loads(row["body"])} for row in rows]
