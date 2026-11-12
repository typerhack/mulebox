"""Opening the runner's own files in `<runner>/_diag/` without following a link.

On an isolated runner (place.py) `_diag` is written by the job's container, so a job could put
a symlink there, to the node's `gh` sign-in for one, or a FIFO that blocks a reader. So every
file of it is opened from the runner folder down, one component at a time, never through a
symlink, and only when it is a regular file; reads are bounded by the callers. A host runner's
`_diag` gets the same, at no cost.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import BinaryIO

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)


def open_diag(runner_dir: Path, *parts: str) -> BinaryIO | None:
    """`<runner_dir>/_diag/<parts...>` opened for reading, or None (missing, a link, not a
    regular file, or a name with a slash in it)."""
    names = ("_diag", *parts)
    if any(not n or "/" in n or n in (".", "..") for n in names):
        return None
    fds: list[int] = []
    try:
        fds.append(os.open(runner_dir, _DIR))
        for name in names[:-1]:
            fds.append(os.open(name, _DIR, dir_fd=fds[-1]))
        fd = os.open(names[-1], _FILE, dir_fd=fds[-1])
    except OSError:
        return None
    finally:
        for parent in fds:
            os.close(parent)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            return None
        os.set_blocking(fd, True)
        return os.fdopen(fd, "rb")
    except OSError:
        os.close(fd)
        return None
