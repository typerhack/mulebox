"""A node's settings that can be changed from afar: `slots` and `priority` (design.md, Node
settings). The rules live here once, for node.toml's reader, the coordinator and the worker.

- `slots`: 1 to 64 jobs at once.
- `priority`: `preferred`, `normal` (the default) or `fallback`; a node takes a job only when no
  node ranked above it could take it now (coordinator/node_settings.py).
- `suggest_slots`: about 4 cores and 6 GB of memory a job, at least 1. Shown beside the value,
  never applied by itself.
"""

from __future__ import annotations

from typing import Any

MIN_SLOTS, MAX_SLOTS = 1, 64
PRIORITIES = ("preferred", "normal", "fallback")  # best first
DEFAULT_PRIORITY = "normal"
EDITABLE = ("slots", "priority")
CORES_PER_JOB = 4
GB_PER_JOB = 6
GB = 1 << 30


def rank(priority: str | None) -> int:
    """Higher is preferred; an unknown or missing value counts as `normal`."""
    name = priority if priority in PRIORITIES else DEFAULT_PRIORITY
    return len(PRIORITIES) - PRIORITIES.index(name)


def check_slots(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"slots must be a whole number, got {value!r}")
    if not MIN_SLOTS <= value <= MAX_SLOTS:
        raise ValueError(f"slots must be from {MIN_SLOTS} to {MAX_SLOTS}, got {value}")
    return value


def check_priority(value: Any) -> str:
    if value not in PRIORITIES:
        raise ValueError(f"priority must be one of {', '.join(PRIORITIES)}, got {value!r}")
    return value


def checked(changes: Any) -> dict[str, Any]:
    """Only the editable settings, each valid; ValueError naming the first that is not."""
    if not isinstance(changes, dict):
        raise ValueError("settings must be a mapping")
    unknown = sorted(set(changes) - set(EDITABLE))
    if unknown:
        raise ValueError(f"{unknown[0]!r} cannot be changed from afar; only "
                         f"{' and '.join(EDITABLE)} can (the rest is in the node's node.toml)")
    out: dict[str, Any] = {}
    if "slots" in changes:
        out["slots"] = check_slots(changes["slots"])
    if "priority" in changes:
        out["priority"] = check_priority(changes["priority"])
    return out


def suggest_slots(cores: int | None, memory_bytes: int | None) -> dict[str, Any] | None:
    """`{slots, reason}` from a machine's logical cores and memory, or None without both."""
    if not cores or not memory_bytes:
        return None
    memory_gb = memory_bytes / GB
    slots = max(MIN_SLOTS, min(cores // CORES_PER_JOB, int(memory_gb // GB_PER_JOB), MAX_SLOTS))
    return {"slots": slots,
            "reason": f"{cores} cores and {memory_gb:.0f} GB of memory, at about "
                      f"{CORES_PER_JOB} cores and {GB_PER_JOB} GB a job"}
