"""Supervision of runner reservations held on this worker (docs/interfaces-m3.md).

A crashed runner never calls its job-completed hook, so the worker watches its own
reservations: every 10 s it asks the coordinator for them (`runner_jobs`). While the
runner's job process (`Runner.Worker`, found through /proc) is alive, a granted
reservation gets a worker heartbeat, which renews its lease. Once the process has been
gone for 60 s the reservation is released as `interrupted`. A granted reservation's steps and
output also go into its log from the runner's own files, every second (live_log.py).

`runner_alive` reads `/proc/<pid>/cmdline` and `/proc/<pid>/cwd`; the proc root and the
whole check are injectable, so this runs in tests on any system.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.config_reader import NAME_RE
from mulebox.common.log import get_logger
from mulebox.common.mounts import is_within
from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.common.redact import StreamRedactor
from mulebox.runners.live_log import RunnerLog
from mulebox.worker.link import request

LOG = get_logger("runners.supervise")
SUPERVISE_S = 10.0
GONE_S = 60.0
FOLLOW_S = 1.0
CLOCK_SLACK_S = 120.0  # the coordinator's clock may differ from this machine's
PROC_ROOT = Path("/proc")
WORKER_NAMES = frozenset({"Runner.Worker", "Runner.Worker.dll"})


def _under(value: str, folder: Path) -> bool:
    return value.startswith("/") and is_within(Path(os.path.normpath(value)), folder)


def runner_alive(runner_dir: Path, proc_root: Path = PROC_ROOT) -> bool:
    """True if a `Runner.Worker` process runs with its cwd or an argument in `runner_dir`."""
    folder = Path(os.path.realpath(runner_dir))
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "cmdline").read_bytes()
        except OSError:
            continue  # gone, or not ours to read
        args = [os.fsdecode(part) for part in raw.split(b"\0") if part]
        if not any(Path(arg).name in WORKER_NAMES for arg in args):
            continue
        if any(_under(arg, folder) for arg in args):
            return True
        try:
            cwd = os.readlink(entry / "cwd")
        except OSError:
            continue
        if _under(cwd, folder):
            return True
    return False


class Supervisor:
    """Called from the worker loop with the current time and a send function."""

    def __init__(self, worker: str, runners_root: Path,
                 alive: Callable[[Path], bool] = runner_alive,
                 interval_s: float = SUPERVISE_S, gone_s: float = GONE_S,
                 redactor: Callable[[], StreamRedactor] = StreamRedactor) -> None:
        self.worker = worker
        self.runners_root = Path(runners_root)
        self.alive = alive
        self.interval_s = interval_s
        self.gone_s = gone_s
        self.next_at = 0.0
        self.missing: dict[str, float] = {}  # job id -> time its runner was first missed
        self.redactor = redactor
        self.logs: dict[str, tuple[RunnerLog, float]] = {}  # job id -> its log, started after
        self.next_follow = 0.0

    def tick(self, now: float, send: Callable[[Message], Message]) -> None:
        """One supervision round when due. Link errors propagate to the caller."""
        self._follow(now, send)
        if now < self.next_at:
            return
        self.next_at = now + self.interval_s
        reply = send(request(MessageType.RUNNER_JOBS, worker=self.worker))
        if reply.type is not MessageType.QUEUE_OK:
            return
        jobs = [job for job in reply.body.get("jobs", []) if isinstance(job, dict)]
        current = {job.get("job_id") for job in jobs}
        for job_id in list(self.missing):
            if job_id not in current:
                del self.missing[job_id]
        self._track_logs(jobs, current, send)
        for job in jobs:
            self._check(job, now, send)

    def _track_logs(self, jobs: list[dict[str, Any]], current: set[Any],
                    send: Callable[[Message], Message]) -> None:
        for job_id in [job_id for job_id in self.logs if job_id not in current]:
            follower, after = self.logs.pop(job_id)
            try:  # its last step: the completed hook released the slot as the runner ended
                follower.poll(after)
                follower.send(send)
            finally:  # a link error propagates, like the rest of a round
                follower.close()
        for job in jobs:
            job_id, runner, started = job.get("job_id"), job.get("runner"), job.get("started_at")
            if (job_id not in self.logs and job.get("state") != JobState.QUEUED
                    and isinstance(runner, str) and NAME_RE.fullmatch(runner)
                    and isinstance(started, (int, float))):
                follower = RunnerLog(job_id, self.runners_root / runner, request, self.redactor())
                self.logs[job_id] = (follower, started - CLOCK_SLACK_S)

    def _follow(self, now: float, send: Callable[[Message], Message]) -> None:
        if now < self.next_follow or not self.logs:
            return
        self.next_follow = now + FOLLOW_S
        for follower, after in self.logs.values():
            follower.poll(after)
            follower.send(send)

    def _check(self, job: dict[str, Any], now: float,
               send: Callable[[Message], Message]) -> None:
        job_id, runner = job.get("job_id"), job.get("runner")
        if isinstance(runner, str) and NAME_RE.fullmatch(runner) and \
                self.alive(self.runners_root / runner):
            self.missing.pop(job_id, None)
            if job.get("state") != JobState.QUEUED:
                send(request(MessageType.HEARTBEAT, job_id=job_id, lease="worker"))
            return
        since = self.missing.setdefault(job_id, now)
        if now - since < self.gone_s:
            return
        LOG.warning("runner %s has no job process for %.0f s; releasing %s",
                    runner, now - since, job_id)
        reply = send(request(MessageType.RELEASE, job_id=job_id,
                             outcome=Outcome.INTERRUPTED.value))
        if reply.type is not MessageType.ERROR:
            self.missing.pop(job_id, None)
