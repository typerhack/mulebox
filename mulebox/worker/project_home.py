"""A project's permanent home on this machine: one git repository, one worktree per branch.

    <projects>/<project>/repo.git            shared objects
    <projects>/<project>/trees/<branch>/     the checkout; what git ignores stays between jobs
    <projects>/<project>/state/<branch>.setup   what the last good `setup` ran on

A job brings a snapshot, and only what differs reaches the worktree: unchanged files keep their
times, so build tools stay incremental, and ignored files (`node_modules`, `vendor`, `.venv`,
build output) stay. Files a job left that the snapshot does not have go, unless git ignores
them, so a job sees what a clean checkout would. Git runs with workspace.py's fixed settings, so
no hook of a project ever runs.

A worktree belongs to one job at a time: the queue never runs two of a branch at once
(queue.py). The git repository is the machine's own and starts empty, whatever the project's
history; each job adds one throwaway commit, so git-based tools work.

`setup` may be skipped when nothing it depends on changed (`setup_key`), and nothing it may have
made has gone: a file that is neither in the snapshot nor ignored can be its work, so losing one
(`Synced.lost`) runs it again. A compose job always runs it: its containers are new, and a
`setup` may be what fills them.
"""

from __future__ import annotations

import filecmp
import hashlib
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mulebox.common import compose, isolation
from mulebox.common.config_jobs import HOST_PORTS_KEY
from mulebox.common.log import get_logger
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker import workspace
from mulebox.worker.archive import extract_tar
from mulebox.worker.paths import NodePaths

LOG = get_logger("worker.home")
BASE = "mulebox-base"
NO_BRANCH = "detached"
CHECKOUT_DIR = 0o755
INCOMING = "incoming"
SETUP, INSTALL = "setup", "install"  # what is known about each, in `state/`
SETUP_INPUTS = (
    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "composer.json",
    "composer.lock", "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "requirements-dev.txt", "uv.lock", "poetry.lock", "Pipfile.lock", "Cargo.toml", "Cargo.lock",
    "Dockerfile", "go.mod", "go.sum", "pubspec.yaml", "pubspec.lock", "Gemfile", "Gemfile.lock", "mix.lock",
    "VERSION", ".nvmrc", ".node-version", ".python-version", ".tool-versions",
)
_NOT_A_NAME = re.compile(r"[^A-Za-z0-9._-]+")
EMPTY_TREE_ID = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


@dataclass(frozen=True)
class Synced:
    tree: Path
    changed: int  # files written
    lost: int  # files gone that were not part of the last snapshot


def slug(branch: str | None) -> str:
    """A folder name for `branch`. The hash keeps `a/b` and `a-b` apart."""
    if not branch:
        return NO_BRANCH
    name = _NOT_A_NAME.sub("-", branch).strip("-.") or "branch"
    return f"{name[:60]}-{hashlib.sha256(branch.encode()).hexdigest()[:8]}"


def _repository(paths: NodePaths, project: str) -> Path:
    home = ensure_dir(paths.project_home(project), paths.roots)
    repo = home / "repo.git"
    if not (repo / "HEAD").exists():
        ensure_dir(repo, paths.roots)
        workspace.git(repo, "init", "-q", "--bare")
        workspace.git(repo, "hash-object", "-t", "tree", "-w", "--stdin")
        first = workspace.git(repo, "commit-tree", EMPTY_TREE_ID, "-m", "mulebox").decode().strip()
        workspace.git(repo, "update-ref", f"refs/heads/{BASE}", first)
    return repo


def tree_for(paths: NodePaths, project: str, branch: str | None) -> Path:
    """The branch's worktree, made if this is its first job."""
    repo = _repository(paths, project)
    name = slug(branch)
    tree = paths.project_home(project) / "trees" / name
    if not (tree / ".git").exists():
        ensure_dir(tree.parent, paths.roots)
        workspace.git(repo, "worktree", "prune")
        workspace.git(repo, "worktree", "add", "-q", "-B", f"tree-{name}", str(tree), BASE)
    return tree


def _wanted(incoming: Path) -> list[str]:
    """Every file and symlink of the snapshot, relative, without following a link."""
    found = []
    for folder, names, files in os.walk(incoming):
        for name in [*files, *(n for n in names if (Path(folder) / n).is_symlink())]:
            found.append(os.path.relpath(os.path.join(folder, name), incoming))
    return found


def _listed(tree: Path, *which: str) -> set[str]:
    listing = workspace.git(tree, "ls-files", "-z", *which)
    return {name.decode("utf-8", "surrogateescape") for name in listing.split(b"\0") if name}


def _same(new: Path, old: Path) -> bool:
    if not os.path.lexists(old):
        return False
    a, b = new.lstat(), old.lstat()
    if new.is_symlink() or old.is_symlink():
        return new.is_symlink() and old.is_symlink() and os.readlink(new) == os.readlink(old)
    return (old.is_file() and a.st_size == b.st_size and a.st_mode == b.st_mode
            and filecmp.cmp(new, old, shallow=False))


