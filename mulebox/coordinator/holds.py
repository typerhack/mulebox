"""A project held still while its folder on the build machine is removed.

A hold is a row in `meta`, so `queue.claim` sees it in the transaction that picks a job and a job
cannot start in the folder being removed. Queued jobs wait behind it. A hold ends by itself, so a
killed command cannot stop a project for good.
"""

import sqlite3

from mulebox.common.protocol import JobState
from mulebox.coordinator.errors import Conflict
from mulebox.coordinator.store import ACTIVE_STATES, Store

HOLD_S = 900.0
_PREFIX = "hold:"


def held(conn: sqlite3.Connection, now: float) -> set[str]:
    """Projects no job may start on now."""
    rows = conn.execute("SELECT key, value FROM meta WHERE key LIKE ?", (f"{_PREFIX}%",))
    return {row["key"][len(_PREFIX):] for row in rows if float(row["value"]) > now}


def take(store: Store, project: str, now: float) -> None:
    """Hold `project`, or raise Conflict while one of its jobs is on a machine."""
    marks = ", ".join("?" for _ in ACTIVE_STATES)
    states = [JobState(state).value for state in ACTIVE_STATES]
    with store.write() as conn:
        row = conn.execute(f"SELECT job_id FROM jobs WHERE project = ? AND state IN ({marks}) "
                           "LIMIT 1", (project, *states)).fetchone()
        if row is not None:
            raise Conflict(f"{project} has a job running ({row['job_id']}); try again after it")
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                     (f"{_PREFIX}{project}", str(now + HOLD_S)))


def release(store: Store, project: str) -> None:
    with store.write() as conn:
        conn.execute("DELETE FROM meta WHERE key = ?", (f"{_PREFIX}{project}",))
