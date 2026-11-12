"""Small files inside the roots, written and read without following a symlink.

The folder is opened through safepath (`open_dir`), and the file is made relative to that
descriptor: written to a fresh temporary name (O_CREAT|O_EXCL|O_NOFOLLOW), flushed to disk,
then renamed over the name, so a reader sees the old file or the new one, never half of one.
A symlink planted at the temporary name, at the name, or in place of the folder after the
check cannot send the write anywhere else. Removal stays with safepath (`remove_tree`).
"""

from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from mulebox.common import safepath
from mulebox.common.roots import os_error

_WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def write_text(path: Path, text: str, roots: safepath.Roots, mode: int = 0o640) -> Path:
    """Replace `path` (its folder must exist inside the roots) with `text`, atomically."""
    folder = safepath.open_dir(path.parent, roots)
    temp = f".{path.name}.{secrets.token_hex(6)}.part"
    try:
        try:
            fd = os.open(temp, _WRITE, mode, dir_fd=folder)
        except OSError as exc:
            raise os_error(f"could not write {path}", exc) from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fchmod(handle.fileno(), mode)  # the umask reduced it at creation
                os.fsync(handle.fileno())
            os.rename(temp, path.name, src_dir_fd=folder, dst_dir_fd=folder)
        except BaseException:
            try:
                os.unlink(temp, dir_fd=folder)
            except OSError:
                pass
            raise
    finally:
        os.close(folder)
    return path


def read_text(path: Path, roots: safepath.Roots, limit: int = 1 << 20) -> str | None:
    """The text of `path` (at most `limit` bytes), or None when it does not exist. A symlink
    or anything but a regular file is refused (UnsafePath)."""
    try:
        folder = safepath.open_dir(path.parent, roots)
    except safepath.UnsafePath:
        if not os.path.lexists(path.parent):
            return None  # no folder, so no file
        raise
    try:
        try:
            fd = os.open(path.name, _READ, dir_fd=folder)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise os_error(f"could not read {path}", exc) from exc
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise safepath.UnsafePath(f"{path} is not a regular file")
            return handle.read(limit).decode("utf-8", errors="replace")
    finally:
        os.close(folder)
