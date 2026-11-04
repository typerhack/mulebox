"""Root-confined paths, and the only code in mulebox that deletes files.

Every path is checked against the configured roots (resolved once, compared by path
components). Deletion and creation are anchored on directory file descriptors: the root is
opened, then each component below it with O_NOFOLLOW relative to its parent, so a parent
swapped for a symlink after the check makes the operation fail instead of escaping. The
tree walk never follows symlinks, never crosses into another device or mount, and refuses
mount points (see mounts.py). There is no privilege escalation here: a permission failure
raises RemovalDenied and the caller decides what to do.

The error classes, Roots and resolve_inside live in roots.py and are re-exported here.
"""

import os
import stat
from pathlib import Path

from mulebox.common import mounts
from mulebox.common.mounts import is_within
from mulebox.common.roots import (
    PathOutsideRoots,
    RemovalDenied,
    Roots,
    UnsafePath,
    os_error,
    require_absolute,
    resolve_inside,
)

__all__ = [
    "DIR_MODE", "PathOutsideRoots", "RemovalDenied", "Roots", "UnsafePath", "confirm_dir",
    "ensure_dir", "remove_tree", "resolve_inside",
]

DIR_MODE = 0o750
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _open_root(root: Path, ident: tuple[int, int]) -> tuple[int, mounts.Identity]:
    try:
        fd = os.open(root, _DIR_FLAGS)
    except OSError as exc:
        raise os_error(f"cannot open root {root}", exc) from exc
    try:
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) != ident:
            raise UnsafePath(f"root {root} was replaced since it was configured")
        return fd, mounts.fd_identity(fd)
    except BaseException:
        os.close(fd)
        raise


def _open_child(dir_fd: int, name: str, where: Path, create: bool = False) -> int | None:
    """Open a subdirectory without following symlinks; None if missing and not create."""
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        if not create:
            return None
    except OSError as exc:
        raise _component_error(dir_fd, name, where, exc) from exc
    created = True
    try:
        os.mkdir(name, DIR_MODE, dir_fd=dir_fd)
    except FileExistsError:
        created = False
    except OSError as exc:
        raise os_error(f"cannot create {where}", exc) from exc
    try:
        fd = os.open(name, _DIR_FLAGS, dir_fd=dir_fd)
    except OSError as exc:
        raise _component_error(dir_fd, name, where, exc) from exc
    try:
        if created:
            os.fchmod(fd, DIR_MODE)  # mkdir's mode is reduced by the umask
    except BaseException:
        os.close(fd)
        raise
    return fd


def _component_error(dir_fd: int, name: str, where: Path, exc: OSError) -> UnsafePath:
    try:
        mode = os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode
    except OSError:
        mode = 0
    if stat.S_ISLNK(mode):
        return UnsafePath(f"{where} is a symlink; refusing to follow it")
    if mode and not stat.S_ISDIR(mode):
        return UnsafePath(f"{where} is not a directory")
    return os_error(f"cannot open {where}", exc)


def _require_same_mount(fd: int, ident: mounts.Identity, where: Path) -> None:
    if not mounts.same_mount(mounts.fd_identity(fd), ident):
        raise UnsafePath(f"{where} is on another device or mount than its root; refusing")


def _open_chain(root: Path, ident: tuple[int, int], parts: tuple[str, ...],
                create: bool) -> tuple[int, mounts.Identity] | None:
    """Open root/parts... component by component; None if a component is missing."""
    fd, root_ident = _open_root(root, ident)
    where = root
    try:
        for name in parts:
            where = where / name
            child = _open_child(fd, name, where, create)
            old, fd = fd, child
            os.close(old)
            if fd is None:
                return None
            _require_same_mount(fd, root_ident, where)
    except BaseException:
        if fd is not None:
            os.close(fd)
        raise
    return fd, root_ident


def _make_writable(fd: int) -> bool:
    """Add u+rwx to a directory we own (e.g. a read-only Go module cache). Via fd only."""
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & stat.S_IWUSR:
            return False
        os.fchmod(fd, stat.S_IMODE(info.st_mode) | stat.S_IRWXU)
        return True
    except OSError:
        return False


def _delete(dir_fd: int, name: str, where: Path, is_dir: bool, fix: bool) -> None:
    """Unlink a non-directory or rmdir an empty directory, relative to dir_fd."""
    op = os.rmdir if is_dir else os.unlink
    try:
        op(name, dir_fd=dir_fd)
        return
    except FileNotFoundError:
        return
    except PermissionError as exc:
        if not (fix and _make_writable(dir_fd)):
            raise RemovalDenied(f"permission denied removing {where}") from exc
    try:
        op(name, dir_fd=dir_fd)
    except FileNotFoundError:
        pass
    except PermissionError as exc:
        raise RemovalDenied(f"permission denied removing {where}") from exc


def _list_entries(fd: int, where: Path) -> list[os.DirEntry]:
    try:
        with os.scandir(fd) as entries:
            return list(entries)
    except OSError as exc:
        raise os_error(f"cannot list {where}", exc) from exc


