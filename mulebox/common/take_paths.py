"""`mulebox run --take <path>`: files a run brings back to the laptop (issue #4).

A command such as `composer update --no-install` or `npm install --package-lock-only` changes
lockfiles on the build machine, where they stayed. With `--take`, the worker reads the named
files from the job's worktree once the command passed, sends them to the coordinator in chunks
(coordinator/taken.py), and the client writes them into the project (client/take_back.py).

Client, coordinator and worker all check a path the same way, here: relative, inside the
project, at most MAX_FILES of them. Sizes are capped, as each file travels in memory.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable

MAX_FILES = 20
MAX_FILE_BYTES = 16 << 20
MAX_TOTAL_BYTES = 32 << 20
CHUNK_BYTES = 512 << 10  # base64 of it stays well under a 1 MiB message line


def problem(path: object) -> str | None:
    """Why `path` cannot be taken back, or None."""
    if not isinstance(path, str) or not path.strip():
        return "is empty"
    if "\0" in path or "\\" in path or len(path) > 400:
        return "is not a plain path"
    if path.startswith("/") or posixpath.normpath(path) != path.rstrip("/") or path.endswith("/"):
        return "must be a file inside the project, written as a relative path such as api/composer.lock"
    if path == "." or path.split("/")[0] == ".." or ".." in path.split("/"):
        return "must stay inside the project"
    return None


def checked(paths: Iterable[object]) -> tuple[str, ...]:
    """The paths, each once, in order; ValueError naming the first bad one."""
    found = tuple(dict.fromkeys(paths))
    if len(found) > MAX_FILES:
        raise ValueError(f"at most {MAX_FILES} files can be taken back")
    for path in found:
        why = problem(path)
        if why:
            raise ValueError(f"--take {path!r} {why}")
    return found  # type: ignore[return-value]
