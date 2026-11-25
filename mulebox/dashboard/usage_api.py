"""What jobs really used, on the dashboard (docs/design.md, Job usage).

    GET /api/usage            ?project=&job=&worker=&kind=&runs=&all=1: per project and job
    GET /api/usage/<job_id>   one run

The same answer as `mulebox usage` (coordinator/usage_api.py), from the dashboard's own
read-only store. Read only: nothing acts on it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from mulebox.coordinator import usage_api, usage_report
from mulebox.coordinator.errors import BadRequest, NotFound
from mulebox.dashboard import keys


def _body(query: Any) -> dict[str, Any]:
    body: dict[str, Any] = {name: query[name] for name in usage_report.FILTERS if query.get(name)}
    if query.get("runs"):
        try:
            body["runs"] = int(query["runs"])
        except ValueError:
            raise web.HTTPBadRequest(text="runs must be a whole number\n") from None
    if query.get("all") in ("1", "true"):
        body["all"] = True
    return body


async def _answer(request: web.Request, body: dict[str, Any]) -> web.Response:
    app = request.app
    try:
        found = await asyncio.to_thread(usage_api.answer, app[keys.DATA].store, body,
                                        app[keys.CLOCK]())
    except BadRequest as exc:
        raise web.HTTPBadRequest(text=f"{exc}\n") from None
    except NotFound as exc:
        raise web.HTTPNotFound(text=f"{exc}\n") from None
    return web.json_response(found)


async def get_usage(request: web.Request) -> web.Response:
    return await _answer(request, _body(request.query))


async def get_run(request: web.Request) -> web.Response:
    return await _answer(request, {"job_id": request.match_info["job_id"]})


def add_routes(app: web.Application) -> None:
    app.router.add_get("/api/usage", get_usage)
    app.router.add_get("/api/usage/{job_id}", get_run)
