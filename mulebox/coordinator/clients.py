"""The laptops that send jobs: the mulebox each last ran, and the state of its agent skill.

Every `submit` says it (`client_version`, `skill`), and the newest word per client is kept, so
the dashboard can warn when a laptop and the build machine are out of step (dashboard/notices.py).
A client older than 0.83.0 says neither and is simply not listed. `client` is the laptop's host
name, as on its jobs.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.versions import parse
from mulebox.coordinator.errors import BadRequest

SKILL_STATES = ("current", "out_of_date", "none")
RECENT_DAYS = 14  # a laptop not seen for longer is left out: it may be gone
TABLE = """
CREATE TABLE IF NOT EXISTS clients (
    client TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    skill TEXT NOT NULL,
    seen_at REAL NOT NULL
)"""


def fields(body: dict[str, Any]) -> tuple[str, str] | None:
    """(version, skill) from a submit body; None when it says neither (an older client)."""
    version, skill = body.get("client_version"), body.get("skill", "none")
    if version is None:
        return None
    if parse(version) is None and not (isinstance(version, str) and 0 < len(version) <= 40):
        raise BadRequest("field 'client_version' must be a version")
    if skill not in SKILL_STATES:
        raise BadRequest(f"field 'skill' must be one of {', '.join(SKILL_STATES)}")
    return version, skill


def seen(conn: sqlite3.Connection, client: str, said: tuple[str, str], now: float) -> None:
    conn.execute("INSERT INTO clients (client, version, skill, seen_at) VALUES (?, ?, ?, ?) "
                 "ON CONFLICT(client) DO UPDATE SET version = excluded.version, "
                 "skill = excluded.skill, seen_at = excluded.seen_at",
                 (client, said[0], said[1], now))


def recent(conn: sqlite3.Connection, now: float) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM clients WHERE seen_at >= ? ORDER BY client",
                        (now - RECENT_DAYS * 86400.0,))
    return [dict(row) for row in rows]
