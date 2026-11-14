"""How many bytes a folder holds, as `du` counts them: symlinks are not followed and a file with
several hard links (pnpm links its store into every `node_modules`) counts once.

A project folder can hold millions of files, so a caller that wants the size of a folder and of
some folders inside it asks once (`sizes`), and the files are read in one walk.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path


def sizes(root: Path, parts: Iterable[Path] = ()) -> tuple[int, dict[Path, int]]:
    """The size of `root`, and of each folder of `parts` inside it, in one walk. A file linked
    in two of them counts in the first one walked."""
    wanted = {str(part): part for part in parts}
    seen: set[tuple[int, int]] = set()
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
