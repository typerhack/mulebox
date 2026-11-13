"""mulebox's services as launchd agents (macOS nodes).

Each service is an agent with the label `mulebox-<name>`, its definition written to
`~/Library/LaunchAgents/mulebox-<name>.plist`, its output to `~/Library/Logs/mulebox/<name>.log`.
launchd loads every agent in that folder at login, so only the services the node's roles run are
written; one the roles no longer name is stopped and disabled, and its file left alone.

Agents go to the user's login session (`gui/<uid>`) when someone is logged in on the Mac's screen,
else to `user/<uid>`, which an ssh login has. Either way they start at login, not at boot: a Mac
with nobody logged in runs no agents, so a node that must come back after a reboot needs automatic
login (boot_note). `KeepAlive` with `SuccessfulExit = false` is systemd's `Restart=on-failure`.

launchd starts agents with a bare PATH, so each gets the places Homebrew, Docker and mulebox put
their commands, then the PATH the installer ran with. GitHub runners are agents too, one each
(launchd_runners.py).
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mulebox.common import command, disclaim
from mulebox.services.base import MISSING, PREFIX, RUNNING, SERVICES, STOPPED, ServiceError, \
    Say, check_name, wanted
from mulebox.services.launchd_runners import LaunchdRunners

THROTTLE_S = 5  # as RestartSec=5 in the systemd units
GONE_WAIT_S = 10.0
_BASE_PATH = ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin", "/usr/bin", "/bin",
              "/usr/sbin", "/sbin")
NICE = {"dashboard": 10}  # as Nice=10 in mulebox-dashboard.service


def label(name: str) -> str:
    return f"{PREFIX}{check_name(name)}"


def search_path(home: Path, inherited: str) -> str:
    """The PATH an agent runs with: the usual tool folders first, then the inherited ones, once."""
    parts = [str(home / ".local" / "bin"), *_BASE_PATH, *inherited.split(":")]
    return ":".join(dict.fromkeys(p for p in parts if p))


def logs_dir(home: Path) -> Path:
    return home / "Library" / "Logs" / "mulebox"


def definition(name: str, home: Path, path: str) -> dict[str, Any]:
    logs = logs_dir(home)
    plist: dict[str, Any] = {
        "Label": label(name),
        "ProgramArguments": [str(home / ".mulebox" / "bin" / "mulebox"), name, "serve"],
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1", "PATH": path,
                                 disclaim.SERVICE_ENV: "launchd"},
        "WorkingDirectory": str(home),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": THROTTLE_S,
        "ProcessType": "Standard",
        "StandardOutPath": str(logs / f"{name}.log"),
        "StandardErrorPath": str(logs / f"{name}.log"),
    }
    if name in NICE:
        plist["Nice"] = NICE[name]
    return plist


class LaunchdServices(LaunchdRunners):
    kind = "launchd"

    def __init__(self, home: Path | None = None, run: command.Runner = command.run,
                 uid: int | None = None, path: str | None = None,
                 sleep=time.sleep, clock=time.monotonic, spawn=subprocess.Popen) -> None:
        self.home = home or Path.home()
        self._spawn = spawn
        self._run = run
        self.uid = os.getuid() if uid is None else uid
        self.path = os.environ.get("PATH", "") if path is None else path
        self._sleep, self._clock = sleep, clock
        self.agent_dir = self.home / "Library" / "LaunchAgents"
        self._domain: str | None = None

    @property
    def domain(self) -> str:
        """`gui/<uid>` with someone logged in on the screen, else `user/<uid>`."""
        if self._domain is None:
            gui = f"gui/{self.uid}"
            self._domain = gui if self._launchctl("print", gui).returncode == 0 \
                else f"user/{self.uid}"
        return self._domain

    def _launchctl(self, *args: str):
        return self._run(["launchctl", *args])

    def _must(self, *args: str) -> None:
        done = self._launchctl(*args)
        if done.returncode != 0:
            raise ServiceError(f"`launchctl {' '.join(args)}` failed: "
                               f"{(done.stderr or done.stdout or '').strip()}")

    def _env_path(self) -> str:
        return search_path(self.home, self.path)

    def _logs(self) -> Path:
        return logs_dir(self.home)

    def plist_path(self, name: str) -> Path:
        return self._plist(label(name))

    def _plist(self, lbl: str) -> Path:
        return self.agent_dir / f"{lbl}.plist"

    def _target(self, lbl: str, domain: str | None = None) -> str:
        return f"{domain or self.domain}/{lbl}"

    def _domains(self) -> tuple[str, str]:
        return f"gui/{self.uid}", f"user/{self.uid}"

    def _where(self, lbl: str) -> dict[str, str]:
        """`launchctl print` of the agent in each domain it is loaded in. Both are looked at: an
        agent loaded over ssh with nobody at the screen stays in `user/` after someone logs in."""
        found = {}
        for domain in self._domains():
            done = self._launchctl("print", self._target(lbl, domain))
            if done.returncode == 0:
                found[domain] = done.stdout or ""
        return found

    def _loaded(self, lbl: str) -> str | None:
        """`launchctl print` of a loaded agent, or None when it is not loaded anywhere."""
        return next(iter(self._where(lbl).values()), None)

    def _write(self, lbl: str, plist: dict[str, Any]) -> None:
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self._logs().mkdir(parents=True, exist_ok=True)
        draft = self.agent_dir / f"{lbl}.plist.new.{os.getpid()}"
        draft.write_bytes(plistlib.dumps(plist))
        draft.chmod(0o644)
        draft.replace(self._plist(lbl))

    def _unload(self, lbl: str, wait_s: float = GONE_WAIT_S) -> None:
        loaded = self._where(lbl)
        if not loaded:
            return
        for domain in loaded:
            self._launchctl("bootout", self._target(lbl, domain))
        end = self._clock() + wait_s
        while self._loaded(lbl) is not None:
            if self._clock() >= end:
                raise ServiceError(f"{lbl} did not stop within {wait_s:.0f} s")
            self._sleep(0.2)

    def _load(self, lbl: str) -> None:
        self._must("enable", self._target(lbl))
        self._must("bootstrap", self.domain, str(self._plist(lbl)))

    def _reload(self, lbl: str, plist: dict[str, Any]) -> bool:
        """Write the definition and load it afresh; True if it was loaded before."""
        was_loaded = self._loaded(lbl) is not None
        self._write(lbl, plist)
        self._unload(lbl)  # a loaded agent keeps its old definition until it is reloaded
        self._load(lbl)
        return was_loaded

    def _restart(self, lbl: str) -> None:
        loaded = self._where(lbl)
        if not loaded:
            if not self._plist(lbl).is_file():
                raise ServiceError(f"{lbl} is not installed on this machine")
            self._load(lbl)
            return
        for domain in loaded:
            self._must("kickstart", "-k", self._target(lbl, domain))

    def _stop(self, lbl: str, wait_s: float = GONE_WAIT_S) -> None:
        """Stop it wherever it is loaded, and keep it from loading in either domain."""
        self._unload(lbl, wait_s)
        self._must("disable", self._target(lbl))
        for domain in self._domains():
            if domain != self.domain:
                self._launchctl("disable", self._target(lbl, domain))  # may not exist now

    def _state(self, lbl: str) -> str:
        shown = self._loaded(lbl)
        if shown is None:
            return STOPPED if self._plist(lbl).is_file() else MISSING
        lines = (line.strip() for line in shown.splitlines())
        return RUNNING if "state = running" in lines else STOPPED

    def install(self, roles: Sequence[str], say: Say) -> None:
        runs = wanted(roles)
        for name in SERVICES:
            if name not in runs and self.plist_path(name).is_file():
                self.stop(name)  # a role this node no longer has
        for name in runs:
            plist = definition(name, self.home, self._env_path())
            was_running = self._reload(label(name), plist)
            say(f"{'Restarted' if was_running else 'Started'} {label(name)} ({self.domain}).")

    def restart(self, name: str) -> None:
        self._restart(label(name))

    def stop(self, name: str) -> None:
        self._stop(label(name))

    def state(self, name: str) -> str:
        return self._state(label(name))

    def logs_argv(self, names: Sequence[str], follow: bool) -> list[str]:
        files = [str(logs_dir(self.home) / f"{check_name(n)}.log") for n in names]
        return ["tail", "-n", "200", *(["-F"] if follow else []), *files]

    def detach(self, name: str, argv: Sequence[str]) -> None:
        """A process in a session of its own: the ssh session's hangup does not reach it, and
        reloading an agent does not stop it, as it is no agent's child."""
        if not name.startswith(PREFIX):
            raise ServiceError(f"refusing name {name!r}: not a {PREFIX}* name")
        try:
            self._spawn(list(argv), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, start_new_session=True, cwd=self.home)
        except OSError as exc:
            raise ServiceError(f"could not start {name}: {exc}") from exc

    def boot_note(self) -> str | None:
        user = os.environ.get("USER") or "this user"
        return (f"On a Mac, the mulebox services start when {user} logs in, not at boot. For a "
                "node that comes back by itself after a restart, turn on automatic login for "
                f"{user} (System Settings > Users & Groups; FileVault must be off for it).")
