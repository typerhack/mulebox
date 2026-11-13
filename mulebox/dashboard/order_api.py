"""The order rules of the line on the dashboard (interfaces-m2.md, HTTP API).

    GET  /api/queue/rules   the rules, their defaults, the levels and the known projects
    POST /api/queue/rules   {"rules": {...}} changes some (maps merge entry by entry, a level of
                            0 removes one), or {"reset": true} brings back the defaults

Reading comes from the read-only store. A change is the `queue_rules` request
`mulebox queue rules` and `mulebox project priority` send, through the canceller's
`mulebox rpc`, so every rule and check stays in the coordinator (coordinator/line_rules.py).
Protected like the other controls (cancel.check); a refused change is 409 with its reason.
"""

from __future__ import annotations

import asyncio

from aiohttp import web

from mulebox.client.remote import CoordinatorError
from mulebox.common.log import get_logger
from mulebox.dashboard import cancel, controls, keys

_log = get_logger(__name__)


async def rules(request: web.Request) -> web.Response:
    return web.json_response(await asyncio.to_thread(request.app[keys.DATA].queue_rules))


async def change(request: web.Request) -> web.Response:
    cancel.check(request)
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="send {\"rules\": {...}} or {\"reset\": true} as JSON\n") from None
    if not isinstance(body, dict) or not (isinstance(body.get("rules"), dict)
                                          or body.get("reset") is True):
        raise web.HTTPBadRequest(text="send {\"rules\": {...}} or {\"reset\": true}\n")
    wanted = {"action": "reset"} if body.get("reset") is True else {"action": "set",
                                                                     "rules": body["rules"]}
    try:
        reply = await request.app[keys.CANCELLER].queue_rules(wanted)
    except CoordinatorError as exc:
        raise controls.refused(exc, "rule") from None
    _log.info("queue rules: %s from the dashboard by %s", wanted["action"], request.remote)
    return web.json_response(reply.body)


def add_routes(app: web.Application, writable: bool) -> None:
    app.router.add_get("/api/queue/rules", rules)
    if writable:
        app.router.add_post("/api/queue/rules", change)
