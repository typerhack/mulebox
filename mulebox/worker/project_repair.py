"""A project's home that git cannot use is made again (docs/design.md, Sudden power loss).

A power cut while git writes can leave an empty object, a torn index or a stale lock in a
branch's worktree or in the project's repository, and then every job of that branch fails on
it. A project home is a cache the next job sets up again, so the job's files go in once more:
first after removing the branch's worktree, then, if git still fails, after removing the whole
project folder. The job's log says what was made again and why.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mulebox.common.log import get_logger
from mulebox.worker import project_disk, project_home
from mulebox.worker.paths import NodePaths
from mulebox.worker.workspace import WorkspaceError

LOG = get_logger("worker.repair")
Note = Callable[[str], None]


def prepare(paths: NodePaths, project: str, branch: str | None, job_id: str, snapshot: Path,
            reclaim: project_disk.Reclaim, note: Note,
            first: Callable[[], project_home.Synced] | None = None) -> project_home.Synced:
    """project_home.prepare, with the branch's folder and then the project's made again on a
    git failure. `first` is the first attempt, when the caller makes it its own way."""
    attempt = first or (lambda: project_home.prepare(paths, project, branch, job_id, snapshot))
    try:
        return attempt()
    except WorkspaceError as exc:
        _made_again(note, "this branch's folder", exc)
    name = project_home.slug(branch)
    try:
        if (paths.project_home(project) / "trees" / name).exists():
            project_disk.remove_worktree(paths, project, name, reclaim)
        return project_home.prepare(paths, project, branch, job_id, snapshot)
    except WorkspaceError as exc:
        _made_again(note, "the project's folder, every branch", exc)
    project_disk.remove_project(paths, project, reclaim)
    return project_home.prepare(paths, project, branch, job_id, snapshot)


def _made_again(note: Note, what: str, exc: WorkspaceError) -> None:
    LOG.warning("git failed in a project home, making %s again: %s", what, exc)
    note(f"mulebox: git could not use {what} on the node (a power cut can leave it so), so it "
         f"is made again and setup runs again: {exc}\n")
