"""How much CPU a GitHub runner's job uses, for its card on the dashboard.

A runner job does not run in a mulebox unit, so its CPU is read from the runner's own service
group (cgroups.runner_group): the listener's share there is near nothing, so the rest is the
job. The containers a workflow starts with Docker Compose run outside that group, in Docker's
scopes, and a step such as `docker compose exec api php artisan test --parallel` does all its
work there: a real CI job kept 8 cores busy while its card read 0.0 cores. So the containers
whose Compose working folder (the label Compose puts on each) is inside the runner's `_work`
folder count too. Docker is asked beside the worker loop (background.Polled), once a round.

On a Mac there are no control groups: the runner's own processes are its launchd agent's process
group, from one `ps` listing (worker/darwin_jobs.py, as for a job), and its containers' CPU comes
from the engine's API, asked beside the loop.

Not counted: a container started with plain `docker run`, which says nothing of where it came
from. A container counts from its second reading, so one that just appeared never adds the CPU
it used before it was seen. A first reading, or a runner group that cannot be read, gives None:
unknown, never zero.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.mounts import is_within
from mulebox.worker import cgroups, darwin_jobs
from mulebox.worker.background import Polled
from mulebox.worker.docker import Docker

WORKDIR_LABEL = "com.docker.compose.project.working_dir"
_RUNNER = "runner"

Reading = dict[str, float]  # CPU seconds by source: the runner, and each of its containers
Reader = Callable[[str], "Reading | None"]  # runner name -> reading


def runner_containers(lines: list[str], runners_root: Path) -> dict[str, list[str]]:
    """`docker ps` lines of `<id>\\t<working folder>` -> runner name -> its containers' ids."""
    root = Path(os.path.normpath(runners_root))
    found: dict[str, list[str]] = {}
    for line in lines:
        container, _, folder = line.partition("\t")
        if not container or not folder.startswith("/"):
            continue
        path = Path(os.path.normpath(folder))
        if not is_within(path, root) or path == root:
            continue
        parts = path.relative_to(root).parts
        if len(parts) >= 2 and parts[1] == "_work":
            found.setdefault(parts[0], []).append(container)
    return found


class CiContainers:
    """Each runner's containers, from one `docker ps` a round. The last answer is kept while a
    new one is late, so a slow daemon does not make the reading jump."""

    def __init__(self, runners_root: Path, docker: Docker | None = None) -> None:
        docker = docker or Docker()
        self._polled = Polled(lambda: runner_containers(docker.lines(
            "ps", "--no-trunc", "--format", f'{{{{.ID}}}}\t{{{{.Label "{WORKDIR_LABEL}"}}}}'),
            Path(runners_root)))
        self._known: dict[str, list[str]] = {}

    def refresh(self) -> None:
        answer = self._polled.value()
        if answer is not None:
            self._known = answer

    def of(self, runner: str) -> list[str]:
        return self._known.get(runner, [])


class PlaceGroups:
    """An isolated runner's job runs in a container, not a service (place.py): its control
    group, from the container the runner's marker names, its id asked of Docker once."""

    def __init__(self, runners_root: Path, docker: Docker | None = None) -> None:
        self.root, self.docker = runners_root, docker
        self._ids: dict[str, str] = {}  # container name -> id

    def group(self, runner: str) -> Path | None:
        from mulebox.runners.supervise import place_container_name

        name = place_container_name(self.root / runner)
        if name is None:
            return None
        if name not in self._ids:
            try:
                self._ids = {name: (self.docker or Docker()).run(
                    "inspect", "--format", "{{.Id}}", name).strip()}
            except Exception:  # noqa: BLE001 - not started yet, or gone: no reading this round
                return None
        return cgroups.container_group(self._ids[name])


def runner_reading(runner: str, containers: CiContainers | None = None,
                   places: PlaceGroups | None = None) -> Reading | None:
    group = cgroups.runner_group(runner)
    if group is None and places is not None:
        group = places.group(runner)
    used = cgroups.cpu_seconds(group) if group is not None else None
    if used is None:
        return None
    reading = {_RUNNER: used}
    for container in containers.of(runner) if containers is not None else []:
        found = cgroups.container_group(container)
        cpu = cgroups.cpu_seconds(found) if found is not None else None
        if cpu is not None:
            reading[container] = cpu
    return reading


class DarwinRunnerReading:
    """`Reader` on a Mac: a job reader per runner (darwin_jobs.JobReader), its traffic left out,
    as only CPU seconds are summed here. The agent's group is asked of launchd once and kept while
    it lives, so a round does not run `launchctl` for every runner."""

    def __init__(self, containers: CiContainers, services: Any,
                 listing: Callable[[], Any] = darwin_jobs.processes) -> None:
        self._containers, self._services, self._listing = containers, services, listing
        self._readers: dict[str, darwin_jobs.JobReader] = {}
        self._groups: dict[str, int] = {}

    def __call__(self, runner: str) -> Reading | None:
        reader = self._readers.get(runner)
        if reader is None:
            stats = darwin_jobs.ContainerStats(lambda: self._containers.of(runner))
            reader = self._readers[runner] = darwin_jobs.JobReader(
                lambda: self._group(runner), stats, self._listing)
        reading = reader()
        if reading is None:
            return None
        return {key: value for key, value in reading.items() if not key.startswith("net:")}

    def _group(self, runner: str) -> int | None:
        known = self._groups.get(runner)
        if known is not None:
            try:
                os.killpg(known, 0)
                return known
            except ProcessLookupError:
                del self._groups[runner]
            except PermissionError:
                return known
        found = self._services.runner_group(runner)
        if found is not None:
            self._groups[runner] = found
        return found


class RunnerMeter:
    @classmethod
    def for_platform(cls, containers: CiContainers, services: Any,
                     platform: str = sys.platform,
                     places: PlaceGroups | None = None) -> "RunnerMeter":
        """cgroups on Linux (and an isolated runner's container), the agent's process group and
        the engine on a Mac."""
        if platform == "darwin":
            return cls(read=DarwinRunnerReading(containers, services), containers=containers)
        return cls(containers=containers, places=places)

    def __init__(self, read: Reader | None = None, containers: CiContainers | None = None,
                 places: PlaceGroups | None = None) -> None:
        self.containers = containers
        self.read = read or (lambda runner: runner_reading(runner, self.containers, places))
        self._last: dict[str, tuple[Reading, float]] = {}  # job id -> (reading, at)

    def new_round(self) -> None:
        """Called once a supervision round, before the cards are read."""
        if self.containers is not None:
            self.containers.refresh()

    def cpu_pct(self, job_id: str, runner: str, now: float) -> float | None:
        """Percent of one core the job used since the last reading of it."""
        reading = self.read(runner)
        last = self._last.get(job_id)
        if reading is None:
            self._last.pop(job_id, None)
            return None
        self._last[job_id] = (reading, now)
        if last is None or now <= last[1]:
            return None
        before, at = last
        used = sum(max(0.0, value - before[key]) for key, value in reading.items() if key in before)
        return round(used / (now - at) * 100.0, 1)

    def forget(self, keep: set) -> None:
        for job_id in [job_id for job_id in self._last if job_id not in keep]:
            del self._last[job_id]
