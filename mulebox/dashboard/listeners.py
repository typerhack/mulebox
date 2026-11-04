"""Run the dashboard app on one or more addresses until SIGTERM or SIGINT."""

from __future__ import annotations

import asyncio
import signal
import ssl
from dataclasses import dataclass

from aiohttp import web

SHUTDOWN_TIMEOUT_S = 5


@dataclass(frozen=True)
class Listener:
    host: str
    port: int
    tls: ssl.SSLContext | None = None


async def _serve(app: web.Application, listeners: list[Listener]) -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    runner = web.AppRunner(app, access_log=None, handle_signals=False,
                           shutdown_timeout=SHUTDOWN_TIMEOUT_S)
    await runner.setup()
    try:
        for item in listeners:
            await web.TCPSite(runner, item.host, item.port, ssl_context=item.tls).start()
        await stop.wait()
    finally:
        await runner.cleanup()


def serve(app: web.Application, listeners: list[Listener]) -> None:
    """Blocks. An address that cannot be bound raises OSError."""
    asyncio.run(_serve(app, listeners))
