"""`keep:` and `--keep`: files a job keeps for the dev machine to fetch (docs/design.md, Files back).

An entry is a file, a folder (all of it, written with or without a trailing `/`), or a pattern
with `*` and `**`, relative to the folder with `.mulebox.yml`. Client, coordinator and worker
check an entry the same way, here; the worker finds the files (worker/files_out.py).
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable
from typing import Any

from mulebox.common import units

MAX_ENTRIES = 20
DEFAULT_MAX_BYTES = 200_000_000  # 200 MB, keep_files_max (common/storage_policy.py)
FOLDER = ".mulebox"  # in a project: what mulebox writes there; git and snapshots leave it out
FILES_DIR = "files"  # .mulebox/files/<job>/: what `mulebox fetch` brings
MAX_LISTED = 50  # left-out files named in a result; the rest are counted


def problem(entry: object) -> str | None:
    """Why `entry` cannot be kept, or None."""
    if not isinstance(entry, str) or not entry.strip():
        return "is empty"
    if "\0" in entry or "\\" in entry or len(entry) > 400:
        return "is not a plain path"
    bare = entry.rstrip("/")
    if entry.startswith("/") or not bare or posixpath.normpath(bare) != bare:
        return "must be a path inside the project, written relative, such as test-results/"
    if bare == "." or ".." in bare.split("/"):
        return "must stay inside the project"
    if any(ch in bare for ch in "?[]{}"):
        return "may use only * and ** as patterns"
    if bare.split("/")[0] == FOLDER:
        return f"is mulebox's own folder ({FOLDER}/)"
    return None


def checked(entries: Iterable[object]) -> tuple[str, ...]:
    """The entries, each once, in order; ValueError naming the first bad one."""
    found = tuple(dict.fromkeys(entries))
    if len(found) > MAX_ENTRIES:
        raise ValueError(f"at most {MAX_ENTRIES} keep entries")
    for entry in found:
        why = problem(entry)
        if why:
            raise ValueError(f"keep {entry!r} {why}")
    return found  # type: ignore[return-value]


def from_config(reader: Any) -> tuple[str, ...] | None:
    """`keep:` from a config Reader (top level or a job's mapping); None when not written."""
    if "keep" not in reader.data:
        return None
    entries = reader.strings("keep")
    try:
        return checked(entries)
    except ValueError as exc:
        reader.fail("keep", str(exc).removeprefix("keep "))
    return None  # not reached: fail raises


def summary(files: dict[str, Any] | None) -> str | None:
    """'12 files kept (3.4 MB), 2 left out' for a job's `files` record, or None for none."""
    if not files or not files.get("count") and not files.get("left_out_count"):
        return None
    count = int(files.get("count") or 0)
    text = f"{count} file{'s' if count != 1 else ''} kept ({units.size(int(files.get('bytes') or 0))})"
    out = int(files.get("left_out_count") or 0)
    return text + (f", {out} left out" if out else "")
