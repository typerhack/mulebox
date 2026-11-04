"""What a job is doing, from what this machine can tell cheaply (docs/design.md, Time limits).

Two file reads every SAMPLE_S and nothing else, in the worker's loop:

- **Output**: bytes reaching the job's raw log (the agent notes when).
- **CPU**: `/proc/stat`, as the dashboard's graphs read it, plus iowait: a job waiting on a disk
  is busy too. Over a sample, at least BUSY_CORE_SHARE of one core counts as active.
- **Network**: `/proc/net/dev`, every interface but loopback. At least NET_ACTIVE_KIB_S counts.

CPU and network are the machine's, not the job's. Nothing narrower sees everything a job does:
containers run outside the job's unit, in the container's control group or none at all (an image
build, a `docker run` of the job's own), and systemd has no per-unit network counters for a
user's units. So a quiet job beside another busy one counts as active. That is the safe side
of this: the time limit still ends such a job, while a silent job doing real work must never
be read as idle. The thresholds sit above what an idle machine does, including services
waiting in containers, a dashboard viewer and ssh.

`idle_s`, the number that can stop a job, is null whenever part of this is unknown: no `/proc`,
the first sample not taken yet, or the `images` stage, which is often quiet and can spend its
CPU on a build with no output. Null is never read as idle (coordinator/attendance.py).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.proc import IDLE, PROC, core_times
from mulebox.common.status import IMAGES

SAMPLE_S = 30.0
BUSY_CORE_SHARE = 0.10  # of one core: idle databases in containers stay below this
NET_ACTIVE_KIB_S = 4.0  # about 256 KiB a minute: more than a dashboard and ssh make
USER_HZ = 100.0  # the unit of /proc/stat on every Linux this runs on

Counters = tuple[float, int]  # busy CPU seconds, network bytes
Reader = Callable[[], Counters | None]


def busy_seconds(text: str) -> float:
    """Busy time of all cores, waiting for a disk included."""
    return sum(sum(values) - values[IDLE] for values in core_times(text)) / USER_HZ


def net_bytes(text: str) -> int:
    """Received plus sent bytes of every interface but loopback, from /proc/net/dev."""
    total = 0
    for line in text.splitlines():
        name, colon, rest = line.partition(":")
        fields = rest.split()
        if colon and name.strip() != "lo" and len(fields) > 8:
            total += int(fields[0]) + int(fields[8])
    return total


def read_counters(proc: Path = PROC) -> Counters | None:
    """The machine's counters now; None where there is no /proc (macOS in development)."""
    try:
        cpu = (proc / "stat").read_text(encoding="ascii", errors="replace")
        net = (proc / "net" / "dev").read_text(encoding="ascii", errors="replace")
        return busy_seconds(cpu), net_bytes(net)
    except (OSError, ValueError, IndexError):
        return None


class MachineMeter:
    """The machine's last reading and the last time it was busy; shared by a worker's jobs."""

    def __init__(self, read: Reader = read_counters) -> None:
        self._read = read
        self._last: Counters | None = None
        self._at = 0.0
        self.busy_at: float | None = None  # agent clock; None until a sample has been taken
        self.cpu_pct: float | None = None
        self.net_kib_s: float | None = None

    def update(self, now: float) -> None:
        """Take a sample once SAMPLE_S has passed. A failed read forgets everything."""
        if self._last is not None and now - self._at < SAMPLE_S:
            return
        counters = self._read()
        if counters is None:
            self._last, self.busy_at, self.cpu_pct, self.net_kib_s = None, None, None, None
            return
        if self._last is not None and now > self._at:
            span = now - self._at
            self.cpu_pct = round(max(0.0, counters[0] - self._last[0]) / span * 100.0, 1)
            self.net_kib_s = round(max(0, counters[1] - self._last[1]) / 1024.0 / span, 1)
            if self.cpu_pct >= BUSY_CORE_SHARE * 100.0 or self.net_kib_s >= NET_ACTIVE_KIB_S:
                self.busy_at = now
            elif self.busy_at is None:
                self.busy_at = self._at
        self._last, self._at = counters, now

    def report(self, started_at: float, output_at: float, stage: str | None,
               now: float) -> dict[str, Any]:
        """The `activity` of a heartbeat, for a job with these times (agent clock)."""
        output_idle = max(0.0, now - max(started_at, output_at))
        idle = None
        if self.busy_at is not None and stage != IMAGES:
            idle = round(min(output_idle, now - self.busy_at), 1)
        return {"output_idle_s": round(output_idle, 1), "idle_s": idle,
                "cpu_pct": self.cpu_pct, "net_kib_s": self.net_kib_s}
