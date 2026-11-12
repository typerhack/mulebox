"""Running a job's process tree: the Executor contract and the subprocess executor.

`Executor` is what the agent loop talks to. `SystemdExecutor` (systemd.py) is the one used
on Linux nodes, `DarwinExecutor` (darwin_exec.py) on macOS nodes. `SubprocessExecutor` here, which
the macOS one builds on, has the same behaviour with a process group instead of a systemd unit:

- the job runs in a new session (its own process group), output appended to the log;
- `poll` enforces the timeout; when the main process ends, whatever is left in the group
  is stopped too (like systemd's KillMode=control-group);
- `stop` sends SIGTERM to the group, then SIGKILL after the grace period (10 s).
A process that starts its own session escapes the group; only systemd catches those.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from mulebox.common.errors import MuleboxError

UNIT_PREFIX = "mulebox-job-"
STOP_GRACE_S = 10.0


class ExecutorError(MuleboxError):
    """A job process could not be started or controlled."""


@dataclass(frozen=True)
class RunSpec:
    name: str  # unit name, `mulebox-job-<job_id>`
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]  # added to (systemd: set in) the job environment
    log_path: Path
    timeout_s: float | None = None  # None: the coordinator decides when the job ends


class Executor(Protocol):
    def start(self, spec: RunSpec) -> Any: ...
    def poll(self, handle: Any) -> int | None: ...
    def timed_out(self, handle: Any) -> bool: ...
    def stop(self, handle: Any) -> None: ...
    def list_orphans(self) -> list[str]: ...
    def kill(self, name: str) -> None: ...
    def freeze(self, handle: Any, on: bool) -> None: ...
    def prioritize(self, handle: Any, on: bool) -> None: ...


def unit_name(job_id: str) -> str:
    return UNIT_PREFIX + job_id


def exit_code_from_status(returncode: int) -> int:
    """Popen returncode to a shell-style exit code (signal N -> 128 + N)."""
    return 128 - returncode if returncode < 0 else returncode


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class ProcessHandle:
    spec: RunSpec
    proc: subprocess.Popen
    deadline: float
    timed_out: bool = False
    exit_code: int | None = None
    stopped: bool = False

    @property
    def pgid(self) -> int:
        return self.proc.pid


@dataclass
class SubprocessExecutor:
    grace_s: float = STOP_GRACE_S
    clock: Callable[[], float] = time.monotonic
    running: dict[str, ProcessHandle] = field(default_factory=dict)

    def start(self, spec: RunSpec) -> ProcessHandle:
        if spec.name in self.running:
            raise ExecutorError(f"{spec.name} is already running")
        env = {**os.environ, **spec.env}
        try:
            with open(spec.log_path, "ab") as log:
                proc = subprocess.Popen(
                    list(spec.argv), cwd=spec.cwd, env=env, stdin=subprocess.DEVNULL,
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                )
        except OSError as exc:
            raise ExecutorError(f"cannot start {spec.name}: {exc}") from exc
        limit = float("inf") if spec.timeout_s is None else spec.timeout_s
        handle = ProcessHandle(spec, proc, self.clock() + limit)
        self.running[spec.name] = handle
        return handle

    def poll(self, handle: ProcessHandle) -> int | None:
        if handle.exit_code is not None:
            return handle.exit_code
        code = handle.proc.poll()
        if code is None and self.clock() >= handle.deadline:
            handle.timed_out = True
            self.stop(handle)
            return handle.exit_code
        if code is None:
            return None
        self._terminate_group(handle)  # leftovers of a finished main process
        return self._finish(handle, code)

    def timed_out(self, handle: ProcessHandle) -> bool:
        return handle.timed_out

    def stop(self, handle: ProcessHandle) -> None:
        handle.stopped = True
        self._terminate_group(handle)
        if handle.exit_code is None:
            self._finish(handle, handle.proc.wait())

    def freeze(self, handle: ProcessHandle, on: bool) -> None:
        """Stop or continue the job's process group (no cgroup freezer without systemd)."""
        self._signal(handle.pgid, signal.SIGSTOP if on else signal.SIGCONT)

    def prioritize(self, handle: ProcessHandle, on: bool) -> None:
        """Nothing to raise without systemd: a plain process group has no weight to set."""

    def list_orphans(self) -> list[str]:
        """Jobs started by this executor whose process group is still alive."""
        return sorted(n for n, h in self.running.items()
                      if n.startswith(UNIT_PREFIX) and group_alive(h.pgid))

    def kill(self, name: str) -> None:
        handle = self.running.get(name)
        if handle is not None:
            self.stop(handle)

    def _finish(self, handle: ProcessHandle, returncode: int) -> int:
        handle.exit_code = exit_code_from_status(returncode)
        self.running.pop(handle.spec.name, None)
        return handle.exit_code

    def _terminate_group(self, handle: ProcessHandle) -> None:
        """SIGTERM the group, wait up to grace_s for it to empty, then SIGKILL."""
        if not self._signal(handle.pgid, signal.SIGTERM):
            handle.proc.poll()
            return
        end = time.monotonic() + self.grace_s
        while time.monotonic() < end:
            handle.proc.poll()  # reap the leader so it stops counting as a member
            if not group_alive(handle.pgid):
                return
            time.sleep(0.05)
        self._signal(handle.pgid, signal.SIGKILL)
        handle.proc.wait()
        end = time.monotonic() + self.grace_s
        while group_alive(handle.pgid) and time.monotonic() < end:
            time.sleep(0.02)

    @staticmethod
    def _signal(pgid: int, sig: int) -> bool:
        try:
            os.killpg(pgid, sig)
            return True
        except ProcessLookupError:
            return False
