"""The `machine` request: drain, resume or remove one worker (`mulebox machine`, docs/install.md).

- `drain`: the worker finishes what it runs and claims no new job; the reply lists `running`, so
  the caller can wait for an empty list. A GitHub runner on it still takes CI jobs: stop the
  runner too (docs/install.md, More machines).
- `resume`: it claims again.
- `remove`: the coordinator forgets it. Refused while it is online, as its next claim would bring
  it back, and while a job runs on it or a CI job waits for it. Its key is taken off by the
  client (`mulebox authorize-worker --remove`), which can reach the coordinator's files.
"""

from __future__ import annotations

import sqlite3

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import workers
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict, NotFound

ACTIONS = ("drain", "resume", "remove")


def running_on(conn: sqlite3.Connection, worker: str) -> list[str]:
    """Unfinished jobs on `worker`, or CI jobs waiting for its runner."""
    rows = conn.execute("SELECT job_id FROM jobs WHERE state != 'finished' "
                        "AND (worker = ? OR pinned_worker = ?) ORDER BY seq", (worker, worker))
    return [row[0] for row in rows]


def machine(req: Request) -> Message:
    name, action = v.text(req.body, "worker"), v.text(req.body, "action")
    if action not in ACTIONS:
        raise BadRequest(f"field 'action' must be one of {', '.join(ACTIONS)}")
    with req.store.write() as conn:
        found = workers.get(conn, name)
        if found is None:
            raise NotFound(f"no machine {name!r}; `mulebox machine list` shows them")
        running = running_on(conn, name)
        if action == "remove":
            if workers.is_online(found, req.now):
                raise Conflict(f"{name} is online; stop it first, on that machine: "
                               "`systemctl --user disable --now mulebox-worker`")
            if running:
                raise Conflict(f"{name} still has {len(running)} job(s): {', '.join(running)}")
            workers.forget(conn, name)
        else:
            workers.set_draining(conn, name, action == "drain")
    return req.reply(MessageType.MACHINE_OK, {"worker": name, "action": action,
                                              "running": running})
