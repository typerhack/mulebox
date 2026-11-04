"""Every project the coordinator has seen, worked out from its jobs.

There is no project table on purpose. What a project needs lives in its `.mulebox.yml`, and
which projects exist is already in the job history; a registry would be a second copy of
both, and could disagree with them.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# With one MAX(), SQLite takes the bare columns from that row: the project's newest job.
_SQL = ("SELECT project, COUNT(*) AS jobs, MAX(seq), created_at AS last_run, kind, state, "
        "outcome FROM jobs GROUP BY project ORDER BY last_run DESC")


def listing(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [{"project": row["project"], "jobs": row["jobs"], "last_run": row["last_run"],
             "kind": row["kind"], "state": row["state"], "outcome": row["outcome"]}
            for row in conn.execute(_SQL)]
