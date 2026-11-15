"""Every change of a node's setting, kept for the owner to read back (design.md, Agents asking
for more space): old and new value, who asked and why, who confirmed, when the node took it.

`setting_changes` (schema 27, its table in migrate.py as SETTING_CHANGES). One row per change: by the owner in the
settings window or with `mulebox machine config` (`how` "owner"), an agent's request answered
("approved", "approved_other", "declined", where a decline keeps the old value), applied without
asking under the Agents option "allow" ("allowed"), an undo ("undo"), and a change of the Agents
option itself (`node` NULL, `setting` "agents"), so a later change with no confirmer is explained.
`in_force_at` is set when the node reports the new value (node_settings.settle).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

HOWS = ("owner", "approved", "approved_other", "declined", "allowed", "undo", "agents")
KEEP = 2000
MAX_ROWS = 500


def _text(value: Any) -> str | None:
    return None if value is None else json.dumps(value)


def record(conn: sqlite3.Connection, *, node: str | None, setting: str, old: Any, new: Any,
           how: str, at: float, asked: dict[str, Any] | None = None, by: str | None = None,
           undo_of: str | None = None) -> str:
    assert how in HOWS, how
    change_id = "chg-" + uuid.uuid4().hex[:12]
    conn.execute("INSERT INTO setting_changes (change_id, node, setting, old, new, how, asked, by, "
                 "at, undo_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (change_id, node, setting, _text(old), _text(new), how,
                  json.dumps(asked, sort_keys=True) if asked else None, by, at, undo_of))
    conn.execute("DELETE FROM setting_changes WHERE change_id NOT IN (SELECT change_id FROM "
                 "setting_changes ORDER BY at DESC LIMIT ?)", (KEEP,))
    return change_id


def in_force(conn: sqlite3.Connection, node: str, settings: dict[str, Any], now: float) -> None:
    """The node now reports these values: the changes that set them are in force."""
    for setting, value in settings.items():
        conn.execute("UPDATE setting_changes SET in_force_at = ? WHERE node = ? AND setting = ? "
                     "AND in_force_at IS NULL AND new = ? AND how != 'declined'",
                     (now, node, setting, _text(value)))


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["change_id"], "node": row["node"], "setting": row["setting"],
            "old": None if row["old"] is None else json.loads(row["old"]),
            "new": None if row["new"] is None else json.loads(row["new"]),
            "how": row["how"], "asked": json.loads(row["asked"]) if row["asked"] else None,
            "by": row["by"], "at": row["at"], "in_force_at": row["in_force_at"],
            "undo_of": row["undo_of"]}


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """The newest changes, newest first, each with `undoable`: it is the node's latest change of
    that setting, it changed a value, and nothing undid it."""
    rows = [_row(row) for row in conn.execute(
        "SELECT * FROM setting_changes ORDER BY at DESC LIMIT ?",
        (max(1, min(limit, MAX_ROWS)),)).fetchall()]
    return [{**row, "undoable": undoable(conn, row)} for row in rows]


def get(conn: sqlite3.Connection, change_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM setting_changes WHERE change_id = ?", (change_id,)).fetchone()
    return None if row is None else _row(row)


def undoable(conn: sqlite3.Connection, change: dict[str, Any]) -> bool:
    if change["how"] in ("declined", "undo", "agents") or change["old"] == change["new"]:
        return False
    if conn.execute("SELECT 1 FROM setting_changes WHERE undo_of = ?", (change["id"],)).fetchone():
        return False
    latest = conn.execute("SELECT change_id FROM setting_changes WHERE node IS ? AND setting = ? "
                          "AND how != 'declined' ORDER BY at DESC LIMIT 1",
                          (change["node"], change["setting"])).fetchone()
    return latest is not None and latest["change_id"] == change["id"]
