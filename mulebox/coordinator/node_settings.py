"""A node's settings from afar, and node priority in claims (design.md, Node settings).

The truth is each node's node.toml. The coordinator keeps what a worker last reported
(`workers.settings`: `slots`, `priority`, `dev`, and `error` when a change could not be written) and a
change its owner asked for (`workers.wanted`, since `wanted_at`). The change goes back in the
reply to the worker's next claim or heartbeat (`node_settings`, `node_settings_at`); the worker
writes it and reports, and what it reports clears the values it now has (`settle`).

- `node_settings` request: `worker`, and `slots`, `priority`, `dev` or `cancel: true` (drop what waits);
  with none of them it only reads. `by` says who changed it, for the settings history
  (setting_changes.py): "mulebox machine config" when absent. Refused for a worker that never reported settings (a mulebox
  older than this), so a change is not left waiting for good. Replied `node_settings_ok`, `view`.
- Priority in claims: node_choice.py.
"""

from __future__ import annotations

import json
import sqlite3
import time
from typing import Any

from mulebox.common import node_settings as ns
from mulebox.common import job_size, storage_policy
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import setting_changes, workers
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict, NotFound
from mulebox.coordinator.store import ACTIVE_STATES

MAX_ERROR = 500
_ALWAYS = ("slots", "priority")  # every node that reports settings has these
_SINCE = {"dev": "1.23", "keep_cores": "1.38", "keep_memory": "1.38", "auto_clean": "1.26",
          "docker_clean": "1.26",
          "max_size": "1.26", "slim_hours": "1.29", "min_free": "1.41"}  # the rest: 1.24
_WHAT = {"dev": "dev mode", "keep_cores": "room kept for the owner",
         "keep_memory": "room kept for the owner", **{name: "storage settings" for name in storage_policy.FIELDS},
         "auto_clean": "automatic cleanup switch", "docker_clean": "Docker cleanup",
         "max_size": "space for mulebox", "slim_hours": "folder slimming",
         "min_free": "free space before a rest"}
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
        if "dev" in value:  # a worker older than 1.23 has no dev mode
            out["dev"] = ns.check_dev(value["dev"])
        if "keep_cores" in value:  # nor one older than 1.38 the owner's reserve
            out["keep_cores"] = job_size.check_keep_cores(value["keep_cores"])
        if "keep_memory" in value:
            out["keep_memory"] = job_size.check_keep_memory(value["keep_memory"])
        for name in storage_policy.FIELDS:  # nor one older than 1.24 storage settings
            if name in value:
                out[name] = storage_policy.check(name, value[name])
    except ValueError:
        return None
    error = value.get("error")
    if isinstance(error, str) and error:
        out["error"] = error[:MAX_ERROR]
    return out


def settle(conn: sqlite3.Connection, worker: str | None, settings: dict[str, Any] | None,
           now: float | None = None) -> dict[str, Any]:
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
            setting_changes.in_force(conn, str(worker), {key: settings.get(key) for key in wanted
                                                          if key not in left},
                                     time.time() if now is None else now)
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
        "current": None if settings is None else {  # what an older node has not, left out
            key: settings.get(key, ns.DEFAULTS.get(key)) for key in ns.EDITABLE
            if key in settings or key in _ALWAYS},
        "pending": wanted, "pending_since": worker.get("wanted_at") if wanted else None,
        "error": (settings or {}).get("error") if wanted else None,
        "suggested": ns.suggest_slots(load.get("cores"), (load.get("memory") or {}).get("total")),
        "choices": {"slots": {"min": ns.MIN_SLOTS, "max": ns.MAX_SLOTS},
                    "priority": list(ns.PRIORITIES), "dev": [False, True],
                    "keep_cores": {"min": 0, "max": load.get("cores")},
                    "keep_memory": {"max_gb": _whole_gb(load)},
                    "keep_free": {"max_share": storage_policy.MAX_SHARE},
                    "unused_days": {"min": 1, "max": storage_policy.MAX_DAYS},
                    "keep_latest": [False, True], "auto_clean": [False, True],
                    "docker_clean": [False, True], "warn_share": storage_policy.WARN_SHARE,
                    "max_size": {"off": "off"},
                    "idle_days": {"min": 1, "max": storage_policy.MAX_DAYS},
                    "slim_hours": {"min": 0, "max": storage_policy.MAX_HOURS}},
        "defaults": dict(storage_policy.DEFAULTS),  # what mulebox suggests for storage
    }


def _whole_gb(load: dict[str, Any]) -> int | None:
    """The node's memory in whole decimal GB, the most `keep_memory` a window offers."""
    total = (load.get("memory") or {}).get("total")
    return int(total // 10**9) if isinstance(total, (int, float)) and total > 0 else None


def _changes(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("warn_size") is not None:
        raise BadRequest(f"warn_size is no setting since 1.30: agents are told from "
                         f"{storage_policy.WARN_SHARE:.0%} of max_size; set that instead")
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
    by = v.text(req.body, "by", None) or "mulebox machine config"
    with req.store.write() as conn:
        before = values(conn, name)
        change(conn, name, changes, req.now, drop=drop)
        for key, value in changes.items():  # the settings history (setting_changes.py)
            if before.get(key) != value:
                setting_changes.record(conn, node=name, setting=key, old=before.get(key),
                                       new=value, how="owner", at=req.now, by=by)
        return req.reply(MessageType.NODE_SETTINGS_OK, view(conn, _require(conn, name), req.now))


def values(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    """What a node runs with, with a change that waits for it on top: what a new change replaces."""
    found = _require(conn, name)
    return {**(found.get("settings") or {}), **(found.get("wanted") or {})}


def change(conn: sqlite3.Connection, name: str, changes: dict[str, Any], now: float, *,
           drop: bool = False) -> None:
    """Ask `name` for `changes` (checked), on its next claim or heartbeat; the rules for every
    change from afar, from the owner or an agent's answered request (setting_asks.py)."""
    found = _require(conn, name)
    current = found.get("settings")
    if current is None:
        raise Conflict(f"{name} has not reported its settings: it runs a mulebox older than "
                       "this one, or has not claimed yet; upgrade it first "
                       f"(`mulebox setup {name}`), or edit its node.toml")
    if changes.get("dev") and name == workers.host(conn):
        raise Conflict(f"dev mode is for other nodes: {name} is the coordinator, which every "
                       "job goes through; put a node added with --worker-of in dev mode")
    for key in changes:
        if key not in current and key not in _ALWAYS:
            raise Conflict(f"{name} runs a mulebox older than {_SINCE.get(key, '1.24')}, "
                           f"which has no {_WHAT.get(key, key)}; upgrade it first "
                           f"(`mulebox setup {name}`)")
    wanted = {} if drop else dict(found.get("wanted") or {})
    wanted.update(changes)
    wanted = {key: value for key, value in wanted.items() if current.get(key) != value}
    _keep_wanted(conn, name, wanted, now)
    if "error" in current:  # it was about the change asked before; the worker tries this one
        current = {key: value for key, value in current.items() if key != "error"}
        conn.execute("UPDATE workers SET settings = ? WHERE worker = ?",
                     (json.dumps(current, sort_keys=True), name))


def _require(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    found = workers.get(conn, name)
    if found is None:
        raise NotFound(f"no machine {name!r}; `mulebox machine list` shows them")
    return found
