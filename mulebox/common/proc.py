"""Reading `/proc/stat`: what the dashboard's graphs and the worker's activity meter share."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

PROC = Path("/proc")
IDLE, IOWAIT = 3, 4


def core_times(text: str) -> Iterator[list[int]]:
    """Each core's jiffies from /proc/stat, in core order: user, nice, system, idle, iowait..."""
    for line in text.splitlines():
        name, _, rest = line.partition(" ")
        if not (name.startswith("cpu") and name[3:].isdigit()):
            continue
        values = [int(v) for v in rest.split()[:8] if v.isdigit()]
        if len(values) > IOWAIT:
            yield values
