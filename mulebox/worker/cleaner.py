"""Cleaning up after a job: its Docker resources, then its folder, in that order.

The order matters: a running container can still write into the folder, and a bind mount
holds it open. `clean` is safe to call again, so the agent retries it until it succeeds.
`recover` does the same for what a crash left, found from the job folders on disk and from
the labels in Docker; one job that cannot be cleaned does not stop the others or the
worker, which logs it and tries again on its next start.
"""

from __future__ import annotations

from pathlib import Path

from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.safepath import RemovalDenied
from mulebox.worker import docker_cleanup, reclaim, workspace
from mulebox.worker.docker import Docker, DockerMissing
from mulebox.worker.paths import NodePaths

LOG = get_logger("worker.cleaner")


class Cleaner:
    def __init__(self, paths: NodePaths, worker: str, docker: Docker | None = None) -> None:
        self.paths, self.worker, self.docker = paths, worker, docker

    def clean(self, project: str, job_id: str, uses_docker: bool) -> None:
        """Remove the job's Docker resources and its folder; MuleboxError means try again."""
        if uses_docker and self.docker is not None:
            docker_cleanup.teardown(self.docker, job_id)
        self._remove_folder(project, job_id)

    def _remove_folder(self, project: str, job_id: str) -> None:
        try:
            workspace.cleanup(self.paths, project, job_id)
        except RemovalDenied:
            if self.docker is None:
                raise
            LOG.info("job %s left files this user cannot delete; reclaiming them", job_id)
            reclaim.reclaim(self.docker, self.paths, project, job_id, self.worker)
            workspace.cleanup(self.paths, project, job_id)

    def _labelled_jobs(self) -> list[str]:
        """Job ids with Docker resources here; turns recovery's Docker steps off if none."""
        if self.docker is None:
            return []
        try:
            return docker_cleanup.labelled_jobs(self.docker, self.worker)
        except DockerMissing:
            LOG.info("no docker on this machine; nothing to look for")
            self.docker = None
        except MuleboxError as exc:
            LOG.error("cannot list leftover Docker resources: %s", exc)
        return []

    def recover(self) -> list[str]:
        """Clean what earlier runs left; return what was cleaned, for the log."""
        cleaned: list[str] = []
        folders = workspace.leftover_job_dirs(self.paths)
        with_folder = {entry.name for entry in folders}
        for job_id in self._labelled_jobs():
            if job_id not in with_folder:
                cleaned += self._attempt(job_id, lambda j=job_id: self._teardown(j))
        for entry in folders:
            cleaned += self._attempt(str(entry), lambda e=entry: self._leftover(e))
        return cleaned

    def _teardown(self, job_id: str) -> None:
        if self.docker is not None:
            docker_cleanup.teardown(self.docker, job_id)

    def _leftover(self, entry: Path) -> None:
        self.clean(entry.parent.name, entry.name, uses_docker=True)

    @staticmethod
    def _attempt(what: str, step) -> list[str]:
        try:
            step()
        except (MuleboxError, OSError) as exc:
            LOG.error("could not clean %s (tried again on the next start): %s", what, exc)
            return []
        return [what]
