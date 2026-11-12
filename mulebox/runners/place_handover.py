"""An isolated runner's container outlives a worker restart (design.md, Runners for public
repositories, Worker restarts).

A deploy restarts the worker. Before, its stop removed every place's container, also one whose
one-job runner GitHub had just given a job: that job then hung until GitHub dropped the runner
(about 10 minutes) and could not be cancelled meanwhile. Now:

- When the worker stops, a container is kept if its job has asked (`io/request.json`) or if
  GitHub will not delete its one-job runner, which it refuses once it has given the runner a
  job. Only a runner GitHub has deleted can never get one, so only then is its container
  removed. The delete is GitHub's own answer, so no job can slip in between.
- The container runs with `--sig-proxy=false` (place_container.py): the stop signal the worker's
  `docker` client gets is not passed on to it, and Docker removes it when it ends (`--rm`).
- The next worker finds it by its label and `.mulebox-place`, follows it to its end, answers its
  job if nothing has yet (the reservation key is the job's own, so asking again finds the same
  reservation), then ends the round as usual. Supervision keeps its slot meanwhile, as it reads
  `.mulebox-place` (supervise.py).
"""

from __future__ import annotations

import re
from pathlib import Path

from mulebox.runners import jit, place_bridge, place_container
from mulebox.runners.github import GhRun
from mulebox.runners.supervise import place_container_name
from mulebox.worker.docker import Docker

CONTAINER_PREFIX = "mulebox-place-"
_SUFFIX = re.compile(r"[0-9a-z]{8}")


def container_name(place: str, suffix: str) -> str:
    return f"{CONTAINER_PREFIX}{place}-{suffix}"


def keep_on_stop(repo: str, place: str, io_dir: Path, runner_ids: list[int] | None,
                 gh: GhRun) -> bool:
    """True when the container must outlive the worker: its job has asked, or GitHub keeps
    its one-job runner (it has given it a job, or could not be asked). `runner_ids` None: a
    container taken over, whose runner is looked up by name; none found counts as kept, as
    GitHub lists a one-job runner until its job ends, and a failed listing finds none too."""
    if place_bridge.read_request(io_dir) is not None:
        return True
    ids = jit.ids_of(repo, place, gh) if runner_ids is None else runner_ids
    if not ids:
        return True
    return not all(jit.delete(repo, runner_id, gh) for runner_id in ids)


class Held:
    """A container an earlier worker left running, followed like a `docker run` client."""

    def __init__(self, docker: Docker, container: str) -> None:
        self.docker, self.container = docker, container

    def poll(self) -> int | None:
        return None if place_container.running(self.docker, self.container) else 0

    def wait(self, timeout: float | None = None) -> int:
        return 0


def held(docker: Docker, place: str, folder: Path, io_prefix: str) -> tuple[str, Path] | None:
    """(container, its io folder) when the container `.mulebox-place` names still runs."""
    name = place_container_name(folder)
    prefix = f"{CONTAINER_PREFIX}{place}-"
    if name is None or not name.startswith(prefix) or not _SUFFIX.fullmatch(name[len(prefix):]):
        return None
    io_dir = folder / f"{io_prefix}{name[len(prefix):]}"
    if io_dir.is_symlink() or not io_dir.is_dir():
        return None
    if not place_container.running(docker, name):
        return None
    return name, io_dir
