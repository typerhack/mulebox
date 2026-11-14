"""An isolated job: its script in a fresh confined container (docs/design.md, Isolation per job).

`wrap` turns the run spec runspec.py built into one whose unit runs `docker run` of the same
script. The unit's environment still holds every value the job gets; the container is given
each by name (`--env NAME`), so no value shows on a command line. What the container sees:

- the job's branch tree, read-write, at its own path, as the job's folder, and the project's
  git repository it is a worktree of, so a job's own git commands work;
- the project's package caches (caches.py), read-write, at their own paths;
- the node's toolchains (toolchains.py) and Playwright's browsers, read-only, at their own
  paths, so `PATH` and `PLAYWRIGHT_BROWSERS_PATH` work unchanged;
- nothing else of the node: no home, no keys, no Docker socket. A read-only root file system
  with `/tmp` in memory, which is also `HOME`.

It runs as the node's user, so what it writes is the worker's to clean, with the confinement
of common/confined.py, `--init` to pass on signals, and a network of the job's own. Container
and network carry the job's labels (common/compose.py), so the teardown that removes a compose
job's containers removes them on every outcome, and a crash's leftovers too
(docker_cleanup.py); pause and boost find the container by the same label (controls.py).

The first isolated job on a node builds mulebox's image (job_image.py) inside its own unit,
so the worker's loop never waits on it; it is in that job's log and time.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path

from mulebox.common import compose, confined
from mulebox.worker import job_image
from mulebox.worker.executor import RunSpec

HOME = "/tmp"
CONTAINER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_UNPASSED = ("PATH", "HOME")  # the container's own
# Before `docker run`: a network of the job's own, and mulebox's image if this node lacks it.
_PREAMBLE = """set -e
docker network create --label "$1" --label "$2" "$3" >/dev/null
image=$4 recipe=$5
shift 5
if [ -n "$recipe" ] && ! docker image inspect "$image" >/dev/null 2>&1; then
  echo "mulebox: building the image for isolated jobs ($image), once for this node"
  printf '%s' "$recipe" | docker build --quiet -t "$image" - >/dev/null
fi
exec "$@"
"""


def network_name(job_id: str) -> str:
    return f"{compose.project_name(job_id)}-isolated"


def container_name(job_id: str) -> str:
    return f"mulebox-job-{compose.project_name(job_id)}"


def _mounts(read_write: Iterable[Path], read_only: Iterable[Path]) -> list[str]:
    args: list[str] = []
    seen: set[str] = set()
    for folder, mode in [*((p, "rw") for p in read_write), *((p, "ro") for p in read_only)]:
        path = str(folder)
        if path in seen or not folder.is_dir():
            continue
        seen.add(path)
        args += ["--volume", f"{path}:{path}:{mode}"]
    return args


def _container_path(bins: Sequence[Path]) -> str:
    return os.pathsep.join([*(str(b) for b in bins), CONTAINER_PATH])


def wrap(spec: RunSpec, job_id: str, worker: str, *, image: str | None, bins: Sequence[Path],
         read_write: Iterable[Path], read_only: Iterable[Path],
         uid: int | None = None, gid: int | None = None) -> RunSpec:
    """`spec`, run in the job's container. `image`: the project's own; None for mulebox's."""
    recipe = "" if image else job_image.dockerfile(job_image.base_image())
    image = image or job_image.tag(recipe)
    labels = (f"{compose.LABEL_JOB}={job_id}", f"{compose.LABEL_WORKER}={worker}")
    network = network_name(job_id)
    user = f"{os.getuid() if uid is None else uid}:{os.getgid() if gid is None else gid}"
    names = [name for name in spec.env if name not in _UNPASSED]
    run = ["docker", "run", "--rm", "--init", "--name", container_name(job_id),
           *(arg for label in labels for arg in ("--label", label)),
           *confined.run_args(), "--user", user, "--network", network,
           "--read-only", "--tmpfs", f"{HOME}:rw,exec,mode=1777",
           *_mounts([spec.cwd, *read_write], read_only),
           "--workdir", str(spec.cwd),
           "--env", f"PATH={_container_path(bins)}", "--env", f"HOME={HOME}",
           *(arg for name in names for arg in ("--env", name)),
           image, *spec.argv]
    argv = ("bash", "-c", _PREAMBLE, "mulebox-isolated", *labels, network, image, recipe, *run)
    return replace(spec, argv=argv)


def note(image: str | None, caches: bool) -> str:
    """What the job's log says about where it runs."""
    sees = "its folder and package caches" if caches else "its folder"
    return (f"isolated: runs in a container ({image or 'mulebox image'}) that sees {sees}, "
            "not the node's home, keys or Docker")
