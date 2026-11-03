"""Safe tar extraction into a folder inside the worker roots.

Used for job snapshots (tar.gz from the client) and toolchain tarballs (tar.xz). Every
member is checked before anything is written: no absolute names, no `..`, no device or
fifo entries, links must stay inside the destination. Extraction itself runs with
tarfile's `filter="data"`, which repeats those checks against the real file system (it
also refuses writing through a symlink that leaves the destination) and drops setuid
bits. The destination is created through `safepath.ensure_dir`.
"""

from __future__ import annotations

import posixpath
import tarfile
from collections.abc import Iterator
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.safepath import Roots, ensure_dir


class ArchiveError(MuleboxError):
    """An archive is unreadable or contains an entry that would escape its folder."""


def _clean_name(name: str, where: Path) -> str:
    if name.startswith("/") or "\\" in name or "\0" in name:
        raise ArchiveError(f"{where}: refusing archive entry {name!r} (absolute or odd name)")
    norm = posixpath.normpath(name)
    if norm == ".." or norm.startswith("../") or ".." in name.split("/"):
        raise ArchiveError(f"{where}: refusing archive entry {name!r} (leaves the folder)")
    return norm


def _strip(name: str, prefix: str | None, where: Path) -> str | None:
    """Drop `prefix/` from name; None for the prefix folder itself."""
    if prefix is None:
        return name
    if name == prefix:
        return None
    if not name.startswith(prefix + "/"):
        raise ArchiveError(f"{where}: entry {name!r} is not under {prefix!r}")
    return name[len(prefix) + 1:]


def _check_link(member: tarfile.TarInfo, name: str, where: Path) -> None:
    target = member.linkname
    if member.issym():
        if target.startswith("/"):
            raise ArchiveError(f"{where}: symlink {name!r} points to an absolute path")
        joined = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
    else:
        joined = posixpath.normpath(target)
    if joined == ".." or joined.startswith("../") or joined.startswith("/"):
        raise ArchiveError(f"{where}: link {name!r} points outside the folder ({target!r})")


def _members(tar: tarfile.TarFile, prefix: str | None, where: Path) -> Iterator[tarfile.TarInfo]:
    for member in tar:
        name = _strip(_clean_name(member.name, where), prefix, where)
        if name is None or name == ".":
            continue
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ArchiveError(f"{where}: refusing special entry {member.name!r}")
        changes: dict = {"name": name}
        if member.islnk():
            link = _strip(_clean_name(member.linkname, where), prefix, where)
            if link is None:
                raise ArchiveError(f"{where}: hard link {member.name!r} to the top folder")
            changes["linkname"] = link
        member = member.replace(**changes, deep=False)
        if member.issym() or member.islnk():
            _check_link(member, name, where)
        yield member


def extract_tar(archive: Path, dest: Path, roots: Roots, *, strip_prefix: str | None = None,
                ) -> Path:
    """Extract archive (any tarfile compression) into dest, created inside the roots.

    strip_prefix drops one leading folder every entry must be under (toolchain tarballs).
    """
    ensure_dir(dest, roots)
    try:
        with tarfile.open(archive, "r:*") as tar:
            members = list(_members(tar, strip_prefix, archive))
            tar.extractall(dest, members=members, filter="data")
    except ArchiveError:
        raise
    except tarfile.FilterError as exc:
        raise ArchiveError(f"{archive}: refusing archive entry: {exc}") from exc
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise ArchiveError(f"{archive}: cannot extract: {exc}") from exc
    return dest
