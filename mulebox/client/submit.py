"""`mulebox check` / `mulebox run`: snapshot, submit, upload, watch (interfaces-m1.md, Client).

The job log goes to stdout unchanged; mulebox's own lines go to stderr with a `mulebox:`
prefix, so an agent reading the output sees what it would see running the command
locally. The exit code is the job's (see report.exit_code_for).

Ctrl-C sends `cancel`, waits up to 15 s for the job to finish and returns 130. A watch
stream that drops (Wi-Fi blip, laptop sleep) is reopened from the last log offset, for 4
minutes while this client holds the job's lease, for 30 minutes when it does not.

With `detach` the job is left to run once its snapshot is uploaded: the job id goes to
stdout and the client exits. The upload has to finish first, because the snapshot is here.
A coordinator too old for detached jobs would cancel this one when its lease ran out, so
a reply that does not echo `detached` cancels the job and fails.

`timeout_min` is no limit: every that many minutes the stream carries a check-in, printed as a
warning, and the person or agent decides. Check-ins and results from while away: attention.py.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TextIO

from mulebox.client import attention, report, summary
from mulebox.client.job_body import job_request, submit_body
from mulebox.client.remote import CoordinatorError, StreamEnded, request
from mulebox.client.snapshot import current_fingerprint, make_snapshot
from mulebox.common.config import ProjectConfig
from mulebox.common.config_jobs import for_job
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import Message, MessageType
from mulebox.common.ssh import RemoteError, SSHUnavailable

CANCEL_WAIT_S = 15.0
CANCEL_POLL_S = 1.0
WATCH_RETRIES = 24  # with the delay: keep trying for 4 min, inside the 300 s client lease
PATIENT_RETRIES = 180  # 30 min; without the lease nothing is lost by waiting longer
WATCH_RETRY_DELAY_S = 10.0
DETACH_HINT = ("this may take a while; next time add --detach and follow the job with "
               "mulebox events")


class WatchLost(MuleboxError):
    """The job was submitted, but the live view could not reconnect to the build machine."""


class RemoteLike(Protocol):
    def call(self, msg: Message) -> Message: ...
    def upload(self, job_id: str, path: Path, sha256: str) -> Message: ...
    def watch(self, job_id: str, offset: int = 0, lease: bool = True,
              log: bool = True) -> Iterator[Message]: ...


@dataclass
class Streams:
    out: TextIO = field(default_factory=lambda: sys.stdout)
    err: TextIO = field(default_factory=lambda: sys.stderr)
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic


def run_job(
    project: ProjectConfig,
    target: str | Sequence[str],
    root: Path,
    remote: RemoteLike,
    streams: Streams | None = None,
    detach: bool = False,
    again: bool = False,
) -> int:
    """Run a job on the build machines as if it ran here; return its exit code.

    With `detach`, return 0 once the job is queued, with its id on stdout."""
    io = streams or Streams()
    job, argv = job_request(project, target)
    project, dropped = for_job(project, target if isinstance(target, str) else None)
    if dropped:
        report.status(io.err, left_out(dropped))
    try:
        snap = make_snapshot(root, project.exclude)
    except KeyboardInterrupt:
        report.status(io.err, "cancelled before the job was submitted")
        return report.EXIT_CANCELLED
    watcher = Watcher(remote, io)
    watcher.suggest_detach = not detach
    try:
        for path in snap.skipped_links:
            report.status(io.err, f"skipped symlink pointing outside the project: {path}")
        report.status(io.err, f"snapshot {snap.files} files, {report.format_size(snap.size)}")
        body = submit_body(project, job, argv, snap, detach,
                           reuse=isinstance(target, str) and not again)
        reply = remote.call(request(MessageType.SUBMIT, **body))
        watcher.job_id = reply.body["job_id"]
        report.status(io.err, f"job {watcher.job_id} ({project.project} {job}) submitted")
        report.dashboard_hint(io.err, reply.body, watcher.job_id)
        attention.tell(reply.body, io.err)
        already = reply.body.get("already")
        if isinstance(already, dict):
            report.status(io.err, attention.already_line(already))
            if already.get("state") == "finished":
                if detach:  # an id on stdout, as ever; `mulebox wait` gives the result
                    io.out.write(f"{watcher.job_id}\n")
                    io.out.flush()
                    return 0
                return report.exit_code_for(already)
        if detach and reply.body.get("detached") is not True:
            _refuse_detach(remote, watcher.job_id)
        if reply.body.get("state") == "uploading":
            remote.upload(watcher.job_id, snap.path, snap.sha256)
        snap.discard()
        if detach:
            _left_running(watcher.job_id, io)
            return 0
        result = watcher.follow()
    except KeyboardInterrupt:
        return watcher.cancel()
    finally:
        snap.discard()
    stale_check(root, project, snap.fingerprint, io)
    watcher.finish(result)
    return report.exit_code_for(result)


def left_out(names: Sequence[str]) -> str:
    """The notice for `env:` entries a job goes without."""
    what = f"entry {names[0]}, which uses" if len(names) == 1 else (
        f"entries {', '.join(names)}, which use")
    return f"this job leaves out the env: {what} a port it does not have"


def _refuse_detach(remote: RemoteLike, job_id: str) -> None:
    remote.call(request(MessageType.CANCEL, job_id=job_id))
    raise CoordinatorError("the build machine's mulebox is too old for --detach, so the job "
                           "was cancelled. Upgrade it (docs/install.md), or run without --detach.")


def _left_running(job_id: str, io: Streams) -> None:
    io.out.write(f"{job_id}\n")
    io.out.flush()
    report.status(io.err, f"job {job_id} runs on without this client, and finishes even if "
                  f"you go away. Be pinged when it ends: mulebox wait {job_id}, in the background. "
                  f"Follow it: mulebox events --job {job_id} --json. Or check later: mulebox "
                  f"status {job_id}; the next mulebox command here tells you its result too")


def stale_check(root: Path, project: ProjectConfig, fingerprint: str, io: Streams) -> None:
    """Warn when the project's files are no longer the ones the job ran on."""
    try:
        changed = current_fingerprint(root, project.exclude) != fingerprint
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

    watch_options: dict[str, Any] = {}
    suggest_detach = False

    def __init__(self, remote: RemoteLike, io: Streams) -> None:
        self.remote, self.io = remote, io
        self.job_id = ""
        self.offset = 0
        self.tail = summary.LogTail()
        self.connected = False  # a message has arrived on some stream
        self._suggested = False
        self._last_line: str | None = None
        self._notices: set[Any] = set()  # a reconnect sends the latest again

    def follow(self, lease: bool = True) -> dict[str, Any]:
        failures = 0
        while True:
            try:
                for msg in self.remote.watch(self.job_id, self.offset, lease,
                                             **self.watch_options):
                    failures = 0
                    self.connected = True
                    if self.handle(msg):
                        return msg.body
            except (SSHUnavailable, RemoteError, StreamEnded) as exc:
                self._raise_unless_dropped(exc, lease)
                failures += 1
                if failures > (WATCH_RETRIES if lease else PATIENT_RETRIES):
                    raise WatchLost(
                        f"lost the connection to the build machine ({exc}). Job "
                        f"{self.job_id} may still be running there; see how it ended with "
                        f"`mulebox wait {self.job_id}`."
                    ) from exc
                report.status(self.io.err, "connection lost, reconnecting")
                self.io.sleep(WATCH_RETRY_DELAY_S)

    def _raise_unless_dropped(self, exc: Exception, lease: bool) -> None:
        """Before the first message there is no connection to lose. A client that just
        submitted knows the machine is there; one that only came to look fails at once."""
        if not self.connected and (not lease or isinstance(exc, RemoteError)):
            raise exc

    def attach(self) -> dict[str, Any]:
        """Follow a job without holding its lease, as `wait`, `events` and `logs -f` do."""
        try:
            return self.follow(lease=False)
        except SSHUnavailable as exc:
            raise WatchLost(f"cannot reach the build machine ({exc}). Job {self.job_id} is not "
                            "affected; run this again once the machine is back.") from exc

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
            if self.suggest_detach and not self._suggested and report.long_wait(body):
                self._suggested = True
                report.status(self.io.err, DETACH_HINT)
            found = attention.notice(self.job_id, body)
            if found is not None and found[0] not in self._notices:
                self._notices.add(found[0])
                report.status(self.io.err, found[1])
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
        """The last lines of all, after the log and its container logs: the outcome, then what
        went wrong. Everything else a command has to say comes first, so the error stays last."""
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
