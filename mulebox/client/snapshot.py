"""Pack the project worktree into a private tar.gz for upload (docs/design.md, Job lifecycle).

Contents: what `git ls-files -co --exclude-standard` lists under the project root (tracked
plus untracked, not ignored), minus the built-in secret excludes and the project's
`exclude` patterns (see excludes.py). Excluded files never enter the archive, even when
they are tracked in git. Symlinks are stored as links; a link that is absolute or points
outside the project root is skipped, because the worker refuses such links on extraction.

Archive members carry the path, permission bits, size and mtime only: owner ids and names
are zeroed so the archive never reveals the laptop's user name. The file is created with
`tempfile.mkstemp` (mode 0600); the caller deletes it with `Snapshot.discard()`.
"""

from __future__ import annotations

import hashlib
import os
import tarfile
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from mulebox.client import gitinfo
from mulebox.client.excludes import Excludes, Patterns
from mulebox.client.tree import (
    Fingerprint,
    current_fingerprint,
    link_digest,
    link_stays_inside,
    selected_paths,
    walk,
)
from mulebox.common.errors import MuleboxError

__all__ = ["Snapshot", "SnapshotError", "current_fingerprint", "make_snapshot", "sha256_file"]

MAX_SNAPSHOT_BYTES = 1024**3  # the coordinator's upload cap
_COMPRESS_LEVEL = 6


class SnapshotError(MuleboxError):
    """The worktree cannot be packed (not a git worktree, too large, changed while read)."""


@dataclass(frozen=True)
class Snapshot:
    path: Path
    sha256: str  # of the tar.gz file
    fingerprint: str  # of the contents (see tree.py)
    base_commit: str
    branch: str
    files: int
    size: int
    skipped_links: tuple[str, ...] = ()

    def discard(self) -> None:
        """Delete the temporary archive (our own temp file; safe to call twice)."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class _HashingReader:
    """File wrapper that hashes every byte tarfile reads from it."""

    def __init__(self, file: BinaryIO) -> None:
        self._file = file
        self.hash = hashlib.sha256()

    def read(self, size: int = -1) -> bytes:
        data = self._file.read(size)
        self.hash.update(data)
        return data


def make_snapshot(root: Path, extra_excludes: Iterable[str] = (),
                  ignore_changes: Iterable[str] = ()) -> Snapshot:
    """Pack `root` (the folder holding .mulebox.yml) into a temporary tar.gz. Paths matching
    `ignore_changes` are packed but left out of the fingerprint."""
    root = Path(root).resolve()
    try:
        gitinfo.ensure_worktree(root)
        gitinfo.ensure_commit(root)
        paths = selected_paths(root, Excludes(extra_excludes))
        commit, branch = gitinfo.base_commit(root), gitinfo.branch(root)
    except gitinfo.GitError as exc:
        raise SnapshotError(str(exc)) from exc
    fd, name = tempfile.mkstemp(prefix="mulebox-snapshot-", suffix=".tar.gz")
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as raw:
            fingerprint, files, skipped = _write_archive(root, paths, raw,
                                                         Patterns(ignore_changes))
        size = path.stat().st_size
        if size > MAX_SNAPSHOT_BYTES:
            raise SnapshotError(
                f"snapshot is {size / 1024**2:.0f} MiB, over the 1 GiB upload limit; add large "
                "generated folders to `exclude` in .mulebox.yml or to .gitignore"
            )
        digest = sha256_file(path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return Snapshot(path, digest, fingerprint, commit, branch, files, size, tuple(skipped))


def _write_archive(root: Path, paths: list[str], raw: BinaryIO,
                   unchecked: Patterns | None = None) -> tuple[str, int, list[str]]:
    fingerprint, files, skipped = Fingerprint(unchecked), 0, []
    with tarfile.open(
        fileobj=raw, mode="w:gz", format=tarfile.PAX_FORMAT, compresslevel=_COMPRESS_LEVEL
    ) as tar:
        for entry in walk(root, paths):
            info = _tar_info(entry.path, entry.st)
            if entry.link is not None:
                if not link_stays_inside(entry.path, entry.link):
                    skipped.append(entry.path)
                    continue
                info.type, info.linkname, info.size = tarfile.SYMTYPE, entry.link, 0
                tar.addfile(info)
                fingerprint.add(entry.path, entry.st.st_mode, link_digest(entry.link))
            else:
                reader = _HashingReader(entry.file)
                try:
                    tar.addfile(info, reader)
                except OSError as exc:  # tarfile: "unexpected end of data"
                    raise SnapshotError(
                        f"{entry.path} changed while the snapshot was taken ({exc}); retry"
                    ) from exc
                fingerprint.add(entry.path, entry.st.st_mode, reader.hash.hexdigest())
            files += 1
    return fingerprint.hexdigest(), files, skipped


def _tar_info(path: str, st: os.stat_result) -> tarfile.TarInfo:
    info = tarfile.TarInfo(path)
    info.mode = st.st_mode & 0o7777
    info.size = st.st_size
    info.mtime = int(st.st_mtime)
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
