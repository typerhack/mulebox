"""One job's CPU, traffic and memory on a macOS node, where there are no cgroups to read.

- **Its own processes**: those in its process group (darwin_exec.py), from one `ps` listing:
  CPU time per process, keyed `unit:<pid>`, so a process that started since the last reading
  counts from nothing and one that ended drops out (job_meter.py `_grown`). Time used by a
  process that started and ended between two readings is not seen; output still is.
- **Its compose services**: the engine's own numbers per container (docker_stats.py), asked
  beside the loop (background.Polled), as the engine can be slow.

A reading is None while the group or the containers are not known, which job_meter.py treats
as unknown, never as idle.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mulebox.common import command
from mulebox.worker import background
from mulebox.worker.docker_stats import Engine

Process = tuple[int, int, float, int]  # pid, pgid, CPU seconds, resident bytes
_UNIT, _SERVICE, _NET = "unit:", "service:", "net:"  # job_meter.py's sources


def cpu_time(text: str) -> float:
    """`ps`'s `time` column: `[[dd-]hh:]mm:ss.ss` -> seconds."""
    days, _, clock = text.rpartition("-")
    parts = [float(p) for p in clock.split(":")]
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds + (int(days) * 86400 if days else 0)


def parse_ps(text: str) -> list[Process]:
    """Lines of `ps -A -o pid=,pgid=,time=,rss=` (rss in KiB)."""
    found = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        try:
            found.append((int(fields[0]), int(fields[1]), cpu_time(fields[2]),
                          int(fields[3]) * 1024))
        except ValueError:
            continue
    return found


def processes() -> list[Process] | None:
    try:
        done = command.run(["ps", "-A", "-o", "pid=,pgid=,time=,rss="], timeout_s=10)
    except command.CommandError:
        return None
    return parse_ps(done.stdout) if done.returncode == 0 else None


def group_memory(pgids: set[int], table: list[Process]) -> int:
    """Resident bytes of every process in these groups."""
    return sum(rss for _, pgid, _, rss in table if pgid in pgids)


class ContainerStats(background.Polled[dict[str, dict[str, float]]]):
    """The engine's numbers for the containers `ids()` names now, asked beside the loop."""

    def __init__(self, ids: Callable[[], list[str] | None], engine: Engine | None = None) -> None:
        engine = engine or Engine()
        super().__init__(lambda: self._ask_all(ids, engine))

    @staticmethod
    def _ask_all(ids: Callable[[], list[str] | None],
                 engine: Engine) -> dict[str, dict[str, float]] | None:
        names = ids()
        if names is None:
            return None
        found = {}
        for container in names:
            stats = engine.stats(container)
            if stats is None:
                return None  # one unknown makes the whole reading unknown
            found[container] = stats
        return found


class JobReader:
    """`JobMeter`'s reader for one job on a Mac."""

    def __init__(self, pgid: Callable[[], int | None], containers: ContainerStats | None,
                 listing: Callable[[], list[Process] | None] = processes) -> None:
        self._pgid, self._containers, self._listing = pgid, containers, listing

    def __call__(self) -> dict[str, float] | None:
        group, table = self._pgid(), self._listing()
        if group is None or table is None:
            return None
        reading: dict[str, Any] = {f"{_UNIT}{pid}": cpu for pid, pgid, cpu, _ in table
                                   if pgid == group}
        if not reading:
            return None  # not started yet, or already gone
        if self._containers is not None:
            stats = self._containers.value()
            if stats is None:
                return None
            for container, numbers in stats.items():
                reading[f"{_SERVICE}{container}"] = numbers["cpu_s"]
                if "net" in numbers:
                    reading[f"{_NET}{container}"] = numbers["net"]
        return reading
