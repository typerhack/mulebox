"""`mulebox project reset` and `clean` on every node (design.md, Project folders; M25.4).

A project's folders are on each node that ran its jobs, and the dev machine reaches only the
coordinator. So the client asks the coordinator (`project_order`), which keeps one order per
online node in `project_orders` (schema 24, its table in migrate.py); each worker gets its orders with its next claim or
heartbeat (`hand_out`), runs them (worker/orders.py) and answers `order_done` with what it
printed. The client reads the group (`project_order` with `group`) until every node answered.

- `reset --yes` holds the project (holds.py) for the whole group: refused while one of its jobs
  runs anywhere, and no job of it starts on any node until every order is done or `ANSWER_S`
  passed (a hold ends by itself after `holds.HOLD_S` too); with the last answer the
  coordinator's upload base of the project goes.
- `clean` takes no hold: each node skips the branches it runs a job in, and takes no new job
  while it cleans. The branch history it needs (projects.branches) goes in the order.
- An order no node answered in `ANSWER_S` counts as lost: the node may be on an older mulebox.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import holds, projects, workers
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest

ANSWER_S = 300.0
ACTIONS = ("reset", "clean")


def _body(req: Request) -> dict[str, Any]:
    action = v.text(req.body, "action")
    if action not in ACTIONS:
        raise BadRequest(f"action must be one of {', '.join(ACTIONS)}")
    body: dict[str, Any] = {"action": action, "yes": v.flag(req.body, "yes")}
    if action == "reset":
        body.update(project=v.text(req.body, "project"), branch=v.text(req.body, "branch", None),
                    caches=v.flag(req.body, "caches"))
    else:
        body["days"] = v.integer(req.body, "days", 14, 0, 3650)
    return body


def control(req: Request) -> Message:
    if (group := v.text(req.body, "group", None)) is not None:
        return req.reply(MessageType.PROJECT_ORDER_OK, read(req.store, group, req.now))
    body = _body(req)
    holding = body["action"] == "reset" and body["yes"]
    if holding:
        holds.take(req.store, body["project"], req.now)  # Conflict while a job of it runs
    group = new_id("grp")
    with req.store.write() as conn:
        if body["action"] == "clean":
            body["used"] = {project: {branch or "": when for branch, when in seen.items()}
                            for project, seen in projects.branches(conn).items()}
        rows = workers.listing(conn)
        online = [w["worker"] for w in rows if workers.is_online(w, req.now)]
        for worker in online:
            conn.execute("INSERT INTO project_orders (order_id, grp, worker, body, created_at) "
                         "VALUES (?, ?, ?, ?, ?)",
                         (new_id("ord"), group, worker, json.dumps(body), req.now))
    if holding and not online:
        holds.release(req.store, body["project"])
    offline = sorted(w["worker"] for w in rows if w["worker"] not in online)
    return req.reply(MessageType.PROJECT_ORDER_OK,
                     {"group": group, "nodes": online, "offline": offline, "done": not online})


def hand_out(conn: sqlite3.Connection, worker: str | None, now: float) -> dict[str, Any]:
    """The orders waiting for `worker`, for a claim's or heartbeat's reply; marked taken."""
    if worker is None:
        return {}
    rows = conn.execute("SELECT order_id, body FROM project_orders WHERE worker = ? AND "
                        "taken_at IS NULL AND created_at > ?", (worker, now - ANSWER_S)).fetchall()
    for row in rows:
        conn.execute("UPDATE project_orders SET taken_at = ? WHERE order_id = ?",
                     (now, row["order_id"]))
    return {"orders": [{"order_id": row["order_id"], **json.loads(row["body"])}
                       for row in rows]} if rows else {}


def done(req: Request) -> Message:
    """A worker's answer to one order."""
    order_id = v.text(req.body, "order_id")
    with req.store.write() as conn:
        row = conn.execute("SELECT grp, body FROM project_orders WHERE order_id = ?",
                           (order_id,)).fetchone()
        if row is None:
            raise BadRequest(f"no order {order_id}")
        conn.execute("UPDATE project_orders SET done_at = ?, exit_code = ?, output = ? "
                     "WHERE order_id = ? AND done_at IS NULL",
                     (req.now, v.integer(req.body, "exit_code", 0), str(req.body.get("output")
                                                                       or "")[:65536], order_id))
    group = read(req.store, row["grp"], req.now)  # the last answer ends a hold
    body = json.loads(row["body"])
    if group["done"] and body["action"] == "reset" and body["yes"] and not body["branch"]:
        req.staging.remove_base(body["project"])  # what deltas were sent against
    return req.reply(MessageType.ORDER_DONE_OK, {})


def read(store: Any, group: str, now: float) -> dict[str, Any]:
    """Each node's answer so far; `done` once every node answered or `ANSWER_S` passed. A done
    group of `reset --yes` lets its project go, and the upload base with it."""
    with store.read() as conn:
        rows = conn.execute("SELECT * FROM project_orders WHERE grp = ? ORDER BY worker",
                            (group,)).fetchall()
    if not rows:
        raise BadRequest(f"no order group {group}")
    answers = [{"node": row["worker"], "output": row["output"], "exit_code": row["exit_code"],
                "answered": row["done_at"] is not None,
                "lost": row["done_at"] is None and now - row["created_at"] > ANSWER_S}
               for row in rows]
    finished = all(a["answered"] or a["lost"] for a in answers)
    body = json.loads(rows[0]["body"])
    if finished and body["action"] == "reset" and body["yes"]:
        holds.release(store, body["project"])
    return {"group": group, "answers": answers, "done": finished, "action": body["action"]}
