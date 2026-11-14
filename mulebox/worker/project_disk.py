"""What project folders hold on this machine, and removing them (docs/design.md, Project folders).

Everything in a project folder can be made again by a job, so removing it costs time, not data.
Callers hold the project first (coordinator/holds.py). Files a container left as root are given
back through `reclaim`, as a job's cleanup does.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.common.safepath import RemovalDenied, remove_tree
from mulebox.common.tree_size import sizes
from mulebox.worker import project_home, workspace
from mulebox.worker.paths import NodePaths

Reclaim = Callable[[Path], None]


def trees(paths: NodePaths, project: str) -> list[Path]:
    folder = paths.project_home(project) / "trees"
    return sorted(path for path in folder.iterdir() if path.is_dir()) if folder.is_dir() else []


def listing(paths: NodePaths) -> list[dict[str, Any]]:
    """Each project folder on this machine, with its size in bytes, read in one walk each."""
    if not paths.projects.is_dir():
        return []
    found = []
    for home in sorted(path for path in paths.projects.iterdir() if path.is_dir()):
        branches = trees(paths, home.name)
        total, each = sizes(home, branches)
        found.append({"project": home.name, "folder": str(home), "size": total,
                      "trees": [{"folder": tree.name, "size": each[tree]} for tree in branches]})
    return found


def unused(names: list[str], used: dict[str | None, float], cutoff: float) -> list[str]:
    """Worktrees to clean: not used since `cutoff`, always keeping the newest of the project."""
    last = {project_home.slug(branch): when for branch, when in used.items()}
    newest_first = sorted(names, key=lambda name: last.get(name, 0.0), reverse=True)
    return [name for name in newest_first[1:] if last.get(name, 0.0) < cutoff]


def _remove(path: Path, paths: NodePaths, reclaim: Reclaim) -> None:
    try:
        remove_tree(path, paths.roots)
    except RemovalDenied:
        reclaim(path)
        remove_tree(path, paths.roots)


def remove_worktree(paths: NodePaths, project: str, name: str, reclaim: Reclaim) -> None:
    """One branch's worktree and what is known about its `setup` and `install`."""
    home = paths.project_home(project)
    _remove(home / "trees" / name, paths, reclaim)
    for kind in (project_home.SETUP, project_home.INSTALL):
        remove_tree(home / "state" / f"{name}.{kind}", paths.roots)
    repo = home / "repo.git"
    workspace.git(repo, "worktree", "prune")
    workspace.git(repo, "update-ref", "-d", f"refs/heads/tree-{name}")


def remove_project(paths: NodePaths, project: str, reclaim: Reclaim) -> None:
    """The whole project folder."""
    for tree in trees(paths, project):
        _remove(tree, paths, reclaim)
    remove_tree(paths.project_home(project), paths.roots)
