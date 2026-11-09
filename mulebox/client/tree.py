"""Walk the files of a snapshot without ever following a symlink.

Every path is opened component by component from a descriptor of the project root with
`O_NOFOLLOW`, so neither the file itself nor any parent directory can redirect a read to
somewhere outside the worktree (a tracked `dir/file` whose `dir` became a symlink is
skipped). Regular files are yielded with an open binary file; symlinks with their target
text. Files that vanished, directories (submodules, nested repositories), sockets, FIFOs
and devices are skipped.

The fingerprint is the sha256 over the sorted entries, one line each:
`<path> NUL <mode in octal> NUL <sha256 of the content, or of the link target>` + `\\n`.
"""

from __future__ import annotations

import errno
import hashlib
import os
import posixpath
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from mulebox.client import gitinfo
from mulebox.client.excludes import Excludes, Patterns

READ_CHUNK = 1024 * 1024
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
_SKIP_ERRNOS = {errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.EACCES, errno.EPERM}


@dataclass
class Entry:
    path: str  # relative to the project root, `/`-separated
    st: os.stat_result
    file: BinaryIO | None = None  # regular files: open for reading, closed after the step
    link: str | None = None  # symlinks: the target, unresolved


def selected_paths(root: Path, excludes: Excludes) -> list[str]:
    """The sorted paths git lists under `root`, minus every excluded one."""
    tracked = gitinfo.tracked_files(root)
    return [p for p in gitinfo.list_files(root) if not excludes.excluded(p, p in tracked)]


def walk(root: Path, paths: list[str]) -> Iterator[Entry]:
    """Yield an Entry per path that is still a regular file or a symlink."""
    root_fd = os.open(root, _DIR_FLAGS & ~os.O_NOFOLLOW)  # the root itself may be a link
    try:
        for path in paths:
            entry = _open_entry(root_fd, path)
            if entry is None:
                continue
            try:
                yield entry
            finally:
                if entry.file is not None:
                    entry.file.close()
    finally:
        os.close(root_fd)


def _open_entry(root_fd: int, path: str) -> Entry | None:
    *parents, name = path.split("/")
    if not name or any(p in ("", ".", "..") for p in parents) or name in (".", ".."):
        return None
    dir_fd = root_fd
    try:
        for part in parents:
            next_fd = os.open(part, _DIR_FLAGS, dir_fd=dir_fd)
            if dir_fd != root_fd:
                os.close(dir_fd)
            dir_fd = next_fd
        return _open_final(dir_fd, path, name)
    except OSError as exc:
        if exc.errno in _SKIP_ERRNOS:
            return None
        raise
    finally:
        if dir_fd != root_fd:
            os.close(dir_fd)


def _open_final(dir_fd: int, path: str, name: str) -> Entry | None:
    st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    if stat.S_ISLNK(st.st_mode):
        return Entry(path, st, link=os.readlink(name, dir_fd=dir_fd))
    if not stat.S_ISREG(st.st_mode):
        return None
    fd = os.open(name, _FILE_FLAGS, dir_fd=dir_fd)
    try:
        st = os.fstat(fd)  # the entry may have been swapped since the lstat
        if not stat.S_ISREG(st.st_mode):
            os.close(fd)
            return None
        os.set_blocking(fd, True)
        return Entry(path, st, file=os.fdopen(fd, "rb"))
    except BaseException:
        os.close(fd)
        raise


class Fingerprint:
    """Accumulates entries (in sorted path order) into the snapshot fingerprint."""

    def __init__(self, unchecked: Patterns | None = None) -> None:
        self._hash = hashlib.sha256()
        self._unchecked = unchecked  # `ignore_changes`: sent, never fingerprinted

    def add(self, path: str, mode: int, digest: str) -> None:
        if self._unchecked and self._unchecked.matches(path):
            return
        line = f"{path}\0{mode:o}\0{digest}\n"
        self._hash.update(line.encode("utf-8", errors="surrogateescape"))

    def hexdigest(self) -> str:
        return self._hash.hexdigest()


def link_stays_inside(path: str, target: str) -> bool:
    """True if the link at `path` points inside the project root (lexically)."""
    if not target or target.startswith("/"):
        return False
    joined = posixpath.normpath(posixpath.join(posixpath.dirname(path), target))
    return joined != ".." and not joined.startswith("../")


def link_digest(target: str) -> str:
    return hashlib.sha256(os.fsencode(target)).hexdigest()


def file_digest(file: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: file.read(READ_CHUNK), b""):
        digest.update(chunk)
    return digest.hexdigest()


def current_fingerprint(root: Path, extra_excludes=(), ignore_changes=()) -> str:
    """Fingerprint of the worktree as it is now (for the stale check after a job)."""
    root = Path(root)
    fingerprint = Fingerprint(Patterns(ignore_changes))
    for entry in walk(root, selected_paths(root, Excludes(extra_excludes))):
        if entry.link is not None:
            if not link_stays_inside(entry.path, entry.link):
                continue  # skipped by the snapshot too
            fingerprint.add(entry.path, entry.st.st_mode, link_digest(entry.link))
        else:
            fingerprint.add(entry.path, entry.st.st_mode, file_digest(entry.file))
    return fingerprint.hexdigest()
