"""Agents asking for more space on a node, and the owner's answer (design.md, Agents asking for
more space).

From 80% of a node's `max_size` every command from a project tells the agent to ask its user
(client/attention.py). With the user's yes the agent sends `mulebox storage ask`: a request
here, in `setting_asks` (schema 27, its table in migrate.py as SETTING_ASKS). Under the Agents option (`meta`
key `agent_asks`), "ask" (as installed) keeps it waiting for the owner's answer, on the
dashboard or with `mulebox storage approve|decline`; "allow" applies it at once. Either way the
change goes to the node as the owner's own would (node_settings.change) and into the settings
history (setting_changes.py) with who asked, why, and who confirmed.

Several requests for one setting of one node get one answer, by default the largest value
asked. An agent hears the answer in its next command from that project (`news`).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from mulebox.common import storage_policy
from mulebox.coordinator import node_settings, setting_changes, workers
from mulebox.coordinator.errors import BadRequest, Conflict, NotFound

ASKABLE = ("max_size",)
OPTION_KEY = "agent_asks"
OPTIONS = ("ask", "allow")
MAX_REASON = 500
DECLINE_DAYS = 7  # how long the agent hears "declined" in place of "ask your user"


def option(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (OPTION_KEY,)).fetchone()
    return row[0] if row and row[0] in OPTIONS else "ask"


def set_option(conn: sqlite3.Connection, value: str, by: str, now: float) -> None:
    if value not in OPTIONS:
        raise BadRequest(f"agents: one of {', '.join(OPTIONS)}")
    before = option(conn)
    if before == value:
        return
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (OPTION_KEY, value))
    setting_changes.record(conn, node=None, setting="agents", old=before, new=value,
                           how="agents", at=now, by=by)


def _size(value: Any) -> int:
    found = storage_policy.warn_bytes(str(value))
    if found is None:
        raise BadRequest("ask for a size, such as 30GB")
    return found


def node_for(conn: sqlite3.Connection, asked: str | None) -> str:
    """The node asked for, or the one node this can be: the only one, or the only one where
    mulebox holds more than its warning size."""
    names = [row["worker"] for row in workers.listing(conn)]
    if asked:
        if asked not in names:
            raise NotFound(f"no machine {asked!r}", error_code="node.unknown")
        return asked
    from mulebox.coordinator import storage
    heavy = [row["worker"] for row in storage.heavy(conn, 0.0, online=False)]
    if len(names) == 1 or len(heavy) == 1:
        return names[0] if len(names) == 1 else heavy[0]
    raise BadRequest(f"say which node: --node, one of {', '.join(names) or 'none yet'}")


def ask(conn: sqlite3.Connection, body: dict[str, Any], now: float) -> dict[str, Any]:
    setting = str(body.get("setting") or "max_size")
    if setting not in ASKABLE:
        raise BadRequest(f"an agent may ask for {', '.join(ASKABLE)} only")
    reason = str(body.get("reason") or "").strip()
    if not reason:
        raise BadRequest("say why: --reason, in a sentence the user reads")
    node = node_for(conn, body.get("node"))
    value = storage_policy.check(setting, str(body.get("value") or ""))
    now_value = node_settings.values(conn, node).get(setting)
    current = storage_policy.warn_bytes(str(now_value)) if now_value else None
    if current is None:
        raise Conflict(f"{node} has no limit on mulebox's space: nothing to ask for")
    if _size(value) <= current:
        raise Conflict(f"{node} already lets mulebox use {now_value}; ask for more than that")
    row = {"id": "ask-" + uuid.uuid4().hex[:12], "node": node, "setting": setting,
           "value": value, "reason": reason[:MAX_REASON], "project": body.get("project"),
           "job_id": body.get("job_id"), "client": body.get("client"), "asked_at": now}
    conn.execute("INSERT INTO setting_asks (ask_id, node, setting, value, reason, project, job_id, "
                 "client, asked_at, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'waiting')",
                 (row["id"], node, setting, json.dumps(value), row["reason"], row["project"],
                  row["job_id"], row["client"], now))
    if option(conn) == "allow":
        _apply(conn, node, setting, value, "allowed", [_get(conn, row["id"])], None, None, now)
    return _get(conn, row["id"])


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["ask_id"], "node": row["node"], "setting": row["setting"],
            "value": json.loads(row["value"]), "reason": row["reason"], "project": row["project"],
            "job_id": row["job_id"], "client": row["client"], "asked_at": row["asked_at"],
            "state": row["state"], "answer": json.loads(row["answer"]) if row["answer"] else None,
            "change_id": row["change_id"]}


def _get(conn: sqlite3.Connection, ask_id: str) -> dict[str, Any]:
    return _row(conn.execute("SELECT * FROM setting_asks WHERE ask_id = ?", (ask_id,)).fetchone())


def waiting(conn: sqlite3.Connection, node: str | None = None) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM setting_asks WHERE state = 'waiting' AND (? IS NULL OR "
                        "node = ?) ORDER BY asked_at", (node, node)).fetchall()
    return [_row(row) for row in rows]


def _apply(conn: sqlite3.Connection, node: str, setting: str, value: Any, how: str,
           asks: list[dict[str, Any]], note: str | None, by: str | None, now: float) -> str:
    old = node_settings.values(conn, node).get(setting)
    if how != "declined":
        node_settings.change(conn, node, {setting: value}, now)
    largest = max(asks, key=lambda item: _size(item["value"]))["value"]
    asked = {"value": largest, "note": note,
             "asks": [{key: item[key] for key in ("value", "reason", "project", "job_id", "client",
                                                  "asked_at")} for item in asks]}
    change_id = setting_changes.record(
        conn, node=node, setting=setting, old=old, new=old if how == "declined" else value,
        how=how, at=now, asked=asked, by=by)
    state = {"declined": "declined", "allowed": "applied"}.get(how, "approved")
    answer = json.dumps({"value": None if how == "declined" else value, "note": note, "by": by,
                         "at": now})
    conn.executemany("UPDATE setting_asks SET state = ?, answer = ?, change_id = ? WHERE ask_id = ?",
                     [(state, answer, change_id, item["id"]) for item in asks])
    return change_id


def answer(conn: sqlite3.Connection, node: str | None, setting: str, approve: bool,
           value: Any, note: str | None, by: str, now: float) -> str:
    """Answer every request waiting for `setting` of `node` (the only node with one when None);
    the id of the change in the settings history."""
    found = waiting(conn, node)
    nodes = sorted({item["node"] for item in found if item["setting"] == setting})
    if not nodes:
        raise NotFound(f"no request waits{f' for {node}' if node else ''}")
    if len(nodes) > 1:
        raise BadRequest(f"requests wait for {', '.join(nodes)}: say which node")
    asks = [item for item in found if item["node"] == nodes[0] and item["setting"] == setting]
    largest = max(asks, key=lambda item: _size(item["value"]))["value"]
    if not approve:
        return _apply(conn, nodes[0], setting, None, "declined", asks, note, by, now)
    chosen = largest if value is None else storage_policy.check(setting, str(value))
    how = "approved" if _size(chosen) == _size(largest) else "approved_other"
    return _apply(conn, nodes[0], setting, chosen, how, asks, note, by, now)


def undo(conn: sqlite3.Connection, change_id: str, by: str, now: float) -> str:
    change = setting_changes.get(conn, change_id)
    if change is None:
        raise NotFound(f"no change {change_id!r} in the settings history")
    if not setting_changes.undoable(conn, change):
        raise Conflict("only a node's latest change of a setting can be undone, once")
    node_settings.change(conn, change["node"], {change["setting"]: change["old"]}, now)
    return setting_changes.record(conn, node=change["node"], setting=change["setting"],
                                  old=change["new"], new=change["old"], how="undo", at=now,
                                  by=by, undo_of=change_id)


def state_of(conn: sqlite3.Connection, node: str, now: float) -> dict[str, Any]:
    """For the agent's notice about a node: a request waiting, or one declined lately."""
    found = [item for item in waiting(conn, node) if item["setting"] == "max_size"]
    if found:
        return {"asked": {"value": found[-1]["value"], "at": found[-1]["asked_at"]}}
    row = conn.execute("SELECT * FROM setting_asks WHERE node = ? AND state = 'declined' AND "
                       "asked_at > ? ORDER BY asked_at DESC LIMIT 1",
                       (node, now - DECLINE_DAYS * 86400)).fetchone()
    if row is None:
        return {}
    item = _row(row)
    return {"declined": {"value": item["value"], "note": (item["answer"] or {}).get("note"),
                         "at": (item["answer"] or {}).get("at")}}