def _clear(top_fd: int, top: Path, ident: mounts.Identity) -> None:
    """Delete everything inside the open directory top_fd (which the caller owns)."""
    stack = [(top_fd, top, iter(_list_entries(top_fd, top)))]
    try:
        while stack:
            fd, where, entries = stack[-1]
            for entry in entries:
                path = where / entry.name
                if not entry.is_dir(follow_symlinks=False):
                    _delete(fd, entry.name, path, is_dir=False, fix=True)
                    continue
                child = _open_child(fd, entry.name, path)
                if child is None:
                    continue
                try:
                    _require_same_mount(child, ident, path)
                    listing = iter(_list_entries(child, path))
                except BaseException:
                    os.close(child)
                    raise
                stack.append((child, path, listing))
                break
            else:
                stack.pop()
                if stack:
                    os.close(fd)
                    _delete(stack[-1][0], where.name, where, is_dir=True, fix=True)
    finally:
        for fd, *_ in stack[1:]:
            os.close(fd)


def _refuse_mounts(target: Path, root: Path) -> None:
    try:
        points = mounts.linux_mount_points()
    except (OSError, ValueError) as exc:
        raise UnsafePath(f"cannot read the mount table, refusing to delete: {exc}") from exc
    if points is None:
        if mounts.is_mount_point(target):
            raise UnsafePath(f"{target} is a mount point; refusing to delete it")
        return
    found = mounts.blocking_mounts(target, root, points)
    if found:
        raise UnsafePath(f"refusing to delete {target}: mount point {found[0]} is in the way")


def remove_tree(path: Path, roots: Roots) -> None:
    """Delete path (file, symlink or directory tree) strictly inside a root. Missing: no-op."""
    path = require_absolute(path)
    if path.name in ("", ".", ".."):
        raise UnsafePath(f"{path} does not name an entry")
    parent = Path(os.path.realpath(path.parent))
    target = parent / path.name
    if target in roots.paths:
        raise UnsafePath(f"{path} is the root {target} itself")
    for index, root in enumerate(roots.paths):
        if is_within(parent, root):
            break
    else:
        raise PathOutsideRoots(f"{path} (resolved: {target}) is outside the configured roots")
    _refuse_mounts(target, root)
    try:
        opened = _open_chain(root, roots._ids[index], parent.relative_to(root).parts, False)
        if opened is None:
            return
        parent_fd, ident = opened
        try:
            _remove_entry(parent_fd, path.name, target, ident)
        finally:
            os.close(parent_fd)
    except OSError as exc:
        raise os_error(f"could not remove {target}", exc) from exc


def _remove_entry(parent_fd: int, name: str, target: Path, ident: mounts.Identity) -> None:
    try:
        mode = os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(mode):
        _delete(parent_fd, name, target, is_dir=False, fix=False)
        return
    fd = _open_child(parent_fd, name, target)
    if fd is None:
        return
    try:
        _require_same_mount(fd, ident, target)
        _clear(fd, target, ident)
    finally:
        os.close(fd)
    _delete(parent_fd, name, target, is_dir=True, fix=False)


def _spelled_under_root(path: Path, roots: Roots) -> tuple[Path, int, Path]:
    """(path, index of its root, the root); no '..', never the root itself."""
    path = require_absolute(path)
    if ".." in path.parts:
        raise UnsafePath(f"{path} contains '..'")
    for index, root in enumerate(roots.paths):
        if is_within(path, root):
            break
    else:
        raise PathOutsideRoots(f"{path} is not under a configured root (use Roots.paths)")
    if path == root:
        raise UnsafePath(f"{path} is the root {root} itself")
    return path, index, root


def confirm_dir(path: Path, roots: Roots) -> Path:
    """Prove path is a real directory strictly inside a root, and return it.

    For handing a path to something that cannot use descriptors, such as a bind mount: it
    must be spelled under a root, no component below the root may be a symlink, and no mount
    may be in or above it. The caller must make sure nothing can change it afterwards.
    """
    path, index, root = _spelled_under_root(path, roots)
    _refuse_mounts(path, root)
    try:
        opened = _open_chain(root, roots._ids[index], path.relative_to(root).parts, False)
    except OSError as exc:
        raise os_error(f"could not open {path}", exc) from exc
    if opened is None:
        raise UnsafePath(f"{path} does not exist")
    os.close(opened[0])
    return path


def ensure_dir(path: Path, roots: Roots) -> Path:
    """Create path (and missing parents) strictly inside a root, mode 0o750.

    The path must be spelled under a root as given in roots.paths, and no component below
    the root may be a symlink (not even one pointing back inside).
    """
    path, index, root = _spelled_under_root(path, roots)
    try:
        opened = _open_chain(root, roots._ids[index], path.relative_to(root).parts, True)
    except OSError as exc:
        raise os_error(f"could not create {path}", exc) from exc
    os.close(opened[0])
    return path
