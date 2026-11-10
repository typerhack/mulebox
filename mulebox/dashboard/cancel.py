"""The dashboard's controls and their protection (interfaces-m2.md, Controls): the cancel
route here, a job's and a machine's controls in controls.py.

mulebox runs on its owner's network, so whoever reaches the dashboard may steer it: the controls
are on unless `controls = false`, on the tunnel and on the LAN address, with or without a
password. What they keep out is other web pages in the same browser. The Host check (server.py)
stops a name rebound to this machine. `Origin` must be this exact origin, and a token only this
dashboard's pages can read must be in a header, which a cross-site request cannot set without a
CORS approval this app never gives. With a password the token is the session's, so it ends with
the sign-in; without one it is a secret made when the service starts.
"""

from __future__ import annotations

import asyncio
import hmac
import secrets

from aiohttp import web

from mulebox.client.remote import CoordinatorError
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState
from mulebox.dashboard import keys, login

TOKEN_HEADER = "X-Mulebox-Token"
PAGE_TOKEN = secrets.token_hex(32)  # this service's own, for pages without a sign-in
_log = get_logger(__name__)


def offered(request: web.Request) -> bool:
    return keys.CANCELLER in request.app


def _token(request: web.Request) -> str:
    if not login.sign_in_needed(request):
        return PAGE_TOKEN
    access = request.app[keys.LAN]
    return access.sessions.action_token(request.cookies.get(login.COOKIE, ""))


def check(request: web.Request) -> None:
    """Refuse anything but a page of this dashboard (and of this session, with a password)."""
    if not offered(request):
        raise web.HTTPNotFound(text="the dashboard's controls are off here\n")
    login.same_site(request)
    if request.headers.get("Origin") != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text="cross-site request refused\n")
    given = request.headers.get(TOKEN_HEADER, "")
    if not hmac.compare_digest(given.encode("utf-8"), _token(request).encode("utf-8")):
        raise web.HTTPForbidden(text="this page's session token is missing or wrong\n")


async def session(request: web.Request) -> web.Response:
    """What this page may do: an `action_token` to send back, or null with the controls off.
    `cancel_token` is the same, for a page loaded before 0.87.0."""
    token = _token(request) if offered(request) else None
    return web.json_response({"action_token": token, "cancel_token": token})


async def cancel_job(request: web.Request) -> web.Response:
    check(request)
    job_id = request.match_info["job_id"]
    job = await asyncio.to_thread(request.app[keys.DATA].job, job_id)
    if job is None:
        raise web.HTTPNotFound(text="no such job\n")
    if job["kind"] != "job":
        raise web.HTTPConflict(text="this only holds a slot for a GitHub run; "
                                    "cancel the run on GitHub\n")
    if job["state"] == JobState.FINISHED:
        raise web.HTTPConflict(text="this job has already finished\n")
    try:
        reply = await request.app[keys.CANCELLER].cancel(job_id)
    except CoordinatorError as exc:
        if exc.code == "not_found":
            raise web.HTTPNotFound(text="no such job\n") from None
        _log.warning("cancel of %s failed: %s", job_id, exc)
        raise web.HTTPBadGateway(text=f"{exc}\n") from None
    _log.info("job %s cancelled from the dashboard by %s", job_id, request.remote)
    body = reply.body
    return web.json_response({"job_id": job_id, "state": body.get("state"),
                              "outcome": body.get("outcome"),
                              "cancel_requested": body.get("cancel_requested", False)})
