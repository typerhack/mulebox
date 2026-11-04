"""Giving root-owned files in a job folder back to the worker's user, without sudo.

Containers often run as root and write into the bind-mounted checkout. The worker's user
cannot delete such files, and mulebox never escalates. Docker can do one narrow thing
instead: a throwaway container changes the owner of the job folder, and then safepath
deletes it as always, so every delete still goes through safepath. Nothing here deletes.

The mount is the safety boundary. It is one job folder, proven by `safepath.confirm_dir`
to be a real directory inside the jobs root: no symlink on the way, not the root itself,
no mount in or above it. By then every job process and container is gone, so nothing is
left to swap it. The container gets no network, a read-only root file system, no new
privileges, and only the capabilities `chown` and `chmod` use on files of another user. A
symlink inside the folder is changed as a link (`-h`), and could only lead into this
disposable container anyway, since nothing else of the machine is mounted.

The image is pinned by digest because it runs as root over job files.
"""

from __future__ import annotations

import os

from mulebox.common import compose
from mulebox.common.safepath import Roots, UnsafePath, confirm_dir
from mulebox.worker.docker import Docker
from mulebox.worker.paths import NodePaths

HELPER_IMAGE = ("alpine:3.22@sha256:"
                "2e0b81d60597f449baa56dc25d355367869d2dca4cd57e866f1e2b52af3eb55f")
MOUNT_AT = "/reclaim"
TIMEOUT_S = 300.0
_SCRIPT = f'chown -hR "$1" {MOUNT_AT} && chmod -R u+rwX {MOUNT_AT}'


def helper_args(source: str, job_id: str, worker: str, uid: int, gid: int) -> tuple[str, ...]:
    """The exact `docker run`; `source` must come from `confirm_dir`."""
    if "," in source:  # would end the path inside the --mount value
        raise UnsafePath(f"{source} contains a comma; refusing to mount it")
    return (
        "run", "--rm",
        "--label", f"{compose.LABEL_JOB}={job_id}",
        "--label", f"{compose.LABEL_WORKER}={worker}",
        "--mount", f"type=bind,source={source},target={MOUNT_AT}",
        "--network=none",
        "--read-only",
        "--security-opt=no-new-privileges",
        "--cap-drop=ALL",
        "--cap-add=CHOWN",
        "--cap-add=DAC_READ_SEARCH",
        "--cap-add=FOWNER",
        "--pids-limit=16",
        HELPER_IMAGE,
        "sh", "-c", _SCRIPT, "mulebox-reclaim", f"{uid}:{gid}",
    )


def reclaim(docker: Docker, paths: NodePaths, project: str, job_id: str, worker: str) -> None:
    """Make the worker's user own everything in this job's folder."""
    source = confirm_dir(paths.job_dir(project, job_id), Roots((paths.jobs,)))
    docker.run(*helper_args(str(source), job_id, worker, os.getuid(), os.getgid()),
               timeout_s=TIMEOUT_S)
