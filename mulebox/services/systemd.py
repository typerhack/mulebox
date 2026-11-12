"""mulebox's services as systemd user units (Linux nodes).

The unit files ship in the package (`mulebox/machine/systemd/`) and are copied into
`~/.config/systemd/user/`. All of them are copied; the coordinator, worker and dashboard are
enabled by `install` for the node's roles, the runner template per runner by `mulebox runner add`.
A runner may be in a job when this runs, so its CPU share is set in place, never by a restart.
"""

from __future__ import annotations

import getpass
import os
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from mulebox.common import command
from mulebox.services.base import MISSING, PREFIX, RUNNING, STOPPED, ServiceError, Say, \
    check_name, wanted

RUNNER_TEMPLATE = "mulebox-runner@.service"
SHARE = ("CPUWeight=50", "IOWeight=50")  # a runner's, as in its template


def unit(name: str) -> str:
    return f"{PREFIX}{check_name(name)}.service"


def shipped_units() -> dict[str, bytes]:
    folder = resources.files("mulebox.machine") / "systemd"
    return {entry.name: entry.read_bytes() for entry in folder.iterdir()
            if entry.name.endswith(".service")}


class SystemdServices:
    kind = "systemd"

    def __init__(self, home: Path | None = None, run: command.Runner = command.run) -> None:
        self.home = home or Path.home()
        self._run = run
        self.unit_dir = self.home / ".config" / "systemd" / "user"

    def _systemctl(self, *args: str, check: bool = True):
        done = self._run(["systemctl", "--user", *args])
        if check and done.returncode != 0:
            raise ServiceError(f"`systemctl --user {' '.join(args)}` failed: "
                               f"{(done.stderr or '').strip()}")
        return done

    def install(self, roles: Sequence[str], say: Say) -> None:
        self.unit_dir.mkdir(parents=True, exist_ok=True)
        for name, text in sorted(shipped_units().items()):
            draft = self.unit_dir / f"{name}.new.{os.getpid()}"
            draft.write_bytes(text)
            draft.chmod(0o644)
            draft.replace(self.unit_dir / name)
        self._systemctl("daemon-reload")
        runners = self._systemctl("list-units", "--plain", "--no-legend", f"{PREFIX}runner@*",
                                  check=False).stdout or ""
        for line in runners.splitlines():
            if words := line.split():
                self._systemctl("set-property", "--runtime", words[0], *SHARE, check=False)
        for name in wanted(roles):
            if self.state(name) == RUNNING:
                self._systemctl("enable", "--quiet", unit(name))
                self._systemctl("restart", unit(name))
                say(f"Restarted {unit(name)}.")
            else:
                self._systemctl("enable", "--now", "--quiet", unit(name))
                say(f"Enabled and started {unit(name)}.")

    def restart(self, name: str) -> None:
        self._systemctl("restart", unit(name))

    def stop(self, name: str) -> None:
        self._systemctl("disable", "--now", unit(name))

    def state(self, name: str) -> str:
        if not (self.unit_dir / unit(name)).is_file():
            return MISSING
        done = self._systemctl("is-active", "--quiet", unit(name), check=False)
        return RUNNING if done.returncode == 0 else STOPPED

    def logs_argv(self, names: Sequence[str], follow: bool) -> list[str]:
        units = [arg for n in names for arg in ("-u", f"{PREFIX}{check_name(n)}")]
        return ["journalctl", "--user", *units, "-n", "200", *(["-f"] if follow else [])]

    def detach(self, name: str, argv: Sequence[str]) -> None:
        """A transient unit of its own, gone once it ends."""
        if not name.startswith(PREFIX):
            raise ServiceError(f"refusing unit name {name!r}: not a {PREFIX}* unit")
        done = self._run(["systemd-run", "--user", f"--unit={name}", "--collect", "--quiet",
                          *argv])
        if done.returncode != 0:
            raise ServiceError(f"could not start {name}: {(done.stderr or '').strip()}")

    def boot_note(self) -> str | None:
        user = os.environ.get("USER") or getpass.getuser()
        try:
            shown = self._run(["loginctl", "show-user", user, "-p", "Linger"]).stdout or ""
            if shown.strip() != "Linger=no":
                return None
            if self._run(["loginctl", "--no-ask-password", "enable-linger", user]).returncode == 0:
                return None
        except command.CommandError:  # no loginctl: nothing to say
            return None
        return (f"Lingering is off for {user}, so the mulebox services stop when you log out.\n"
                "To keep them running after logout (and start them at boot), run once:\n"
                f"    sudo loginctl enable-linger {user}")
