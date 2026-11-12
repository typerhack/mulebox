"""What a job is doing, as told to the coordinator (docs/design.md, Time limits).

- **Output**: bytes reaching the job's raw log (the agent notes when).
- **The job's CPU and traffic**: worker/job_meter.py. These, with output, decide `idle_s`, the
  number that can stop a job.
- **The machine's CPU and network**: `/proc/stat` and `/proc/net/dev` (macOS: common/host.py), every SAMPLE_S, for whoever
  reads the job's status. They never decide anything: on a real machine a desktop and a VPN kept
  them far above any idle level.

`idle_s` is null whenever part of this is unknown: no reading of the job's unit, its containers
not known yet, or the `images` stage, which is often quiet and can spend its CPU on a build with
no output. Null is never read as idle (coordinator/attendance.py).
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.host import DarwinHost
from mulebox.common.proc import PROC, busy_seconds
from mulebox.common.status import IMAGES
from mulebox.worker.cgroups import net_bytes
from mulebox.worker.job_meter import SAMPLE_S, JobMeter

Counters = tuple[float, int]  # busy CPU seconds, network bytes
Reader = Callable[[], Counters | None]


def read_counters(proc: Path = PROC) -> Counters | None:
    """The machine's counters now, from Linux's /proc; None where there is none."""
    try:
        cpu = (proc / "stat").read_text(encoding="ascii", errors="replace")
        net = (proc / "net" / "dev").read_text(encoding="ascii", errors="replace")
        return busy_seconds(cpu), net_bytes(net)
    except (OSError, ValueError, IndexError):
        return None


def mac_counters() -> Counters | None:
    """The same from macOS (common/darwin_host.py), over its physical interfaces."""
    reading = DarwinHost()
    busy, net = reading.busy_seconds(), reading.net()
    return None if busy is None or net is None else (busy, net[0] + net[1])


def machine_counters() -> Counters | None:
    return mac_counters() if sys.platform == "darwin" else read_counters()


class MachineMeter:
    """The machine's last reading; shared by a worker's jobs."""

    def __init__(self, read: Reader = machine_counters) -> None:
        self._read = read
        self._last: Counters | None = None
        self._at = 0.0
        self.cpu_pct: float | None = None
        self.net_kib_s: float | None = None

    def update(self, now: float) -> None:
        """Take a sample once SAMPLE_S has passed. A failed read forgets everything."""
        if self._last is not None and now - self._at < SAMPLE_S:
            return
        counters = self._read()
        if counters is None:
            self._last, self.cpu_pct, self.net_kib_s = None, None, None
            return
        if self._last is not None and now > self._at:
            span = now - self._at
            self.cpu_pct = round(max(0.0, counters[0] - self._last[0]) / span * 100.0, 1)
            self.net_kib_s = round(max(0, counters[1] - self._last[1]) / 1024.0 / span, 1)
        self._last, self._at = counters, now


def report(machine: MachineMeter, job: JobMeter, started_at: float, output_at: float,
           stage: str | None, last_line: str | None, now: float) -> dict[str, Any]:
    """The `activity` of a heartbeat, for a job with these times (agent clock). `last_line` is
    the stage's last output, redacted: inside `command`, the only sign of which step is on."""
    output_idle = max(0.0, now - max(started_at, output_at))
    idle = None
    if job.busy_at is not None and stage != IMAGES:
        idle = round(min(output_idle, now - job.busy_at), 1)
    return {"output_idle_s": round(output_idle, 1), "idle_s": idle, "job_cpu_pct": job.cpu_pct,
            "cpu_pct": machine.cpu_pct, "net_kib_s": machine.net_kib_s, "last_line": last_line}
