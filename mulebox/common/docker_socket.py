"""Where the Docker Engine API listens, as the `docker` command would find it.

`DOCKER_HOST` first (only `unix://` is used: a TCP engine is not asked). Else the current
`docker context`'s socket (`DOCKER_CONTEXT`, else the one `docker context use` chose), as the
`docker` command the worker runs uses it: with Colima chosen beside Docker Desktop, the readings
come from the engine that runs the job's containers. Else, with no `docker` to ask, the usual
socket, `/var/run/docker.sock`. None when there is no unix socket to ask.
"""

from __future__ import annotations

import os
from pathlib import Path

from mulebox.common import command

DEFAULT_SOCKET = "/var/run/docker.sock"


def _unix(host: str) -> str | None:
    return host.removeprefix("unix://") if host.startswith("unix://") else None


def from_context() -> str | None:
    try:
        done = command.run(["docker", "context", "inspect", "--format",
                            "{{.Endpoints.docker.Host}}"], timeout_s=10)
    except command.CommandError:
        return None
    return _unix(done.stdout.strip()) if done.returncode == 0 else None


def socket_path(environ: dict[str, str] | None = None, default: str = DEFAULT_SOCKET,
                context=from_context) -> str | None:
    host = (environ if environ is not None else os.environ).get("DOCKER_HOST", "")
    if host:
        return _unix(host)
    found = context()
    if found:
        return found
    return default if Path(default).exists() else None
