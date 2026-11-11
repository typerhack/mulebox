"""Can the node reach these registries? For `mulebox doctor`, before any job finds out.

A TCP connection and no more: it needs no login, says the route and name lookup work, and that
is what breaks on a machine behind a VPN. It says nothing about whether an image exists. It runs
where the coordinator runs, which until there are several machines is the node.
"""

from __future__ import annotations

import re
import socket
from concurrent.futures import ThreadPoolExecutor

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest

MAX_HOSTS = 8
TIMEOUT_S = 4.0
HTTPS_PORT = 443
_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{0,252}(:[0-9]{1,5})?")


def _open(host: str) -> bool:
    name, _, port = host.partition(":")
    try:
        with socket.create_connection((name, int(port or HTTPS_PORT)), timeout=TIMEOUT_S):
            return True
    except (OSError, ValueError):
        return False


def reach(req: Request) -> Message:
    hosts = req.body["hosts"]
    if (not isinstance(hosts, list) or len(hosts) > MAX_HOSTS
            or not all(isinstance(host, str) and _HOST.fullmatch(host) for host in hosts)):
        raise BadRequest(f"field 'hosts' must be at most {MAX_HOSTS} host names")
    with ThreadPoolExecutor(max_workers=MAX_HOSTS) as pool:
        found = dict(zip(hosts, pool.map(_open, hosts), strict=True)) if hosts else {}
    return req.reply(MessageType.REACH_OK, {"hosts": found})
