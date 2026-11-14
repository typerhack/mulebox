"""An isolated job: its script in a fresh confined container (docs/design.md, Isolation per job).

`wrap` turns the run spec runspec.py built into one whose unit runs, on the node, a script of
mulebox's own: a compose job's `up` and its failure report (compose_job.py), a network of the
job's own, mulebox's image if the node lacks it (job_image.py), then the container, made,
joined to the job's compose networks, and started attached, so its output is the job's log and
its exit code the job's. The unit's environment holds every value the job gets; the container
is given each by name (`--env NAME`), so no value shows on a command line. What it sees:

- the job's branch tree and the project's git repository it is a worktree of, read-write;
- the project's package caches (caches.py), read-write, at their own paths;
- the node's toolchains (toolchains.py) and Playwright's browsers, read-only, at their own
  paths, so `PATH` and `PLAYWRIGHT_BROWSERS_PATH` work unchanged;
- for a compose job: its services by name on their networks, the job's compose file read-only,
  the node's `docker` command and Compose plugin read-only, and as `DOCKER_HOST` the job's door
  (docker_door.py), which lets by only exec, logs, inspect, start, stop and restart of this
  job's own containers; and `localhost:$MULEBOX_PORT_...` forwarded to the services
  (port_forward.py), when the image has a Python;
- nothing else of the node: no home, no keys, no engine. A read-only root file system with
  `/tmp` in memory, which is also `HOME`.

It runs as the node's user, so what it writes is the worker's to clean, with the confinement of
common/confined.py and `--init` to pass on signals. Container and network carry the job's labels
(common/compose.py), so the teardown that removes a compose job's containers removes them on
every outcome, and a crash's leftovers too (docker_cleanup.py); pause and boost find the
container by the same label (controls.py). The first isolated job on a node builds mulebox's
image inside its own unit, so the worker's loop never waits on it.
"""

from __future__ import annotations

import os
import shlex
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from mulebox.common import compose, confined
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.worker import job_image, steps
from mulebox.worker.executor import ExecutorError, RunSpec
from mulebox.worker.paths import NodePaths

HOME = "/tmp"
CONTAINER_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
DOOR = "/run/mulebox/docker.sock"
FORWARDER = "/run/mulebox/port_forward.py"
DOCKER_CLI = "/usr/local/bin/docker"
COMPOSE_PLUGIN = "/usr/local/lib/docker/cli-plugins/docker-compose"
_UNPASSED = ("PATH", "HOME")  # the container's own
_PLUGIN_DIRS = ("/usr/libexec/docker/cli-plugins", "/usr/lib/docker/cli-plugins",
                "/usr/local/lib/docker/cli-plugins", "$HOME/.docker/cli-plugins")


@dataclass(frozen=True)
class ComposeAccess:
    """What an isolated compose job reaches of its services (compose_job.ComposeJob)."""
    project: str
    compose_file: Path
    socket: Path  # the door's, made by door_socket
    forwards: tuple[tuple[int, str, int], ...] = ()


DOORS = "_doors"  # under the jobs root; a project name starts with a letter or digit
MAX_SOCKET = 107  # bytes a Unix socket's path may hold


def door_socket(paths: NodePaths, job_id: str) -> Path:
    """Where the job's door listens, inside mulebox's jobs root, short enough for a socket;
    the folder is made through safepath. The cleaner removes it (`remove_door`)."""
    folder = ensure_dir(paths.jobs / DOORS, paths.roots)
    socket = folder / f"{job_id}.sock"
    if len(os.fsencode(socket)) > MAX_SOCKET:
        raise ExecutorError(f"{socket} is too long for a socket; give the node a shorter jobs root")
    return socket


def remove_door(paths: NodePaths, job_id: str) -> None:
    remove_tree(paths.jobs / DOORS / f"{job_id}.sock", paths.roots)


def name(job_id: str) -> str:
    """The job's container and network: `mulebox-job-<id>`, as its Compose project."""
    return compose.project_name(job_id)


def inner_lines(access: ComposeAccess | None) -> tuple[str, ...]:
    """Lines at the start of the job's own script in the container: the port forwarder."""
    if access is None or not access.forwards:
        return ()
    specs = " ".join(shlex.quote(f"127.0.0.1:{port}={service}:{target}")
                     for port, service, target in access.forwards)
    return ("if command -v python3 >/dev/null; then",
            f"  python3 {FORWARDER} {specs} &",
            "else echo 'mulebox: no python3 in the image, so localhost:$MULEBOX_PORT_... does not "
            "reach the services; use their names'; fi")


def _mounts(read_write: Iterable[Path], read_only: Iterable[Path]) -> list[str]:
    args: list[str] = []
    seen: set[str] = set()
    for folder, mode in [*((p, "rw") for p in read_write), *((p, "ro") for p in read_only)]:
        path = str(folder)
        if path in seen or not folder.exists():
            continue
        seen.add(path)
        args += ["--volume", f"{path}:{path}:{mode}"]
    return args


