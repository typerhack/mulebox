"""Mount detection for safepath: is a path, or anything under it, a mount point?

Linux: /proc/self/mountinfo lists every mount point (bind mounts included, even when they
share a device with their source), and /proc/self/fdinfo/<fd> gives the mount id of an
open file descriptor, so a directory can be checked after it is opened, without a race.
Other systems (macOS) have neither: callers fall back to st_dev and os.path.ismount.

This module only reports; the decisions (and the errors) live in safepath.py.
"""

import os
import re
import sys
from pathlib import Path

MOUNTINFO = "/proc/self/mountinfo"
# The kernel escapes space, tab, newline and backslash in mountinfo paths as \ooo.
_OCTAL_ESCAPE = re.compile(rb"\\([0-3][0-7]{2})")

# (st_dev, mount id or None when the system cannot tell)
Identity = tuple[int, int | None]


def is_within(path: Path, base: Path) -> bool:
    """True if path is base or below it, compared by path components (not string prefix)."""
    return path.parts[: len(base.parts)] == base.parts


def unescape(field: bytes) -> str:
    """Decode one mountinfo path field (\\040 -> space, \\134 -> backslash, ...)."""
    raw = _OCTAL_ESCAPE.sub(lambda match: bytes([int(match.group(1), 8)]), field)
    return os.fsdecode(raw)


def parse_mountinfo(data: bytes | str) -> list[Path]:
    """Return the mount points listed in mountinfo text. ValueError on a malformed line."""
    if isinstance(data, str):
        data = os.fsencode(data)
    points = []
    for line in data.splitlines():
        if not line.strip():
            continue
        fields = line.split(b" ")
        # id parent major:minor root mount-point options ... - fstype source super-options
        if len(fields) < 5 or not fields[4].startswith(b"/"):
            raise ValueError(f"malformed mountinfo line: {line!r}")
        points.append(Path(unescape(fields[4])))
    return points


def linux_mount_points() -> list[Path] | None:
    """Mount points of this process on Linux; None on systems without mountinfo.

    On Linux a missing or unreadable mount table raises OSError: callers must fail closed.
    """
    if not sys.platform.startswith("linux"):
        return None
    with open(MOUNTINFO, "rb") as handle:
        return parse_mountinfo(handle.read())


def blocking_mounts(target: Path, root: Path, points: list[Path]) -> list[Path]:
    """Mount points that make deleting target unsafe.

    That is any mount at or below target, and any mount strictly inside root that target
    lives under (a bind mount between the root and the target could lead outside the root).
    The root itself being a mount point is fine.
    """
    found = []
    for point in points:
        if is_within(point, target):
            found.append(point)
        elif point != root and is_within(point, root) and is_within(target, point):
            found.append(point)
    return found


def is_mount_point(path: Path) -> bool:
    """Fallback check for systems without mountinfo (does not follow a final symlink)."""
    return os.path.ismount(path)


def parse_fdinfo_mnt_id(data: bytes) -> int | None:
    """Read the mnt_id field from /proc/self/fdinfo/<fd> text."""
    for line in data.splitlines():
        if line.startswith(b"mnt_id:"):
            return int(line.split(b":", 1)[1].strip())
    return None


def fd_mount_id(fd: int) -> int | None:
    """Mount id of an open fd on Linux; None elsewhere or when /proc cannot tell."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        with open(f"/proc/self/fdinfo/{fd}", "rb") as handle:
            return parse_fdinfo_mnt_id(handle.read())
    except (OSError, ValueError):
        return None


def fd_identity(fd: int) -> Identity:
    """(st_dev, mount id) of an open file descriptor."""
    return os.fstat(fd).st_dev, fd_mount_id(fd)


def same_mount(a: Identity, b: Identity) -> bool:
    """True if both identities are on one mount. Unknown on one side only counts as different."""
    if a[0] != b[0]:
        return False
    if a[1] is None and b[1] is None:
        return True
    return a[1] == b[1]
