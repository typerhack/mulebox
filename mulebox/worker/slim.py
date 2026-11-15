"""Slimming an idle branch folder (design.md, Disk use and cleanup on its own, Slim folders).

A branch folder keeps what git ignores between jobs (`node_modules`, `vendor`, `.venv`, build
output such as `.next`), so the branch's next job is quick. Most of a folder is that, and most
branches get no job again once their pull request is merged. So once a folder had no job for
the node's `slim_hours`, the sweep removes what git ignores in it and keeps the checkout and its
git history: a slim folder is the size of the project's own files.

Its next job then runs `setup` and `install` again, as what they made is gone: slimming forgets
both and leaves a mark, `state/<folder>.slim`, which the next job's `prepare`
(project_home.py) takes away. The mark is how the sweep and the report tell a slim folder.

Removal goes through safepath like every other (project_disk.py); files a container left as
root are given back through `reclaim` first.
"""

from __future__ import annotations

import os
from pathlib import Path

from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.common.tree_size import freed
from mulebox.worker import project_disk, project_home, workspace
from mulebox.worker.paths import NodePaths

SLIM = project_home.SLIM


def _mark(paths: NodePaths, project: str, folder: str) -> Path:
    return paths.project_home(project) / "state" / f"{folder}.{SLIM}"


def is_slim(paths: NodePaths, project: str, folder: str) -> bool:
    mark = _mark(paths, project, folder)
    return mark.is_file() and not mark.is_symlink()


def ignored(tree: Path) -> list[Path]:
    """What git ignores in the folder, each ignored folder once (not the files in it)."""
    listing = workspace.git(tree, "ls-files", "-z", "--others", "--ignored", "--exclude-standard",
                            "--directory")
    names = {name.decode("utf-8", "surrogateescape").rstrip("/")
             for name in listing.split(b"\0") if name}
    return [tree / name for name in sorted(names) if name and not name.startswith("../")]


def would_free(paths: NodePaths, project: str, folder: str) -> int:
    """The bytes slimming the folder gives back now."""
    return freed(ignored(paths.project_home(project) / "trees" / folder))


def slim(paths: NodePaths, project: str, folder: str, reclaim: project_disk.Reclaim) -> None:
    """Remove what git ignores in the folder, forget its `setup` and `install`, and mark it."""
    for kind in (project_home.SETUP, project_home.INSTALL):
        remove_tree(paths.project_home(project) / "state" / f"{folder}.{kind}", paths.roots)
    for path in ignored(paths.project_home(project) / "trees" / folder):
        project_disk.remove_path(path, paths, reclaim)
    mark = _mark(paths, project, folder)
    ensure_dir(mark.parent, paths.roots)
    remove_tree(mark, paths.roots)
    os.close(os.open(mark, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600))

