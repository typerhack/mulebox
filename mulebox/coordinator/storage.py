"""What mulebox holds on each node, and the user's keep marks (design.md, Project folders, Disk
use and cleanup on its own).

- **Reports**: a worker sends what its last sweep measured (worker/storage_sweep.py) as
  `storage` with a claim or heartbeat, once; `keep_report` stores the last one per node in
  `workers.storage` (schema 25). A report past `MAX_REPORT` bytes is dropped, never cut.
- **Keep marks**: a project, or one branch of it, that no automatic rule removes on any node,
  in `storage_keeps` (schema 25). Every claim's and heartbeat's reply carries them all as
  `storage_keeps`, so a worker always has the current set.
- **Requests**: `storage` reads every node's report with the keep marks and, per project, the
  branch each folder name stands for (from the job history, as a folder is named after its
  branch, worker/project_home.py); `storage_keep` sets or drops a mark.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.common import storage_policy
from mulebox.common.branch_folder import slug
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import branch_lists, projects, setting_asks, storage_history, workers
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request

MAX_REPORT = 4 << 20  # the table: migrate.STORAGE_KEEPS


def keep_report(conn: sqlite3.Connection, worker: str, body: dict[str, Any]) -> None:
    """Store a claim's or heartbeat's `storage`, when it has one that is well formed."""
    report = body.get("storage")
    if not isinstance(report, dict) or not isinstance(report.get("at"), (int, float)):
        return
    text = json.dumps(report, sort_keys=True)
    if len(text) <= MAX_REPORT:
        conn.execute("UPDATE workers SET storage = ? WHERE worker = ?", (text, worker))
        storage_history.add(conn, worker, report)


def keeps(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT project, branch, created_at FROM storage_keeps "
                        "ORDER BY project, branch").fetchall()
    return [{"project": row["project"], "branch": row["branch"] or None,
             "since": row["created_at"]} for row in rows]


def reply_fields(conn: sqlite3.Connection, now: float) -> dict[str, Any]:
    """What every claim's and heartbeat's reply carries for the worker's sweep: the keep marks
    and the branches no dev machine has any more (branch_lists.py)."""
    return {"storage_keeps": [{"project": k["project"], "branch": k["branch"]}
                              for k in keeps(conn)],
            "storage_gone": branch_lists.gone(conn, now)}


def _names(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Per project, the branch each folder name stands for, from the job history."""
    return {project: {slug(branch or None): branch for branch in seen if branch}
            for project, seen in projects.branches(conn).items()}


def body(conn: sqlite3.Connection, now: float, history: int = 50) -> dict[str, Any]:
    """Every node's last report, the keep marks and the folders' branch names: the `storage`
    reply, and the dashboard's `/api/storage` from its own read-only store."""
    stored = {row["worker"]: row["storage"] for row in conn.execute(
        "SELECT worker, storage FROM workers").fetchall()}
    nodes = [{"node": row["worker"], "online": workers.is_online(row, now),
              "version": row.get("version"),
              "report": json.loads(stored[row["worker"]]) if stored.get(row["worker"]) else None}
             for row in workers.listing(conn)]
    return {"nodes": nodes, "keeps": keeps(conn), "branches": _names(conn),
            "history": storage_history.recent(conn, history)}


def heavy(conn: sqlite3.Connection, now: float, online: bool = True) -> list[dict[str, Any]]:
    """Online nodes where mulebox holds more than its warning size, `WARN_SHARE` of the node's
    `max_size` (or, from a node older than 1.30, its own `warn_size`), for every command from
    a project to pass on to the user (client/attention.py), with a request for more space that
    waits or was declined lately (setting_asks.state_of)."""
    out = []
    for row in workers.listing(conn):
        text = conn.execute("SELECT storage FROM workers WHERE worker = ?",
                            (row["worker"],)).fetchone()["storage"]
        if not text or (online and not workers.is_online(row, now)):
            continue
        report = json.loads(text)
        policy = report.get("policy") or {}
        most = storage_policy.warn_bytes(str(policy.get("max_size", "OFF")))
        limit = (int(most * storage_policy.WARN_SHARE) if most is not None
                 else storage_policy.warn_bytes(str(policy.get("warn_size", "OFF"))))
        held = report.get("held")
        if limit is not None and isinstance(held, int) and held > limit:
            out.append({"worker": row["worker"], "held": held, "warn": limit, "max": most,
                        **(setting_asks.state_of(conn, row["worker"], now) if online else {})})
    return out


def read(req: Request) -> Message:
    with req.store.read() as conn:
        return req.reply(MessageType.STORAGE_OK,
                         body(conn, req.now, v.integer(req.body, "history", 50, 1, 500)))


def keep(req: Request) -> Message:
    project = v.text(req.body, "project")
    branch = v.text(req.body, "branch", None)
    on = req.body.get("keep", True) is not False
    with req.store.write() as conn:
        if on:
            conn.execute("INSERT OR IGNORE INTO storage_keeps (project, branch, created_at) "
                         "VALUES (?, ?, ?)", (project, branch or "", req.now))
        else:
            conn.execute("DELETE FROM storage_keeps WHERE project = ? AND branch = ?",
                         (project, branch or ""))
        marks = keeps(conn)
    return req.reply(MessageType.STORAGE_KEEP_OK, {"keeps": marks})
