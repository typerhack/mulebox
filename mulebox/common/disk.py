"""When a build machine's disk counts as low, and what to tell someone about it.

Worker, coordinator and client share this: the worker reports the free space of the fullest disk
holding its folders, and nothing else decides. A warning only: what can go is a person's call,
and `mulebox project clean` shows it first. Docker's images are not mulebox's to remove.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable

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


def is_low(free: int | None) -> bool:
    return free is not None and free < LOW_FREE_BYTES


def warning(worker: str, free: int) -> str:
    return (f"{worker} has {free / 1e9:.1f} GB free, and jobs can fail for lack of space. "
            "`mulebox project clean` lists what can go and `--yes` removes it; "
            "`docker system df` on the machine shows what Docker holds")
