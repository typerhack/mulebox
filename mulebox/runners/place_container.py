"""The confined container an isolated runner's job runs in (place.py).

What it gets, and only that:
- the place's `hooks` read-only, its `io` and `_diag` folders, and a tool cache volume of its
  own (`/opt/hostedtoolcache`, where setup-python and setup-node keep what they download), so
  a job does not fetch its toolchains again; it is written only by jobs the guard let in;
- no Docker socket, no capability (`--cap-drop ALL`), `no-new-privileges` (so the image's
  sudo does nothing), the runner image's own user;
- its own network, `mulebox-isolated`, which reaches the internet; the node's dashboard is
  closed to it by the firewall mulebox's LAN mode sets (docs/install.md);
- limits on memory (three quarters of the node's) and processes, and half the CPU weight of
  the node's own processes, as a mulebox job has.

The runner's configuration comes on stdin, so neither `ps` nor `docker inspect` shows it.
`--sig-proxy=false`: the stop signal the worker's `docker` client gets when the worker stops is
not passed on, so the container outlives the worker (place_handover.py); Docker removes it when
it ends.
Containers carry the label `mulebox.place=<name>`, by which any a crash left are removed.
"""

from __future__ import annotations

from pathlib import Path

from mulebox.common import confined
from mulebox.common.confined import CPU_SHARES, PIDS, memory_limit_mb  # noqa: F401
from mulebox.common.errors import MuleboxError
from mulebox.runners.place_hook import HOOKS_MOUNT, IO_MOUNT
from mulebox.runners.place_image import TOOL_CACHE
from mulebox.worker.docker import Docker, DockerError

NETWORK = "mulebox-isolated"
LABEL = "mulebox.place"
DIAG = "/home/runner/_diag"
ENTRY = 'read -r cfg; exec ./run.sh --jitconfig "$cfg"'


class PlaceError(MuleboxError):
    """An isolated runner cannot run its next job."""


def tool_volume(place: str) -> str:
    return f"mulebox-tools-{place}"


def run_argv(container: str, place: str, image: str, *, hooks_dir: Path, io_dir: Path,
             diag_dir: Path, memory_mb: int | None = None) -> list[str]:
    return [
        "docker", "run", "--interactive", "--rm", "--sig-proxy=false", "--name", container,
        "--label", f"{LABEL}={place}",
        *confined.run_args(memory_mb), "--network", NETWORK,
        "--volume", f"{hooks_dir}:{HOOKS_MOUNT}:ro",
        "--volume", f"{io_dir}:{IO_MOUNT}",
        "--volume", f"{diag_dir}:{DIAG}",
        "--volume", f"{tool_volume(place)}:{TOOL_CACHE}",
        "--env", f"ACTIONS_RUNNER_HOOK_JOB_STARTED={HOOKS_MOUNT}/started.sh",
        "--env", f"RUNNER_TOOL_CACHE={TOOL_CACHE}",
        "--env", f"AGENT_TOOLSDIRECTORY={TOOL_CACHE}",
        "--entrypoint", "sh", image, "-c", ENTRY,
    ]


def ensure_network(docker: Docker) -> None:
    try:
        docker.run("network", "inspect", NETWORK)
    except DockerError:
        docker.run("network", "create", "--label", f"{LABEL}=network", NETWORK)


def remove(docker: Docker, container: str) -> None:
    try:
        docker.run("rm", "--force", container)
    except DockerError:
        pass  # gone already


def remove_left(docker: Docker, place: str) -> list[str]:
    """Remove every container of this place: what a crash or a stop left running."""
    found = docker.run("ps", "--all", "--quiet", "--filter", f"label={LABEL}={place}").split()
    for container in found:
        remove(docker, container)
    return found


def running(docker: Docker, container: str) -> bool:
    try:
        return docker.run("inspect", "--format", "{{.State.Running}}",
                          container).strip() == "true"
    except DockerError:
        return False
