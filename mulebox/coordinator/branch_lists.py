"""Which branches the dev machines still have, so nodes can remove the folders of gone ones
(design.md, Disk use and cleanup on its own).

Every job's `submit` carries `branches`, the repository's own branches on the dev machine that
sent it (client/gitinfo.py); `seen` keeps the newest list per project and dev machine in
`project_branches` (schema 26, its table in migrate.py).

A branch is **gone** when every dev machine that ran a job on it has sent a list since that
job, and none of those lists, nor any other recent one of the project, has it. A dev machine on
an older mulebox sends no list, so its branches are never judged; a list older than the
branch's last job from that machine says nothing about it either.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.coordinator.clients import RECENT_DAYS
from mulebox.coordinator.errors import BadRequest

MAX_NAMES = 5000
MAX_NAME = 250
HISTORY_DAYS = 365  # branches with a job this recent are judged


def checked(body: dict[str, Any]) -> list[str] | None:
    """A submit's `branches`, or None when it has none (an older client, or git could not say)."""
    value = body.get("branches")
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) > MAX_NAMES
            or not all(isinstance(n, str) and 0 < len(n) <= MAX_NAME for n in value)):
        raise BadRequest(f"field 'branches' must be a list of up to {MAX_NAMES} branch names")
    return value


def seen(conn: sqlite3.Connection, project: str, client: str, names: list[str],
         now: float) -> None:
    conn.execute("INSERT INTO project_branches (project, client, branches, seen_at) "
                 "VALUES (?, ?, ?, ?) ON CONFLICT(project, client) DO UPDATE SET "
                 "branches = excluded.branches, seen_at = excluded.seen_at",
                 (project, client, json.dumps(sorted(set(names))), now))


def gone(conn: sqlite3.Connection, now: float) -> dict[str, list[str]]:
    """Per project, its branches no dev machine has any more."""
    lists: dict[str, dict[str, tuple[set[str], float]]] = {}
    for row in conn.execute("SELECT project, client, branches, seen_at FROM project_branches "
                            "WHERE seen_at >= ?", (now - RECENT_DAYS * 86400.0,)):
        lists.setdefault(row["project"], {})[row["client"]] = (
            set(json.loads(row["branches"])), row["seen_at"])
    if not lists:
        return {}
    runs: dict[tuple[str, str], dict[str, float]] = {}
    marks = ", ".join("?" * len(lists))
    for row in conn.execute(
            "SELECT project, branch, client, MAX(created_at) AS last FROM jobs WHERE kind = 'job' "
            f"AND branch IS NOT NULL AND project IN ({marks}) AND created_at >= ? "
            "GROUP BY project, branch, client", (*lists, now - HISTORY_DAYS * 86400.0)):
        runs.setdefault((row["project"], row["branch"]), {})[row["client"]] = row["last"]
    out: dict[str, list[str]] = {}
    for (project, branch), by_client in sorted(runs.items()):
        known = lists[project]
        if any(branch in names for names, _ in known.values()):
            continue
        if all(client in known and known[client][1] >= last
               for client, last in by_client.items()):
            out.setdefault(project, []).append(branch)
    return out
