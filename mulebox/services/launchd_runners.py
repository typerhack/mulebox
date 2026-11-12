"""GitHub runners as launchd agents on a Mac; launchd.py holds the agents' plumbing.

Each runner is the agent `mulebox-runner-<name>`, which runs `<runners>/<name>/run.sh` from the
runner's folder, as `mulebox-runner@.service` does on Linux:

- `RUNNER_MANUALLY_TRAP_SIG=1`, so run.sh passes a stop on to the listener; launchd then ends
  whatever is left in the agent's process group (it does not abandon the group), as KillMode=mixed.
- `KeepAlive` and 10 s between starts: Restart=always, RestartSec=10. An exit timeout of 5 min,
  as TimeoutStopSec, gives a job time to stop.
- `Nice` 5, as a mulebox job on a Mac (worker/darwin_exec.py): CI and agents' jobs are equals, and
  both yield to the Mac's own use. Only root can raise a priority again, so boost reaches a run's
  containers only (runners/runner_controls.py), as it does for a job.

Pause stops the agent's process group (SIGSTOP), listener and job alike, as systemd's freezer does
the unit; resume continues it. launchd makes each agent the leader of a group of its own; a runner
whose first process is not one is never signalled as a group. A stop or restart continues the
group first, so a paused runner can take its SIGTERM. A process of the run that starts a session of
its own leaves the group and is neither paused nor counted.

A removed runner's definition stays in ~/Library/LaunchAgents, disabled, so it never loads again:
mulebox deletes only inside its roots. Adding a runner of that name again replaces it.
"""

from __future__ import annotations

import os
import re
import signal
from pathlib import Path
from typing import Any

from mulebox.services.base import PREFIX, RUNNING, STOPPED, ServiceError, check_runner

RUNNER_THROTTLE_S = 10
RUNNER_EXIT_S = 300
RUNNER_NICE = 5
_PID = re.compile(r"^\s*pid = (\d+)\s*$", re.M)


def runner_label(name: str) -> str:
    return f"{PREFIX}runner-{check_runner(name)}"


def runner_definition(name: str, folder: Path, path: str, logs: Path) -> dict[str, Any]:
    log = str(logs / f"runner-{check_runner(name)}.log")
    return {
        "Label": runner_label(name),
        "ProgramArguments": [str(folder / "run.sh")],
        "WorkingDirectory": str(folder),
        "EnvironmentVariables": {"RUNNER_MANUALLY_TRAP_SIG": "1", "PATH": path},
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": RUNNER_THROTTLE_S,
        "ExitTimeOut": RUNNER_EXIT_S,
        "Nice": RUNNER_NICE,
        "ProcessType": "Standard",
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }


class LaunchdRunners:
    """The runner half of LaunchdServices (launchd.py), which supplies `_reload`, `_stop`,
    `_restart`, `_state`, `_loaded`, `_env_path` and `_logs`."""

    def runner_check(self, runners: Path) -> None:
        """Nothing to check: an agent runs a runner from wherever its folder is."""

    def runner_start(self, name: str, folder: Path) -> None:
        self._reload(runner_label(name),
                     runner_definition(name, folder, self._env_path(), self._logs()))

    def runner_stop(self, name: str) -> None:
        self._signal_group(name, signal.SIGCONT)
        self._stop(runner_label(name), RUNNER_EXIT_S + 10)

    def runner_restart(self, name: str) -> None:
        self._signal_group(name, signal.SIGCONT)
        self._restart(runner_label(name))

    def runner_state(self, name: str) -> str:
        return RUNNING if self._state(runner_label(name)) == RUNNING else STOPPED

    def runner_freeze(self, name: str, on: bool) -> None:
        if not self._signal_group(name, signal.SIGSTOP if on else signal.SIGCONT) and on:
            raise ServiceError(f"runner {name} is not running in a process group of its own; "
                               "not paused")

    def runner_boost(self, name: str, on: bool) -> None:
        """Nothing for its own processes: only root can raise a priority again on macOS."""

    def runner_group(self, name: str) -> int | None:
        """The agent's process group: its first process's, when that process leads one. None
        for a name no runner could have, or an agent not running."""
        try:
            lbl = runner_label(name)
        except ServiceError:
            return None
        match = _PID.search(self._loaded(lbl) or "")
        if match is None:
            return None
        pid = int(match.group(1))
        try:
            group = os.getpgid(pid)
        except OSError:
            return None
        return group if group == pid else None

    def _signal_group(self, name: str, sig: int) -> bool:
        group = self.runner_group(name)
        if group is None:
            return False
        try:
            os.killpg(group, sig)
        except (ProcessLookupError, PermissionError):
            return False
        return True
