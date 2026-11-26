"""How a node keeps its disk in check: the storage settings and their checks (design.md,
Project folders, Disk use and cleanup on its own). Read from node.toml, changed from afar like
`slots` (common/node_settings.py), and applied by the worker's sweep (worker/storage_sweep.py).

Space for mulebox, one setting to the user (1.30.0): `max_size` is the most mulebox may hold on
the node, everything it keeps counted (20 GB by default); agents are told from `WARN_SHARE` of
it; `keep_free` is the floor for the disk itself, which counts only when the disk is nearly full
for another reason. `warn_size` (1.26 to 1.29) is no setting any more: a node.toml that still
has it is read and the value left aside, and the report carries the warning size worked out
from `max_size` under that name, for coordinators older than 1.30.

- `keep_free`: free space to leave on the disk of mulebox's folders, a share (`"10%"`, 1 to
  90) or a size (`"50GB"`, `"500MB"`, `"1TB"`, decimal as every size shown).
- `unused_days`: a branch folder with no job for this long is removed on its own (1 to 365).
- `keep_latest`: each project's latest folder stays however old.
- `slim_hours`: a branch folder with no job for this long is slimmed: what git ignores in it
  (`node_modules`, `vendor`, build output) goes, the checkout stays (worker/slim.py); never the
  project's latest, a kept or a running one. 0 for never (0 to 720).
- `idle_days`: a project with no job for this long gets a suggestion, never a removal (1 to 365).
- `auto_clean`: the sweep removes on its own; off, it only measures and says what would go.
- `docker_clean`: the sweep also removes Docker's build cache, dangling images and the images
  mulebox's jobs pulled, unused for `unused_days` (worker/docker_prune.py); never volumes, an
  image a container uses, or one mulebox never used.
- `max_size`: the most mulebox may hold on the node (`"20GB"`, the default); past it the sweep
  slims the oldest folders that may be slimmed, then removes the oldest that may go, never a
  running, kept or latest one. From `WARN_SHARE` of it every command from a project tells the
  agent to ask its user. `"off"` for no limit and no warning.
- `min_free`: free space below which the node takes no job and rests (`"5GB"`, the default;
  worker/health.py, design.md, A node that rests). The sweep runs first, from `keep_free`.
- `keep_failed_min`: a failed job's containers and folder stay this many minutes for a rerun
  with `mulebox check --from-stage` (15, the default; 0 keeps nothing; worker/kept.py,
  design.md, Rerun from the failed stage).
- `keep_files_max`: the most one job keeps for `mulebox fetch` (`"200MB"`, the default; past it
  the smallest files go in first, worker/files_out.py, design.md, Files back).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FIELDS = ("keep_free", "unused_days", "keep_latest", "idle_days", "auto_clean", "docker_clean",
          "max_size", "slim_hours", "min_free", "keep_failed_min", "keep_files_max")
FLAGS = ("keep_latest", "auto_clean", "docker_clean")
DEFAULTS: dict[str, Any] = {"keep_free": "10%", "unused_days": 7, "keep_latest": True,
                            "idle_days": 14, "auto_clean": True, "docker_clean": True,
                            "max_size": "20GB", "slim_hours": 12, "min_free": "5GB",
                            "keep_failed_min": 15, "keep_files_max": "200MB"}
GONE = ("warn_size",)  # settings of older versions, read from node.toml and left aside
WARN_SHARE = 0.8  # agents are told from this share of `max_size`
MAX_DAYS = 365
MAX_HOURS = 720
MAX_KEEP_MIN = 240
MAX_SHARE = 90
UNITS = {"MB": 10**6, "GB": 10**9, "TB": 10**12}
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(%|MB|GB|TB)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class StoragePolicy:
    keep_free: str = DEFAULTS["keep_free"]
    unused_days: int = DEFAULTS["unused_days"]
    keep_latest: bool = DEFAULTS["keep_latest"]
    idle_days: int = DEFAULTS["idle_days"]
    auto_clean: bool = DEFAULTS["auto_clean"]
    docker_clean: bool = DEFAULTS["docker_clean"]
    max_size: str = DEFAULTS["max_size"]
    slim_hours: int = DEFAULTS["slim_hours"]
    min_free: str = DEFAULTS["min_free"]
    keep_failed_min: int = DEFAULTS["keep_failed_min"]
    keep_files_max: str = DEFAULTS["keep_files_max"]

    def reserve(self, total: int) -> int:
        """The bytes to keep free on a disk of `total` bytes."""
        amount, unit = _parsed(self.keep_free)
        return int(total * amount / 100) if unit == "%" else int(amount * UNITS[unit])

    def min_free_bytes(self) -> int:
        """Free space below which the node takes no job (worker/health.py)."""
        amount, unit = _parsed(self.min_free)
        return int(amount * UNITS[unit])

    def keep_files_bytes(self) -> int:
        """The most one job keeps for `mulebox fetch`."""
        amount, unit = _parsed(self.keep_files_max)
        return int(amount * UNITS[unit])

    def max_bytes(self) -> int | None:
        """The most mulebox may hold, or None for no limit."""
        return None if self.max_size == "OFF" else warn_bytes(self.max_size)

    def warn_bytes(self) -> int | None:
        """The size from which agents are told, or None with no limit."""
        limit = self.max_bytes()
        return None if limit is None else int(limit * WARN_SHARE)

    def report(self) -> dict[str, Any]:
        """The settings, as a node reports them."""
        return {name: getattr(self, name) for name in FIELDS}

    def shown(self) -> dict[str, Any]:
        """The settings in a storage report: with the warning size under its old name, which
        coordinators older than 1.30 read."""
        warn = self.warn_bytes()
        return {**{name: getattr(self, name) for name in FIELDS},
                "warn_size": "OFF" if warn is None else f"{warn / 10**9:g}GB"}


def _parsed(value: str) -> tuple[float, str]:
    found = _SIZE.match(value)
    if found is None:
        raise ValueError(f"keep_free must be a share such as \"10%\" or a size such as \"50GB\", "
                         f"got {value!r}")
    return float(found.group(1)), found.group(2).upper()


def check_keep_free(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"keep_free must be text such as \"10%\" or \"50GB\", got {value!r}")
    amount, unit = _parsed(value)
    if unit == "%" and not 1 <= amount <= MAX_SHARE:
        raise ValueError(f"keep_free must be from 1% to {MAX_SHARE}%, got {value!r}")
    if unit != "%" and amount <= 0:
        raise ValueError(f"keep_free must be more than nothing, got {value!r}")
    return value.strip().replace(" ", "").upper()


def warn_bytes(value: str) -> int | None:
    """A `warn_size` in bytes; None for `off` or anything unreadable."""
    try:
        amount, unit = _parsed(value)
    except ValueError:
        return None
    return None if unit == "%" else int(amount * UNITS[unit])


def check_size(name: str, value: Any) -> str:
    """A size such as "50GB", or "off"."""
    if isinstance(value, str) and value.strip().lower() == "off":
        return "OFF"
    ok = isinstance(value, str) and storage_size(value)
    if not ok:
        raise ValueError(f"{name} must be a size such as \"50GB\" or \"off\", got {value!r}")
    return value.strip().replace(" ", "").upper()


def storage_size(value: str) -> bool:
    found = _SIZE.match(value)
    return bool(found) and found.group(2) != "%" and float(found.group(1)) > 0


def check_days(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a whole number of days, got {value!r}")
    if not 1 <= value <= MAX_DAYS:
        raise ValueError(f"{name} must be from 1 to {MAX_DAYS} days, got {value}")
    return value


def check_hours(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a whole number of hours, got {value!r}")
    if not 0 <= value <= MAX_HOURS:
        raise ValueError(f"{name} must be from 0 (never) to {MAX_HOURS} hours, got {value}")
    return value


def check_minutes(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a whole number of minutes, got {value!r}")
    if not 0 <= value <= MAX_KEEP_MIN:
        raise ValueError(f"{name} must be from 0 (keep nothing) to {MAX_KEEP_MIN} minutes, "
                         f"got {value}")
    return value


def check_flag(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false, got {value!r}")
    return value


def check(name: str, value: Any) -> Any:
    """One storage setting, valid, or ValueError saying why."""
    if name == "keep_free":
        return check_keep_free(value)
    if name in ("warn_size", "max_size"):
        return check_size(name, value)
    if name in ("min_free", "keep_files_max"):
        if not (isinstance(value, str) and storage_size(value)):
            example = "5GB" if name == "min_free" else "200MB"
            raise ValueError(f"{name} must be a size such as \"{example}\", got {value!r}")
        return value.strip().replace(" ", "").upper()
    if name in FLAGS:
        return check_flag(name, value)
    if name == "slim_hours":
        return check_hours(name, value)
    if name == "keep_failed_min":
        return check_minutes(name, value)
    return check_days(name, value)


def read(table: dict[str, Any]) -> StoragePolicy:
    """The policy from node.toml's top-level keys, the defaults for those left out."""
    return StoragePolicy(**{name: check(name, table[name]) for name in FIELDS if name in table})
