"""How many bytes a folder holds, as `du` counts them: symlinks are not followed and a file with
several hard links (pnpm links its store into every `node_modules`) counts once.

A project folder can hold millions of files, so a caller that wants the size of a folder and of
some folders inside it asks once (`sizes`), and the files are read in one walk.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


def sizes(root: Path, parts: Iterable[Path] = (),
          seen: set[tuple[int, int]] | None = None) -> tuple[int, dict[Path, int]]:
    """The size of `root`, and of each folder of `parts` inside it, in one walk. A file linked
    in two of them counts in the first one walked; pass the same `seen` to several walks to
    count it once across them all. A part inside another counts in the innermost."""
    wanted = {str(part): part for part in parts}
    seen = set() if seen is None else seen
    total, found = _walk(str(root), wanted, seen)
    return total, {wanted[key]: found.get(key, 0) for key in wanted}


def size_of(folder: Path) -> int:
    return sizes(folder)[0]


def _walk(top: str, wanted: dict[str, Path],
          seen: set[tuple[int, int]]) -> tuple[int, dict[str, int]]:
    total, found = 0, dict[str, int]()
    stack: list[tuple[str, str | None]] = [(top, None)]
    while stack:
        folder, inside = stack.pop()
        try:
            entries = os.scandir(folder)
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((entry.path, entry.path if entry.path in wanted else inside))
                        continue
                    info = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                if info.st_nlink > 1:
                    key = (info.st_dev, info.st_ino)
                    if key in seen:
                        continue
                    seen.add(key)
                total += info.st_size
                if inside is not None:
                    found[inside] = found.get(inside, 0) + info.st_size
    return total, found



def freed(roots: Iterable[Path]) -> int:
    """The bytes removing all of `roots` gives back: a file counts only when every hard link to
    it is inside them (a pnpm `node_modules` links its store, which stays, so its files free
    nothing). Symlinks are not followed."""
    total, links = 0, dict[tuple[int, int], list[int]]()

    def count(info: os.stat_result) -> None:
        nonlocal total
        if info.st_nlink <= 1:
            total += info.st_size
            return
        seen = links.setdefault((info.st_dev, info.st_ino), [info.st_nlink, 0, info.st_size])
        seen[1] += 1

    stack: list[str] = []
    for root in roots:
        try:
            if root.is_dir() and not root.is_symlink():
                stack.append(str(root))
            else:
                count(root.lstat())
        except OSError:
            continue
    while stack:
        try:
            entries = os.scandir(stack.pop())
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    else:
                        count(entry.stat(follow_symlinks=False))
                except OSError:
                    continue
    return total + sum(size for nlink, inside, size in links.values() if inside >= nlink)
