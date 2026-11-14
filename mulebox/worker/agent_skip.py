"""What a job may skip: a `setup` or `install` that nothing it depends on has changed.

Split from agent.py: `Agent` provides `paths`.
"""

from typing import Any

from mulebox.common import compose
from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.status import COMMAND, SETUP
from mulebox.worker import project_home
from mulebox.worker.job import ActiveJob

LOG = get_logger("worker.agent")


class Skipping:
    def _with_setup(self, job: ActiveJob, claim: dict[str, Any], synced: project_home.Synced
                    ) -> dict[str, Any]:
        """`claim` without its `setup` when nothing it depends on changed."""
        if not claim.get("setup") or compose.COMPOSE_FILES_KEY in (claim.get("env") or {}):
            return claim
        key = project_home.setup_key(synced.tree, claim)
        if (not synced.lost
                and project_home.is_current(self.paths, job.project, job.branch, key)):
            job.tailer.note("mulebox: setup skipped: nothing it depends on changed\n")
            return {**claim, "setup": None}
        project_home.forget_setup(self.paths, job.project, job.branch)
        job.setup_key = key
        return claim

    def _with_install(self, job: ActiveJob, claim: dict[str, Any], synced: project_home.Synced
                      ) -> dict[str, Any]:
        """`claim` without its `install` when nothing it depends on changed."""
        if not claim.get("install"):
            return claim
        key = project_home.install_key(synced.tree, claim)
        if not synced.lost and project_home.is_current(self.paths, job.project, job.branch, key,
                                                       project_home.INSTALL):
            job.tailer.note("mulebox: install skipped: nothing it depends on changed\n")
            return {**claim, "install": None}
        project_home.forget_setup(self.paths, job.project, job.branch, project_home.INSTALL)
        job.install_key = key
        return claim

    def _keep_setup(self, job: ActiveJob) -> None:
        try:
            if job.setup_key is not None and job.steps.reached(COMMAND):
                project_home.remember_setup(self.paths, job.project, job.branch, job.setup_key)
            if job.install_key is not None and (job.steps.reached(SETUP)
                                                or job.steps.reached(COMMAND)):
                project_home.remember_setup(self.paths, job.project, job.branch, job.install_key,
                                            project_home.INSTALL)
        except (MuleboxError, OSError) as exc:  # the next job only runs it again
            LOG.warning("could not record the setup of %s: %s", job.job_id, exc)