def _image_lines(image: str, recipe: str) -> list[str]:
    if not recipe:
        return []
    told = f"mulebox: building the image for isolated jobs ({image}), once for this node"
    return [f"if ! docker image inspect {shlex.quote(image)} >/dev/null 2>&1; then",
            f"  echo {shlex.quote(told)}",
            f"  printf '%s' {shlex.quote(recipe)} | docker build --quiet -t {shlex.quote(image)} - "
            ">/dev/null",
            "fi"]


def _door_lines(job_id: str, access: ComposeAccess) -> list[str]:
    socket = shlex.quote(str(access.socket))
    dirs = " ".join(f'"{d}"' for d in _PLUGIN_DIRS)
    return [f"rm -f {socket}",
            f"{shlex.quote(sys.executable)} -m mulebox.worker.docker_door --listen {socket} "
            f"--job {shlex.quote(job_id)} &",
            f"for _ in $(seq 100); do [ -S {socket} ] && break; sleep 0.1; done",
            "mulebox_tools=()",
            "mulebox_docker=$(command -v docker)",
            f'mulebox_tools+=(--volume "$mulebox_docker:{DOCKER_CLI}:ro")',
            f"for d in {dirs}; do",
            '  if [ -x "$d/docker-compose" ]; then',
            f'    mulebox_tools+=(--volume "$d/docker-compose:{COMPOSE_PLUGIN}:ro"); break',
            "  fi",
            "done"]


def _create(spec: RunSpec, job_id: str, worker: str, image: str, bins: Sequence[Path],
            read_write: Iterable[Path], read_only: Iterable[Path], access: ComposeAccess | None,
            user: str) -> list[str]:
    labels = (f"{compose.LABEL_JOB}={job_id}", f"{compose.LABEL_WORKER}={worker}")
    names = [n for n in spec.env if n not in _UNPASSED]
    extra_ro: list[Path] = []
    door: list[str] = []
    if access is not None:
        extra_ro = [access.compose_file]
        door = ["--env", f"DOCKER_HOST=unix://{DOOR}",
                "--volume", f"{access.socket}:{DOOR}",
                "--volume", f"{Path(__file__).with_name('port_forward.py')}:{FORWARDER}:ro"]
    return ["docker", "create", "--rm", "--init", "--name", name(job_id),
            *(arg for label in labels for arg in ("--label", label)),
            *confined.run_args(), "--user", user, "--network", name(job_id),
            "--read-only", "--tmpfs", f"{HOME}:rw,exec,mode=1777",
            *_mounts([spec.cwd, *read_write], [*read_only, *extra_ro]),
            "--workdir", str(spec.cwd),
            "--env", f"PATH={os.pathsep.join([*(str(b) for b in bins), CONTAINER_PATH])}",
            "--env", f"HOME={HOME}", *door,
            *(arg for n in names for arg in ("--env", n))]


def wrap(spec: RunSpec, job_id: str, worker: str, *, image: str | None, bins: Sequence[Path],
         read_write: Iterable[Path], read_only: Iterable[Path], host_lines: Sequence[str] = (),
         marker: str | None = None, access: ComposeAccess | None = None,
         uid: int | None = None, gid: int | None = None) -> RunSpec:
    """`spec`, run in the job's container. `image`: the project's own; None for mulebox's.
    `host_lines`: mulebox's lines that run on the node first (a compose job's `up`)."""
    recipe = "" if image else job_image.dockerfile(job_image.base_image())
    image = image or job_image.tag(recipe)
    labels = (f"{compose.LABEL_JOB}={job_id}", f"{compose.LABEL_WORKER}={worker}")
    user = f"{os.getuid() if uid is None else uid}:{os.getgid() if gid is None else gid}"
    create = _create(spec, job_id, worker, image, bins, read_write, read_only, access, user)
    container = shlex.quote(name(job_id))
    lines = ["set -e", *([steps.shell_function(marker)] if marker else []), *host_lines,
             f"docker network create {' '.join(f'--label {shlex.quote(x)}' for x in labels)} "
             f"{container} >/dev/null",
             *_image_lines(image, recipe)]
    tools = ""
    if access is not None:
        lines += _door_lines(job_id, access)
        tools = ' "${mulebox_tools[@]}"'
    lines.append(f"{shlex.join(create)}{tools} {shlex.quote(image)} {shlex.join(spec.argv)} "
                 ">/dev/null")
    if access is not None:
        project = shlex.quote(f"label={compose.LABEL_COMPOSE_PROJECT}={access.project}")
        lines += [f"for net in $(docker network ls --quiet --filter {project}); do",
                  f'  docker network connect "$net" {container}',
                  "done"]
    lines.append(f"docker start --attach {container}")
    return replace(spec, argv=("bash", "-c", "\n".join(lines) + "\n"))


def note(image: str | None, caches: bool, uses_compose: bool) -> str:
    """What the job's log says about where it runs."""
    sees = "its folder and package caches" if caches else "its folder"
    if uses_compose:
        sees += ", its services by name, and Docker only for exec, logs and restarts of them"
    return (f"isolated: runs in a container ({image or 'mulebox image'}) that sees {sees}; "
            "not the node's home, keys or other projects")
