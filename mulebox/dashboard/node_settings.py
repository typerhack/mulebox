"""A machine's settings window on the dashboard (interfaces-m2.md, Node settings).

    GET  /api/machines/<name>/settings   what it has, what waits, the suggestion, the choices
    POST /api/machines/<name>/settings   {"slots": 3, "priority": "preferred"} or {"cancel": true}

GET reads the dashboard's own read-only store, with the same `view` the coordinator answers
`mulebox machine config` with, plus `editable`: whether this dashboard has its controls on.
POST, only with the controls on and protected like them (cancel.check), sends the same
`node_settings` request as `mulebox machine config` through the canceller's `mulebox rpc`, so
every rule stays in the coordinator (coordinator/node_settings.py); it answers the new view.
A value out of range is 400, a refusal 409 with the coordinator's words, an unknown machine 404.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from mulebox.client.remote import CoordinatorError
from mulebox.common import node_settings as ns
from mulebox.common.log import get_logger
from mulebox.dashboard import cancel, controls, keys

_log = get_logger(__name__)


async def get_settings(request: web.Request) -> web.Response:
    app, name = request.app, request.match_info["name"]
    view = await asyncio.to_thread(app[keys.DATA].node_settings, name, app[keys.CLOCK]())
    if view is None:
        raise web.HTTPNotFound(text="no such machine\n")
    return web.json_response({**view, "editable": cancel.offered(request)})


async def _change(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="send the settings as JSON\n") from None
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="send the settings as a JSON object\n")
    if body.get("cancel") is True:
        return {"cancel": True}
    try:
        change = ns.checked({key: value for key, value in body.items()
                             if value is not None and key != "cancel"})
    except ValueError as exc:
        raise web.HTTPBadRequest(text=f"{exc}\n") from None
    if not change:
        raise web.HTTPBadRequest(text="send slots, priority, or cancel: true\n")
    return change


async def post_settings(request: web.Request) -> web.Response:
    cancel.check(request)
    name = request.match_info["name"]
    change = await _change(request)
    try:
        reply = await request.app[keys.CANCELLER].node_settings(name, **change)
    except CoordinatorError as exc:
        raise controls.refused(exc, "machine") from None
    _log.info("machine %s: settings %s from the dashboard by %s", name, change, request.remote)
    return web.json_response({**reply.body, "editable": True})


def add_routes(app: web.Application, editable: bool) -> None:
    app.router.add_get("/api/machines/{name}/settings", get_settings)
    if editable:
        app.router.add_post("/api/machines/{name}/settings", post_settings)
