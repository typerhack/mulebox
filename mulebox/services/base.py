"""What both service managers share: mulebox's services, which of them a node runs, and the
contract `mulebox service` talks to (systemd.py on Linux, launchd.py on macOS).

A service's short name (`worker`) is what people type; each manager turns it into its own name,
`mulebox-worker.service` for systemd and the launchd label `mulebox-worker`.

A GitHub runner (runners/manage.py) is a service of its own per runner, through the same manager:
an instance of `mulebox-runner@.service` on Linux, the agent `mulebox-runner-<name>` on macOS.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from mulebox.common.config_reader import NAME_RE
from mulebox.common.errors import MuleboxError

PREFIX = "mulebox-"
# Every service a node can run, in start order; the GitHub runners are instances of their own.
SERVICES = ("coordinator", "dashboard", "worker")
RUNNING, STOPPED, MISSING = "running", "stopped", "not installed"
RUNNER_NAME_MAX = 64  # as runners/names.py allows

Say = Callable[[str], None]


class ServiceError(MuleboxError):
    """A service could not be installed, started or stopped; the message says what to do."""


def check_name(name: str) -> str:
    if name not in SERVICES:
        raise ServiceError(f"no mulebox service called {name!r}; there are {', '.join(SERVICES)}")
    return name


def check_runner(name: str) -> str:
    """A runner name, which becomes part of a unit or label name."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > RUNNER_NAME_MAX:
        raise ServiceError(f"{name!r} is not a runner name")
    return name


def wanted(roles: Sequence[str]) -> list[str]:
    """The services a node with these roles runs: the dashboard goes with the coordinator."""
    names = []
    if "coordinator" in roles:
        names += ["coordinator", "dashboard"]
    if "worker" in roles:
        names.append("worker")
    return names


class Manager(Protocol):
    kind: str  # "systemd" or "launchd", for messages

    def install(self, roles: Sequence[str], say: Say) -> None:
        """Write every service's definition and (re)start the ones these roles run."""

    def restart(self, name: str) -> None: ...

    def stop(self, name: str) -> None:
        """Stop it, and keep it from starting again at boot or login."""

    def state(self, name: str) -> str:
        """RUNNING, STOPPED or MISSING."""

    def logs_argv(self, names: Sequence[str], follow: bool) -> list[str]:
        """The command that shows these services' recent logs, and new lines as they come."""

    def detach(self, name: str, argv: Sequence[str]) -> None:
        """Start `argv` apart from the caller, so it outlives the ssh session and a restart of
        mulebox's services (an upgrade's waiter). `name` is a `mulebox-...` name for it."""

    def boot_note(self) -> str | None:
        """What a person must do once for the services to start at boot, if anything."""

    # --- GitHub runners, one service each -------------------------------------------------

    def runner_check(self, runners: Path) -> None:
        """Refuse, before any download, when a runner in `runners` could not be run here."""

    def runner_start(self, name: str, folder: Path) -> None:
        """Run `folder`/run.sh as the runner's service, now and at boot or login."""

    def runner_stop(self, name: str) -> None:
        """Stop it, and keep it from starting again."""

    def runner_restart(self, name: str) -> None: ...

    def runner_state(self, name: str) -> str:
        """RUNNING or STOPPED."""

    def runner_freeze(self, name: str, on: bool) -> None:
        """Stop or continue every process of the runner, listener and job alike."""

    def runner_boost(self, name: str, on: bool) -> None:
        """Raise the runner's share of the machine, or set it back; nothing where it cannot."""

    def runner_group(self, name: str) -> int | None:
        """The runner's own process group, for its readings, where the manager gives one."""
