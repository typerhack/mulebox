"""The worker loop: recovery, claim, run, heartbeat, clean up, report.

`Agent.step(now)` is one iteration and does no sleeping, so tests drive it with an
injected clock, a fake link and the subprocess executor. `serve()` runs recovery and then
calls `step` once per second until asked to stop.

Per job: fetch snapshot, prepare the workspace, `job_update running`, start the unit, then
each step ship new log text, poll the process, heartbeat every 3 s. The job is stopped on
`cancel: true`, when the coordinator says the job is over, or when no reply came for
120 s (the worker lease length). After it ends: flush the log, `job_update cleaning`,
remove what the job left (cleaner.py), `result`. Cleanup runs beside the loop (background.py),
so heartbeats, cancels and supervision go on while Docker is slow, and the job keeps its
lease. It happens even while the coordinator is unreachable; the reports are delivered once
it answers again. No new job is claimed while reports are pending. With a supervisor, each
step also lets it watch this worker's runner reservations (runners/supervise.py; every 10 s).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common import compose, status
from mulebox.common.config import NodeConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.common.safepath import remove_tree
from mulebox.runners.supervise import Supervisor
from mulebox.worker import background, runspec, toolchains, workspace
from mulebox.worker.cleaner import Cleaner
from mulebox.worker.docker import Docker
from mulebox.worker.executor import Executor, RunSpec
from mulebox.worker.job import ActiveJob, outcome_for
from mulebox.worker.link import CoordinatorLink, LinkError, request
from mulebox.worker.logtail import LogTailer
from mulebox.worker.paths import NodePaths
from mulebox.worker.ports import PortPool

LOG = get_logger("worker.agent")
POLL_S = 1.0
HEARTBEAT_S = 3.0  # also how fast a cancel is noticed; the lease is still 120 s
LEASE_S = 120.0
RETRY_S = 5.0  # pause between calls after the coordinator failed to answer
SHUTDOWN_WAIT_S = 60.0  # for cleanups in progress; systemd allows the stop 90 s


class Agent:
    def __init__(self, node: NodeConfig, link: CoordinatorLink, executor: Executor,
                 paths: NodePaths, clock: Callable[[], float] = time.time,
                 supervisor: Any = None, docker: Docker | None = None) -> None:
        self.node, self.link, self.executor, self.paths = node, link, executor, paths
        self.clock = clock
        self.supervisor = supervisor  # runners.supervise.Supervisor, or None
        self.cleaner = Cleaner(paths, node.name, docker)
        self.ports = PortPool()
        self.machine = runspec.Machine(node.name, paths, docker, self.ports, node.job_env)
        self.active: dict[str, ActiveJob] = {}
        self.finishing: list[ActiveJob] = []
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
        if not self.finishing and len(self.active) < self.node.slots and self._online(now):
            self._claim(now)

    def _claim(self, now: float) -> None:
        msg = request(MessageType.CLAIM, worker=self.node.name,
                      capabilities=compose.worker_capabilities(self.node.capabilities),
                      free_slots=self.node.slots - len(self.active),
                      restarted=self.fresh)
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
        safe = _safe(self.paths, project, job_id)
        log_path = self.paths.job_dir(project, job_id) / "out.log" if safe else None
        tailer = LogTailer(log_path, job_id, attempt_id, request)
        job = ActiveJob(job_id, attempt_id, project, tailer, started_at=now, last_heartbeat=now,
                        uses_docker=compose.COMPOSE_FILES_KEY in (claim.get("env") or {}))
        self.active[job_id] = job
        LOG.info("claimed %s (%s, attempt %s)", job_id, project, attempt_id)
        try:
            spec = self._prepare(job, claim, log_path)
            reply = self._call(request(MessageType.JOB_UPDATE, job_id=job_id,
                                       state=JobState.RUNNING.value, attempt_id=attempt_id), now)
            if reply.type is MessageType.ERROR or reply.body.get("cancel"):
                self._end(job, Outcome.CANCELLED, None, now)
                return
            job.handle = self.executor.start(spec)
        except LinkError:
            self._end(job, Outcome.INTERRUPTED, None, now)
        except (MuleboxError, OSError) as exc:
            LOG.error("job %s could not start: %s", job_id, exc)
            tailer.note(f"{status.NOT_STARTED_NOTE} {exc}\n")
            self._end(job, Outcome.FAILED, None, now)

    def _prepare(self, job: ActiveJob, claim: dict[str, Any], log_path: Path) -> RunSpec:
        snapshot = workspace.job_dir(self.paths, job.project, job.job_id) / "snapshot.tar.gz"
        self.link.fetch_snapshot(job.job_id, snapshot)
        src = workspace.prepare(self.paths, job.project, job.job_id, snapshot)
        remove_tree(snapshot, self.paths.roots)
        bins = toolchains.path_for(self.paths, claim.get("toolchain") or {})
        spec, notes = runspec.build(self.machine, job.job_id, claim, src, log_path, bins)
        for note in notes:
            job.tailer.note(f"mulebox: {note}\n")
        return spec

    def _tend(self, job: ActiveJob, now: float) -> None:
        job.tailer.read_new()
        if self._online(now):
            try:
                job.tailer.send(self._sender(now))
            except LinkError:
                pass
        code = self.executor.poll(job.handle)
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
                      attempt_id=job.attempt_id)
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

    # -- ending a job ------------------------------------------------------------------
    def _end(self, job: ActiveJob, outcome: Outcome, exit_code: int | None, now: float) -> None:
        """Stop the process, flush the log, clean up; reports go out via _deliver."""
        if job.handle is not None and self.executor.poll(job.handle) is None:
            self.executor.stop(job.handle)
        job.outcome, job.exit_code = outcome, exit_code
        job.duration_s = max(0.0, now - job.started_at)
        job.tailer.finish()
        self.active.pop(job.job_id, None)
        self.finishing.append(job)
        LOG.info("job %s ended: %s (exit %s)", job.job_id, outcome, exit_code)
        if self._online(now):
            try:
                self._send_cleaning(job, now)
            except LinkError:
                pass
        self._deliver(job, now)

    def _clean(self, job: ActiveJob) -> None:
        if _safe(self.paths, job.project, job.job_id):
            self.cleaner.clean(job.project, job.job_id, job.uses_docker)

    def _cleanup(self, job: ActiveJob) -> None:
        """Start the job's cleanup, or take its outcome; a failed one starts again next step."""
        if job.cleanup is None:
            job.cleanup = background.start_thread(lambda: self._clean(job))
        if not job.cleanup.done:
            return
        task, job.cleanup = job.cleanup, None
        if task.error is not None:
            LOG.error("cleanup of %s failed (retrying): %s", job.job_id, task.error)
            return
        job.cleaned = True
        self.ports.release(job.job_id)

    def _keep_lease(self, job: ActiveJob, now: float) -> None:
        """The job counts for its slot until the result; a slow cleanup must not lose it."""
        if now - job.last_heartbeat >= HEARTBEAT_S and self._online(now):
            self._ping(job, now)

    def _send_cleaning(self, job: ActiveJob, now: float) -> None:
        if job.cleaning_sent:
            return
        job.tailer.send(self._sender(now))
        self._call(request(MessageType.JOB_UPDATE, job_id=job.job_id,
                           state=JobState.CLEANING.value, attempt_id=job.attempt_id), now)
        job.cleaning_sent = True

    def _deliver(self, job: ActiveJob, now: float) -> None:
        if not job.cleaned:
            self._cleanup(job)
            if not job.cleaned:
                self._keep_lease(job, now)
                return
        if not self._online(now):
            return
        try:
            self._send_cleaning(job, now)
            self._call(request(
                MessageType.RESULT, job_id=job.job_id, outcome=job.outcome.value,
                exit_code=job.exit_code, duration_s=round(job.duration_s, 3),
                attempt_id=job.attempt_id), now)
        except LinkError:
            return
        job.result_sent = True
        self.finishing.remove(job)

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


def _safe(paths: NodePaths, project: str, job_id: str) -> bool:
    try:
        paths.job_dir(project, job_id)
    except MuleboxError:
        return False
    return True


def serve(node: NodeConfig, link: CoordinatorLink, executor: Executor, *,
          paths: NodePaths | None = None, stop: threading.Event | None = None,
          docker: Docker | None = None) -> None:
    """Recovery first, then the claim loop until `stop` is set."""
    paths = paths or NodePaths.from_config(node.roots)
    stop = stop or threading.Event()
    agent = Agent(node, link, executor, paths, docker=docker,
                  supervisor=Supervisor(node.name, paths.runners))
    agent.recover()
    LOG.info("worker %s ready (%d slot(s))", node.name, node.slots)
    while not stop.is_set():
        try:
            agent.step()
        except (MuleboxError, OSError) as exc:
            LOG.error("worker step failed: %s", exc)
        stop.wait(POLL_S)
    agent.shutdown()
