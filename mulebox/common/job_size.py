"""Job sizes and a node's room for them (docs/design.md, Job sizes, M23.2).

A size is `{"cores": float, "memory": bytes}`, from `size:` in `.mulebox.yml`; either may be
left out. It decides where and when a job starts, and caps nothing (the user's decision): a job
that uses more slows its neighbours, and `mulebox usage` shows it.

A node's budget is its cores and memory less what it keeps for its owner (`keep_cores`,
`keep_memory` in node.toml). A job with no size, and every GitHub run, counts as one of the
node's slots: its budget over `slots`, so a project that declares nothing sees no change. A part
of a size the job leaves out counts as that share too. A node that has not reported its cores
and memory (older than this) has no budget: only `slots` count there.

The rules live here once, for the client's config reader, the coordinator and node.toml.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from mulebox.common import units

MAX_CORES = 1024
_MEMORY = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(MB|GB|TB)\s*$", re.IGNORECASE)
_UNITS = {"MB": 10**6, "GB": 10**9, "TB": 10**12}  # decimal, as every size shown
Size = dict[str, float]


def memory_bytes(value: Any, name: str = "memory", zero: bool = False) -> int:
    """`"6GB"`, `"512MB"` -> bytes (`"0GB"` too with `zero`); ValueError naming `name` otherwise."""
    found = _MEMORY.match(value) if isinstance(value, str) else None
    if found is None or float(found.group(1)) < (0 if zero else 1e-12):
        raise ValueError(f"{name} must be a size such as \"6GB\" or \"512MB\", got {value!r}")
    return int(float(found.group(1)) * _UNITS[found.group(2).upper()])


def cores_of(value: Any, name: str = "cores") -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= MAX_CORES:
        raise ValueError(f"{name} must be a number of cores above 0, up to {MAX_CORES}, "
                         f"got {value!r}")
    return float(value)


def check_keep_cores(value: Any) -> float | int:
    """`keep_cores`: cores a node keeps for its owner, 0 (the default) or more."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_CORES:
        raise ValueError(f"keep_cores must be a number of cores from 0 to {MAX_CORES}, "
                         f"got {value!r}")
    return value


def check_keep_memory(value: Any) -> str:
    """`keep_memory`: memory a node keeps for its owner, such as "4GB"; "0GB" (the default)."""
    memory_bytes(value, "keep_memory", zero=True)
    return value.strip().replace(" ", "").upper()


def checked(value: Any) -> Size | None:
    """A size from a config (`memory` as text) or the wire (`memory` in bytes); None for none."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"cores", "memory"} or not value:
        raise ValueError("size must be a mapping of cores and memory, such as "
                         "{cores: 4, memory: 6GB}")
    out: Size = {}
    if value.get("cores") is not None:
        out["cores"] = cores_of(value["cores"], "size.cores")
    memory = value.get("memory")
    if isinstance(memory, int) and not isinstance(memory, bool) and memory > 0:
        out["memory"] = memory
    elif memory is not None:
        out["memory"] = memory_bytes(memory, "size.memory")
    return out or None


def words(size: Size) -> str:
    parts = []
    if "cores" in size:
        parts.append(f"{size['cores']:g} {'core' if size['cores'] == 1 else 'cores'}")
    if "memory" in size:
        parts.append(units.size(size["memory"]))
    return " and ".join(parts)


@dataclass(frozen=True)
class Budget:
    """What a node can give to jobs, and its `slots`."""
    cores: float
    memory: int
    slots: int

    def share(self) -> Size:
        """One slot's part of it: what a job with no size counts as."""
        return {"cores": self.cores / self.slots, "memory": self.memory / self.slots}

    def of(self, size: Size | None) -> Size:
        """A job's size on this node, a part it leaves out counted as one slot's share."""
        return {**self.share(), **(size or {})}

    def holds(self, size: Size | None) -> bool:
        """Whether the job could ever fit here, with nothing else running."""
        need = self.of(size)
        return need["cores"] <= self.cores + 1e-9 and need["memory"] <= self.memory + 1


def budget(load: dict[str, Any] | None, settings: dict[str, Any] | None,
           slots: int | None) -> Budget | None:
    """A node's budget from its last report; None while its size is not known."""
    load, settings = load or {}, settings or {}
    cores, memory = load.get("cores"), (load.get("memory") or {}).get("total")
    if not cores or not memory or not slots:
        return None
    keep_cores = settings.get("keep_cores") or 0
    try:
        keep_memory = (memory_bytes(settings["keep_memory"], zero=True)
                       if settings.get("keep_memory") else 0)
    except ValueError:
        keep_memory = 0
    return Budget(cores=max(0.0, cores - keep_cores), memory=max(0, memory - keep_memory),
                  slots=max(1, int(slots)))


def free(budget: Budget, running: list[Size | None]) -> Size:
    """What is left of `budget` with these jobs on it (None: a job with no size)."""
    used = [budget.of(size) for size in running]
    return {"cores": budget.cores - sum(s["cores"] for s in used),
            "memory": budget.memory - sum(s["memory"] for s in used)}


def fits(budget: Budget, running: list[Size | None], size: Size | None) -> bool:
    left, need = free(budget, running), budget.of(size)
    return need["cores"] <= left["cores"] + 1e-9 and need["memory"] <= left["memory"] + 1


def room_words(budget: Budget, running: list[Size | None]) -> str:
    left = free(budget, running)
    cores = max(0.0, math.floor(left["cores"] * 10) / 10)
    return f"{cores:g} {'core' if cores == 1 else 'cores'} and {units.size(max(0, left['memory']))} free"
