"""`GET /api/metrics`, with `?machine=<worker name>` for another machine (interfaces-m2.md).

The dashboard's own machine (no parameter, or its own name) gets the hub's samples, as its live
updates come on the event stream. Another worker gets what machine_history.py kept of its
reports. A name the history has not seen yet is looked up in the store once, so a request right
after the dashboard started is not refused; a name the store does not know is a 404.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from mulebox.dashboard import keys


def host_reply(hub: Any) -> dict[str, Any]:
    return {"history": list(hub.history), "drops": hub.bus.drops,
            "machine": hub.local_name, "host": True}


async def reply(request: web.Request) -> dict[str, Any]:
    app = request.app
    hub, now = app[keys.HUB], app[keys.CLOCK]()
    name = request.query.get("machine") or None
    if name is None or name == hub.local_name:
        return host_reply(hub)
    if not hub.machine_history.knows(name):
        _, found = await asyncio.to_thread(app[keys.DATA].fleet, now)
        hub.machine_history.record(found, now)
    body = hub.machine_history.reply(name, now)
    if body is None:
        raise web.HTTPNotFound(text="no such machine\n")
    return body