def news(conn: sqlite3.Connection, project: str, now: float) -> list[dict[str, Any]]:
    """This project's requests answered since its agent last heard; telling marks them told."""
    rows = [_row(row) for row in conn.execute(
        "SELECT * FROM setting_asks WHERE project = ? AND state != 'waiting' AND told_at IS NULL "
        "ORDER BY asked_at", (project,)).fetchall()]
    conn.executemany("UPDATE setting_asks SET told_at = ? WHERE ask_id = ?",
                     [(now, item["id"]) for item in rows])
    return rows


ALLOWED_TOLD_S = 86400  # a change made without asking is told in the strip for a day


def live(conn: sqlite3.Connection, now: float) -> dict[str, Any]:
    """For the dashboard's live machines panel: what waits, and what was applied without asking
    in the last day, for the strip."""
    allowed = [row for row in setting_changes.recent(conn, 50)
               if row["how"] == "allowed" and row["at"] > now - ALLOWED_TOLD_S]
    return {"asks": waiting(conn), "allowed": allowed}


def body(conn: sqlite3.Connection, history: int = 50) -> dict[str, Any]:
    """The `asks_ok` reply and the dashboard's `/api/asks`: what waits, the history, the option."""
    return {"asks": waiting(conn), "changes": setting_changes.recent(conn, history),
            "agents": option(conn)}
