"""Add and remove isolated runners on this node (place.py runs them).

`add_isolated` needs no registration token: the node's own `gh`, signed in as an admin of the
repository, makes a one-job runner for each job. It checks that first, builds the image, and
writes the folder and its `.mulebox-runner.json`; the worker starts the place within 10 s.

`count` places run jobs at once, a group: `<name>`, `<name>-2`, ... Each is a place of its own,
with its own container, reservation and tool cache, and its metadata names the group. Adding a
group that exists adds only its missing members, so `mulebox-ci` keeps its warm cache when it
grows to two. `remove_isolated` removes every member: its containers, the one-job runner
GitHub still holds for it, its tool cache volume and its folder.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.runners import jit, layout, place_container, place_image
from mulebox.runners.github import GhRun, run_gh
from mulebox.runners.manage import Machine, RunnerError
from mulebox.runners.names import RunnerUsageError, check_repo
from mulebox.runners.supervise import PLACE_ROUND
from mulebox.worker import reclaim
from mulebox.worker.docker import Docker, DockerError

STOP_WAIT_S = 600.0
MAX_COUNT = 8  # a round building its image can take this long to notice


def member_names(name: str, count: int) -> list[str]:
    return [name] + [f"{name}-{i}" for i in range(2, count + 1)]


def members(m: Machine, name: str) -> list[str]:
    """The places of the group `name`: itself and those whose metadata names it."""
    found = []
    for folder in layout.runner_folders(m.paths):
        meta = layout.read_meta(folder)
        if meta.get("isolated") is True and (folder.name == name or meta.get("group") == name):
            found.append(folder.name)
    return found


def add_isolated(m: Machine, repo: str, *, name: str, labels: Sequence[str],
                 actors: Sequence[str], count: int = 1, gh: GhRun = run_gh,
                 docker: Docker | None = None,
                 version: Callable[[], str] | None = None) -> list[Path]:
    check_repo(repo)
    if not actors:
        raise RunnerUsageError("an isolated runner needs the accounts whose runs it takes")
    if not 1 <= count <= MAX_COUNT:
        raise RunnerUsageError(f"--count is 1 to {MAX_COUNT}")
    names = member_names(name, count)
    for member in names:
        folder = layout.runner_dir(m.paths, member)
        meta = layout.read_meta(folder) if folder.is_dir() else {}
        if (folder.exists() or folder.is_symlink()) and not (
                meta.get("isolated") is True and meta.get("repo") == repo
                and meta.get("group", name) == name and not meta.get("removing")):
            raise RunnerUsageError(f"runner {member} already exists in {folder}; "
                                   f"remove it first with `mulebox runner remove {member}`")
    missing = [n for n in names if not layout.runner_dir(m.paths, n).exists()]
    if not missing:
        m.say(f"Isolated runner {name} already has {count} place(s)")
        return []
    is_admin, visibility = jit.admin(repo, gh)
    if not is_admin:
        raise RunnerError(f"the node's `gh` is not an admin of {repo}, and only an admin can "
                          "make a runner; run `gh auth login` on the node as one")
    docker = docker or Docker()
    from mulebox.runners.place import latest_version

    runner_version = (version or latest_version)()
    m.say(f"Building the runner image for runner {runner_version} (once per version)")
    image = place_image.ensure(docker, m.paths, runner_version)
    place_container.ensure_network(docker)
    m.say(f"Image {image}")
    made = []
    for member in missing:
        folder = ensure_dir(layout.runner_dir(m.paths, member), m.paths.roots)
        layout.write_meta(m.paths, folder, {
            "name": member, "group": name, "repo": repo, "labels": list(labels),
            "actors": list(actors), "isolated": True, "public": visibility == "public",
            "added_at": int(time.time())})
        made.append(folder)
    m.say(f"Isolated runner {name} for {repo} ({visibility}): {', '.join(missing)} added, "
          f"{count} job(s) at once; the worker starts them within 10 s, a fresh container "
          "for each job")
    return made


def is_isolated(m: Machine, name: str) -> bool:
    return layout.read_meta(layout.runner_dir(m.paths, name)).get("isolated") is True


def remove_isolated(m: Machine, name: str, *, gh: GhRun = run_gh,
                    docker: Docker | None = None, wait_s: float = STOP_WAIT_S,
                    sleep: Callable[[float], None] = time.sleep) -> None:
    """Remove every place of the group `name` (one, when `name` is a member's own name)."""
    docker = docker or Docker()
    for member in members(m, name) or [name]:
        _remove_one(m, member, gh=gh, docker=docker, wait_s=wait_s, sleep=sleep)


def _remove_one(m: Machine, name: str, *, gh: GhRun, docker: Docker, wait_s: float,
                sleep: Callable[[float], None]) -> None:
    """Stop the place first (`removing`: the worker starts no new round, and its round ends
    when its container goes), then remove what is left of it. A round that does not end in
    time leaves everything as it is, still `removing`: run it again."""
    folder = layout.runner_dir(m.paths, name)
    meta = layout.read_meta(folder)
    repo = meta.get("repo")
    layout.write_meta(m.paths, folder, {**meta, "removing": True})
    gone: set[str] = set()
    deadline = time.monotonic() + wait_s
    while (folder / PLACE_ROUND).exists():
        gone.update(place_container.remove_left(docker, name))
        if time.monotonic() >= deadline:
            raise RunnerError(f"runner {name} is still ending its last round; it takes no new "
                              f"job, so run `mulebox runner remove {name}` again in a minute")
        sleep(1.0)  # its round is ending: the worker removes the mark when it has
    gone.update(place_container.remove_left(docker, name))
    m.say(f"Removed {len(gone)} container(s) of {name}")
    if repo:
        for runner_id in jit.ids_of(repo, name, gh):
            jit.delete(repo, runner_id, gh)
    try:
        docker.run("volume", "rm", "--force", place_container.tool_volume(name))
    except DockerError:
        pass  # none yet
    try:
        remove_tree(folder, m.paths.roots)
    except (MuleboxError, OSError):  # files its container wrote, owned by the container's user
        reclaim.reclaim_runner_dir(docker, m.paths, folder, m.node)
        remove_tree(folder, m.paths.roots)
    m.say(f"Removed {folder}; the worker stops its thread within 10 s")
