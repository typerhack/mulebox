"""The machine's own CPU, memory, swap and network, the same on Linux and macOS.

What the load a worker reports (proc.py `HostLoad`), its activity meter (worker/activity.py) and
the dashboard's graphs (dashboard/metrics.py) read. Linux reads `/proc` and `/sys/class/net`
(proc.py, netdev.py); macOS asks its kernel and commands (darwin_host.py). Each reading is None
when it cannot be had, and nothing fails.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

from mulebox.common import darwin_host, netdev
from mulebox.common.proc import PROC, busy_seconds, parse_cpu, parse_memory, parse_swap, read


Cores = list[tuple[int, int]]  # (busy, total) ticks per core, in core order


class Host(Protocol):
    def cores(self) -> Cores:
        """Busy and total ticks of each core; busy leaves out idle and waiting for a disk."""

    def busy_seconds(self) -> float | None:
        """Busy CPU seconds of all cores since boot, waiting for a disk counted as busy."""

    def memory(self) -> dict[str, int] | None:
        """total, available and used bytes."""

    def swap(self) -> dict[str, int] | None:
        """total and used bytes."""

    def net(self) -> tuple[int, int] | None:
        """Bytes in and out over the physical interfaces."""


class LinuxHost:
    def __init__(self, proc: Path = PROC, net_root: Path = netdev.SYS_NET) -> None:
        self.proc, self.net_root = proc, net_root

    def cores(self) -> Cores:
        text = read(self.proc / "stat")
        return parse_cpu(text) if text else []

    def busy_seconds(self) -> float | None:
        text = read(self.proc / "stat")
        return busy_seconds(text) if text else None

    def _meminfo(self) -> str | None:
        return read(self.proc / "meminfo")

    def memory(self) -> dict[str, int] | None:
        text = self._meminfo()
        return parse_memory(text) if text else None

    def swap(self) -> dict[str, int] | None:
        text = self._meminfo()
        return parse_swap(text) if text else None

    def net(self) -> tuple[int, int] | None:
        return netdev.totals(self.net_root)


class DarwinHost:
    def cores(self) -> Cores:
        ticks = darwin_host.core_ticks() or []
        return [(sum(t) - t[darwin_host.IDLE], sum(t)) for t in ticks]

    def busy_seconds(self) -> float | None:
        cores = self.cores()
        return sum(busy for busy, _ in cores) / darwin_host.TICKS_PER_S if cores else None

    def memory(self) -> dict[str, int] | None:
        return darwin_host.memory()

    def swap(self) -> dict[str, int] | None:
        return darwin_host.swap()

    def net(self) -> tuple[int, int] | None:
        return darwin_host.net()


def for_platform(platform: str = sys.platform) -> Host:
    """This machine's readings; a system with neither (Windows) reads as Linux: all None."""
    return DarwinHost() if platform == "darwin" else LinuxHost()
