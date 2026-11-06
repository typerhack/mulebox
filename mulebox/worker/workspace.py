"""Job folders: `<jobs>/<project>/<job_id>`, what one job needs and nothing it keeps, and git.

The project's own files live in its home (project_home.py). Git runs with fixed identity, no
hooks, no signing and no pager, never through a shell.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker.paths import NodePaths

LOG = get_logger("worker.workspace")
GIT_TIMEOUT_S = 300
GIT_CONFIG = (
    "-c", "user.name=mulebox",
    "-c", "user.email=mulebox@localhost",
    "-c", "core.hooksPath=/dev/null",
    "-c", "commit.gpgsign=false",
    "-c", "init.defaultBranch=main",
    "-c", "core.pager=cat",
)


class WorkspaceError(MuleboxError):
    """The workspace could not be prepared."""


def git(cwd: Path, *args: str) -> bytes:
    """Run git here with the fixed settings; its stdout."""
    argv = ["git", *GIT_CONFIG, *args]
    try:
        proc = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=GIT_TIMEOUT_S,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceError(f"git {args[0]} failed in {cwd}: {exc}") from exc
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()[-500:]
        raise WorkspaceError(f"git {args[0]} failed in {cwd} (exit {proc.returncode}): {detail}")
    return proc.stdout


def job_dir(paths: NodePaths, project: str, job_id: str) -> Path:
    """Create and return `<jobs>/<project>/<job_id>`."""
    return ensure_dir(paths.job_dir(project, job_id), paths.roots)


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
