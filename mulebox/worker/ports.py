"""Host ports for jobs' containers: free now, and not promised to another job.

Ports come from a range below the kernel's and Docker's ephemeral ports, from a random
start, and each is proven free by binding it on 127.0.0.1. A port stays with its job until
the job is cleaned up, because its container may not have started yet when the next job
asks. The worst case left is an unrelated program taking a port in the moment before the
job's containers start: that job then fails with Docker's clear "address already in use".
"""

from __future__ import annotations

import errno
import random
import socket
from collections.abc import Callable, Sequence

from mulebox.common.compose import ComposeError

LOW, HIGH = 20000, 29999


def is_free(port: int) -> bool:
    """True if nothing, on 127.0.0.1 or on all addresses, holds this TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            if exc.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            return False
    return True


class PortPool:
    def __init__(self, free: Callable[[int], bool] = is_free,
                 pick: Callable[[int, int], int] = random.randint) -> None:
        self._free, self._pick = free, pick
        self._held: dict[str, set[int]] = {}

    def take(self, job_id: str, names: Sequence[str]) -> dict[str, int]:
        """One free port per name, held for `job_id` until `release`."""
        taken = {port for ports in self._held.values() for port in ports}
        chosen: dict[str, int] = {}
        start, size = self._pick(LOW, HIGH), HIGH - LOW + 1
        candidates = (LOW + (start - LOW + step) % size for step in range(size))
        for name in names:
            for port in candidates:
                if port not in taken and self._free(port):
                    chosen[name] = port
                    break
            else:
                raise ComposeError(f"no free port between {LOW} and {HIGH} for {name}")
        self._held.setdefault(job_id, set()).update(chosen.values())
        return chosen

    def release(self, job_id: str) -> None:
        self._held.pop(job_id, None)
