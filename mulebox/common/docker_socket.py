"""Where the Docker Engine API listens, as the `docker` command would find it.

`DOCKER_HOST` first (only `unix://` is used: a TCP engine is not asked). Else the usual socket,
`/var/run/docker.sock`, which Linux has and Docker Desktop and OrbStack link on a Mac. Else the
current `docker context`'s socket, which is how Colima and a Docker Desktop without the link are
reached. None when there is no unix socket to ask.
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
    if Path(default).exists():
        return default
    return context() or default
