"""Whether one job is doing anything (docs/design.md, Time limits).

The machine's readings cannot say: on a real machine with a desktop and a VPN they never came
near idle, so a stuck job looked active for its whole life. So only the job counts here:

- its own processes, the systemd unit: at least UNIT_CPU_SHARE of a core, or IO_ACTIVE_KIB_S
  read and written (cgroups.py `io_bytes`). A sleeping process uses nothing measurable and a
  quiet download a few percent of CPU, and a slow one next to none, so its bytes count too.
- its compose services, found by label: at least SERVICE_CPU_SHARE of a core together, as
  databases waiting in containers use a little all the time, or NET_ACTIVE_KIB_S of their traffic.

Blind spot, accepted by the user: a `docker run` or `docker build` of the job's own has no label
and runs outside the unit. It counts only through its output.

`busy_at` is None when part of this is unknown, and unknown is never idle (worker/activity.py).

Each reading also carries the memory the job holds (`_MEMORY`, a gauge, not a counter), and the
meter keeps the run's peaks of cores and memory (common/usage.py, docs/design.md, Job usage).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mulebox.common import compose
from mulebox.common.usage import Peaks
from mulebox.worker import background, cgroups
from mulebox.worker.docker import Docker
from mulebox.worker.executor import unit_name

SAMPLE_S = 10.0  # also how current a job's card is on the dashboard (web/src/lib/doing.ts)
UNIT_CPU_SHARE = 0.01  # of one core
SERVICE_CPU_SHARE = 0.10  # of one core: idle databases in containers stay below this
NET_ACTIVE_KIB_S = 4.0  # about 256 KiB a minute
IO_ACTIVE_KIB_S = 4.0  # the job's own processes: read and written, sockets included
_UNIT, _SERVICE, _NET, _IO = "unit", "service:", "net:", "io:"
_MEMORY = "memory"  # bytes held now; never summed as growth (no other source starts with it)

Reading = dict[str, float]  # counters by source; a source may come and go
Reader = Callable[[], Reading | None]


class ContainerList(background.Polled[list[str]]):
    """The job's containers, by label, asked of Docker beside the loop (background.Polled)."""

    def __init__(self, docker: Docker, job_id: str) -> None:
        super().__init__(labelled(docker, job_id))

    def ids(self) -> list[str] | None:
        return self.value()


def read_job(job_id: str, containers: ContainerList | None) -> Reading | None:
    """The job's counters. None if its unit cannot be read or its containers are not known."""
    unit = cgroups.unit_group(unit_name(job_id))
    used = cgroups.cpu_seconds(unit)
    if used is None:
        return None
    ids = containers.ids() if containers is not None else []
    if ids is None:
        return None
    reading = {_UNIT: used}
    memory = cgroups.memory_bytes(unit)
    for pid, value in (cgroups.io_bytes(unit) or {}).items():
        reading[f"{_IO}{pid}"] = float(value)
    for container in ids:
        group = cgroups.container_group(container)
        cpu = cgroups.cpu_seconds(group) if group else None
        net = cgroups.group_net_bytes(group) if group else None
        held = cgroups.memory_bytes(group) if group else None
        if cpu is not None:
            reading[f"{_SERVICE}{container}"] = cpu
        if net is not None:
            reading[f"{_NET}{container}"] = float(net)
        if held is not None and memory is not None:
            memory += held
    if memory is not None:
        reading[_MEMORY] = float(memory)
    return reading


def _grown(now: Reading, before: Reading, source: str) -> float:
    """How much counters of `source` grew; one that just appeared started at zero."""
    return sum(max(0.0, value - before.get(key, 0.0))
               for key, value in now.items() if key.startswith(source))


class JobMeter:
    def __init__(self, read: Reader = lambda: None) -> None:
        self._read = read
        self._last: Reading | None = None
        self._at: float | None = None
        self._tried: float | None = None
        self.busy_at: float | None = None  # agent clock; None while it cannot tell
        self.cpu_busy_at: float | None = None  # the same, CPU and services only, not bytes
        self.cpu_pct: float | None = None
        self.io_kib_s: float | None = None  # the job's own processes; None where not read
        self.peaks = Peaks()

    def update(self, now: float, stage: str | None = None) -> None:
        """Take a sample once SAMPLE_S has passed. A failed read forgets everything but the
        peaks, which are the run's so far. `stage` is the job's stage now, kept with a peak."""
        if self._tried is not None and now - self._tried < SAMPLE_S:
            return
        self._tried = now
        reading = self._read()
        if reading is None:
            self._last, self._at, self.busy_at, self.cpu_pct = None, None, None, None
            self.cpu_busy_at, self.io_kib_s = None, None
            return
        cores = None
        if self._last is not None and self._at is not None and now > self._at:
            cores = self._judge(reading, self._last, now - self._at, now, self._at)
        span = now - self._at if cores is not None and self._at is not None else 0.0
        memory = reading.get(_MEMORY)
        self.peaks.add(cores, None if memory is None else int(memory), stage, (cores or 0) * span)
        self._last, self._at = reading, now

    def _judge(self, now_read: Reading, last: Reading, span: float, now: float,
               before: float) -> float:
        """Judge the span; return the cores the job kept busy in it."""
        unit = _grown(now_read, last, _UNIT) / span
        services = _grown(now_read, last, _SERVICE) / span
        net_kib_s = _grown(now_read, last, _NET) / 1024.0 / span
        io_kib_s = _grown(now_read, last, _IO) / 1024.0 / span
        self.cpu_pct = round((unit + services) * 100.0, 1)
        self.io_kib_s = round(io_kib_s, 1) if any(k.startswith(_IO) for k in now_read) else None
        computing = unit >= UNIT_CPU_SHARE or services >= SERVICE_CPU_SHARE
        if computing:
            self.cpu_busy_at = now
        elif self.cpu_busy_at is None:
            self.cpu_busy_at = before
        if computing or net_kib_s >= NET_ACTIVE_KIB_S or io_kib_s >= IO_ACTIVE_KIB_S:
            self.busy_at = now
        elif self.busy_at is None:
            self.busy_at = before
        return unit + services


def labelled(docker: Docker, job_id: str) -> Callable[[], list[str]]:
    return lambda: docker.lines("ps", "--quiet", "--no-trunc", "--filter",
                                f"label={compose.LABEL_JOB}={job_id}")


def for_job(job_id: str, uses_docker: bool, docker: Docker, executor: Any = None) -> JobMeter:
    """The job's meter: from cgroups on Linux; on a Mac, from its process group, which only the
    executor knows (darwin_exec.py `pgid_of`), and the engine's numbers (darwin_jobs.py)."""
    pgid_of = getattr(executor, "pgid_of", None)
    if pgid_of is not None:
        from mulebox.worker import darwin_jobs

        stats = darwin_jobs.ContainerStats(labelled(docker, job_id)) if uses_docker else None
        return JobMeter(darwin_jobs.JobReader(lambda: pgid_of(unit_name(job_id)), stats))
    containers = ContainerList(docker, job_id) if uses_docker else None
    return JobMeter(lambda: read_job(job_id, containers))
