"""The LAN listener's rules and the login pages (`lan` mode, interfaces-m2.md).

A request on the LAN listener must come from the LAN range and hold a session, except
for the login page and its stylesheet. Which listener a request arrived on comes from
its socket, never from a header, and TLS plays no part in that. The other listener is
only ever on 127.0.0.1, where the SSH tunnel keeps working without a password.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

from mulebox.common.log import get_logger
from mulebox.dashboard import keys, password
from mulebox.dashboard.session import SESSION_TTL_S, LanAccess

COOKIE = "mulebox_session"
PUBLIC_PATHS = frozenset({"/login", "/static/style.css"})
MARKER = "<!--message-->"
FAILED = '<p class="login-error" role="alert">Wrong password.</p>'
WAIT = '<p class="login-error" role="alert">Too many attempts. Try again in {} s.</p>'
_log = get_logger(__name__)
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def on_lan(request: web.Request) -> bool:
    """True when this request came in on the LAN listener."""
    access = request.app.get(keys.LAN)
    if access is None:
        return False
    transport = request.transport
    return access.is_lan_socket(transport.get_extra_info("sockname") if transport else None)


@web.middleware
async def lan_guard(request: web.Request, handler: Handler) -> web.StreamResponse:
    if not on_lan(request):
        return await handler(request)
    access = request.app[keys.LAN]
    if not access.allows(request.remote):
        return web.Response(status=403, text="not allowed from this address\n")
    if request.path in PUBLIC_PATHS or access.sessions.valid(request.cookies.get(COOKIE)):
        return await handler(request)
    if request.path == "/healthz" or request.path.startswith("/api/"):
        return web.Response(status=401, text="sign in first\n")
    raise web.HTTPSeeOther("/login")


def add_routes(app: web.Application, static_dir: Path) -> None:
    app.router.add_get("/login", _page(static_dir))
    app.router.add_post("/login", _submit(static_dir))
    app.router.add_post("/logout", _logout)


def _lan(request: web.Request) -> LanAccess:
    """The LAN state; these pages do not exist on the plain listener."""
    if not on_lan(request):
        raise web.HTTPNotFound(text="no sign-in here\n")
    return request.app[keys.LAN]


def _same_site(request: web.Request) -> None:
    """Refuse cross-site posts. `Origin` cannot do this: the page's no-referrer policy
    makes browsers send `Origin: null` on a same-site form post. Browsers send
    `Sec-Fetch-Site` only over HTTPS; over HTTP, `SameSite=Strict` does this job."""
    if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
        raise web.HTTPForbidden(text="cross-site request refused\n")


def _render(static_dir: Path, message: str = "", status: int = 200) -> web.Response:
    page = (static_dir / "login.html").read_text(encoding="utf-8")
    return web.Response(text=page.replace(MARKER, message), status=status,
                        content_type="text/html", headers={"Cache-Control": "no-store"})


def _page(static_dir: Path) -> Handler:
    async def page(request: web.Request) -> web.StreamResponse:
        if _lan(request).sessions.valid(request.cookies.get(COOKIE)):
            raise web.HTTPSeeOther("/")
        return _render(static_dir)
    return page


def _submit(static_dir: Path) -> Handler:
    async def submit(request: web.Request) -> web.StreamResponse:
        access = _lan(request)
        _same_site(request)
        who = request.remote or ""
        wait = access.limiter.retry_after(who)
        if wait > 0:
            return _render(static_dir, WAIT.format(math.ceil(wait)), 429)
        form = await request.post()
        given = form.get("password")
        given = given if isinstance(given, str) else ""
        async with access.hashing:
            good = await asyncio.to_thread(password.verify, given, access.password_hash)
        if not good:
            access.limiter.failed(who)
            _log.warning("failed dashboard login from %s", who)
            return _render(static_dir, FAILED, 401)
        access.limiter.succeeded(who)
        response = web.HTTPSeeOther("/")
        response.set_cookie(COOKIE, access.sessions.create(), max_age=SESSION_TTL_S, path="/",
                            secure=request.secure, httponly=True, samesite="Strict")
        raise response
    return submit


async def _logout(request: web.Request) -> web.Response:
    access = _lan(request)
    _same_site(request)
    access.sessions.end(request.cookies.get(COOKIE))
    response = web.Response(status=204)
    response.del_cookie(COOKIE, path="/", secure=request.secure, httponly=True,
                        samesite="Strict")
    return response
