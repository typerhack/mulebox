"""A node's settings from afar, and node priority in claims (design.md, Node settings).

The truth is each node's node.toml. The coordinator keeps what a worker last reported
(`workers.settings`: `slots`, `priority`, and `error` when a change could not be written) and a
change its owner asked for (`workers.wanted`, since `wanted_at`). The change goes back in the
reply to the worker's next claim or heartbeat (`node_settings`, `node_settings_at`); the worker
writes it and reports, and what it reports clears the values it now has (`settle`).

- `node_settings` request: `worker`, and `slots`, `priority` or `cancel: true` (drop what waits);
  with none of them it only reads. Refused for a worker that never reported settings (a mulebox
  older than this), so a change is not left waiting for good. Replied `node_settings_ok`, `view`.
- Priority (`held_back`): a node does not take a job that a node ranked above it could take now;
  a job that waited `GRACE_S` in spite of that goes to whoever claims it.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from mulebox.common import node_settings as ns
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import workers
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict, NotFound
from mulebox.coordinator.store import ACTIVE_STATES

GRACE_S = 30.0
MAX_ERROR = 500
MAX_REPORTED = 4096  # slots a report may say, past the 64 a request may ask
_ACTIVE = "state IN ({})".format(", ".join(f"'{s.value}'" for s in ACTIVE_STATES))


def reported(body: dict[str, Any]) -> dict[str, Any] | None:
    """A claim's or heartbeat's `settings`, or None when absent or not well formed: a report
    must not fail a claim."""
    value = body.get("settings")
    if not isinstance(value, dict):
        return None
    slots = value.get("slots")
    if isinstance(slots, bool) or not isinstance(slots, int) or not 1 <= slots <= MAX_REPORTED:
        return None  # a hand edit may hold more than the 64 asked from afar
    try:
        out: dict[str, Any] = {"slots": slots, "priority": ns.check_priority(value.get("priority"))}
    except ValueError:
        return None
    error = value.get("error")
    if isinstance(error, str) and error:
        out["error"] = error[:MAX_ERROR]
    return out


def settle(conn: sqlite3.Connection, worker: str | None, settings: dict[str, Any] | None
           ) -> dict[str, Any]:
    """Keep what `worker` reported, drop the asked values it now has; for the reply, the change
    still waiting for it (`node_settings`, `node_settings_at`), or nothing."""
    row = conn.execute("SELECT wanted, wanted_at FROM workers WHERE worker = ?",
                       (worker,)).fetchone()
    if row is None:
        return {}
    wanted = json.loads(row["wanted"]) if row["wanted"] else {}
    if settings is not None:
        left = {key: value for key, value in wanted.items() if settings.get(key) != value}
        conn.execute("UPDATE workers SET settings = ?, slots = ? WHERE worker = ?",
                     (json.dumps(settings, sort_keys=True), settings["slots"], worker))
        if left != wanted:
            _keep_wanted(conn, worker, left, row["wanted_at"])
        wanted = left
    return {"node_settings": wanted, "node_settings_at": row["wanted_at"]} if wanted else {}


def _keep_wanted(conn: sqlite3.Connection, worker: str, wanted: dict[str, Any],
                 since: float | None) -> None:
    conn.execute("UPDATE workers SET wanted = ?, wanted_at = ? WHERE worker = ?",
                 (json.dumps(wanted, sort_keys=True) if wanted else None,
                  since if wanted else None, worker))


def _running(conn: sqlite3.Connection, worker: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM jobs WHERE {_ACTIVE} AND worker = ?",
                        (worker,)).fetchone()[0]


def view(conn: sqlite3.Connection, worker: dict[str, Any], now: float) -> dict[str, Any]:
    """What a settings window shows: the values the node has, what waits, the suggestion."""
    settings = worker.get("settings")
    load = worker.get("load") or {}
    wanted = worker.get("wanted") or None
    return {
        "worker": worker["worker"], "online": workers.is_online(worker, now),
        "draining": bool(worker.get("draining")), "version": worker.get("version"),
        "running": _running(conn, worker["worker"]),
        "applies": settings is not None,
        "current": None if settings is None else {key: settings[key] for key in ns.EDITABLE},
        "pending": wanted, "pending_since": worker.get("wanted_at") if wanted else None,
        "error": (settings or {}).get("error") if wanted else None,
        "suggested": ns.suggest_slots(load.get("cores"), (load.get("memory") or {}).get("total")),
        "choices": {"slots": {"min": ns.MIN_SLOTS, "max": ns.MAX_SLOTS},
                    "priority": list(ns.PRIORITIES)},
    }


def _changes(body: dict[str, Any]) -> dict[str, Any]:
    asked = {key: body[key] for key in ns.EDITABLE if body.get(key) is not None}
    try:
        return ns.checked(asked)
    except ValueError as exc:
        raise BadRequest(str(exc)) from None


def request(req: Request) -> Message:
    name = v.text(req.body, "worker")
    changes, drop = _changes(req.body), v.flag(req.body, "cancel")
    if not changes and not drop:
        with req.store.read() as conn:
            return req.reply(MessageType.NODE_SETTINGS_OK, view(conn, _require(conn, name), req.now))
    with req.store.write() as conn:
        found = _require(conn, name)
        current = found.get("settings")
        if current is None:
            raise Conflict(f"{name} has not reported its settings: it runs a mulebox older than "
                           "this one, or has not claimed yet; upgrade it first "
                           f"(`mulebox setup {name}`), or edit its node.toml")
        wanted = {} if drop else dict(found.get("wanted") or {})
        wanted.update(changes)
        wanted = {key: value for key, value in wanted.items() if current.get(key) != value}
        _keep_wanted(conn, name, wanted, req.now)
        if "error" in current:  # it was about the change asked before; the worker tries this one
            current = {key: value for key, value in current.items() if key != "error"}
            conn.execute("UPDATE workers SET settings = ? WHERE worker = ?",
                         (json.dumps(current, sort_keys=True), name))
        return req.reply(MessageType.NODE_SETTINGS_OK, view(conn, _require(conn, name), req.now))


def _require(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    found = workers.get(conn, name)
    if found is None:
        raise NotFound(f"no machine {name!r}; `mulebox machine list` shows them")
    return found


def better_free(conn: sqlite3.Connection, worker: str, now: float,
                priority: str | None = None) -> list[set[str]]:
    """What each node ranked above `worker` (at `priority`, as its claim says, else as stored)
    offers, of those that could take a job now: online, not paused, running no boosted job,
    with a free slot. Empty for a node at the top."""
    rows = workers.listing(conn)
    if priority is None:
        priority = next(((r.get("settings") or {}).get("priority") for r in rows
                         if r["worker"] == worker), None)
    mine = ns.rank(priority)
    found = []
    for row in rows:
        if (row["worker"] == worker or ns.rank((row.get("settings") or {}).get("priority")) <= mine
                or not workers.is_online(row, now) or row.get("draining")):
            continue
        busy = conn.execute(f"SELECT COUNT(*), MAX(boost) FROM jobs WHERE {_ACTIVE} AND worker = ?",
                            (row["worker"],)).fetchone()
        if not busy[1] and (row["slots"] or 0) - busy[0] > 0:
            found.append(set(row["capabilities"]))
    return found


def held_back(job: dict[str, Any], better: list[set[str]], now: float) -> bool:
    """Whether `job` waits for a better node in `better` (better_free) rather than this one."""
    if not better or now - (job.get("queued_at") or now) >= GRACE_S:
        return False
    needs = set(job["needs"])
    return any(needs <= offers for offers in better)
