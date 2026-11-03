"""Count running Docker containers through the Engine API socket, or None.

Asks `GET /containers/json` on the Unix socket (DOCKER_HOST when it is `unix://...`, else
/var/run/docker.sock) with a short timeout. No docker CLI process per sample. Any problem
(no socket, no permission, daemon down, odd reply) yields None, shown as "not available";
the dashboard never fails because of Docker. Only the count is kept: no names, images,
environment or inspect output reach the dashboard.
"""

from __future__ import annotations

import os
from pathlib import Path

import aiohttp

DEFAULT_SOCKET = "/var/run/docker.sock"
TIMEOUT_S = 2.0


def socket_path(environ: dict[str, str] | None = None) -> str | None:
    """The Docker socket to ask, or None when DOCKER_HOST points somewhere else (tcp)."""
    host = (environ if environ is not None else os.environ).get("DOCKER_HOST", "")
    if not host:
        return DEFAULT_SOCKET
    if host.startswith("unix://"):
        return host[len("unix://"):]
    return None


async def running_containers(path: str | None) -> int | None:
    if path is None or not Path(path).exists():
        return None
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_S)
    try:
        connector = aiohttp.UnixConnector(path=path)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get("http://docker/containers/json") as reply:
                if reply.status != 200:
                    return None
                body = await reply.json()
    except (aiohttp.ClientError, OSError, TimeoutError, ValueError):
        return None
    return len(body) if isinstance(body, list) else None
