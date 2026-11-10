"""The dashboard's controls on a job and on a machine (interfaces-m2.md, Controls).

    POST /api/jobs/<id>/control      {"action": "pause|resume|first|boost|normal"}
    POST /api/machines/<name>/control {"action": "pause|resume"}

The same requests `mulebox pause|resume|first|boost|normal` and `mulebox machine pause|resume`
send, through the canceller's `mulebox rpc`, so every rule stays in the coordinator
(coordinator/job_control.py, coordinator/machine_api.py). Protected like cancel (cancel.check).
A coordinator's refusal comes back as 409 with its own words.
"""

from __future__ import annotations

from typing import Any

from aiohttp import web

from mulebox.client.remote import CoordinatorError
from mulebox.common.log import get_logger
from mulebox.dashboard import cancel, keys

JOB_ACTIONS = frozenset({"pause", "resume", "first", "boost", "normal"})
MACHINE_ACTIONS = {"pause": "drain", "resume": "resume"}  # the dashboard's word -> the request
_log = get_logger(__name__)


async def _action(request: web.Request, allowed: Any) -> str:
    try:
        body = await request.json()
    except ValueError:
        raise web.HTTPBadRequest(text="send {\"action\": ...} as JSON\n") from None
    action = body.get("action") if isinstance(body, dict) else None
    if action not in allowed:
        raise web.HTTPBadRequest(text=f"action must be one of {', '.join(sorted(allowed))}\n")
    return action


def _refused(exc: CoordinatorError, what: str) -> web.HTTPException:
    if exc.code == "not_found":
        return web.HTTPNotFound(text=f"no such {what}\n")
    if exc.code in ("conflict", "bad_request"):
        return web.HTTPConflict(text=f"{exc}\n")
    _log.warning("a %s control failed: %s", what, exc)
    return web.HTTPBadGateway(text=f"{exc}\n")


async def job_control(request: web.Request) -> web.Response:
    cancel.check(request)
    job_id = request.match_info["job_id"]
    action = await _action(request, JOB_ACTIONS)
    try:
        reply = await request.app[keys.CANCELLER].control(job_id, action)
    except CoordinatorError as exc:
        raise _refused(exc, "job") from None
    _log.info("job %s: %s from the dashboard by %s", job_id, action, request.remote)
    body = reply.body
    return web.json_response({"job_id": job_id, "action": action, "state": body.get("state"),
                              **{key: body.get(key, False if key != "priority" else 0)
                                 for key in ("paused", "boost", "priority")}})


async def machine_control(request: web.Request) -> web.Response:
    cancel.check(request)
    name = request.match_info["name"]
    action = await _action(request, MACHINE_ACTIONS)
    try:
        reply = await request.app[keys.CANCELLER].machine(name, MACHINE_ACTIONS[action])
    except CoordinatorError as exc:
        raise _refused(exc, "machine") from None
    _log.info("machine %s: %s from the dashboard by %s", name, action, request.remote)
    return web.json_response({"machine": name, "action": action,
                              "running": reply.body.get("running", [])})


def add_routes(app: web.Application) -> None:
    app.router.add_post("/api/jobs/{job_id}/control", job_control)
    app.router.add_post("/api/machines/{name}/control", machine_control)
