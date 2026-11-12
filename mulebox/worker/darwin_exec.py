"""Executor for macOS nodes: the process-group executor, kept across a worker restart.

macOS has no systemd, so a job is a process group (executor.py `SubprocessExecutor`): timeout,
stop, cancel and freeze work on the group. What a systemd unit gives for free is added here:

- **Orphans.** A unit outlives the worker and `list_orphans` finds it by name. A process group
  has no name, so each job leaves a record, `<staging>/job-groups/<unit name>`, holding its
  group id and the start time of its first process. A worker started again reads them: a group
  still alive whose first process is the one recorded (or gone, as the group id cannot be
  reused while the group exists) is the job's, and is stopped. A record of a group that ended,
  or whose id now belongs to another process, is only removed.
- **A lower priority.** Units get a CPU weight of 50, half the default, so the machine's own use
  comes first. Here the job starts under `nice -n 5`. Boost cannot undo that: macOS lets only
  root raise a priority. So boost changes the job's containers only (controls.py), not its own
  processes, and the docs say so.

A process that starts a session of its own leaves the group and is not stopped with it; systemd
would have caught it. Records go through safepath, inside the staging root.
"""

from __future__ import annotations

import json
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mulebox.common import command, safepath
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.worker.executor import (
    STOP_GRACE_S,
    UNIT_PREFIX,
    ProcessHandle,
    RunSpec,
    SubprocessExecutor,
    group_alive,
)

LOG = get_logger("worker.darwin_exec")
NICE = 5
RECORDS = "job-groups"

StartTime = Callable[[int], str | None]


def process_start(pid: int) -> str | None:
    """When process `pid` started, as `ps` prints it; None when there is no such process."""
    try:
        done = command.run(["ps", "-o", "lstart=", "-p", str(pid)], timeout_s=10)
    except command.CommandError:
        return None
    text = done.stdout.strip() if done.returncode == 0 else ""
    return text or None


def _signalled(pgid: int, sig: int) -> bool:
    """Send `sig` to the group; False once nothing in it can take a signal. macOS answers EPERM,
    not ESRCH, for a group left with exited processes nobody has reaped yet."""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def stop_group(pgid: int, grace_s: float, sleep=time.sleep, clock=time.monotonic) -> None:
    """SIGTERM the group, SIGKILL whatever is left after `grace_s`."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not _signalled(pgid, sig):
            return
        end = clock() + grace_s
        while _signalled(pgid, 0):
            if clock() >= end:
                break
            sleep(0.05)
        else:
            return


@dataclass
class DarwinExecutor(SubprocessExecutor):
    records: Path | None = None  # `<staging>/job-groups`; None keeps no records (tests)
    roots: safepath.Roots | None = None
    start_time: StartTime = process_start
    nice: int = NICE
    _stop: Callable[[int, float], None] = field(default=stop_group, repr=False)

    def start(self, spec: RunSpec) -> ProcessHandle:
        niced = RunSpec(spec.name, ("nice", "-n", str(self.nice), *spec.argv), spec.cwd,
                        spec.env, spec.log_path, spec.timeout_s)
        handle = super().start(niced)
        try:
            self._record(spec.name, handle.pgid)
        except (OSError, MuleboxError) as exc:  # it runs; only a restart's clean-up misses it
            LOG.warning("could not record the process group of %s: %s", spec.name, exc)
        return handle

    def _finish(self, handle: ProcessHandle, returncode: int) -> int:
        code = super()._finish(handle, returncode)
        try:
            self._forget(handle.spec.name)
        except (OSError, MuleboxError) as exc:  # a stale record is checked, not trusted
            LOG.warning("could not remove the record of %s: %s", handle.spec.name, exc)
        return code

    def list_orphans(self) -> list[str]:
        """Live groups of this executor, and of a worker that ran before it on this machine."""
        names = set(super().list_orphans())
        for name, (pgid, started) in self._recorded().items():
            if name in self.running:
                continue
            if self._ours(pgid, started):
                names.add(name)
            else:
                self._forget(name)
        return sorted(names)

    def kill(self, name: str) -> None:
        if name in self.running:
            super().kill(name)
            return
        found = self._recorded().get(name)
        if found is not None and self._ours(*found):
            LOG.warning("stopping the process group %d of %s", found[0], name)
            self._stop(found[0], self.grace_s)
        self._forget(name)

    def _ours(self, pgid: int, started: str | None) -> bool:
        if not group_alive(pgid):
            return False
        now = self.start_time(pgid)
        return now is None or now == started  # first process gone: the id is still the group's

    # --- records -------------------------------------------------------------------------

    def _record(self, name: str, pgid: int) -> None:
        if self.records is None or self.roots is None:
            return
        folder = safepath.ensure_dir(self.records, self.roots)
        draft = folder / f".{name}.new"
        draft.write_text(json.dumps({"pgid": pgid, "started": self.start_time(pgid)}),
                         encoding="utf-8")
        draft.replace(folder / name)

    def _forget(self, name: str) -> None:
        if self.records is not None and self.roots is not None:
            safepath.remove_tree(self.records / name, self.roots)

    def _recorded(self) -> dict[str, tuple[int, str | None]]:
        if self.records is None or not self.records.is_dir():
            return {}
        found = {}
        for path in sorted(self.records.iterdir()):
            if not path.name.startswith(UNIT_PREFIX) or path.is_symlink():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                found[path.name] = (int(data["pgid"]), data.get("started"))
            except (OSError, ValueError, KeyError, TypeError):
                LOG.warning("unreadable job record %s; left alone", path)
        return found


def for_node(staging: Path, roots: safepath.Roots) -> DarwinExecutor:
    return DarwinExecutor(grace_s=STOP_GRACE_S, records=staging / RECORDS, roots=roots)
