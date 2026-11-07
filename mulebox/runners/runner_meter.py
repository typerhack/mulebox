"""How much CPU a GitHub runner's job uses, for its card on the dashboard.

A runner job does not run in a mulebox unit, so its CPU is read from the runner's own service
group (cgroups.runner_group): the listener's share there is near nothing, so the rest is the
job. Containers the workflow starts itself run outside it and are not counted. A first reading,
or a group that cannot be read, gives None: unknown, never zero.
"""

from __future__ import annotations

from collections.abc import Callable

from mulebox.worker import cgroups

CpuReader = Callable[[str], "float | None"]  # runner name -> CPU seconds so far


def runner_cpu_seconds(runner: str) -> float | None:
    group = cgroups.runner_group(runner)
    return cgroups.cpu_seconds(group) if group is not None else None


class RunnerMeter:
    def __init__(self, read: CpuReader = runner_cpu_seconds) -> None:
        self.read = read
        self._last: dict[str, tuple[float, float]] = {}  # job id -> (CPU seconds, at)

    def cpu_pct(self, job_id: str, runner: str, now: float) -> float | None:
        """Percent of one core the runner used since the last reading of this job."""
        used = self.read(runner)
        last = self._last.get(job_id)
        if used is None:
            self._last.pop(job_id, None)
            return None
        self._last[job_id] = (used, now)
        if last is None or now <= last[1]:
            return None
        return round(max(0.0, used - last[0]) / (now - last[1]) * 100.0, 1)

    def forget(self, keep: set) -> None:
        for job_id in [job_id for job_id in self._last if job_id not in keep]:
            del self._last[job_id]
