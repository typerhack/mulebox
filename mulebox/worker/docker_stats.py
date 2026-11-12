"""A container's CPU, memory and traffic from the Docker Engine API, for nodes without cgroups.

On Linux these come from the kernel's files (cgroups.py). On a Mac the containers run in Docker
Desktop's, OrbStack's or Colima's virtual machine, out of the host's reach, so the engine is
asked: `GET /containers/<id>/stats?stream=false&one-shot=true` over its unix socket, the one the
`docker` command uses (common/docker_socket.py). The answer has the same numbers
the cgroup files hold: CPU used since the container started, memory less the page cache it can
drop, and bytes in and out of its own network namespace.

Any failure is no reading, which callers treat as unknown, never as idle.
"""

from __future__ import annotations

import http.client
import json
import socket
from typing import Any

from mulebox.common.docker_socket import socket_path

TIMEOUT_S = 5.0


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("docker", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


def parse(stats: dict[str, Any]) -> dict[str, float] | None:
    """cpu_s, memory and net bytes from one stats answer; None if its CPU is missing."""
    try:
        cpu_s = stats["cpu_stats"]["cpu_usage"]["total_usage"] / 1e9
    except (KeyError, TypeError):
        return None
    out: dict[str, float] = {"cpu_s": cpu_s}
    memory = stats.get("memory_stats") or {}
    if "usage" in memory:
        page_cache = (memory.get("stats") or {}).get("inactive_file", 0)
        out["memory"] = float(max(0, memory["usage"] - page_cache))
    networks = stats.get("networks")
    if isinstance(networks, dict):
        out["net"] = float(sum(n.get("rx_bytes", 0) + n.get("tx_bytes", 0)
                               for n in networks.values() if isinstance(n, dict)))
    return out


class Engine:
    def __init__(self, path: str | None = None, timeout_s: float = TIMEOUT_S) -> None:
        self._path = path
        self.timeout_s = timeout_s

    def stats(self, container: str) -> dict[str, float] | None:
        if not container.isalnum():
            return None
        path = self._path = self._path or socket_path()
        if path is None:
            return None
        conn = _UnixConnection(path, self.timeout_s)
        try:
            conn.request("GET", f"/containers/{container}/stats?stream=false&one-shot=true")
            reply = conn.getresponse()
            body = reply.read()
            if reply.status != 200:
                return None
            return parse(json.loads(body))
        except (OSError, ValueError, http.client.HTTPException):
            return None
        finally:
            conn.close()
