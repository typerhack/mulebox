"""When a node's disk counts as low, and what to tell someone about it.

Worker, coordinator and client share this: the worker reports the free space of the fullest disk
holding its folders, and nothing else decides. A warning only: what can go is a person's call,
and `mulebox project clean` shows it first. Docker's images are not mulebox's to remove.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable
from typing import Any

from mulebox.common import units
LOW_FREE_BYTES = 10_000_000_000  # a compose job's images and an install can take that


def free_bytes(folders: Iterable[str]) -> int | None:
    """Free space on the fullest disk of `folders`; None when none can be read."""
    found = []
    for folder in folders:
        try:
            found.append(shutil.disk_usage(folder).free)
        except OSError:
            continue
    return min(found) if found else None


DiskUsage = Callable[[str], Any]


def usage_by_device(roots: dict[str, str], usage: DiskUsage = shutil.disk_usage
                    ) -> list[dict[str, Any]]:
    """One entry per file system holding a root: the root names on it, its `total`, `used` and
    `free` bytes. A file system's usage, not a `du` of the roots: walking job folders and caches
    would cost far more than a reading may. Roots that cannot be read are left out."""
    by_device: dict[int, dict[str, Any]] = {}
    for name, path in sorted(roots.items()):
        try:
            device = os.stat(path).st_dev
            found = usage(path)
        except OSError:
            continue
        entry = by_device.setdefault(device, {
            "roots": [], "total": found.total, "used": found.used, "free": found.free,
        })
        entry["roots"].append(name)
    return list(by_device.values())


def fullest(roots: dict[str, str], usage: DiskUsage = shutil.disk_usage
            ) -> dict[str, Any] | None:
    """The entry of `usage_by_device` with the least free space; None when none can be read."""
    found = usage_by_device(roots, usage)
    return min(found, key=lambda entry: entry["free"]) if found else None


def is_low(free: int | None) -> bool:
    return free is not None and free < LOW_FREE_BYTES


def warning(worker: str, free: int) -> str:
    return (f"{worker} has {units.size(free)} free, and jobs can fail for lack of space. "
            "`mulebox project clean` lists what can go and `--yes` removes it; "
            "`docker system df` on the machine shows what Docker holds")
