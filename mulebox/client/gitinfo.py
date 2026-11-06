"""Read-only git queries the client needs: file list, base commit, branch.

git runs with an argument list in the project root (never through a shell) and with
`GIT_OPTIONAL_LOCKS=0`, so a snapshot never takes the index lock an agent may need.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mulebox.common.errors import MuleboxError

GIT_BINARY = "git"


class GitError(MuleboxError):
    """git is missing, the folder is not a git worktree, or a git query failed."""


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        proc = subprocess.run(
            [GIT_BINARY, *args], cwd=root, capture_output=True, env=env, stdin=subprocess.DEVNULL
        )
    except OSError as exc:
        raise GitError(f"cannot run git ({exc}); install git to use mulebox") from exc
    if check and proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"`git {' '.join(args)}` failed in {root}: {detail}")
    return proc


def ensure_worktree(root: Path) -> None:
    """Raise GitError unless `root` is inside a git worktree."""
    proc = _git(root, "rev-parse", "--is-inside-work-tree", check=False)
    if proc.returncode != 0 or proc.stdout.strip() != b"true":
        raise GitError(
            f"{root} is not inside a git worktree; mulebox sends the files git knows about, "
            "so run it from a git checkout (the folder holding .mulebox.yml)"
        )


def ensure_commit(root: Path) -> None:
    """Raise GitError in a repository without commits: a job records the commit it came from."""
    if not base_commit(root):
        raise GitError(f"{root} has no commits yet; commit once, then run this again")


def list_files(root: Path) -> list[str]:
    """Tracked and untracked, not ignored paths under `root`, relative to it."""
    out = _git(root, "ls-files", "-co", "--exclude-standard", "-z").stdout
    names = {os.fsdecode(raw) for raw in out.split(b"\0") if raw}
    return sorted(names)


def tracked_files(root: Path) -> set[str]:
    """Paths git tracks under `root`, relative to it."""
    out = _git(root, "ls-files", "-c", "-z").stdout
    return {os.fsdecode(raw) for raw in out.split(b"\0") if raw}


def main_checkout(root: Path) -> Path | None:
    """The repository's main folder when `root` is the top of a linked worktree, else None.

    A worktree's folder is named after a task or a branch; the repository is what is shared."""
    try:
        out = _git(root, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-dir",
                   "--git-common-dir", check=False)
    except GitError:
        return None
    lines = out.stdout.decode(errors="surrogateescape").splitlines()
    if out.returncode != 0 or len(lines) != 3:
        return None
    top, own, common = (Path(line) for line in lines)
    if own == common or top != root.resolve():
        return None
    return common.parent if common.name == ".git" else common.with_suffix("")


def base_commit(root: Path) -> str:
    """`git rev-parse HEAD`, or an empty string in a repository without commits."""
    proc = _git(root, "rev-parse", "--verify", "-q", "HEAD", check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else ""


def remote_url(root: Path) -> str:
    """The `origin` remote's URL, or "" without one."""
    proc = _git(root, "remote", "get-url", "origin", check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else ""


def config_value(root: Path, key: str) -> str:
    """A `git config` value, or "" when it is not set."""
    proc = _git(root, "config", "--get", key, check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else ""


def branch(root: Path) -> str:
    """`git rev-parse --abbrev-ref HEAD` (`HEAD` when detached), or "" without commits."""
    proc = _git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    return proc.stdout.decode().strip() if proc.returncode == 0 else ""
