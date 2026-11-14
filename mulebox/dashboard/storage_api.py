"""What mulebox holds on each node, on the dashboard (interfaces-m2.md, Storage; design.md,
Project folders, Disk use and cleanup on its own).

    GET  /api/storage                 every node's last report, keep marks, branch names
    POST /api/storage/keep            {"project", "branch"?, "keep": true|false}
    POST /api/storage/remove          {"project", "branch"?}: a project's folders, or a branch's,
                                      on every node, as `mulebox project reset --yes`
    GET  /api/storage/remove/<group>  each node's answer to that removal so far
    POST /api/storage/sweep           {"node"?, "docker"?}: the cleanup now, as `mulebox storage
                                      clean`; its answers at /api/storage/remove/<group>

GET /api/storage reads the dashboard's own read-only store, plus `editable`. The rest needs the
controls on and is protected like them (cancel.check); it goes through the canceller's
`mulebox rpc` as the commands do, so every rule stays in the coordinator: a removal is refused
while a job of the project runs (coordinator/project_orders.py).
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


async def get_storage(request: web.Request) -> web.Response:
    app = request.app
    body = await asyncio.to_thread(app[keys.DATA].storage, app[keys.CLOCK]())
    return web.json_response({**body, "editable": cancel.offered(request)})


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="send JSON\n") from None
    if not isinstance(body, dict) or not isinstance(body.get("project"), str):
        raise web.HTTPBadRequest(text="send {\"project\": ..., \"branch\": ...}\n")
    branch = body.get("branch")
    if branch is not None and not isinstance(branch, str):
        raise web.HTTPBadRequest(text="branch must be text\n")
    return {"project": body["project"], **({"branch": branch} if branch else {}),
            "keep": body.get("keep", True) is not False}


async def _send(request: web.Request, msg: Any) -> dict[str, Any]:
    try:
        return (await request.app[keys.CANCELLER].send(msg)).body
    except CoordinatorError as exc:
        raise controls.refused(exc, "project") from None


async def post_keep(request: web.Request) -> web.Response:
    cancel.check(request)
    body = await _body(request)
    reply = await _send(request, message(MessageType.STORAGE_KEEP, **body))
    _log.info("storage: keep %s from the dashboard by %s", body, request.remote)
    return web.json_response(reply)


async def post_remove(request: web.Request) -> web.Response:
    cancel.check(request)
    body = await _body(request)
    order = {"action": "reset", "project": body["project"], "yes": True,
             **({"branch": body["branch"]} if "branch" in body else {})}
    reply = await _send(request, message(MessageType.PROJECT_ORDER, **order))
    _log.info("storage: remove %s from the dashboard by %s", order, request.remote)
    return web.json_response(reply)


async def post_sweep(request: web.Request) -> web.Response:
    cancel.check(request)
    try:
        body = await request.json()
    except ValueError:
        body = {}
    body = body if isinstance(body, dict) else {}
    node = body.get("node")
    if node is not None and not isinstance(node, str):
        raise web.HTTPBadRequest(text="node must be text\n")
    order = {"action": "sweep", "docker": body.get("docker", True) is not False,
             **({"node": node} if node else {})}
    reply = await _send(request, message(MessageType.PROJECT_ORDER, **order))
    _log.info("storage: cleanup now %s from the dashboard by %s", order, request.remote)
    return web.json_response(reply)


async def get_removal(request: web.Request) -> web.Response:
    """Only reads: a page's GET carries no Origin, and the answers change nothing."""
    group = request.match_info["group"]
    return web.json_response(await _send(request, message(MessageType.PROJECT_ORDER, group=group)))


def add_routes(app: web.Application, editable: bool) -> None:
    app.router.add_get("/api/storage", get_storage)
    if editable:
        app.router.add_post("/api/storage/keep", post_keep)
        app.router.add_post("/api/storage/remove", post_remove)
        app.router.add_post("/api/storage/sweep", post_sweep)
        app.router.add_get("/api/storage/remove/{group}", get_removal)
