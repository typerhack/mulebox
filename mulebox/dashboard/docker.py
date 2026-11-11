"""Ask Docker through the Engine API socket: its containers, and how much disk it uses.

Asks on the Unix socket (DOCKER_HOST when it is `unix://...`, else /var/run/docker.sock) with a
short timeout. No docker CLI process per sample. Any problem (no socket, no permission, daemon
down, odd reply) yields None, shown as "not available"; the dashboard never fails because of
Docker. Only what the Memory and Disk boxes need is kept: the count of running containers, the
ids of those mulebox started for a job or a GitHub runner started from its work folder, and
Docker's disk use. No names, images, environment or inspect output reach the dashboard.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import aiohttp

from mulebox.common.compose import LABEL_JOB
from mulebox.runners.runner_meter import WORKDIR_LABEL, runner_containers

DEFAULT_SOCKET = "/var/run/docker.sock"
TIMEOUT_S = 2.0
DF_TIMEOUT_S = 30.0  # `/system/df` sizes every image layer: 0.7 s on a machine with 59 images


def socket_path(environ: dict[str, str] | None = None) -> str | None:
    """The Docker socket to ask, or None when DOCKER_HOST points somewhere else (tcp)."""
    host = (environ if environ is not None else os.environ).get("DOCKER_HOST", "")
    if not host:
        return DEFAULT_SOCKET
    if host.startswith("unix://"):
        return host[len("unix://"):]
    return None


async def _get(path: str | None, url: str, timeout_s: float = TIMEOUT_S) -> Any:
    if path is None or not Path(path).exists():
        return None
    timeout = aiohttp.ClientTimeout(total=timeout_s)
    try:
        connector = aiohttp.UnixConnector(path=path)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.get(f"http://docker{url}") as reply:
                if reply.status != 200:
                    return None
                return await reply.json()
    except (aiohttp.ClientError, OSError, TimeoutError, ValueError):
        return None


async def containers(path: str | None) -> list[dict[str, Any]] | None:
    """The running containers, as `GET /containers/json` lists them, or None."""
    body = await _get(path, "/containers/json")
    return body if isinstance(body, list) else None


async def running_containers(path: str | None) -> int | None:
    found = await containers(path)
    return None if found is None else len(found)


def job_containers(listing: list[dict[str, Any]], runners_root: str | None) -> list[str]:
    """Ids of the containers of mulebox jobs (their label) and of GitHub runners' jobs (Compose's
    working folder inside a runner's `_work`, as runners/runner_meter.py finds them)."""
    ids = [c["Id"] for c in listing if isinstance(c.get("Id"), str)
           and LABEL_JOB in (c.get("Labels") or {})]
    if runners_root:
        lines = [f"{c['Id']}\t{(c.get('Labels') or {}).get(WORKDIR_LABEL, '')}"
                 for c in listing if isinstance(c.get("Id"), str) and c["Id"] not in ids]
        ids += [cid for found in runner_containers(lines, Path(runners_root)).values()
                for cid in found]
    return ids


def df_total(body: Any) -> int | None:
    """What `docker system df` adds up: image layers, containers' own layers, volumes and the
    build cache, in bytes; None for a reply without them."""
    if not isinstance(body, dict) or not isinstance(body.get("LayersSize"), int):
        return None
    total = body["LayersSize"]
    total += sum(c.get("SizeRw") or 0 for c in body.get("Containers") or [])
    total += sum(max(0, (v.get("UsageData") or {}).get("Size") or 0) for v in body.get("Volumes") or [])
    total += sum(b.get("Size") or 0 for b in body.get("BuildCache") or [])
    return total


async def disk_use(path: str | None) -> int | None:
    return df_total(await _get(path, "/system/df", DF_TIMEOUT_S))
