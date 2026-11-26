"""The files a job's `keep:` names, found and packed on the worker (docs/design.md, Files back).

Read from the branch's folder once the job's cleanup ran, so files its containers wrote are the
worker's own. An entry is a file, a folder or a pattern with `*` (inside one name) and `**`
(any depth); each is walked from its fixed part, never through a symlink: the start must be
reached with none, and a link met on the way is named, not followed. Only regular files go in.
Past `keep_files_max` (on the files' own size) the smallest go first, so a report keeps its many
small files over one big trace; the rest are named as left out. The pack is a tar.gz in
`<staging>/files-out/`, with names relative to the project and no owner or link entries.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import tarfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mulebox.common import keep_files, units
from mulebox.common.safepath import Roots, ensure_dir, remove_tree

OUT = "files-out"
MAX_FILES = 50_000  # files looked at per job; past it the rest are counted as left out


@dataclass
class Gathered:
    files: list[tuple[str, int]] = field(default_factory=list)  # (path in the project, size)
    left_out: list[str] = field(default_factory=list)  # "path: why"
    left_out_count: int = 0

    def leave(self, path: str, why: str) -> None:
        self.left_out_count += 1
        if len(self.left_out) < keep_files.MAX_LISTED:
            self.left_out.append(f"{path}: {why}")

    @property
    def size(self) -> int:
        return sum(size for _, size in self.files)

    def report(self, packed: bool) -> dict[str, Any]:
        return {"count": len(self.files), "bytes": self.size, "left_out": self.left_out,
                "left_out_count": self.left_out_count, "packed": packed}


def _pattern(entry: str) -> re.Pattern[str]:
    parts = []
    for piece in re.split(r"(\*\*/?|\*)", entry):
        if piece.startswith("**"):
            parts.append("(?:.*/)?" if piece.endswith("/") else ".*")
        elif piece == "*":
            parts.append("[^/]*")
        else:
            parts.append(re.escape(piece))
    return re.compile("".join(parts) + "(?:/.*)?")  # a folder that matches brings all of it


def _start(entry: str) -> str:
    """The fixed folders before the first pattern, '' for the project itself."""
    fixed = []
    for name in entry.split("/"):
        if "*" in name:
            break
        fixed.append(name)
    return "/".join(fixed[:-1] if fixed == entry.split("/") else fixed)


def _unlinked(tree: Path, rel: str) -> bool:
    """Is `rel` reached from `tree` with no symlink on the way?"""
    real = os.path.realpath(tree)
    return os.path.realpath(os.path.join(real, rel)) == os.path.normpath(os.path.join(real, rel))


def _walk(tree: Path, entry: str, found: dict[str, int], out: Gathered) -> None:
    bare = entry.rstrip("/")
    start = bare if "*" not in bare else _start(bare)
    if start and not _unlinked(tree, start):
        out.leave(entry, "goes through a link, not followed")
        return
    try:
        info = os.lstat(tree / start) if start else os.lstat(tree)
    except OSError:
        out.leave(entry, "matches nothing")
        return
    match = _pattern(bare) if "*" in bare else None
    if stat.S_ISREG(info.st_mode):
        _take(tree, start, info, found, out)
        return
    if not stat.S_ISDIR(info.st_mode):
        out.leave(entry, "is not a file or folder")
        return
    before = len(found) + out.left_out_count
    for folder, names, files in os.walk(tree / start if start else tree):
        here = os.path.relpath(folder, tree)
        for name in sorted(names):  # os.walk does not go into a link with followlinks off
            rel = os.path.normpath(os.path.join(here, name))
            if os.path.islink(os.path.join(folder, name)) and (match is None or match.fullmatch(rel)):
                out.leave(rel, "is a link, not followed")
        for name in sorted(files):
            rel = os.path.normpath(os.path.join(here, name))
            if match is not None and not match.fullmatch(rel):
                continue
            try:
                info = os.lstat(os.path.join(folder, name))
            except OSError:
                continue
            _take(tree, rel, info, found, out)
            if len(found) >= MAX_FILES:
                out.leave(entry, f"has more than {MAX_FILES} files; the rest were not looked at")
                return
    if len(found) + out.left_out_count == before:
        out.leave(entry, "matches nothing")


def _take(tree: Path, rel: str, info: os.stat_result, found: dict[str, int], out: Gathered) -> None:
    if rel in found:
        return
    if stat.S_ISLNK(info.st_mode):
        out.leave(rel, "is a link, not followed")
    elif not stat.S_ISREG(info.st_mode):
        out.leave(rel, "is not a plain file")
    elif not os.access(tree / rel, os.R_OK):
        out.leave(rel, "cannot be read")
    else:
        found[rel] = info.st_size


def gather(tree: Path, entries: list[str], max_bytes: int) -> Gathered:
    """What the entries name in `tree`, smallest first up to `max_bytes`."""
    out, found = Gathered(), {}
    for entry in entries:
        if keep_files.problem(entry) is None:
            _walk(tree, entry, found, out)
    total = 0
    for rel, size in sorted(found.items(), key=lambda item: (item[1], item[0])):
        if total + size > max_bytes:
            out.leave(rel, f"past keep_files_max ({units.size(max_bytes)})")
            continue
        out.files.append((rel, size))
        total += size
    out.files.sort()
    return out


def pack(tree: Path, gathered: Gathered, staging: Path, roots: Roots, job_id: str
         ) -> tuple[Path, str]:
    """The files into `<staging>/files-out/<job_id>.tar.gz`; (its path, its sha256)."""
    target = ensure_dir(staging / OUT, roots) / f"{job_id}.tar.gz"
    remove_tree(target, roots)
    with tarfile.open(target, "w:gz") as tar:
        for rel, _ in list(gathered.files):
            try:
                fd = os.open(tree / rel, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            except OSError:
                gathered.files.remove((rel, _))
                gathered.leave(rel, "went before it was packed")
                continue
            with os.fdopen(fd, "rb") as handle:
                info = tar.gettarinfo(fileobj=handle, arcname=rel)
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode &= 0o755
                tar.addfile(info, handle)
    digest = hashlib.sha256()
    with open(target, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return target, digest.hexdigest()


def leftovers(staging: Path, roots: Roots) -> int:
    """Remove packs an earlier worker left; how many (at the worker's start)."""
    folder = staging / OUT
    if not folder.is_dir():
        return 0
    count = 0
    for name in os.listdir(folder):
        remove_tree(folder / name, roots)
        count += 1
    return count
