"""How a node keeps its disk in check: the four storage settings and their checks (design.md,
Project folders, Disk use and cleanup on its own). Read from node.toml, changed from afar like
`slots` (common/node_settings.py), and applied by the worker's sweep (worker/storage_sweep.py).

- `keep_free`: free space to leave on the disk of mulebox's folders, a share (`"10%"`, 1 to
  90) or a size (`"50GB"`, `"500MB"`, `"1TB"`, decimal as every size shown).
- `unused_days`: a branch folder with no job for this long is removed on its own (1 to 365).
- `keep_latest`: each project's latest folder stays however old.
- `idle_days`: a project with no job for this long gets a suggestion, never a removal (1 to 365).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FIELDS = ("keep_free", "unused_days", "keep_latest", "idle_days")
DEFAULTS: dict[str, Any] = {"keep_free": "10%", "unused_days": 7, "keep_latest": True,
                            "idle_days": 14}
MAX_DAYS = 365
MAX_SHARE = 90
UNITS = {"MB": 10**6, "GB": 10**9, "TB": 10**12}
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(%|MB|GB|TB)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class StoragePolicy:
    keep_free: str = DEFAULTS["keep_free"]
    unused_days: int = DEFAULTS["unused_days"]
    keep_latest: bool = DEFAULTS["keep_latest"]
    idle_days: int = DEFAULTS["idle_days"]

    def reserve(self, total: int) -> int:
        """The bytes to keep free on a disk of `total` bytes."""
        amount, unit = _parsed(self.keep_free)
        return int(total * amount / 100) if unit == "%" else int(amount * UNITS[unit])

    def report(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in FIELDS}


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


def check_days(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a whole number of days, got {value!r}")
    if not 1 <= value <= MAX_DAYS:
        raise ValueError(f"{name} must be from 1 to {MAX_DAYS} days, got {value}")
    return value


def check_flag(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false, got {value!r}")
    return value


def check(name: str, value: Any) -> Any:
    """One storage setting, valid, or ValueError saying why."""
    if name == "keep_free":
        return check_keep_free(value)
    if name == "keep_latest":
        return check_flag(name, value)
    return check_days(name, value)


def read(table: dict[str, Any]) -> StoragePolicy:
    """The policy from node.toml's top-level keys, the defaults for those left out."""
    return StoragePolicy(**{name: check(name, table[name]) for name in FIELDS if name in table})
