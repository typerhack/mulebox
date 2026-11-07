"""Machine metrics for the dashboard graphs: CPU per core, memory, disk, own overhead.

Read from `/proc` on Linux. The proc root, the disk-usage function and the clocks are
injectable, so tests feed fixed files; on a machine without `/proc` (macOS during
development) CPU and memory are None and nothing fails.

- CPU: busy share per core between two samples of `/proc/stat` (busy = total - idle -
  iowait), in percent. The first sample has no previous one, so it reports None.
- Memory: `/proc/meminfo` MemTotal and MemAvailable (used = total - available), bytes.
- Disk: file system usage (`shutil.disk_usage`) of each mulebox root, one entry per file
  system (roots on the same device are listed together). Not a `du` of the roots: walking
  job folders and caches would cost far more than the dashboard is allowed to.
- Self: CPU share and resident memory of the dashboard process itself (the overhead).
"""

from __future__ import annotations

import os
import resource
import shutil
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.proc import PROC, cpu_percent, parse_cpu, parse_memory, read

DiskUsage = Callable[[str], Any]
__all__ = ["Sampler", "cpu_percent", "disk_usage", "parse_cpu", "parse_memory"]


def disk_usage(roots: dict[str, str], usage: DiskUsage = shutil.disk_usage
               ) -> list[dict[str, Any]]:
    """One entry per file system holding a root: the root names on it and its usage."""
    by_device: dict[int, dict[str, Any]] = {}
    for name, path in sorted(roots.items()):
        try:
            device = os.stat(path).st_dev
            found = usage(path)
        except OSError:
            continue
        entry = by_device.setdefault(device, {
            "roots": [], "total": found.total, "used": found.used, "free": found.free,
        })
        entry["roots"].append(name)
    return list(by_device.values())


class Sampler:
    """Keeps the previous CPU sample and the process times between calls."""

    def __init__(self, proc: Path = PROC, *, wall: Callable[[], float] = time.monotonic,
                 cpu_time: Callable[[], float] = time.process_time) -> None:
        self.proc = proc
        self.wall, self.cpu_time = wall, cpu_time
        self._cpu: list[tuple[int, int]] = []
        self._self = (wall(), cpu_time())

    def cpu(self) -> list[float] | None:
        text = read(self.proc / "stat")
        now = parse_cpu(text) if text else []
        result = cpu_percent(self._cpu, now)
        self._cpu = now
        return result

    def memory(self) -> dict[str, int] | None:
        text = read(self.proc / "meminfo")
        return parse_memory(text) if text else None

    def own(self) -> dict[str, float | int | None]:
        """CPU percent of one core used by this process since the last call, and its RSS."""
        wall, cpu = self.wall(), self.cpu_time()
        span = wall - self._self[0]
        share = (cpu - self._self[1]) / span * 100 if span > 0 else 0.0
        self._self = (wall, cpu)
        return {"cpu": round(share, 2), "rss": self._rss()}

    def _rss(self) -> int | None:
        text = read(self.proc / "self" / "statm")
        parts = text.split() if text else []
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1]) * os.sysconf("SC_PAGE_SIZE")
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # fallback: peak RSS
        return peak if sys.platform == "darwin" else peak * 1024

    def fast(self) -> dict[str, Any]:
        """The every-2-seconds part of a metrics event."""
        return {"cpu": self.cpu(), "memory": self.memory(), "self": self.own()}
