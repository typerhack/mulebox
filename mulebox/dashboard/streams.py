"""Streaming endpoints: `/api/events` (queue + metrics) and a job's live log over SSE.

`/api/events`: replays what a reconnecting viewer missed (`Last-Event-ID`), or sends a
snapshot (`queue`, `metrics_history`) when that is not possible, then every bus event.
A viewer that is too slow is dropped by the bus and its stream ends here.

`/api/jobs/{id}/log`: `log` events whose id is the byte offset after the chunk, so a
reconnect resumes exactly where it stopped; a `state` event when the job's state
changes; one `end` event (the job detail) once the job is finished and its whole log has
been sent. Starts at `Last-Event-ID`, else `?offset=`, else `?tail=` bytes before the end.
Log text is redacted by the worker before it is stored and is shown as text, never HTML.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from mulebox.dashboard import keys
from mulebox.dashboard.events import KEEPALIVE, count, encode, frame

POLL_S = 0.5
KEEPALIVE_S = 15.0
TEXT_CHUNK = 128 * 1024


async def _open(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(headers={
        "Content-Type": "text/event-stream", "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
    })
    await response.prepare(request)
    return response


async def events(request: web.Request) -> web.StreamResponse:
    hub = request.app[keys.HUB]
    bus = hub.bus
    last_id = request.headers.get("Last-Event-ID") or request.query.get("last_id")
    sub = bus.subscribe()  # before `since`: nothing is published between the two calls
    replay = bus.since(last_id)
    try:
        response = await _open(request)
        if replay is None:
            queue = hub.current_queue()
            if queue is None:
                data = request.app[keys.DATA]
                now = request.app[keys.CLOCK]()
                queue = await asyncio.to_thread(data.queue_snapshot, now)
            await response.write(frame("queue", queue, bus.last_id))
            await response.write(frame("metrics_history", {"history": list(hub.history)},
                                       bus.last_id))
        else:
            for event in replay:
                await response.write(encode(event))
        while True:
            try:
                event = await asyncio.wait_for(sub.queue.get(), KEEPALIVE_S)
            except TimeoutError:
                await response.write(KEEPALIVE)
                continue
            if event is None:  # dropped as too slow; the browser reconnects
                break
            await response.write(encode(event))
    except (ConnectionResetError, ConnectionError):
        pass
    finally:
        bus.unsubscribe(sub)
    return response


def _start_offset(request: web.Request, size: int) -> int:
    for raw in (request.headers.get("Last-Event-ID"), request.query.get("offset")):
        start = count(raw)
        if start is not None:
            return start
    tail = count(request.query.get("tail"))
    return max(0, size - tail) if tail is not None else 0


async def log_stream(request: web.Request) -> web.StreamResponse:
    data = request.app[keys.DATA]
    job_id = request.match_info["job_id"]
    detail = await asyncio.to_thread(data.job, job_id)
    if detail is None:
        raise web.HTTPNotFound(text="no such job\n")
    offset = _start_offset(request, detail["log_size"])
    response = await _open(request)
    state: Any = None
    idle = 0.0
    try:
        while True:
            chunk = await asyncio.to_thread(data.log_chunk, job_id, offset)
            if chunk is None:
                break
            if chunk["state"] != state:
                state = chunk["state"]
                await response.write(frame("state", {"state": state}))
            if chunk["next_offset"] > offset:
                body = {k: chunk[k] for k in ("offset", "next_offset", "data")}
                await response.write(frame("log", body, str(chunk["next_offset"])))
                offset, idle = chunk["next_offset"], 0.0
                continue
            if chunk["eof"]:
                final = await asyncio.to_thread(data.job, job_id)
                await response.write(frame("end", final or {}, str(offset)))
                break
            if idle >= KEEPALIVE_S:
                await response.write(KEEPALIVE)
                idle = 0.0
            await asyncio.sleep(POLL_S)
            idle += POLL_S
    except (ConnectionResetError, ConnectionError):
        pass
    return response


async def log_text(request: web.Request) -> web.StreamResponse:
    """The whole log as plain text (as stored at the time of the request)."""
    data = request.app[keys.DATA]
    job_id = request.match_info["job_id"]
    if await asyncio.to_thread(data.job, job_id) is None:
        raise web.HTTPNotFound(text="no such job\n")
    size = await asyncio.to_thread(data.log_size, job_id)
    response = web.StreamResponse(headers={"Content-Type": "text/plain; charset=utf-8"})
    await response.prepare(request)
    offset = 0
    try:
        while offset < size:
            raw = await asyncio.to_thread(data.staging.read_log, job_id, offset, TEXT_CHUNK)
            if not raw:
                break
            await response.write(raw)
            offset += len(raw)
    except (ConnectionResetError, ConnectionError):
        pass
    return response
