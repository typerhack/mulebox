"""Typed access to request body fields; every problem raises BadRequest.

Protocol decoding (common.protocol) only checks that required fields exist; the types
and ranges the coordinator relies on are checked here.
"""

from typing import Any

from mulebox.common.ids import is_valid_id
from mulebox.coordinator.errors import BadRequest

_MISSING = object()


def _get(body: dict[str, Any], name: str, default: Any) -> Any:
    value = body.get(name, _MISSING)
    if value is _MISSING or value is None:
        if default is _MISSING:
            raise BadRequest(f"field '{name}' is required")
        return default
    return value


def text(body: dict[str, Any], name: str, default: Any = _MISSING) -> Any:
    """A non-empty string (or `default` when absent or null)."""
    value = _get(body, name, default)
    if value is default and default is not _MISSING:
        return value
    if not isinstance(value, str) or not value:
        raise BadRequest(f"field '{name}' must be a non-empty string")
    return value


def strings(body: dict[str, Any], name: str, *, non_empty: bool = False) -> list[str]:
    """A list of non-empty strings (empty list when absent)."""
    value = _get(body, name, [])
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise BadRequest(f"field '{name}' must be a list of non-empty strings")
    if non_empty and not value:
        raise BadRequest(f"field '{name}' must not be empty")
    return value


def string_map(body: dict[str, Any], name: str) -> dict[str, str]:
    """A mapping of non-empty strings to non-empty strings (empty when absent)."""
    value = _get(body, name, {})
    ok = isinstance(value, dict) and all(
        isinstance(k, str) and k and isinstance(v, str) and v for k, v in value.items()
    )
    if not ok:
        raise BadRequest(f"field '{name}' must map names to version strings")
    return value


def versions_by_name(body: dict[str, Any], name: str) -> dict[str, list[str]] | None:
    """A mapping of names to lists of version strings; None when absent."""
    value = body.get(name)
    if value is None:
        return None
    ok = isinstance(value, dict) and all(
        isinstance(k, str) and k and isinstance(v, list)
        and all(isinstance(item, str) and item for item in v) for k, v in value.items()
    )
    if not ok:
        raise BadRequest(f"field '{name}' must map names to lists of versions")
    return value


def integer(body: dict[str, Any], name: str, default: Any = _MISSING,
            low: int | None = None, high: int | None = None) -> Any:
    """An int within [low, high] (bool is rejected); `default` when absent or null."""
    value = _get(body, name, default)
    if value is default and default is not _MISSING:
        return value
    if not isinstance(value, int) or isinstance(value, bool):
        raise BadRequest(f"field '{name}' must be an integer")
    if (low is not None and value < low) or (high is not None and value > high):
        raise BadRequest(f"field '{name}' must be between {low} and {high}, got {value}")
    return value


def number(body: dict[str, Any], name: str, default: Any = _MISSING) -> Any:
    """A non-negative int or float; `default` when absent or null."""
    value = _get(body, name, default)
    if value is default and default is not _MISSING:
        return value
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise BadRequest(f"field '{name}' must be a non-negative number")
    return value


def flag(body: dict[str, Any], name: str, default: bool = False) -> bool:
    value = _get(body, name, default)
    if not isinstance(value, bool):
        raise BadRequest(f"field '{name}' must be true or false")
    return value


def job_id(body: dict[str, Any], name: str = "job_id") -> str:
    value = _get(body, name, _MISSING)
    return check_job_id(value)


def check_job_id(value: Any) -> str:
    """A well-formed `job-<ULID>` id; it ends up in file names, so this is strict."""
    if not isinstance(value, str) or not is_valid_id(value, "job"):
        raise BadRequest(f"not a valid job id: {value!r}")
    return value


LOAD_FIELDS = ("cpu_pct", "mem_pct", "cores", "net_in_kib_s", "net_out_kib_s")
MAX_KIB_S = 100 * 1024 * 1024  # 100 GiB/s: anything above is not a reading
CI_RESULT_FIELDS = {"outcome": 32, "step": 200, "message": 500}  # name -> longest kept


def ci_result(body: dict[str, Any], name: str = "ci_result") -> dict[str, str]:
    """How a GitHub job went, as a runner's completed hook read it (runners/diary.py): its
    `outcome`, and the `step` that failed with GitHub's `message`. Only non-empty strings are kept,
    cut to a length; anything else is dropped, so an odd value never fails a release."""
    value = body.get(name)
    if not isinstance(value, dict):
        return {}
    return {key: item[:limit] for key, limit in CI_RESULT_FIELDS.items()
            if isinstance(item := value.get(key), str) and item}


def load(body: dict[str, Any], name: str = "load") -> dict[str, Any] | None:
    """A worker's machine load: `cpu_pct` and `mem_pct` (0 to 100), `cores`, and its network in
    and out (`net_in_kib_s`, `net_out_kib_s`, M14.2), each or null.
    Anything else in it, or a value out of range, is dropped: a reading must not fail a claim."""
    value = body.get(name)
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    for key in LOAD_FIELDS:
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            out[key] = None
        elif key == "cores":
            out[key] = int(item) if 1 <= item <= 4096 else None
        elif key.startswith("net_"):
            out[key] = float(item) if 0 <= item <= MAX_KIB_S else None
        else:
            out[key] = float(item) if 0 <= item <= 100 else None
    return out
