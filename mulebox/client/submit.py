"""`mulebox check` / `mulebox run`: snapshot, submit, upload, watch (interfaces-m1.md, Client).

The job log goes to stdout unchanged; mulebox's own lines go to stderr with a `mulebox:`
prefix, so an agent reading the output sees what it would see running the command
locally. The exit code is the job's (see report.exit_code_for).

Ctrl-C sends `cancel`, waits up to 15 s for the job to finish and returns 130. A watch
stream that drops (Wi-Fi blip, laptop sleep) is reopened from the last log offset a few
times, well inside the 120 s client lease.
"""

from __future__ import annotations

import socket
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO

from mulebox.client import report, summary
from mulebox.client.remote import request
from mulebox.client.snapshot import Snapshot, current_fingerprint, make_snapshot
from mulebox.common import compose
from mulebox.common.config import ProjectConfig
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import new_id
from mulebox.common.protocol import Message, MessageType
from mulebox.common.ssh import SSHUnavailable

CANCEL_WAIT_S = 15.0
CANCEL_POLL_S = 1.0
WATCH_RETRIES = 24  # with the delay: keep trying for 4 min, inside the 300 s client lease
WATCH_RETRY_DELAY_S = 10.0
RUN_JOB_NAME = "run"  # job name sent for `mulebox run`


class WatchLost(MuleboxError):
    """The job was submitted, but the live view could not reconnect to the build machine."""


class RemoteLike(Protocol):
    def call(self, msg: Message) -> Message: ...
    def upload(self, job_id: str, path: Path, sha256: str) -> Message: ...
    def watch(self, job_id: str, offset: int = 0, lease: bool = True) -> Iterator[Message]: ...


@dataclass
class Streams:
    out: TextIO = field(default_factory=lambda: sys.stdout)
    err: TextIO = field(default_factory=lambda: sys.stderr)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic


def job_request(project: ProjectConfig, target: str | Sequence[str]) -> tuple[str, list[str]]:
    """(job name, argv): a job from .mulebox.yml runs as `bash -e -c <script>`, so the first
    failing line of a multi-line job fails it, as in a GitHub Actions `run:` step."""
    if isinstance(target, str):
        return target, ["bash", "-e", "-c", project.jobs[target]]
    return RUN_JOB_NAME, list(target)


def job_env(project: ProjectConfig) -> dict[str, str]:
    """The project's `env:` values, plus the compose file list (common/compose.py)."""
    env = dict(project.env)
    if project.compose:
        env[compose.COMPOSE_FILES_KEY] = compose.join_files(project.compose)
    return env


def submit_body(project: ProjectConfig, job: str, argv: list[str], snap: Snapshot) -> dict:
    return {
        "project": project.project,
        "job": job,
        "argv": argv,
        "idempotency_key": new_id("sub"),
        "fingerprint": snap.fingerprint,
        "base_commit": snap.base_commit,
        "branch": snap.branch,
        "client": socket.gethostname() or "client",
        "setup": project.setup,
        "toolchain": dict(project.toolchain),
        "env": job_env(project),
        "needs": list(project.all_needs),
        "timeout_min": project.timeout_min,
    }


def run_job(
    project: ProjectConfig,
    target: str | Sequence[str],
    root: Path,
    remote: RemoteLike,
    streams: Streams | None = None,
) -> int:
    """Run a job on the build machines as if it ran here; return its exit code."""
    io = streams or Streams()
    job, argv = job_request(project, target)
    try:
        snap = make_snapshot(root, project.exclude)
    except KeyboardInterrupt:
        report.status(io.err, "cancelled before the job was submitted")
        return report.EXIT_CANCELLED
    watcher = Watcher(remote, io)
    try:
        for path in snap.skipped_links:
            report.status(io.err, f"skipped symlink pointing outside the project: {path}")
        report.status(io.err, f"snapshot {snap.files} files, {report.format_size(snap.size)}")
        reply = remote.call(request(MessageType.SUBMIT, **submit_body(project, job, argv, snap)))
        watcher.job_id = reply.body["job_id"]
        report.status(io.err, f"job {watcher.job_id} ({project.project} {job}) submitted")
        if reply.body.get("state") == "uploading":
            remote.upload(watcher.job_id, snap.path, snap.sha256)
        snap.discard()
        result = watcher.follow()
    except KeyboardInterrupt:
        return watcher.cancel()
    finally:
        snap.discard()
    watcher.finish(result)
    _stale_check(root, project, snap, io)
    return report.exit_code_for(result)


