"""What `project reset` and `project clean` do to a node's project folders, for any node.

On the coordinator's machine `mulebox project-home` runs them (project_commands.py); on every
node a project order brings them (worker/orders.py, coordinator/project_orders.py). Both say
what they find and what they remove through `say`, so the dev machine prints it. Holding the
project while its folder goes is the caller's: these only remove, through the path-safety
module (project_disk.py).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Collection

from mulebox.common import units
from mulebox.common.config import NodeConfig
from mulebox.common.ids import new_id
from mulebox.common.tree_size import size_of
from mulebox.worker import caches, project_disk, project_home, reclaim
from mulebox.worker.docker import Docker
from mulebox.worker.paths import NodePaths

Say = Callable[[str], None]
Hold = Callable[[str, Callable[[], None]], None]  # (project, work): run work with it held
DEFAULT_DAYS = 14


def _reclaimer(node: NodeConfig, paths: NodePaths) -> project_disk.Reclaim:
    return lambda tree: reclaim.reclaim_tree(Docker(), paths, tree, new_id("job"), node.name)


def _size(path) -> str:
    return units.size(size_of(path))


def _free(project: str, work: Callable[[], None]) -> None:
    work()


def clean(node: NodeConfig, paths: NodePaths, used: dict[str, dict[str | None, float]],
          days: int, yes: bool, say: Say, skip: Collection[tuple[str, str]] = (),
          hold: Hold = _free) -> int:
    """Branch folders no job used for `days` (`used`: projects.branches), keeping each project's
    newest; `skip`: (project, folder) pairs a job runs in now. Returns how many."""
    cutoff = time.time() - days * 86400
    count = 0
    for row in project_disk.listing(paths):
        project = row["project"]
        names = [tree["folder"] for tree in row["trees"]
                 if (project, tree["folder"]) not in skip]
        for name in project_disk.unused(names, used.get(project, {}), cutoff):
            count += 1
            say(f"{project}: {name}, {_size(paths.project_home(project) / 'trees' / name)}")
            if yes:
                hold(project, lambda p=project, n=name: project_disk.remove_worktree(
                    paths, p, n, _reclaimer(node, paths)))
    say(f"{'removed' if yes else 'would remove'} {count} branch folders; each is set up "
        "again by its next job")
    return count


def reset(node: NodeConfig, paths: NodePaths, project: str, branch: str | None,
          with_caches: bool, yes: bool, say: Say, after: Callable[[], None] | None = None,
          hold: Hold = _free) -> None:
    """A project's folder, or one branch's, and with `with_caches` its package caches.
    `after`: what else goes with the whole folder (the coordinator's upload base)."""
    home = paths.project_home(project)
    target = home / "trees" / project_home.slug(branch) if branch else home
    say(f"{target}, {_size(target)}" if target.is_dir() else f"no folder at {target}")
    if with_caches:
        say(f"{paths.packages_dir(project)}, {_size(paths.packages_dir(project))}")
    if not yes:
        say("nothing removed: add --yes; the next job sets it up again")
        return

    def work() -> None:
        reclaimer = _reclaimer(node, paths)
        if branch and target.is_dir():
            project_disk.remove_worktree(paths, project, target.name, reclaimer)
        elif not branch:
            project_disk.remove_project(paths, project, reclaimer)
            if after is not None:
                after()
        if with_caches:
            caches.clear(paths, project, Docker())

    hold(project, work)
    say("removed; the next job sets it up again")
