"""A job's project folder, and what it may skip there: a `setup` or `install` that nothing it
depends on has changed.

Split from agent.py: `Agent` provides `paths`, `docker`, `node`, `link`, `machine` and `clock`.
"""

from pathlib import Path
from typing import Any

from mulebox.common import compose
from mulebox.common.errors import MuleboxError
from mulebox.common.safepath import RemovalDenied, remove_tree
from mulebox.common.log import get_logger
from mulebox.common.status import COMMAND, ENVIRONMENT, SETUP
from mulebox.worker import kept as kept_jobs
from mulebox.worker import project_home, reclaim, runspec, toolchains, workspace
from mulebox.worker.executor import RunSpec
from mulebox.worker.job import ActiveJob

LOG = get_logger("worker.agent")


class Skipping:
    def _prepare(self, job: ActiveJob, claim: dict[str, Any], log_path: Path) -> RunSpec:
        scratch = workspace.job_dir(self.paths, job.project, job.job_id)
        snapshot = scratch / "snapshot.tar.gz"
        self.link.fetch_snapshot(job.job_id, snapshot)
        job.branch = claim.get("branch")
        synced = self._into_home(job, snapshot)
        src = job.tree = synced.tree
        remove_tree(snapshot, self.paths.roots)
        job.tailer.note(f"mulebox: project folder {src}, {synced.changed} files changed\n")
        settled = bool(claim.get("install") or claim.get("setup"))
        claim = self._rerun_claim(job, claim, src)  # a rerun skips what it reuses (agent_kept.py)
        claim = {**self._with_install(job, self._with_setup(job, claim, synced), synced),
                 "deps_settled": settled}
        job.steps.begin(ENVIRONMENT, self.clock())
        bins = toolchains.path_for(self.paths, claim.get("toolchain") or {})
        spec, notes = runspec.build(self.machine, job.job_id, claim, src, log_path, bins,
                                    job.steps.marker, scratch, job.kept_env)
        if job.rerun_key is not None and job.kept_env is None:
            job.kept_env = kept_jobs.compose_env(spec.env)
        for note in notes:
            job.tailer.note(f"mulebox: {note}\n")
        return spec

    def _into_home(self, job: ActiveJob, snapshot: Path) -> project_home.Synced:
        """The job's files into the project's worktree; a crash can leave root's files there."""
        branch = job.branch
        try:
            return project_home.prepare(self.paths, job.project, branch, job.job_id, snapshot)
        except (RemovalDenied, PermissionError):
            if self.docker is None:
                raise
        tree = project_home.tree_for(self.paths, job.project, branch)
        reclaim.reclaim_tree(self.docker, self.paths, tree, job.job_id, self.node.name)
        return project_home.prepare(self.paths, job.project, branch, job.job_id, snapshot)

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
