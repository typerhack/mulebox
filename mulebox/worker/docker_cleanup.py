"""Removing a job's Docker resources, and finding those a crash left behind.

The rule that matters: something is removed only because a docker listing, filtered on the
exact labels of one job (common/compose.py), returned its id. There is no other way in:
no prune, no removal by name, nothing derived from what looks unused. That leaves
everything else on the machine alone, including stopped containers, other volumes, and
images, which stay as cache. The one image exception is an image built for this job: it
carries the job's label and its tag exists for this job only, while the layers stay in
Docker's build cache.

A normal end and a crash take the same path, so the crash path runs on every job. After
removing, the listing runs again, and teardown only returns when it comes back empty:
compose killed mid-`up` can still leave the daemon finishing a container. Resources that
depend on each other go in order (containers, then what they use), and a failure is
logged and retried on the next pass; if something is still there at the end, DockerError
is raised and the agent tries again. An image alone does not hold a job back: it is a
leftover tag, and another job can be using it if the compose file names its own tag.
"""

from __future__ import annotations

from dataclasses import dataclass

from mulebox.common import compose
from mulebox.common.ids import is_valid_id
from mulebox.common.log import get_logger
from mulebox.worker.docker import Docker, DockerError

LOG = get_logger("worker.docker_cleanup")
PASSES = 3
_JOB_LABEL_FORMAT = '{{.Label "' + compose.LABEL_JOB + '"}}'


@dataclass(frozen=True)
class Kind:
    name: str
    list_args: tuple[str, ...]
    remove_args: tuple[str, ...]


KINDS = (
    Kind("containers", ("ps", "--all", "--quiet", "--no-trunc"), ("rm", "--force", "--volumes")),
    Kind("networks", ("network", "ls", "--quiet", "--no-trunc"), ("network", "rm")),
    Kind("volumes", ("volume", "ls", "--quiet"), ("volume", "rm")),
    Kind("images", ("image", "ls", "--quiet", "--no-trunc"), ("image", "rm", "--force")),
)
# What can be listed with the job's label as text. Images cannot, and an image alone is
# never all that is left of a job: its folder is still there, and that is enumerated too.
_ENUMERABLE = KINDS[:3]


def _found(docker: Docker, job_id: str) -> list[tuple[Kind, list[str]]]:
    """What exists for this job and nothing else: both filters name this one job."""
    found = []
    for kind in KINDS:
        ids: list[str] = []
        for exact in (compose.job_filter(job_id), compose.project_filter(job_id)):
            ids += docker.lines(*kind.list_args, "--filter", exact)
        if ids:
            found.append((kind, list(dict.fromkeys(ids))))
    return found


def teardown(docker: Docker, job_id: str) -> None:
    """Remove everything labelled for this job; DockerError if something stays."""
    for _ in range(PASSES):
        found = _found(docker, job_id)
        if not found:
            return
        for kind, ids in found:
            LOG.info("removing %d %s of %s", len(ids), kind.name, job_id)
            try:
                docker.run(*kind.remove_args, *ids)
            except DockerError as exc:
                LOG.warning("removing %s of %s: %s", kind.name, job_id, exc)
    left = _found(docker, job_id)
    held = [(kind, ids) for kind, ids in left if kind.name != "images"]
    if held:
        names = ", ".join(f"{len(ids)} {kind.name}" for kind, ids in held)
        raise DockerError(f"could not remove {names} of {job_id}")
    if left:
        LOG.warning("left the image built for %s in place: it is still in use", job_id)


def labelled_jobs(docker: Docker, worker: str) -> list[str]:
    """Job ids this worker's labels are on. A value that is no job id is ignored."""
    filters = ("--filter", f"label={compose.LABEL_JOB}",
               "--filter", compose.worker_filter(worker))
    seen: dict[str, None] = {}
    for kind in _ENUMERABLE:
        listing = tuple(arg for arg in kind.list_args if arg != "--quiet")
        for value in docker.lines(*listing, *filters, "--format", _JOB_LABEL_FORMAT):
            if is_valid_id(value, "job"):
                seen[value] = None
            else:
                LOG.warning("ignoring the label value %r: not a job id", value)
    return list(seen)
