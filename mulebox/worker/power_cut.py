"""Was the node's power cut while this worker ran? (docs/design.md, Sudden power loss)

The worker writes the boot it runs in to `<staging>/worker-state/boot` when it starts and removes the
file when it stops cleanly. Found at the next start with another boot in it, the node went down
under the worker: a power cut, or a crash of the system. Then files written in the last seconds
may never have reached the disk, so what each branch remembers about its `setup` and `install`
is forgotten, and the next job of each branch runs them again. A worker killed within one boot
(`kill -9`) loses nothing on disk, so that forgets nothing.

The boot is Linux's `boot_id`, or a Mac's boot time from `sysctl`; with neither, nothing is
judged.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from mulebox.common import safefile
from mulebox.common.log import get_logger
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker import project_home
from mulebox.worker.paths import NodePaths

LOG = get_logger("worker.power_cut")
FOLDER, FILE = "worker-state", "boot"
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
_BOOTTIME = re.compile(r"sec\s*=\s*(\d+)")


def current_boot(read: Callable[[], str | None] | None = None) -> str | None:
    """This boot's identity, or None when the system gives none."""
    if read is not None:
        return read()
    try:
        return BOOT_ID.read_text().strip() or None
    except OSError:
        pass
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True,
                             timeout=5, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = _BOOTTIME.search(out)
    return f"boottime-{found.group(1)}" if found else None


def started(paths: NodePaths, boot: str | None) -> bool:
    """Record this boot; True when the last worker ran in another and never stopped."""
    marker = paths.staging / FOLDER / FILE
    before = safefile.read_text(marker, paths.roots)
    if boot is None:
        return False
    ensure_dir(marker.parent, paths.roots)
    safefile.write_text(marker, boot + "\n", paths.roots, 0o600)
    return before is not None and before.strip() not in ("", boot)


def stopped(paths: NodePaths) -> None:
    """A clean stop: nothing was cut short."""
    remove_tree(paths.staging / FOLDER / FILE, paths.roots)


def forget_setups(paths: NodePaths) -> int:
    """Forget every branch's remembered `setup` and `install`; how many were forgotten."""
    count = 0
    root = paths.projects
    if not root.is_dir():
        return 0
    for state in sorted(root.glob("*/state/*")):
        if state.is_symlink() or not state.is_file():
            continue
        if state.suffix.lstrip(".") in (project_home.SETUP, project_home.INSTALL):
            remove_tree(state, paths.roots)
            count += 1
    return count


def after_start(paths: NodePaths, boot: str | None) -> bool:
    """At the worker's start: forget what a power cut may have lost; True if it did."""
    if not started(paths, boot):
        return False
    forgotten = forget_setups(paths)
    LOG.warning("the node went down while the worker ran (a power cut or a crash): %d remembered "
                "setup(s) and install(s) forgotten, so each branch's next job runs them again",
                forgotten)
    return True
