"""Agents asking for more space, on the dashboard (interfaces-m2.md, Requests for more space;
design.md, Agents asking for more space).

    GET  /api/asks          {asks, changes, agents, editable}: what waits, the settings history
                            (`?history=N`, 50), the Agents option
    POST /api/asks          {"action": "answer", "approve": true, "node"?, "value"?, "note"?}
                            {"action": "undo", "change": "chg-..."}
                            {"action": "agents", "option": "ask" | "allow"}

What waits and the changes applied without asking in the last day also ride on the machines
panel of the live stream (`asks`, `allowed`), so the strip shows a request within seconds. GET
reads the dashboard's own read-only store. POST needs the controls on and is protected like them
(cancel.check); it goes through the canceller's `mulebox rpc`, so every rule stays in the
coordinator (coordinator/asks_api.py). Who answered is recorded as "the dashboard, from
<address>": the dashboard has no sign-in.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from mulebox.client.remote import CoordinatorError, request as message
from mulebox.common.log import get_logger
from mulebox.common.protocol import MessageType
from mulebox.dashboard import cancel, controls, keys

_log = get_logger(__name__)
ACTIONS = ("answer", "undo", "agents")
FIELDS = {"answer": ("approve", "node", "value", "note", "setting"), "undo": ("change",),
          "agents": ("option",)}


async def get_asks(request: web.Request) -> web.Response:
    app = request.app
    try:
        history = max(1, min(int(request.query.get("history", "50")), 500))
    except ValueError:
        raise web.HTTPBadRequest(text="history: a number\n") from None
    body = await asyncio.to_thread(app[keys.DATA].asks, history)
    return web.json_response({**body, "editable": cancel.offered(request)})


async def post_asks(request: web.Request) -> web.Response:
    cancel.check(request)
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="send JSON\n") from None
    action = body.get("action") if isinstance(body, dict) else None
    if action not in ACTIONS:
        raise web.HTTPBadRequest(text=f"action: one of {', '.join(ACTIONS)}\n")
    sent: dict[str, Any] = {key: body[key] for key in FIELDS[action]
                            if body.get(key) is not None}
    sent["by"] = f"the dashboard, from {request.remote or 'an unknown address'}"
    try:
        reply = await request.app[keys.CANCELLER].send(message(MessageType.ASKS, action=action,
                                                               **sent))
    except CoordinatorError as exc:
        raise controls.refused(exc, "machine") from None
    _log.info("asks: %s %s from the dashboard by %s", action, sent, request.remote)
    return web.json_response({**reply.body, "editable": True})


def add_routes(app: web.Application, editable: bool) -> None:
    app.router.add_get("/api/asks", get_asks)
    if editable:
        app.router.add_post("/api/asks", post_asks)
