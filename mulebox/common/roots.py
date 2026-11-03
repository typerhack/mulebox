"""Configured roots and path checks for safepath (public API: mulebox.common.safepath).

Roots are absolute, resolved once, must be existing directories, and may not be "/", the
user's home, a system directory, or anything containing one. Containment is compared by
path components on resolved paths, never by string prefix.
"""

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.mounts import is_within

# A root may not be one of these, nor contain one (so "/" and "/private" are out too).
_SYSTEM_DIRS = (
    "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib32", "/lib64", "/libx32",
    "/media", "/mnt", "/opt", "/proc", "/root", "/run", "/sbin", "/snap", "/srv", "/sys",
    "/tmp", "/usr", "/var", "/Applications", "/Library", "/System", "/Users", "/Volumes",
    "/cores", "/private/etc", "/private/tmp", "/private/var",
)
# A root may not live inside these pseudo file systems.
_PSEUDO_FS = ("/dev", "/proc", "/sys")


class PathOutsideRoots(MuleboxError):
    """The path is not inside any configured root."""


class UnsafePath(MuleboxError):
    """The path or operation is refused for safety (root itself, symlink, mount, ...)."""


class RemovalDenied(UnsafePath):
    """The operating system denied a deletion or creation (permission). Never escalated here."""


def _protected_paths() -> set[Path]:
    protected = {Path("/")}
    candidates = list(_SYSTEM_DIRS)
    try:
        candidates.append(str(Path.home()))
    except (RuntimeError, KeyError):
        pass
    for item in candidates:
        protected.add(Path(item))
        protected.add(Path(os.path.realpath(item)))
    return protected


def _check_root(path: Path) -> tuple[Path, tuple[int, int]]:
    """Validate one root; return its resolved path and (st_dev, st_ino)."""
    path = Path(path)
    if not path.is_absolute():
        raise UnsafePath(f"root {path} is not an absolute path")
    real = Path(os.path.realpath(path))
    try:
        info = os.stat(real)
    except OSError as exc:
        raise UnsafePath(f"root {path} cannot be used: {exc.strerror}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise UnsafePath(f"root {path} is not a directory")
    for pseudo in _PSEUDO_FS:
        if is_within(real, Path(pseudo)):
            raise UnsafePath(f"root {path} is inside the system directory {pseudo}")
    for protected in sorted(_protected_paths()):
        if is_within(protected, real):
            raise UnsafePath(f"root {path} is or contains the protected path {protected}")
    return real, (info.st_dev, info.st_ino)


@dataclass(frozen=True)
class Roots:
    """The folders mulebox may write and delete in. Resolved and checked at construction."""

    paths: tuple[Path, ...]
    _ids: tuple[tuple[int, int], ...] = field(default=(), init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        checked = [_check_root(path) for path in self.paths]
        if not checked:
            raise UnsafePath("no roots configured")
        resolved = [real for real, _ in checked]
        for i, a in enumerate(resolved):
            for b in resolved[i + 1:]:
                if is_within(a, b) or is_within(b, a):
                    raise UnsafePath(f"roots {a} and {b} overlap; roots must be separate")
        object.__setattr__(self, "paths", tuple(resolved))
        object.__setattr__(self, "_ids", tuple(ident for _, ident in checked))

    @classmethod
    def from_config(cls, roots: dict[str, str]) -> "Roots":
        """Build from a config mapping such as {"jobs": "/srv/mulebox/jobs", ...}."""
        if not roots:
            raise UnsafePath("no roots configured")
        for name, value in roots.items():
            if not isinstance(value, str) or not value:
                raise UnsafePath(f"root {name!r} must be a non-empty path string")
            try:
                _check_root(Path(value))
            except UnsafePath as exc:
                raise UnsafePath(f"root {name!r}: {exc}") from exc
        return cls(tuple(Path(value) for value in roots.values()))


def require_absolute(path: Path) -> Path:
    """Return path as a Path; UnsafePath if it is relative or contains a NUL byte."""
    path = Path(path)
    if "\0" in str(path):
        raise UnsafePath(f"path {str(path)!r} contains a NUL byte")
    if not path.is_absolute():
        raise UnsafePath(f"path {path} is not absolute")
    return path


def resolve_inside(path: Path, roots: Roots) -> Path:
    """Resolve symlinks and return the real path; it must be strictly inside one root."""
    path = require_absolute(path)
    real = Path(os.path.realpath(path))
    for root in roots.paths:
        if real == root:
            raise UnsafePath(f"{path} is the root {root} itself")
        if is_within(real, root):
            return real
    raise PathOutsideRoots(f"{path} (resolved: {real}) is outside the configured roots")


def os_error(what: str, exc: OSError) -> UnsafePath:
    """Wrap an OSError: permission problems become RemovalDenied, the rest UnsafePath."""
    cls = RemovalDenied if isinstance(exc, PermissionError) else UnsafePath
    return cls(f"{what}: {exc.strerror or exc}")
