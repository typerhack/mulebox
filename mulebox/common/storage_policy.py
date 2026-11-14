"""How a node keeps its disk in check: the storage settings and their checks (design.md,
Project folders, Disk use and cleanup on its own). Read from node.toml, changed from afar like
`slots` (common/node_settings.py), and applied by the worker's sweep (worker/storage_sweep.py).

- `keep_free`: free space to leave on the disk of mulebox's folders, a share (`"10%"`, 1 to
  90) or a size (`"50GB"`, `"500MB"`, `"1TB"`, decimal as every size shown).
- `unused_days`: a branch folder with no job for this long is removed on its own (1 to 365).
- `keep_latest`: each project's latest folder stays however old.
- `idle_days`: a project with no job for this long gets a suggestion, never a removal (1 to 365).
- `auto_clean`: the sweep removes on its own; off, it only measures and says what would go.
- `docker_clean`: the sweep also removes Docker's build cache, dangling images and the images
  mulebox's jobs pulled, unused for `unused_days` (worker/docker_prune.py); never volumes, an
  image a container uses, or one mulebox never used.
- `max_size`: the most mulebox's own folders may take on the node (`"100GB"`); past it the sweep
  removes the oldest folders that may go, never a running, kept or latest one. `"off"` (the
  default) for no limit.
- `warn_size`: when mulebox's own folders on the node pass this size (`"50GB"`), every command
  from a project tells the agent to tell its user, who may ask an agent to look; `"off"` for none.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

FIELDS = ("keep_free", "unused_days", "keep_latest", "idle_days", "auto_clean", "docker_clean",
          "warn_size", "max_size")
FLAGS = ("keep_latest", "auto_clean", "docker_clean")
DEFAULTS: dict[str, Any] = {"keep_free": "10%", "unused_days": 7, "keep_latest": True,
                            "idle_days": 14, "auto_clean": True, "docker_clean": True,
                            "warn_size": "50GB", "max_size": "OFF"}
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
    auto_clean: bool = DEFAULTS["auto_clean"]
    docker_clean: bool = DEFAULTS["docker_clean"]
    warn_size: str = DEFAULTS["warn_size"]
    max_size: str = DEFAULTS["max_size"]

    def reserve(self, total: int) -> int:
        """The bytes to keep free on a disk of `total` bytes."""
        amount, unit = _parsed(self.keep_free)
        return int(total * amount / 100) if unit == "%" else int(amount * UNITS[unit])

    def warn_bytes(self) -> int | None:
        """The size past which the node warns, or None when that is off."""
        return None if self.warn_size == "OFF" else warn_bytes(self.warn_size)

    def max_bytes(self) -> int | None:
        """The most mulebox may hold, or None for no limit."""
        return None if self.max_size == "OFF" else warn_bytes(self.max_size)

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
    if name in FLAGS:
        return check_flag(name, value)
    return check_days(name, value)


def read(table: dict[str, Any]) -> StoragePolicy:
    """The policy from node.toml's top-level keys, the defaults for those left out."""
    return StoragePolicy(**{name: check(name, table[name]) for name in FIELDS if name in table})
