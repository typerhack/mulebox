"""The dashboard's aiohttp application: routes, guards and static files (interfaces-m2.md).

Read-only, and GET-only apart from signing in and out. Guards on every request:
- Host check: only `127.0.0.1`, `localhost` and `[::1]` (any port, since the SSH tunnel's
  local port may differ), or the configured address on the LAN listener. This stops DNS
  rebinding from a web page reaching the dashboard.
- On the LAN listener (`lan` mode): the address range and a session (login.py).
- Headers: a strict Content-Security-Policy (only this origin, no inline script), no
  sniffing, no referrer, no framing; API replies are not cached.
Static files come from the package (`static/`); no CDN, no build step.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

from mulebox.dashboard import keys, login, streams
from mulebox.dashboard.data import HISTORY_DEFAULT, DashboardData
from mulebox.dashboard.hub import Hub
from mulebox.dashboard.session import LanAccess
from mulebox.version import get_version

STATIC_DIR = Path(__file__).with_name("static")
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
LOGIN_CSP = CSP.replace("form-action 'none'", "form-action 'self'")
Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def host_name(host: str | None) -> str:
    """The name part of a Host header: `[::1]:8090` -> `[::1]`, `x:1` -> `x`."""
    host = (host or "").strip().lower()
    if host.startswith("["):
        return host[: host.find("]") + 1] if "]" in host else host
    return host.rsplit(":", 1)[0] if ":" in host else host


@web.middleware
async def guard(request: web.Request, handler: Handler) -> web.StreamResponse:
    lan = login.on_lan(request)
    allowed = request.app[keys.LAN].hosts if lan else request.app[keys.ALLOWED_HOSTS]
    if host_name(request.host) not in allowed:
        return web.Response(status=421, text="unexpected Host header\n")
    return await handler(request)


async def _headers(request: web.Request, response: web.StreamResponse) -> None:
    """Runs for every response just before its headers go out (streams and errors too)."""
    headers = response.headers
    headers["Content-Security-Policy"] = LOGIN_CSP if request.path == "/login" else CSP
    headers["X-Content-Type-Options"] = "nosniff"
    headers["Referrer-Policy"] = "no-referrer"
    headers["X-Frame-Options"] = "DENY"
    if request.path.startswith("/api/"):
        headers.setdefault("Cache-Control", "no-store")


def build_app(data: DashboardData, hub: Hub, *, clock: Callable[[], float] = time.time,
              allowed_hosts: frozenset[str] = LOCAL_HOSTS, start_hub: bool = True,
              static_dir: Path = STATIC_DIR, lan: LanAccess | None = None) -> web.Application:
    app = web.Application(middlewares=[guard, login.lan_guard])
    app[keys.ALLOWED_HOSTS] = allowed_hosts
    if lan is not None:
        app[keys.LAN] = lan
        login.add_routes(app, static_dir)
    app[keys.HUB], app[keys.DATA], app[keys.CLOCK] = hub, data, clock
    app.on_response_prepare.append(_headers)
    app.router.add_get("/", _index(static_dir))
    app.router.add_get("/healthz", _health)
    app.router.add_get("/api/queue", _queue)
    app.router.add_get("/api/machines", _machines)
    app.router.add_get("/api/history", _history)
    app.router.add_get("/api/metrics", _metrics)
    app.router.add_get("/api/jobs/{job_id}", _job)
    app.router.add_get("/api/jobs/{job_id}/log.txt", streams.log_text)
    app.router.add_get("/api/jobs/{job_id}/log", streams.log_stream)
    app.router.add_get("/api/events", streams.events)
    app.router.add_static("/static/", static_dir, follow_symlinks=False)
    if start_hub:
        app.on_startup.append(_start_hub)
        app.on_cleanup.append(_stop_hub)
    return app


async def _start_hub(app: web.Application) -> None:
    app[keys.HUB].start()


async def _stop_hub(app: web.Application) -> None:
    await app[keys.HUB].stop()


def _index(static_dir: Path) -> Handler:
    async def index(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(static_dir / "index.html")
    return index


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "version": get_version(), "lan": login.on_lan(request),
                              "sign_in": login.sign_in_needed(request)})


async def _queue(request: web.Request) -> web.Response:
    app = request.app
    body = await asyncio.to_thread(app[keys.DATA].queue_snapshot, app[keys.CLOCK]())
    return web.json_response(body)


async def _machines(request: web.Request) -> web.Response:
    app = request.app
    body = await asyncio.to_thread(app[keys.DATA].machines, app[keys.CLOCK]())
    return web.json_response(body)


async def _job(request: web.Request) -> web.Response:
    job = await asyncio.to_thread(request.app[keys.DATA].job, request.match_info["job_id"])
    if job is None:
        raise web.HTTPNotFound(text="no such job\n")
    return web.json_response(job)


async def _history(request: web.Request) -> web.Response:
    query = request.query
    try:
        limit = int(query.get("limit", HISTORY_DEFAULT))
        before = float(query["before"]) if query.get("before") else None
    except ValueError:
        raise web.HTTPBadRequest(text="limit and before must be numbers\n") from None
    project = query.get("project") or None
    body = await asyncio.to_thread(request.app[keys.DATA].history, limit, before, project)
    return web.json_response(body)


async def _metrics(request: web.Request) -> web.Response:
    hub = request.app[keys.HUB]
    return web.json_response({"history": list(hub.history), "drops": hub.bus.drops})
