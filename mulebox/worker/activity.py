"""What a job is doing, as told to the coordinator (docs/design.md, Time limits).

- **Output**: bytes reaching the job's raw log (the agent notes when).
- **The job's CPU and traffic**: worker/job_meter.py. These, with output, decide `idle_s`, the
  number that can stop a job.
- **The machine's CPU and network**: `/proc/stat` and `/proc/net/dev`, every SAMPLE_S, for whoever
  reads the job's status. They never decide anything: on a real machine a desktop and a VPN kept
  them far above any idle level.

`idle_s` is null whenever part of this is unknown: no reading of the job's unit, its containers
not known yet, or the `images` stage, which is often quiet and can spend its CPU on a build with
no output. Null is never read as idle (coordinator/attendance.py).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.proc import IDLE, PROC, core_times
from mulebox.common.status import IMAGES
from mulebox.worker.cgroups import net_bytes
from mulebox.worker.job_meter import SAMPLE_S, JobMeter

USER_HZ = 100.0  # the unit of /proc/stat on every Linux this runs on

Counters = tuple[float, int]  # busy CPU seconds, network bytes
Reader = Callable[[], Counters | None]


def busy_seconds(text: str) -> float:
    """Busy time of all cores, waiting for a disk included."""
    return sum(sum(values) - values[IDLE] for values in core_times(text)) / USER_HZ


def read_counters(proc: Path = PROC) -> Counters | None:
    """The machine's counters now; None where there is no /proc (macOS in development)."""
    try:
        cpu = (proc / "stat").read_text(encoding="ascii", errors="replace")
        net = (proc / "net" / "dev").read_text(encoding="ascii", errors="replace")
        return busy_seconds(cpu), net_bytes(net)
    except (OSError, ValueError, IndexError):
        return None


class MachineMeter:
    """The machine's last reading; shared by a worker's jobs."""

    def __init__(self, read: Reader = read_counters) -> None:
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
           stage: str | None, now: float) -> dict[str, Any]:
    """The `activity` of a heartbeat, for a job with these times (agent clock)."""
    output_idle = max(0.0, now - max(started_at, output_at))
    idle = None
    if job.busy_at is not None and stage != IMAGES:
        idle = round(min(output_idle, now - job.busy_at), 1)
    return {"output_idle_s": round(output_idle, 1), "idle_s": idle, "job_cpu_pct": job.cpu_pct,
            "cpu_pct": machine.cpu_pct, "net_kib_s": machine.net_kib_s}
