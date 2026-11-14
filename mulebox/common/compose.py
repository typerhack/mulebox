"""What client and worker share about `compose:` projects: names, labels, the file list.

The project name and the labels are derived from the job id and from nothing else, so a
filter built here can only ever match resources of that one job. Everything that decides
what Docker removes starts from these functions.

The list of compose files travels inside the job's `env` values, under `COMPOSE_FILES_KEY`,
and the worker takes it out again. `env:` in `.mulebox.yml` cannot set a `MULEBOX*` name, so
the key cannot clash, and the coordinator's store needs no new column.

An older worker offering `docker` would see that key as plain environment, skip all of this
and run the job's commands against whatever is on the machine. So a `compose:` job also
needs `COMPOSE_CAPABILITY`, which is no setting: a worker reports it by itself, when it
offers docker, and a worker that cannot do this cannot report it. Raise the number when a
job needs something older workers cannot do.
"""

from __future__ import annotations

import re
import sys

from mulebox.common import isolation
from mulebox.common.errors import MuleboxError
from mulebox.common.ids import is_valid_id
from mulebox.common.package_cache import CAPABILITIES as PACKAGE_CACHES

DOCKER_CAPABILITY = "docker"
COMPOSE_CAPABILITY = "compose-v1"
COMPOSE_FILES_KEY = "MULEBOX_COMPOSE_FILES"
LABEL_JOB = "mulebox.job"
LABEL_WORKER = "mulebox.worker"
LABEL_COMPOSE_PROJECT = "com.docker.compose.project"
_SEPARATOR = ":"  # the separator of COMPOSE_FILE on Linux
_FILE_RE = re.compile(r"[A-Za-z0-9._/-]+")
_NOT_IN_A_TAG = re.compile(r"[^a-z0-9]+")


class ComposeError(MuleboxError):
    """A compose project cannot be used as it is."""


def worker_capabilities(configured: tuple[str, ...], platform: str = sys.platform) -> list[str]:
    """What a worker tells the coordinator: `capabilities` from its node.toml, and what it
    reports by itself."""
    implied = (COMPOSE_CAPABILITY,) if DOCKER_CAPABILITY in configured else ()
    implied = (*implied, *isolation.offered(configured, DOCKER_CAPABILITY, platform))
    return list(dict.fromkeys((*configured, *implied, *PACKAGE_CACHES)))


def file_problem(name: str) -> str | None:
    """Why `name` cannot be a compose file in the project, or None if it can."""
    if not _FILE_RE.fullmatch(name):
        return "may only contain letters, digits, '.', '_', '-' and '/'"
    if name.startswith(("/", "-")) or ".." in name.split("/"):
        return "must be a path inside the project, without '..'"
    return None


def join_files(files: tuple[str, ...] | list[str]) -> str:
    return _SEPARATOR.join(files)


def split_files(value: str) -> tuple[str, ...]:
    """The file list from a job's env value; every name is checked again on the worker."""
    files = tuple(value.split(_SEPARATOR))
    for name in files:
        problem = file_problem(name)
        if problem:
            raise ComposeError(f"compose file {name!r} {problem}")
    return files


def _checked(job_id: str) -> str:
    if not is_valid_id(job_id, "job"):
        raise ComposeError(f"{job_id!r} is not a mulebox job id")
    return job_id


def project_name(job_id: str) -> str:
    """The job's Compose project name. Compose wants lowercase, and a ULID has one case, so
    lowering it keeps the name unique."""
    return f"mulebox-{_checked(job_id).lower()}"


def image_name(job_id: str, index: int, service: str) -> str:
    """The tag of an image built for this job. Only this job has it, so only it removes it."""
    slug = _NOT_IN_A_TAG.sub("-", service.lower()).strip("-")
    return f"{project_name(job_id)}-{index}-{slug}"


def owns_image(job_id: str, reference: str) -> bool:
    """True if a `repository:tag` is one `image_name` gave this job."""
    return reference.startswith(f"{project_name(job_id)}-")


def job_filter(job_id: str) -> str:
    """`docker ... --filter` value for what carries this job's own label."""
    return f"label={LABEL_JOB}={_checked(job_id)}"


def worker_filter(worker: str) -> str:
    """`docker ... --filter` value for what this worker labelled."""
    return f"label={LABEL_WORKER}={worker}"


def project_filter(job_id: str) -> str:
    """`docker ... --filter` value for what Compose labelled with this job's project."""
    return f"label={LABEL_COMPOSE_PROJECT}={project_name(job_id)}"