def _put(new: Path, old: Path, paths: NodePaths) -> None:
    """Replace `old`, never through a link a job left: `old` goes first, and O_NOFOLLOW."""
    remove_tree(old, paths.roots)
    if new.is_symlink():
        os.symlink(os.readlink(new), old)
        return
    target = os.open(old, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     new.stat().st_mode & 0o777)
    with os.fdopen(target, "wb") as out, new.open("rb") as source:
        shutil.copyfileobj(source, out)


def _open_folder(folder: Path, tree: Path, paths: NodePaths, ready: set[Path]) -> None:
    """Make `folder` as on any checkout, up to the tree. A container's user is rarely the
    worker's, so a folder a project mounts must be readable by others; what keeps other users
    of the machine out is the project home above it. A folder a container's root made stays."""
    ensure_dir(folder, paths.roots)  # refuses a link on the way
    while folder != tree and folder not in ready:
        ready.add(folder)
        info = folder.lstat()
        if info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) & CHECKOUT_DIR != CHECKOUT_DIR:
            folder.chmod(stat.S_IMODE(info.st_mode) | CHECKOUT_DIR)
        folder = folder.parent


def sync(incoming: Path, tree: Path, paths: NodePaths) -> tuple[int, int]:
    """Make the worktree hold the snapshot; (files written, files of a job's lost)."""
    wanted = _wanted(incoming)
    made_here = _listed(tree, "--others", "--exclude-standard")
    for gone in (_listed(tree, "--cached") | made_here) - set(wanted):
        remove_tree(tree / gone, paths.roots)
    ready: set[Path] = set()
    changed = 0
    for name in wanted:
        new, old = incoming / name, tree / name
        if old.parent not in ready:
            _open_folder(old.parent, tree, paths, ready)
        if not _same(new, old):
            _put(new, old, paths)
            changed += 1
    return changed, len(made_here - set(wanted))


def prepare(paths: NodePaths, project: str, branch: str | None, job_id: str,
            snapshot: Path) -> Synced:
    """Make the branch's worktree hold the snapshot."""
    tree = tree_for(paths, project, branch)
    incoming = workspace.job_dir(paths, project, job_id) / INCOMING
    remove_tree(incoming, paths.roots)
    extract_tar(snapshot, incoming, paths.roots)
    changed, lost = sync(incoming, tree, paths)
    remove_tree(incoming, paths.roots)
    workspace.git(tree, "add", "-A")
    workspace.git(tree, "commit", "-q", "--no-verify", "--allow-empty", "-m", f"mulebox {job_id}")
    return Synced(tree, changed, lost)


def _inputs(tree: Path) -> list[Path]:
    near = [tree, *(p for p in sorted(tree.iterdir()) if p.is_dir() and not p.is_symlink()
                    and not p.name.startswith(".") and p.name != "node_modules")]
    return [folder / name for folder in near for name in SETUP_INPUTS
            if (folder / name).is_file() and not (folder / name).is_symlink()]


def _compose_files(tree: Path, claim: dict[str, Any]) -> list[Path]:
    files = (claim.get("env") or {}).get(compose.COMPOSE_FILES_KEY)
    names = compose.split_files(files) if files else ()
    return [tree / name for name in names if (tree / name).is_file()
            and not (tree / name).is_symlink()]


def install_key(tree: Path, claim: dict[str, Any]) -> str:
    """Changes when something an `install` depends on does: an image is named in a compose file
    or built from a Dockerfile, so those count. A tag that moves on its registry is not seen."""
    return _key(tree, claim, claim.get("install"), _compose_files(tree, claim))


def setup_key(tree: Path, claim: dict[str, Any]) -> str:
    """Changes when something a `setup` depends on does."""
    return _key(tree, claim, claim.get("setup"), [])


def _key(tree: Path, claim: dict[str, Any], line: str | None, more: list[Path]) -> str:
    env = {k: v for k, v in (claim.get("env") or {}).items() if k != HOST_PORTS_KEY}
    parts: list[Any] = [line, claim.get("toolchain"), env]
    if isolation.CAPABILITY in (claim.get("needs") or ()):
        parts.append(isolation.CAPABILITY)  # built in a container: not what the node would build
    digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode())
    for path in [*_inputs(tree), *more]:
        digest.update(str(path.relative_to(tree)).encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _state(paths: NodePaths, project: str, branch: str | None, kind: str) -> Path:
    return paths.project_home(project) / "state" / f"{slug(branch)}.{kind}"


def is_current(paths: NodePaths, project: str, branch: str | None, key: str,
               kind: str = SETUP) -> bool:
    state = _state(paths, project, branch, kind)
    return state.is_file() and not state.is_symlink() and state.read_text() == key


def forget_setup(paths: NodePaths, project: str, branch: str | None, kind: str = SETUP) -> None:
    """Before a `setup` or `install` runs: one that dies halfway must not count."""
    remove_tree(_state(paths, project, branch, kind), paths.roots)


def remember_setup(paths: NodePaths, project: str, branch: str | None, key: str,
                   kind: str = SETUP) -> None:
    state = _state(paths, project, branch, kind)
    ensure_dir(state.parent, paths.roots)
    remove_tree(state, paths.roots)
    fd = os.open(state, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as out:
        out.write(key)
