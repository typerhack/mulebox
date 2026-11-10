"""Pause and boost of a running job, as the coordinator's heartbeat reply asks (M14.3).

The coordinator keeps what the owner asked (coordinator/job_control.py); every heartbeat reply
says `paused` and `boost` while they are on, and this brings the machine in line with it.

- Pause freezes the job's unit (the cgroup freezer: its processes stop where they are, nothing
  is killed) and pauses its Compose containers. Resume unpauses them, then thaws the unit, so a
  container is up again before the job's commands talk to it.
- Boost raises the CPU and disk weight of the job's unit and its containers far above everything
  else on the machine, which keeps the default; the coordinator stops giving the machine new
  jobs meanwhile. Containers that start later are boosted with the next reply.

The same class steers a GitHub run on its runner (runners/runner_controls.py): there the "unit"
is the runner's service and the containers are found by their Compose folder, not by a label.

Docker can be slow, so changes run on a background thread (background.py) and the loop never
waits; a change that fails is tried again with the next reply. Before a job is stopped its pause
is released at once (`release`), as Docker does not stop a paused container.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mulebox.common import compose
from mulebox.common.log import get_logger
from mulebox.worker import background
from mulebox.worker.docker import DockerError

LOG = get_logger("worker.controls")
BOOST_WEIGHT = 10000  # the top of cgroup v2's cpu.weight and io.weight
JOB_WEIGHT = 50  # a job unit's own (systemd.py)
BOOST_SHARES, NORMAL_SHARES = 262144, 2621  # docker's cpu-shares for weight 10000 and 100


@dataclass(frozen=True)
class Wanted:
    paused: bool = False
    boost: bool = False


def wanted(body: dict[str, Any]) -> Wanted:
    return Wanted(bool(body.get("paused")), bool(body.get("boost")))


def containers(docker: Any, job_id: str) -> list[str]:
    """The ids of the job's running or paused containers, by the label mulebox puts on them."""
    if docker is None:
        return []
    return docker.lines("ps", "--quiet", "--filter", f"label={compose.LABEL_JOB}={job_id}")


class JobControls:
    """What has been applied to one job, and the change in progress."""

    def __init__(self, find: Callable[[], list[str]] | None = None,
                 applied: Wanted | None = None) -> None:
        self.find = find  # the containers to steer; by default the job's, by its label
        self.applied = applied if applied is not None else Wanted()
        self.task: Any = None

    def _containers(self, docker: Any, job: Any) -> list[str]:
        return self.find() if self.find is not None else containers(docker, job.job_id)

    def follow(self, body: dict[str, Any], job: Any, executor: Any, docker: Any) -> None:
        """Start bringing `job` in line with a heartbeat reply; a no-op while one is running."""
        if self.task is not None:
            if not self.task.done:
                return
            if self.task.error is not None:
                LOG.warning("controls of %s failed (retrying): %s", job.job_id, self.task.error)
            self.task = None
        want = wanted(body)
        if job.handle is None or (want == self.applied and not want.boost):
            return  # before the unit starts there is nothing to freeze; it is done then
        self.task = background.start_thread(lambda: self._apply(want, job, executor, docker))

    def _apply(self, want: Wanted, job: Any, executor: Any, docker: Any) -> None:
        ids = self._containers(docker, job)
        if want.boost or self.applied.boost:
            executor.prioritize(job.handle, want.boost)
            for cid in ids:
                docker.run("update", "--cpu-shares",
                           str(BOOST_SHARES if want.boost else NORMAL_SHARES), cid)
        if want.paused and not self.applied.paused:
            executor.freeze(job.handle, True)
            for cid in ids:
                docker.run("pause", cid)
            LOG.info("paused %s (%d containers)", job.job_id, len(ids))
        elif self.applied.paused and not want.paused:
            self._unpause(job, executor, docker, ids)
        self.applied = want

    def _unpause(self, job: Any, executor: Any, docker: Any, ids: list[str]) -> None:
        for cid in ids:
            try:
                docker.run("unpause", cid)
            except DockerError as exc:  # one already running, or gone: thaw the rest anyway
                LOG.warning("could not unpause %s of %s: %s", cid, job.job_id, exc)
        executor.freeze(job.handle, False)
        LOG.info("resumed %s", job.job_id)

    def release(self, job: Any, executor: Any, docker: Any) -> None:
        """Before the job is stopped: undo a pause now, waiting for a change in progress."""
        if self.task is not None:
            self.task.wait(30.0)
            self.task = None
        if self.applied.paused and job.handle is not None:
            try:
                self._unpause(job, executor, docker, self._containers(docker, job))
            except Exception as exc:  # noqa: BLE001 - the stop goes on regardless
                LOG.warning("could not resume %s before stopping it: %s", job.job_id, exc)
        self.applied = Wanted()
