"""Whether one job is doing anything (docs/design.md, Time limits).

The machine's readings cannot say: on a real machine with a desktop and a VPN they never came
near idle, so a stuck job looked active for its whole life. So only the job counts here:

- its own processes, the systemd unit: at least UNIT_CPU_SHARE of a core. A sleeping process uses
  nothing measurable and a quiet download a few percent, so this can be low.
- its compose services, found by label: at least SERVICE_CPU_SHARE of a core together, as
  databases waiting in containers use a little all the time, or NET_ACTIVE_KIB_S of their traffic.

Blind spot, accepted by the user: a `docker run` or `docker build` of the job's own has no label
and runs outside the unit. It counts only through its output.

`busy_at` is None when part of this is unknown, and unknown is never idle (worker/activity.py).
"""

from __future__ import annotations

from collections.abc import Callable

from mulebox.common import compose
from mulebox.worker import background, cgroups
from mulebox.worker.docker import Docker
from mulebox.worker.executor import unit_name

SAMPLE_S = 10.0  # also how current a job's card is on the dashboard (web/src/lib/doing.ts)
UNIT_CPU_SHARE = 0.01  # of one core
SERVICE_CPU_SHARE = 0.10  # of one core: idle databases in containers stay below this
NET_ACTIVE_KIB_S = 4.0  # about 256 KiB a minute
_UNIT, _SERVICE, _NET = "unit", "service:", "net:"

Reading = dict[str, float]  # counters by source; a source may come and go
Reader = Callable[[], Reading | None]


class ContainerList(background.Polled[list[str]]):
    """The job's containers, by label, asked of Docker beside the loop (background.Polled)."""

    def __init__(self, docker: Docker, job_id: str) -> None:
        super().__init__(lambda: docker.lines(
            "ps", "--quiet", "--no-trunc", "--filter", f"label={compose.LABEL_JOB}={job_id}"))

    def ids(self) -> list[str] | None:
        return self.value()


def read_job(job_id: str, containers: ContainerList | None) -> Reading | None:
    """The job's counters. None if its unit cannot be read or its containers are not known."""
    used = cgroups.cpu_seconds(cgroups.unit_group(unit_name(job_id)))
    if used is None:
        return None
    ids = containers.ids() if containers is not None else []
    if ids is None:
        return None
    reading = {_UNIT: used}
    for container in ids:
        group = cgroups.container_group(container)
        cpu = cgroups.cpu_seconds(group) if group else None
        net = cgroups.group_net_bytes(group) if group else None
        if cpu is not None:
            reading[f"{_SERVICE}{container}"] = cpu
        if net is not None:
            reading[f"{_NET}{container}"] = float(net)
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
        self.cpu_pct: float | None = None

    def update(self, now: float) -> None:
        """Take a sample once SAMPLE_S has passed. A failed read forgets everything."""
        if self._tried is not None and now - self._tried < SAMPLE_S:
            return
        self._tried = now
        reading = self._read()
        if reading is None:
            self._last, self._at, self.busy_at, self.cpu_pct = None, None, None, None
            return
        if self._last is not None and self._at is not None and now > self._at:
            self._judge(reading, self._last, now - self._at, now, self._at)
        self._last, self._at = reading, now

    def _judge(self, now_read: Reading, last: Reading, span: float, now: float,
               before: float) -> None:
        unit = _grown(now_read, last, _UNIT) / span
        services = _grown(now_read, last, _SERVICE) / span
        net_kib_s = _grown(now_read, last, _NET) / 1024.0 / span
        self.cpu_pct = round((unit + services) * 100.0, 1)
        if unit >= UNIT_CPU_SHARE or services >= SERVICE_CPU_SHARE or net_kib_s >= NET_ACTIVE_KIB_S:
            self.busy_at = now
        elif self.busy_at is None:
            self.busy_at = before


def for_job(job_id: str, uses_docker: bool, docker: Docker) -> JobMeter:
    containers = ContainerList(docker, job_id) if uses_docker else None
    return JobMeter(lambda: read_job(job_id, containers))
