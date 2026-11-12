"""Pause and boost of a GitHub run on its runner, as the owner asked (coordinator/job_control.py).

A run does not live in a mulebox unit: it runs in the runner's own service,
`mulebox-runner@<name>.service`, and its Compose containers run in Docker's groups, found by their
Compose folder inside the runner's `_work` (runner_meter.CiContainers). So pausing freezes that
service, listener and all, and pauses the containers; boosting raises the service's CPU and disk
weight and the containers' shares. The rest is the job's own code (worker/controls.JobControls).

A frozen listener stops answering GitHub, which may give up on the runner and fail the run if the
freeze lasts long; the owner chose to have it anyway.

When a run's reservation is gone (its run ended, or was released) while it was paused or boosted,
its service is thawed and set back at once, or the runner would stay frozen with no job to show
for it. After a worker restart nothing is known of what was applied, so the first round sets the
service as the coordinator says, undoing a freeze or boost left from before.

An isolated runner (place.py) has no service: its job runs in one container, which is paused and
given CPU shares in its place (ContainerUnit), found by `place(runner)`.
"""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState
from mulebox.runners.names import RunnerUsageError, unit_name
from mulebox.worker.controls import BOOST_WEIGHT, JobControls, Wanted

LOG = get_logger("runners.controls")
SERVICE_WEIGHT = 50  # the runner unit's own (machine/systemd/mulebox-runner@.service)
_RUNNING = (JobState.STARTING, JobState.RUNNING)


class RunnerUnit:
    """The runner's service in the shape JobControls drives: `handle` is the unit's name."""

    def __init__(self, systemctl: Callable[..., Any]) -> None:
        self._systemctl = systemctl

    def freeze(self, handle: str, on: bool) -> None:
        self._systemctl("freeze" if on else "thaw", handle)

    def prioritize(self, handle: str, on: bool) -> None:
        weight = BOOST_WEIGHT if on else SERVICE_WEIGHT
        self._systemctl("set-property", "--runtime", handle, f"CPUWeight={weight}",
                        f"IOWeight={weight}")


class ContainerUnit:
    """An isolated runner's container in the same shape: `handle` is the container's name."""

    def __init__(self, docker: Any) -> None:
        self.docker = docker

    def freeze(self, handle: str, on: bool) -> None:
        self.docker.run("pause" if on else "unpause", handle)

    def prioritize(self, handle: str, on: bool) -> None:
        from mulebox.runners.place_container import CPU_SHARES
        from mulebox.worker.controls import BOOST_SHARES

        self.docker.run("update", "--cpu-shares", str(BOOST_SHARES if on else CPU_SHARES), handle)


def _no_place(runner: str) -> str | None:
    return None


class RunnerControls:
    """Called once a supervision round with the reservations the coordinator listed."""

    def __init__(self, unit: RunnerUnit, docker: Any,
                 containers: Callable[[str], list[str]],
                 place: Callable[[str], str | None] = _no_place) -> None:
        self.unit, self.docker, self.containers, self.place = unit, docker, containers, place
        # job id -> its controls, its target, what steers it (the service or the container)
        self.held: dict[str, tuple[JobControls, Any, Any]] = {}

    def follow(self, jobs: list[dict[str, Any]]) -> None:
        seen = set()
        for job in jobs:
            runner, job_id = job.get("runner"), job.get("job_id")
            if job.get("state") not in _RUNNING or not isinstance(runner, str):
                continue
            try:
                handle = unit_name(runner)
            except RunnerUsageError:  # a name the runner tools would refuse: leave it alone
                continue
            seen.add(job_id)
            if job_id not in self.held:  # nothing known: set it as asked, whatever was left
                container = self.place(runner)
                if container:
                    controls = JobControls(find=list, applied=Wanted())
                    target, steer = container, ContainerUnit(self.docker)
                else:
                    controls = JobControls(find=lambda r=runner: self.containers(r),
                                           applied=Wanted(paused=True, boost=True))
                    target, steer = handle, self.unit
                self.held[job_id] = (controls, SimpleNamespace(job_id=job_id, handle=target),
                                     steer)
            controls, target, steer = self.held[job_id]
            controls.follow(job, target, steer, self.docker)
        for job_id in [job_id for job_id in self.held if job_id not in seen]:
            controls, target, steer = self.held.pop(job_id)
            if controls.applied.boost:
                try:
                    steer.prioritize(target.handle, False)
                except Exception as exc:  # noqa: BLE001 - the next run starts at the default
                    LOG.warning("could not end the boost of %s: %s", target.handle, exc)
            controls.release(target, steer, self.docker)
