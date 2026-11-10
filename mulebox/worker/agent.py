"""The worker loop: recovery, claim, run, heartbeat, clean up, report.

`Agent.step(now)` is one iteration and does no sleeping; `serve()` runs recovery and then
calls it until asked to stop.

Per job: fetch snapshot, prepare the workspace, `job_update running`, start the unit, then each
step ship new log text, poll the process, heartbeat every 3 s with what the job is doing
(activity.py). It is stopped on `cancel: true`, when the coordinator says it is over, or when no
reply came for 120 s (the lease). After it ends: flush the log, `job_update cleaning`, remove
what it left (cleaner.py), `result`. Stages go out with the log. Cleanup runs beside the loop
(background.py), so heartbeats, cancels and supervision go on while Docker is slow, and the job
keeps its lease, also while the coordinator is unreachable; the reports follow once it
answers. A job holds its slot until its result is out (agent_end.py). With a supervisor, each step also
lets it watch this worker's runner reservations (runners/supervise.py; every 10 s).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.proc import HostLoad
from mulebox.common import compose, status
from mulebox.common.config import NodeConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.common.safepath import RemovalDenied, remove_tree
from mulebox.common.status import ENVIRONMENT, PREPARE, TOOLCHAIN
from mulebox.worker import activity, advert, background, job_meter, runspec
from mulebox.worker import project_home, reclaim, toolchains, workspace
from mulebox.worker.agent_end import HEARTBEAT_S, Ending
from mulebox.worker.agent_skip import Skipping
from mulebox.worker.cleaner import Cleaner
from mulebox.worker.docker import Docker
from mulebox.worker.executor import Executor, RunSpec
from mulebox.worker.job import ActiveJob, outcome_for
from mulebox.worker.link import CoordinatorLink, LinkError, request
from mulebox.common.redact import StreamRedactor, secret_values
from mulebox.worker.logtail import LogTailer
from mulebox.worker.paths import NodePaths
from mulebox.worker.ports import PortPool

LOG = get_logger("worker.agent")
POLL_S = 0.5
FINISHING_POLL_S = 0.05  # an agent is waiting for this result, on nothing but this loop
LEASE_S = 120.0
RETRY_S = 5.0  # pause between calls after the coordinator failed to answer
SHUTDOWN_WAIT_S = 60.0  # for cleanups in progress; systemd allows the stop 90 s


class Agent(Ending, Skipping):
    def __init__(self, node: NodeConfig, link: CoordinatorLink, executor: Executor,
                 paths: NodePaths, clock: Callable[[], float] = time.time,
                 supervisor: Any = None, docker: Docker | None = None) -> None:
        self.node, self.link, self.executor, self.paths = node, link, executor, paths
        self.clock = clock
        self.supervisor = supervisor  # runners.supervise.Supervisor, or None
        self.docker = docker or Docker()
        self.cleaner = Cleaner(paths, node.name, docker)
        self.ports = PortPool()
        self.meter = activity.MachineMeter()
        self.host = HostLoad()  # the machine's CPU and memory, sent with claims and heartbeats
        self.machine = runspec.Machine(node.name, paths, docker, self.ports, node.job_env)
        self.active: dict[str, ActiveJob] = {}
        self.finishing: list[ActiveJob] = []
        self.install_toolchain = lambda paths, name, version: toolchains.install(
            paths, name, version, machine_env=node.job_env)
        self.retry_at = 0.0
        self.fresh = True  # tell the coordinator on the first claim that we (re)started
        self.last_reply = 0.0  # agent clock of the last answer from the coordinator

    # -- coordinator calls -------------------------------------------------------------
    def _online(self, now: float) -> bool:
        return now >= self.retry_at

    def _call(self, msg: Message, now: float) -> Message:
        try:
            reply = self.link.call(msg)
        except LinkError as exc:
            LOG.warning("coordinator unreachable: %s", exc)
            self.retry_at = now + RETRY_S
            raise
        self.last_reply = max(self.last_reply, now)
        if reply.type is MessageType.ERROR:
            LOG.warning("coordinator refused %s: %s", msg.type, reply.body.get("message"))
        return reply

    def _sender(self, now: float) -> Callable[[Message], Message]:
        return lambda msg: self._call(msg, now)

    def recover(self) -> None:
        """Stop orphan `mulebox-job-*` units, then clean what jobs left behind."""
        for name in self.executor.list_orphans():
            LOG.warning("stopping orphan unit %s", name)
            self.executor.kill(name)
        for what in self.cleaner.recover():
            LOG.warning("cleaned up leftover job %s", what)

    def step(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        for job in list(self.active.values()):
            self._tend(job, now)
        for job in list(self.finishing):
            self._deliver(job, now)
        if self.supervisor is not None and self._online(now):
            try:
                self.supervisor.tick(now, self._sender(now))
            except LinkError:
                pass
        if self._free_slots() > 0 and self._online(now):
            self._claim(now)

    def _free_slots(self) -> int:
        """A slot is free only after its job's cleanup and result."""
        return self.node.slots - len(self.active) - len(self.finishing)

    def wait_s(self) -> float:
        """How long `serve` waits before the next step."""
        return FINISHING_POLL_S if self.finishing else POLL_S

    def _claim(self, now: float) -> None:
        msg = request(MessageType.CLAIM, **advert.fields(self.node, self.paths, self.host),
                      free_slots=self._free_slots(), restarted=self.fresh)
        try:
            reply = self._call(msg, now)
        except LinkError:
            return
        if reply.type is not MessageType.ERROR:
            self.fresh = False  # the coordinator has released our old jobs
        if reply.type is MessageType.CLAIM_OK:
            self._start(reply.body, now)

    def _start(self, claim: dict[str, Any], now: float) -> None:
        job_id, attempt_id = claim["job_id"], claim["attempt_id"]
        project = claim["project"]
        safe = self.paths.is_safe_job(project, job_id)
        log_path = self.paths.job_dir(project, job_id) / "out.log" if safe else None
        tailer = LogTailer(log_path, job_id, attempt_id, request,
                           StreamRedactor(secret_values(self.node.job_env)))
        job = ActiveJob(job_id, attempt_id, project, tailer, started_at=now, last_heartbeat=now,
                        uses_docker=compose.COMPOSE_FILES_KEY in (claim.get("env") or {}),
                        take=[p for p in claim.get("take") or [] if isinstance(p, str)])
        job.meter = job_meter.for_job(job_id, job.uses_docker, self.docker)
        self.active[job_id] = job
        job.steps.begin(PREPARE, now)
        LOG.info("claimed %s (%s, attempt %s)", job_id, project, attempt_id)
        job.launch = lambda when: self._launch(job, claim, log_path, when)
        try:
            gaps = toolchains.missing(self.paths, claim.get("toolchain") or {})
        except MuleboxError as exc:
            self._not_started(job, exc, now)
            return
        if not gaps:
            job.launch(now)
            return
        job.steps.begin(TOOLCHAIN, now)
        names = ", ".join(" ".join(gap) for gap in gaps)
        tailer.note(f"mulebox: installing {names} on this machine, once for every job after it\n")
        job.install = background.start_thread(
            lambda: toolchains.install_missing(self.paths, gaps, self.install_toolchain))

    def _launch(self, job: ActiveJob, claim: dict[str, Any], log_path: Path, now: float) -> None:
        try:
            spec = self._prepare(job, claim, log_path)
            reply = self._call(request(MessageType.JOB_UPDATE, job_id=job.job_id,
                                       state=JobState.RUNNING.value, attempt_id=job.attempt_id),
                               now)
            if reply.type is MessageType.ERROR or reply.body.get("cancel"):
                self._end(job, Outcome.CANCELLED, None, now)
                return
            job.handle = self.executor.start(spec)
        except LinkError:
            self._end(job, Outcome.INTERRUPTED, None, now)
        except (MuleboxError, OSError) as exc:
            self._not_started(job, exc, now)

    def _not_started(self, job: ActiveJob, exc: Exception, now: float) -> None:
        LOG.error("job %s could not start: %s", job.job_id, exc)
        job.tailer.note(f"{status.NOT_STARTED_NOTE} {exc}\n")
        self._end(job, Outcome.FAILED, None, now)

    def _after_install(self, job: ActiveJob, now: float) -> None:
        task, job.install = job.install, None
        if task.error is not None:
            self._not_started(job, task.error, now)
        else:
            job.steps.begin(PREPARE, now)
            job.launch(now)

    def _prepare(self, job: ActiveJob, claim: dict[str, Any], log_path: Path) -> RunSpec:
        scratch = workspace.job_dir(self.paths, job.project, job.job_id)
        snapshot = scratch / "snapshot.tar.gz"
        self.link.fetch_snapshot(job.job_id, snapshot)
        job.branch = claim.get("branch")
        synced = self._into_home(job, snapshot)
        src = job.tree = synced.tree
        remove_tree(snapshot, self.paths.roots)
        job.tailer.note(f"mulebox: project folder {src}, {synced.changed} files changed\n")
        settled = bool(claim.get("install") or claim.get("setup"))
        claim = {**self._with_install(job, self._with_setup(job, claim, synced), synced),
                 "deps_settled": settled}
        job.steps.begin(ENVIRONMENT, self.clock())
        bins = toolchains.path_for(self.paths, claim.get("toolchain") or {})
        spec, notes = runspec.build(self.machine, job.job_id, claim, src, log_path, bins,
                                    job.steps.marker, scratch)
        for note in notes:
            job.tailer.note(f"mulebox: {note}\n")
        return spec

    def _into_home(self, job: ActiveJob, snapshot: Path) -> project_home.Synced:
        """The job's files into the project's worktree; a crash can leave root's files there."""
        branch = job.branch
        try:
            return project_home.prepare(self.paths, job.project, branch, job.job_id, snapshot)
        except (RemovalDenied, PermissionError):
            if self.docker is None:
                raise
        tree = project_home.tree_for(self.paths, job.project, branch)
        reclaim.reclaim_tree(self.docker, self.paths, tree, job.job_id, self.node.name)
        return project_home.prepare(self.paths, job.project, branch, job.job_id, snapshot)

    def _tend(self, job: ActiveJob, now: float) -> None:
        self.meter.update(now)
        job.meter.update(now)
        job.last_output = now if job.tailer.read_new() else job.last_output
        if self._online(now):
            try:
                job.tailer.send(self._sender(now))
            except LinkError:
                pass
        if job.install is not None and job.install.done:
            self._after_install(job, now)
            if job.job_id not in self.active:
                return
        code = self.executor.poll(job.handle) if job.handle is not None else None
        if code is not None:
            self._end(job, outcome_for(code, self.executor.timed_out(job.handle)), code, now)
            return
        if now - job.last_heartbeat >= HEARTBEAT_S and self._online(now):
            self._heartbeat(job, now)
        silent = now - max(job.started_at, self.last_reply)
        if job.job_id in self.active and silent >= LEASE_S:
            LOG.error("no reply from the coordinator for %.0f s; stopping %s",
                      silent, job.job_id)
            self._end(job, Outcome.INTERRUPTED, None, now)

    def _ping(self, job: ActiveJob, now: float) -> Message | None:
        job.last_heartbeat = now
        msg = request(MessageType.HEARTBEAT, job_id=job.job_id, lease="worker",
                      attempt_id=job.attempt_id, load=self.host.sample(), activity=activity.report(
                          self.meter, job.meter, job.started_at, job.last_output,
                          job.steps.stage, job.steps.last_line, now))
        try:
            return self._call(msg, now)
        except LinkError:
            return None

    def _heartbeat(self, job: ActiveJob, now: float) -> None:
        reply = self._ping(job, now)
        if reply is None:
            return
        if reply.body.get("cancel"):
            LOG.info("cancel requested for %s", job.job_id)
            self._end(job, Outcome.CANCELLED, None, now)
        elif reply.type is MessageType.ERROR or reply.body.get("state") == JobState.FINISHED:
            LOG.warning("coordinator no longer runs %s; stopping it", job.job_id)
            self._end(job, Outcome.INTERRUPTED, None, now)
        else:
            job.controls.follow(reply.body, job, self.executor, self.docker)

    def shutdown(self, now: float | None = None) -> None:
        """Stop every running job as interrupted and try to report once."""
        now = self.clock() if now is None else now
        for job in list(self.active.values()):
            self._end(job, Outcome.INTERRUPTED, None, now)
        deadline = time.monotonic() + SHUTDOWN_WAIT_S
        for job in list(self.finishing):
            if job.cleanup is not None:
                job.cleanup.wait(max(0.0, deadline - time.monotonic()))
            self._deliver(job, now)
