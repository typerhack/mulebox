"""`<runners>/<runner>/.mulebox-reservation`: the job id of the runner's current slot.

Written by the job-started hook (atomically: temp file, then rename), read and removed by
the job-completed hook. The runner folder is created and the file removed only through
`common.safepath`, inside the runners root; no path component may be a symlink.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from mulebox.common.config_reader import NAME_RE
from mulebox.common.ids import is_valid_id
from mulebox.common.safepath import UnsafePath, ensure_dir, remove_tree
from mulebox.worker.paths import NodePaths

FILE_NAME = ".mulebox-reservation"
_FILE_MODE = 0o640
_MAX_BYTES = 256


def runner_dir(paths: NodePaths, runner: str) -> Path:
    """The runner's folder under the runners root; the name must be a simple name."""
    if not isinstance(runner, str) or not NAME_RE.fullmatch(runner):
        raise UnsafePath(f"runner name {runner!r} is not a safe folder name")
    return paths.runners / runner


def path_for(paths: NodePaths, runner: str) -> Path:
    return runner_dir(paths, runner) / FILE_NAME


def write(paths: NodePaths, runner: str, job_id: str) -> Path:
    """Store `job_id` for `runner`, replacing an older file atomically."""
    if not is_valid_id(job_id, "job"):
        raise UnsafePath(f"not a mulebox job id: {job_id!r}")
    folder = ensure_dir(runner_dir(paths, runner), paths.roots)
    temp = folder / f"{FILE_NAME}.{secrets.token_hex(6)}.part"
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 _FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(job_id + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, folder / FILE_NAME)
    except BaseException:
        remove_tree(temp, paths.roots)
        raise
    return folder / FILE_NAME


def read(paths: NodePaths, runner: str) -> str | None:
    """The stored job id, or None when there is no (valid) reservation file."""
    try:
        fd = os.open(path_for(paths, runner), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as handle:
        text = handle.read(_MAX_BYTES).decode("ascii", errors="replace").strip()
    return text if is_valid_id(text, "job") else None


def remove(paths: NodePaths, runner: str) -> None:
    """Remove the file (missing is fine)."""
    remove_tree(path_for(paths, runner), paths.roots)
