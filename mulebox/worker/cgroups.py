"""One job's CPU and network, from the files of the kernel's control groups (cgroup v2).

A job's own processes are in its systemd unit. Its compose services are in the containers' scopes,
which Docker creates: `system.slice/docker-<id>.scope` with the systemd driver, `docker/<id>` with
cgroupfs. Each container has its own network namespace, so `/proc/<pid>/net/dev` of any process
in it counts that container's traffic alone. A unit shares the machine's namespace, so a job's own
processes have no network reading, only CPU. A file that cannot be read is no reading.
"""

from __future__ import annotations

import os
from pathlib import Path

from mulebox.common.proc import PROC
from mulebox.worker.executor import UNIT_PREFIX

ROOT = Path("/sys/fs/cgroup")
_USAGE = "usage_usec"


def net_bytes(text: str) -> int:
    """Received plus sent bytes of every interface but loopback, from a `net/dev` file."""
    total = 0
    for line in text.splitlines():
        name, colon, rest = line.partition(":")
        fields = rest.split()
        if colon and name.strip() != "lo" and len(fields) > 8:
            total += int(fields[0]) + int(fields[8])
    return total


def unit_group(unit: str, root: Path = ROOT) -> Path:
    """A transient `systemd-run --user` unit, in the user manager's default slice."""
    uid = os.getuid()
    return root / f"user.slice/user-{uid}.slice/user@{uid}.service/app.slice/{unit}.service"


def container_group(container: str, root: Path = ROOT) -> Path | None:
    for group in (root / f"system.slice/docker-{container}.scope", root / "docker" / container):
        if group.is_dir():
            return group
    return None


def memory_bytes(group: Path) -> int | None:
    """Memory used by everything in `group` now: `memory.current` less the page cache the kernel
    can drop at once (`inactive_file` in `memory.stat`), the working set, as the machine's own
    "used" leaves out what it could free. A build that reads many files is not counted for them."""
    try:
        current = int((group / "memory.current").read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None
    try:
        for line in (group / "memory.stat").read_text(encoding="ascii").splitlines():
            key, _, value = line.partition(" ")
            if key == "inactive_file":
                return max(0, current - int(value))
    except (OSError, ValueError):
        pass
    return current


def job_unit_groups(root: Path = ROOT) -> list[Path]:
    """The groups of the agent job units running now (worker/executor.py `unit_name`)."""
    try:
        return [group for group in unit_group("x", root).parent.glob(f"{UNIT_PREFIX}*.service")
                if group.is_dir()]
    except OSError:
        return []


def cpu_seconds(group: Path) -> float | None:
    """CPU time used by everything in `group`, children included, since it was made."""
    try:
        for line in (group / "cpu.stat").read_text(encoding="ascii").splitlines():
            key, _, value = line.partition(" ")
            if key == _USAGE:
                return int(value) / 1_000_000
    except (OSError, ValueError):
        pass
    return None


def group_net_bytes(group: Path, proc: Path = PROC) -> int | None:
    """Traffic of the network namespace of the first process in `group`."""
    try:
        pids = (group / "cgroup.procs").read_text(encoding="ascii").split()
        return net_bytes((proc / pids[0] / "net" / "dev").read_text(encoding="ascii"))
    except (OSError, ValueError, IndexError):
        return None


def runner_group(runner: str, root: Path = ROOT) -> Path | None:
    """A GitHub runner's service, `mulebox-runner@<name>.service`, in the user manager. systemd
    puts a template's instances in a slice of their own, so both places are looked at."""
    uid = os.getuid()
    apps = root / f"user.slice/user-{uid}.slice/user@{uid}.service/app.slice"
    unit = f"mulebox-runner@{runner}.service"
    for group in (apps / "app-mulebox\\x2drunner.slice" / unit, apps / unit):
        if group.is_dir():
            return group
    return None