def _stale_check(root: Path, project: ProjectConfig, snap: Snapshot, io: Streams) -> None:
    try:
        changed = current_fingerprint(root, project.exclude) != snap.fingerprint
    except Exception:  # the result stands; only the staleness is unknown
        changed = False
    if changed:
        report.status(
            io.err,
            "warning: files changed since the snapshot was taken; this result is stale "
            "(it is for the files as they were at submission). Run the job again.",
        )


class Watcher:
    """Follows one job's watch stream: log to stdout, state changes to stderr."""

    def __init__(self, remote: RemoteLike, io: Streams) -> None:
        self.remote, self.io = remote, io
        self.job_id = ""
        self.offset = 0
        self.tail = summary.LogTail()
        self._last_line: str | None = None

    def follow(self, lease: bool = True) -> dict[str, Any]:
        failures = 0
        while True:
            try:
                for msg in self.remote.watch(self.job_id, self.offset, lease):
                    failures = 0
                    if self.handle(msg):
                        return msg.body
            except SSHUnavailable as exc:
                failures += 1
                if failures > WATCH_RETRIES:
                    raise WatchLost(
                        f"lost the connection to the build machine ({exc}). Job "
                        f"{self.job_id} keeps running there; see its result with "
                        f"`mulebox logs {self.job_id}`."
                    ) from exc
                report.status(self.io.err, "connection lost, reconnecting")
                self.io.sleep(WATCH_RETRY_DELAY_S)

    def handle(self, msg: Message) -> bool:
        """Print what `msg` says; True when it is the final result."""
        body = msg.body
        if msg.type is MessageType.LOG_CHUNK:
            self.write_log(body)
        elif msg.type is MessageType.STATUS_OK:
            line = report.state_line(body)
            if line is not None and line != self._last_line:
                self._last_line = line
                report.status(self.io.err, line)
        return msg.type is MessageType.RESULT

    def write_log(self, body: dict[str, Any]) -> None:
        data = body.get("data") or ""
        raw = data.encode("utf-8", errors="surrogatepass")
        start = body.get("offset", self.offset)
        if not isinstance(start, int) or start + len(raw) <= self.offset:
            return  # already printed (a reconnect replays from the last offset)
        if start < self.offset:
            raw = raw[self.offset - start :]
        self.offset = max(self.offset, start) + len(raw)
        text = raw.decode("utf-8", errors="replace")
        self.tail.feed(text)
        self.io.out.write(text)
        self.io.out.flush()

    def finish(self, result: dict[str, Any]) -> None:
        """The last lines after a job's log: its outcome, then what went wrong."""
        report.status(self.io.err, report.outcome_line(self.job_id, result))
        if summary.wanted(result):
            lines = summary.relevant_lines(self.tail)
            for line in summary.render(self.job_id, result, lines):
                report.status(self.io.err, line)

    def cancel(self) -> int:
        if not self.job_id:
            report.status(self.io.err, "cancelled before the job was submitted")
            return report.EXIT_CANCELLED
        report.status(self.io.err, f"cancelling job {self.job_id}")
        try:
            self.remote.call(request(MessageType.CANCEL, job_id=self.job_id))
            result = self._wait_finished()
        except KeyboardInterrupt:
            result = None
        except Exception as exc:
            report.status(self.io.err, f"cancel request failed: {exc}")
            result = None
        if result is None:
            report.status(
                self.io.err,
                f"job {self.job_id} did not confirm the cancel yet; it stops when its "
                "client lease expires (about 2 minutes)",
            )
        else:
            report.status(self.io.err, report.outcome_line(self.job_id, result))
        return report.EXIT_CANCELLED

    def _wait_finished(self) -> dict[str, Any] | None:
        deadline = self.io.clock() + CANCEL_WAIT_S
        while True:
            reply = self.remote.call(request(MessageType.STATUS, job_id=self.job_id))
            if reply.body.get("state") == "finished":
                return reply.body
            if self.io.clock() >= deadline:
                return None
            self.io.sleep(CANCEL_POLL_S)
