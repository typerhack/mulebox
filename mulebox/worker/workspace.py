"""Job workspaces: `<jobs>/<project>/<job_id>/src` built from the client's snapshot.

The snapshot is extracted safely (see archive.py), then turned into a throwaway git
repository with one commit, so git-based tools (lint-staged, `git diff`, ...) work. Git
runs with fixed identity, no hooks, no signing and no pager, never through a shell.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker.archive import extract_tar
from mulebox.worker.paths import NodePaths

LOG = get_logger("worker.workspace")
GIT_TIMEOUT_S = 300
_GIT_CONFIG = (
    "-c", "user.name=mulebox",
    "-c", "user.email=mulebox@localhost",
    "-c", "core.hooksPath=/dev/null",
    "-c", "commit.gpgsign=false",
    "-c", "init.defaultBranch=main",
    "-c", "core.pager=cat",
)


class WorkspaceError(MuleboxError):
    """The workspace could not be prepared."""


def _git(src: Path, *args: str) -> None:
    argv = ["git", *_GIT_CONFIG, *args]
    try:
        proc = subprocess.run(argv, cwd=src, capture_output=True, timeout=GIT_TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceError(f"git {args[0]} failed in {src}: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise WorkspaceError(f"git {args[0]} failed in {src} (exit {proc.returncode}): {detail}")


def job_dir(paths: NodePaths, project: str, job_id: str) -> Path:
    """Create and return `<jobs>/<project>/<job_id>`."""
    return ensure_dir(paths.job_dir(project, job_id), paths.roots)


def prepare(paths: NodePaths, project: str, job_id: str, snapshot: Path) -> Path:
    """Extract snapshot into the job's `src` folder and commit it; return `src`."""
    src = job_dir(paths, project, job_id) / "src"
    if src.exists():
        raise WorkspaceError(f"{src} already exists; refusing to reuse a workspace")
    extract_tar(snapshot, src, paths.roots)
    _git(src, "init", "-q")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "--no-verify", "--allow-empty", "-m", f"mulebox {job_id}")
    return src


def cleanup(paths: NodePaths, project: str, job_id: str) -> None:
    """Remove the whole job folder through safepath."""
    remove_tree(paths.job_dir(project, job_id), paths.roots)


def leftover_job_dirs(paths: NodePaths) -> list[Path]:
    """Job folders still on disk (`<jobs>/<project>/<job_id>`), for recovery."""
    found = []
    if not paths.jobs.is_dir():
        return found
    for project in sorted(paths.jobs.iterdir()):
        if project.is_symlink() or not project.is_dir():
            continue
        for entry in sorted(project.iterdir()):
            try:
                paths.job_dir(project.name, entry.name)
            except MuleboxError:
                LOG.warning("leaving unknown entry %s in the jobs root", entry)
                continue
            found.append(entry)
    return found
