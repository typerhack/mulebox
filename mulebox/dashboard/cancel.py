"""The optional cancel button's routes and their protection (interfaces-m2.md, Cancel button).

The route exists only with `cancel_button` on, and answers only on the LAN listener with a
password: the tunnel listener has no sign-in, so nobody there is known to have asked. A session
alone is not enough. `SameSite=Strict` does not cover a page on another port of this address,
which counts as the same site, and `Sec-Fetch-Site` does not come over plain HTTP. So `Origin`
must be this exact origin, and a token only this session's pages can read must be in a header,
which a cross-site request cannot set without a CORS approval this app never gives.
"""

from __future__ import annotations

import asyncio
import hmac

from aiohttp import web

from mulebox.client.remote import CoordinatorError
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState
from mulebox.dashboard import keys, login

TOKEN_HEADER = "X-Mulebox-Token"
_log = get_logger(__name__)


def _offered(request: web.Request) -> bool:
    return keys.CANCELLER in request.app and login.sign_in_needed(request)


def _token(request: web.Request) -> str:
    access = request.app[keys.LAN]
    return access.sessions.action_token(request.cookies.get(login.COOKIE, ""))


def _check_origin(request: web.Request) -> None:
    """After login.same_site: only a page of this dashboard, in this session, gets through."""
    if request.headers.get("Origin") != f"{request.scheme}://{request.host}":
        raise web.HTTPForbidden(text="cross-site request refused\n")
    given = request.headers.get(TOKEN_HEADER, "")
    if not hmac.compare_digest(given.encode("utf-8"), _token(request).encode("utf-8")):
        raise web.HTTPForbidden(text="this page's session token is missing or wrong\n")


async def session(request: web.Request) -> web.Response:
    """What this page may do: a `cancel_token` to send back, or null for no button."""
    return web.json_response({"cancel_token": _token(request) if _offered(request) else None})


async def cancel_job(request: web.Request) -> web.Response:
    if not _offered(request):
        raise web.HTTPNotFound(text="no cancel button here\n")
    login.same_site(request)
    _check_origin(request)
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
