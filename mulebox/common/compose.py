"""What client and worker share about `compose:` projects: names, labels, the file list.

The project name and the labels are derived from the job id and from nothing else, so a
filter built here can only ever match resources of that one job. Everything that decides
what Docker removes starts from these functions.

The list of compose files travels inside the job's `env` values, under `COMPOSE_FILES_KEY`,
and the worker takes it out again. `env:` in `.mulebox.yml` cannot set a `MULEBOX*` name, so
the key cannot clash, and the coordinator's store needs no new column.
"""

from __future__ import annotations

import re

from mulebox.common.errors import MuleboxError
from mulebox.common.ids import is_valid_id

DOCKER_CAPABILITY = "docker"
COMPOSE_FILES_KEY = "MULEBOX_COMPOSE_FILES"
LABEL_JOB = "mulebox.job"
LABEL_WORKER = "mulebox.worker"
LABEL_COMPOSE_PROJECT = "com.docker.compose.project"
RESERVED_ENV = ("COMPOSE_FILE", "COMPOSE_PATH_SEPARATOR", "COMPOSE_PROJECT_NAME")
_SEPARATOR = ":"  # the separator of COMPOSE_FILE on Linux
_FILE_RE = re.compile(r"[A-Za-z0-9._/-]+")


class ComposeError(MuleboxError):
    """A compose project cannot be used as it is."""


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


def job_filter(job_id: str) -> str:
    """`docker ... --filter` value for what carries this job's own label."""
    return f"label={LABEL_JOB}={_checked(job_id)}"


def worker_filter(worker: str) -> str:
    """`docker ... --filter` value for what this worker labelled."""
    return f"label={LABEL_WORKER}={worker}"


def project_filter(job_id: str) -> str:
    """`docker ... --filter` value for what Compose labelled with this job's project."""
    return f"label={LABEL_COMPOSE_PROJECT}={project_name(job_id)}"
