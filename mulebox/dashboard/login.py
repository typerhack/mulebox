"""The LAN listener's rules and the login pages (`lan` mode, interfaces-m2.md).

A request on the LAN listener must come from the LAN range and hold a session, except
for the login page, its stylesheet and the fonts. The page is part of the front end's build
(`web/login.html`, built to `app/login.html` and `app/login.css`; fonts under `app/fonts/`
by fixed names, web/vite.config.ts); without a build it answers as `/` does (pages.py).
Which listener a request arrived on comes from
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
from mulebox.dashboard import keys, pages, password
from mulebox.dashboard.session import SESSION_TTL_S, LanAccess

COOKIE = "mulebox_session"
PUBLIC_PATHS = frozenset({"/login", "/app/login.css"})
PUBLIC_PREFIXES = ("/app/fonts/",)  # the bundled fonts (OFL), nothing of the user's
MARKER = "<!--message-->"
# Lucide's octagon-alert, the design system's danger icon (docs/design-system.md, Icons).
_ICON = ('<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M12 16h.01"/><path d="M12 8v4"/>'
         '<path d="M15.312 2a2 2 0 0 1 1.414.586l4.688 4.688A2 2 0 0 1 22 8.688v6.624a2 2 0 0 1'
         '-.586 1.414l-4.688 4.688a2 2 0 0 1-1.414.586H8.688a2 2 0 0 1-1.414-.586l-4.688-4.688A2 '
         '2 0 0 1 2 15.312V8.688a2 2 0 0 1 .586-1.414l4.688-4.688A2 2 0 0 1 8.688 2z"/></svg>')
FAILED = f'<p class="login-error" role="alert">{_ICON}<span>Wrong password.</span></p>'
WAIT = (f'<p class="login-error" role="alert">{_ICON}'
        '<span>Too many attempts. Try again in {} s.</span></p>')
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
    if (access.password_hash is None or is_public(request.path)
            or access.sessions.valid(request.cookies.get(COOKIE))):
        return await handler(request)
    if request.path == "/healthz" or request.path.startswith("/api/"):
        return web.Response(status=401, text="sign in first\n")
    raise web.HTTPSeeOther("/login")


def is_public(path: str) -> bool:
    """What a visitor with no session may fetch: the sign-in page and what it loads."""
    return path in PUBLIC_PATHS or (path.startswith(PUBLIC_PREFIXES) and ".." not in path)


def add_routes(app: web.Application, app_dir: Path) -> None:
    app.router.add_get("/login", _page(app_dir))
    app.router.add_post("/login", _submit(app_dir))
    app.router.add_post("/logout", _logout)


def sign_in_needed(request: web.Request) -> bool:
    return on_lan(request) and request.app[keys.LAN].password_hash is not None


def _lan(request: web.Request) -> LanAccess:
    """The LAN state; these pages do not exist on the tunnel listener or without a password."""
    if not sign_in_needed(request):
        raise web.HTTPNotFound(text="no sign-in here\n")
    return request.app[keys.LAN]


def same_site(request: web.Request) -> None:
    """Refuse cross-site posts. `Origin` cannot do this: the page's no-referrer policy
    makes browsers send `Origin: null` on a same-site form post. Browsers send
    `Sec-Fetch-Site` only over HTTPS; over HTTP, `SameSite=Strict` does this job."""
    if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
        raise web.HTTPForbidden(text="cross-site request refused\n")


def _render(app_dir: Path, message: str = "", status: int = 200) -> web.Response:
    path = app_dir / "login.html"
    if not path.is_file():
        return pages.not_built()
    page = path.read_text(encoding="utf-8")
    return web.Response(text=page.replace(MARKER, message), status=status,
                        content_type="text/html", headers={"Cache-Control": "no-store"})


def _page(app_dir: Path) -> Handler:
    async def page(request: web.Request) -> web.StreamResponse:
        if on_lan(request) and not sign_in_needed(request):
            raise web.HTTPSeeOther("/")
        if _lan(request).sessions.valid(request.cookies.get(COOKIE)):
            raise web.HTTPSeeOther("/")
        return _render(app_dir)
    return page


def _submit(app_dir: Path) -> Handler:
    async def submit(request: web.Request) -> web.StreamResponse:
        access = _lan(request)
        same_site(request)
        who = request.remote or ""
        wait = access.limiter.retry_after(who)
        if wait > 0:
            return _render(app_dir, WAIT.format(math.ceil(wait)), 429)
        form = await request.post()
        given = form.get("password")
        given = given if isinstance(given, str) else ""
        async with access.hashing:
            # Asked again here: attempts sent together all pass the check above, while the
            # first is still being hashed, and each would otherwise get its guess.
            wait = access.limiter.retry_after(who)
            if wait > 0:
                return _render(app_dir, WAIT.format(math.ceil(wait)), 429)
            good = await asyncio.to_thread(password.verify, given, access.password_hash)
            if not good:
                access.limiter.failed(who)
        if not good:
            _log.warning("failed dashboard login from %s", who)
            return _render(app_dir, FAILED, 401)
        access.limiter.succeeded(who)
        response = web.HTTPSeeOther("/")
        response.set_cookie(COOKIE, access.sessions.create(), max_age=SESSION_TTL_S, path="/",
                            secure=request.secure, httponly=True, samesite="Strict")
        raise response
    return submit


async def _logout(request: web.Request) -> web.Response:
    access = _lan(request)
    same_site(request)
    access.sessions.end(request.cookies.get(COOKIE))
    response = web.Response(status=204)
    response.del_cookie(COOKIE, path="/", secure=request.secure, httponly=True,
                        samesite="Strict")
    return response
