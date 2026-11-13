"""The dashboard's aiohttp application: routes, guards and static files (interfaces-m2.md).

Read-only, and GET-only apart from signing in and out and the optional cancel button
(cancel.py), which writes through `mulebox rpc`, never here. Guards on every request:
- Host check: only `127.0.0.1`, `localhost` and `[::1]` (any port, since the SSH tunnel's
  local port may differ), or the configured address on the LAN listener. This stops DNS
  rebinding from a web page reaching the dashboard.
- On the LAN listener (`lan` mode): the address range and a session (login.py).
- Headers: a strict Content-Security-Policy (only this origin, no inline script), no
  sniffing, no referrer, no framing; API replies are not cached.
Pages and their files come from the package (pages.py): the React app's build, or a 503 page
that says how to build it; no CDN.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import web

from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.stats import GROUPS as STAT_FILTERS
from mulebox.dashboard import (cancel, controls, history_query, keys, login, metrics_api,
                               node_settings, order_api, pages, streams)
from mulebox.dashboard.canceller import Canceller
from mulebox.dashboard.data import HISTORY_DEFAULT, DashboardData
from mulebox.dashboard.hub import Hub
from mulebox.dashboard.session import LanAccess
from mulebox.version import get_version

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; "
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
    else:  # the page's files: asked after every load, or an upgrade would not reach the browser
        headers.setdefault("Cache-Control", "no-cache")


def build_app(data: DashboardData, hub: Hub, *, clock: Callable[[], float] = time.time,
              allowed_hosts: frozenset[str] = LOCAL_HOSTS, start_hub: bool = True,
              lan: LanAccess | None = None, canceller: Canceller | None = None,
              app_dir: Path = pages.APP_DIR) -> web.Application:
    """`app_dir` is the React build (pages.py)."""
    app = web.Application(middlewares=[guard, login.lan_guard])
    app[keys.ALLOWED_HOSTS] = allowed_hosts
    if lan is not None:
        app[keys.LAN] = lan
        login.add_routes(app, app_dir)
    app[keys.HUB], app[keys.DATA], app[keys.CLOCK] = hub, data, clock
    if canceller is not None:
        app[keys.CANCELLER] = canceller
        app.router.add_post("/api/jobs/{job_id}/cancel", cancel.cancel_job)
        controls.add_routes(app)
    node_settings.add_routes(app, editable=canceller is not None)
    app.on_response_prepare.append(_headers)
    pages.add_routes(app, app_dir)
    app.router.add_get("/healthz", _health)
    app.router.add_get("/api/session", cancel.session)
    app.router.add_get("/api/queue", _queue)
    app.router.add_get("/api/machines", _machines)
    app.router.add_get("/api/history", _history)
    app.router.add_get("/api/metrics", _metrics)
    app.router.add_get("/api/stats", _stats)
    order_api.add_routes(app, writable=canceller is not None)
    app.router.add_get("/api/jobs/{job_id}", _job)
    app.router.add_get("/api/jobs/{job_id}/log.txt", streams.log_text)
    app.router.add_get("/api/jobs/{job_id}/log", streams.log_stream)
    app.router.add_get("/api/events", streams.events)
    if start_hub:
        app.on_startup.append(_start_hub)
        app.on_cleanup.append(_stop_hub)
    return app


async def _start_hub(app: web.Application) -> None:
    app[keys.HUB].start()


async def _stop_hub(app: web.Application) -> None:
    await app[keys.HUB].stop()


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "version": get_version(), "lan": login.on_lan(request),
                              "sign_in": login.sign_in_needed(request)})


async def _queue(request: web.Request) -> web.Response:
    app = request.app
    body = await asyncio.to_thread(app[keys.DATA].queue_snapshot, app[keys.CLOCK]())
    return web.json_response(body)


async def _machines(request: web.Request) -> web.Response:
    app = request.app
    body = app[keys.HUB].current_machines()  # carries the local machine's readings
    if body is None:
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
    try:
        chosen = history_query.filters(query)
    except BadRequest as exc:
        raise web.HTTPBadRequest(text=f"{exc}\n") from None
    body = await asyncio.to_thread(request.app[keys.DATA].history, limit, before, chosen)
    return web.json_response(body)


def _numbers(text: str) -> list[float]:
    return [float(part) for part in text.split(",") if part]


async def _stats(request: web.Request) -> web.Response:
    """Job minutes: `from`, `to`, `day_starts` (commas) in epoch seconds, `by` (commas) and
    one value per filter (coordinator/stats.py, GROUPS)."""
    query, body = request.query, {}
    try:
        body.update({name: float(query[name]) for name in ("from", "to") if query.get(name)})
        if query.get("day_starts"):
            body["day_starts"] = _numbers(query["day_starts"])
    except ValueError:
        raise web.HTTPBadRequest(text="from, to and day_starts must be numbers\n") from None
    if "by" in query:
        body["by"] = [part for part in query["by"].split(",") if part]
    body.update({name: value for name, value in query.items() if name in STAT_FILTERS and value})
    try:
        found = await asyncio.to_thread(request.app[keys.DATA].stats, body, request.app[keys.CLOCK]())
    except BadRequest as exc:
        raise web.HTTPBadRequest(text=f"{exc}\n") from None
    return web.json_response(found)


async def _metrics(request: web.Request) -> web.Response:
    return web.json_response(await metrics_api.reply(request))
