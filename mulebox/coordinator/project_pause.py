"""Pause whole projects: none of their jobs or GitHub runs starts while the rest of the queue goes on
(`mulebox project pause|resume|paused`, docs/install.md, Steering jobs and machines).

A paused project's waiting jobs keep their place and say why; what already runs finishes. A
pause ends by itself after its minutes (MAX_MINUTES at most), so a forgotten one cannot stop a
project for good. Stored in `meta` like the other holds (holds.py), so `queue.claim` and
`reservations.try_grant` see it in the transaction that starts a job.
"""

from __future__ import annotations

import sqlite3
import time

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest

_PREFIX = "pause:"
DEFAULT_MINUTES = 60
MAX_MINUTES = 24 * 60


def paused(conn: sqlite3.Connection, now: float) -> dict[str, float]:
    """Paused project -> when its pause ends."""
    rows = conn.execute("SELECT key, value FROM meta WHERE key LIKE ?", (f"{_PREFIX}%",))
    return {row["key"][len(_PREFIX):]: float(row["value"]) for row in rows
            if float(row["value"]) > now}


def reason(project: str, until: float) -> str:
    return (f"project {project} is paused until {time.strftime('%H:%M', time.localtime(until))}; "
            f"`mulebox project resume {project}` lets it go on")


def control(req: Request) -> Message:
    action = v.text(req.body, "action")
    if action not in ("pause", "resume", "list"):
        raise BadRequest("field 'action' must be one of pause, resume, list")
    projects = req.body.get("projects") or []
    if action != "list" and (not isinstance(projects, list) or not projects
                             or not all(isinstance(p, str) and p for p in projects)):
        raise BadRequest("field 'projects' must be a list of project names")
    minutes = v.integer(req.body, "minutes", DEFAULT_MINUTES, 1, MAX_MINUTES)
    with req.store.write() as conn:
        for project in projects if action != "list" else ():
            if action == "pause":
                conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                             (f"{_PREFIX}{project}", str(req.now + minutes * 60)))
            else:
                conn.execute("DELETE FROM meta WHERE key = ?", (f"{_PREFIX}{project}",))
        now_paused = paused(conn, req.now)
    return req.reply(MessageType.PROJECT_PAUSE_OK, {"paused": now_paused})
