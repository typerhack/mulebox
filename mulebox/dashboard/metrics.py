"""Machine metrics for the dashboard graphs: CPU per core, memory, disk, own overhead.

Read from `/proc` on Linux. The proc root, the disk-usage function and the clocks are
injectable, so tests feed fixed files; on a machine without `/proc` (macOS during
development) CPU and memory are None and nothing fails.

- CPU: busy share per core between two samples of `/proc/stat` (busy = total - idle -
  iowait), in percent. The first sample has no previous one, so it reports None.
- Memory: `/proc/meminfo` MemTotal and MemAvailable (used = total - available), bytes.
- Disk: file system usage of each mulebox root, one entry per file system (roots on the same
  device are listed together; common/disk.py `usage_by_device`, which workers report too).
- Swap: `/proc/meminfo` SwapTotal and SwapFree, bytes, read with memory.
- Jobs' memory: the working set (`memory.current` less `inactive_file`) of what mulebox runs for jobs (`jobs_memory`), the agent job
  units, the services of GitHub runners running a job, and the containers of both.
- Self: CPU share and resident memory of the dashboard process itself (the overhead).
"""

from __future__ import annotations

import os
import resource
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.disk import usage_by_device as disk_usage
from mulebox.common.proc import PROC, cpu_percent, parse_cpu, parse_memory, parse_swap, read
from mulebox.worker import cgroups

__all__ = ["Sampler", "cpu_percent", "disk_usage", "jobs_memory", "parse_cpu", "parse_memory",
           "parse_swap"]


def jobs_memory(containers: list[str], runners: list[str], root: Path = cgroups.ROOT) -> int | None:
    """Bytes charged to the running agent job units, to the services of `runners` (those running
    a GitHub job: an idle listener is no job) and to `containers`; None without cgroup v2. A
    group gone between the listing and the read counts nothing."""
    if not (root / "cgroup.controllers").is_file():
        return None
    groups = cgroups.job_unit_groups(root)
    groups += [g for name in runners if (g := cgroups.runner_group(name, root)) is not None]
    groups += [g for cid in containers if (g := cgroups.container_group(cid, root)) is not None]
    return sum(cgroups.memory_bytes(group) or 0 for group in groups)


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

    def memory_and_swap(self) -> tuple[dict[str, int] | None, dict[str, int] | None]:
        text = read(self.proc / "meminfo")
        return (parse_memory(text), parse_swap(text)) if text else (None, None)

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
        memory, swap = self.memory_and_swap()
        return {"cpu": self.cpu(), "memory": memory, "swap": swap, "self": self.own()}
