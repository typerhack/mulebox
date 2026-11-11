"""Reading `/proc`: what the dashboard's graphs, the worker's activity meter and the load a
worker reports with its claims (`HostLoad`, M5.3) share. Without `/proc` (macOS) the readers
give nothing and nothing fails."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from mulebox.common import disk, netdev

PROC = Path("/proc")
IDLE, IOWAIT = 3, 4


def core_times(text: str) -> Iterator[list[int]]:
    """Each core's jiffies from /proc/stat, in core order: user, nice, system, idle, iowait..."""
    for line in text.splitlines():
        name, _, rest = line.partition(" ")
        if not (name.startswith("cpu") and name[3:].isdigit()):
            continue
        values = [int(v) for v in rest.split()[:8] if v.isdigit()]
        if len(values) > IOWAIT:
            yield values


def parse_cpu(text: str) -> list[tuple[int, int]]:
    """(busy, total) jiffies per core from /proc/stat, in core order."""
    cores = []
    for values in core_times(text):
        total = sum(values)
        cores.append((total - values[IDLE] - values[IOWAIT], total))
    return cores


def cpu_percent(before: list[tuple[int, int]], after: list[tuple[int, int]]
                ) -> list[float] | None:
    """Busy percent per core between two parse_cpu results; None if they do not match."""
    if not before or len(before) != len(after):
        return None
    out = []
    for (busy0, total0), (busy1, total1) in zip(before, after):
        span = total1 - total0
        share = (busy1 - busy0) / span if span > 0 else 0.0
        out.append(round(max(0.0, min(1.0, share)) * 100, 1))
    return out


def parse_memory(text: str) -> dict[str, int] | None:
    """total, available and used bytes from /proc/meminfo; None if a field is missing."""
    fields = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if name in ("MemTotal", "MemAvailable") and parts and parts[0].isdigit():
            fields[name] = int(parts[0]) * 1024
    if len(fields) != 2:
        return None
    total, available = fields["MemTotal"], fields["MemAvailable"]
    return {"total": total, "available": available, "used": max(0, total - available)}


def parse_swap(text: str) -> dict[str, int] | None:
    """total and used swap bytes from /proc/meminfo; None if a field is missing."""
    fields = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if name in ("SwapTotal", "SwapFree") and parts and parts[0].isdigit():
            fields[name] = int(parts[0]) * 1024
    if len(fields) != 2:
        return None
    return {"total": fields["SwapTotal"],
            "used": max(0, fields["SwapTotal"] - fields["SwapFree"])}


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="replace")
    except OSError:
        return None


class HostLoad:
    """The machine's CPU (average of its cores) and memory in percent, and its network in and out
    in KiB/s over its physical interfaces (common/netdev.py), for the coordinator. For the
    dashboard's graphs of a machine it is not on, also `cpu` (busy percent per core), `memory`
    (total, available and used bytes) and `disk`, the fullest file system under `roots`
    (common/disk.py `fullest`), each null when not read.

    CPU and network are the change between two samples, so the first call has neither. Calls closer together
    than `min_span_s` give the last answer again: a worker asks on every claim and heartbeat."""

    def __init__(self, proc: Path = PROC, min_span_s: float = 2.0,
                 clock: Callable[[], float] = time.monotonic, net: Path = netdev.SYS_NET,
                 roots: dict[str, str] | None = None) -> None:
        self.proc, self.min_span_s, self.clock, self.net = proc, min_span_s, clock, net
        self.roots = roots or {}
        self._cpu: list[tuple[int, int]] = []
        self._net: tuple[int, int] | None = None
        self._at: float | None = None
        self._last: dict[str, Any] = {"cpu_pct": None, "cores": None, "mem_pct": None,
                                      "net_in_kib_s": None, "net_out_kib_s": None,
                                      "cpu": None, "memory": None, "disk": None}

    def sample(self) -> dict[str, Any]:
        now = self.clock()
        if self._at is not None and now - self._at < self.min_span_s:
            return self._last
        span, self._at = (now - self._at if self._at is not None else 0.0), now
        stat = read(self.proc / "stat")
        cores = parse_cpu(stat) if stat else []
        shares = cpu_percent(self._cpu, cores)
        self._cpu = cores
        meminfo = read(self.proc / "meminfo")
        memory = parse_memory(meminfo) if meminfo else None
        net = netdev.totals(self.net)
        flow = netdev.rates(self._net, net, span)
        self._net = net
        self._last = {
            "cpu_pct": round(sum(shares) / len(shares), 1) if shares else None,
            "cores": len(cores) or None,
            "mem_pct": round(memory["used"] / memory["total"] * 100, 1)
            if memory and memory["total"] else None,
            "net_in_kib_s": flow[0] if flow else None,
            "net_out_kib_s": flow[1] if flow else None,
            "cpu": shares, "memory": memory,
            "disk": disk.fullest(self.roots) if self.roots else None,
        }
        return self._last
