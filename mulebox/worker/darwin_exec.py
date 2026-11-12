"""Executor for macOS nodes: the process-group executor, kept across a worker restart.

macOS has no systemd, so a job is a process group (executor.py `SubprocessExecutor`): timeout,
stop, cancel and freeze work on the group. What a systemd unit gives for free is added here:

- **Orphans.** A unit outlives the worker and `list_orphans` finds it by name. A process group
  has no name, so each job leaves a record, `<staging>/job-groups/<unit name>`, holding its
  group id and the start time of its first process. The job's command does not run before
  that record is on disk: it starts behind a gate, a shell that waits for "go" on its stdin,
  so a worker killed in between leaves a shell that exits (75) and runs nothing. A worker
  started again reads the records: a group whose first process is still the recorded one is
  the job's, and is stopped. A record of a group that ended, whose id now belongs to another
  process, or whose first process is gone, is only removed: a group id is reused once a
  group ends, so with its first process gone nothing proves the group is still the job's,
  and leftovers of a job whose main process ended while no worker ran are left alone (systemd
  would have stopped them). When `ps` cannot be run, the record is kept and nothing stopped.
- **A lower priority.** Units get a CPU weight of 50, half the default, so the machine's own use
  comes first. Here the job starts under `nice -n 5`. Boost cannot undo that: macOS lets only
  root raise a priority. So boost changes the job's containers only (controls.py), not its own
  processes, and the docs say so.

A process that starts a session of its own leaves the group and is not stopped with it; systemd
would have caught it. Records are written and read through safefile.py, inside the staging
root, never through a symlink.
"""

from __future__ import annotations

import contextlib
import json
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from mulebox.common import command, safefile, safepath
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.worker.executor import (
    STOP_GRACE_S,
    UNIT_PREFIX,
    ExecutorError,
    ProcessHandle,
    RunSpec,
    SubprocessExecutor,
    group_alive,
    signal_group,
)

LOG = get_logger("worker.darwin_exec")
NICE = 5
RECORDS = "job-groups"
# Runs the job's command only once the worker writes "go" (after its record is on disk).
GATE = 'read -r go || exit 75; [ "$go" = go ] || exit 75; exec "$@" </dev/null'

StartTime = Callable[[int], str | None]


def process_start(pid: int) -> str | None:
    """When process `pid` started, as `ps` prints it; None when there is no such process.
    Raises CommandError when `ps` cannot tell (it could not run, or printed an error)."""
    done = command.run(["ps", "-o", "lstart=", "-p", str(pid)], timeout_s=10)
    text = done.stdout.strip() if done.returncode == 0 else ""
    if not text and done.returncode != 0 and done.stderr.strip():
        raise command.CommandError(f"ps failed: {done.stderr.strip()}")
    return text or None


def stop_group(pgid: int, grace_s: float, sleep=time.sleep, clock=time.monotonic) -> None:
    """SIGTERM the group (then SIGCONT, so a frozen job can take it), SIGKILL whatever is left
    after `grace_s`."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not signal_group(pgid, sig):
            return
        if sig == signal.SIGTERM:
            signal_group(pgid, signal.SIGCONT)
        end = clock() + grace_s
        while signal_group(pgid, 0):
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
        gated = RunSpec(spec.name, ("/bin/sh", "-c", GATE, "mulebox-gate", "nice", "-n",
                                    str(self.nice), *spec.argv),
                        spec.cwd, spec.env, spec.log_path, spec.timeout_s)
        handle = self._spawn(gated, subprocess.PIPE)
        gate = handle.proc.stdin
        try:
            self._record(spec.name, handle.pgid)
            gate.write(b"go\n")
            gate.close()
        except (OSError, MuleboxError) as exc:  # no record: the job must not run
            with contextlib.suppress(OSError):
                gate.close()  # the gate reads nothing and exits 75
            handle.proc.wait()
            self.running.pop(spec.name, None)
            with contextlib.suppress(OSError, MuleboxError):
                self._forget(spec.name)
            raise ExecutorError(f"cannot start {spec.name}: no record of its process group "
                                f"({exc})") from exc
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
            verdict = self._ours(pgid, started)
            if verdict:
                names.add(name)
            elif verdict is False:
                self._forget(name)
        return sorted(names)

    def kill(self, name: str) -> None:
        if name in self.running:
            super().kill(name)
            return
        found = self._recorded().get(name)
        verdict = None if found is None else self._ours(*found)
        if verdict:
            LOG.warning("stopping the process group %d of %s", found[0], name)
            self._stop(found[0], self.grace_s)
        if verdict is not None or found is None:
            self._forget(name)

    def pgid_of(self, name: str) -> int | None:
        """The process group of a job this executor runs, for its readings (darwin_jobs.py)."""
        handle = self.running.get(name)
        return handle.pgid if handle is not None else None

    def _ours(self, pgid: int, started: str | None) -> bool | None:
        """True: the job's group, its first process still the recorded one. False: gone, or not
        provably the job's. None: `ps` could not tell, so the record is kept for a later try."""
        if not group_alive(pgid):
            return False
        try:
            now = self.start_time(pgid)
        except MuleboxError as exc:
            LOG.warning("cannot tell whether process group %d is a job's: %s", pgid, exc)
            return None
        if now is None:
            LOG.warning("process group %d lives on without its first process; it cannot be "
                        "proven to be the job's, so it is left alone", pgid)
            return False
        return started is not None and now == started

    # --- records -------------------------------------------------------------------------

    def _record(self, name: str, pgid: int) -> None:
        if self.records is None or self.roots is None:
            return
        folder = safepath.ensure_dir(self.records, self.roots)
        record = {"pgid": pgid, "started": self.start_time(pgid)}
        safefile.write_text(folder / name, json.dumps(record), self.roots, 0o600)

    def _forget(self, name: str) -> None:
        if self.records is not None and self.roots is not None:
            safepath.remove_tree(self.records / name, self.roots)

    def _recorded(self) -> dict[str, tuple[int, str | None]]:
        if self.records is None or self.roots is None or not self.records.is_dir():
            return {}
        found = {}
        for path in sorted(self.records.iterdir()):
            if not path.name.startswith(UNIT_PREFIX):
                continue
            try:
                data = json.loads(safefile.read_text(path, self.roots, 4096) or "")
                found[path.name] = (int(data["pgid"]), data.get("started"))
            except (OSError, MuleboxError, ValueError, KeyError, TypeError):
                LOG.warning("unreadable job record %s; left alone", path)
        return found


def for_node(staging: Path, roots: safepath.Roots) -> DarwinExecutor:
    return DarwinExecutor(grace_s=STOP_GRACE_S, records=staging / RECORDS, roots=roots)
