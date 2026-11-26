"""What the worker loop does with kept failed jobs (kept.py, rerun.py): keep one when it ends,
hand it to a rerun, remove it when its time is up or another job needs its branch.

Split from agent.py: `Agent` provides `kept`, `unkeeping`, `cleaner`, `ports`, `docker`,
`node` and `clock`. Removal runs beside the loop, as every cleanup does (background.py).
"""

from __future__ import annotations

from typing import Any

from mulebox.common import compose, isolation
from mulebox.common.log import get_logger
from mulebox.worker import background, rerun
from mulebox.worker import kept as kept_jobs
from mulebox.worker.job import ActiveJob
from mulebox.worker.kept import Kept

LOG = get_logger("worker.kept")
RETRY_S = 30.0  # after a removal that failed


class Keeping:
    def _kept_fields(self, now: float) -> dict[str, Any]:
        """`kept` for claims and heartbeats: what the coordinator may send a rerun to."""
        return {"kept": self.kept.report(now)}

    def _kept_result(self, job: ActiveJob, now: float) -> dict[str, Any]:
        """`kept` in a result: how long the job is kept, so its client hears it at once."""
        found = self.kept.jobs.get(job.job_id)
        if found is None:
            return {}
        return {"kept": {"left_s": round(max(0.0, found.until - now), 1), "memory": found.memory}}

    def _kept_tick(self, now: float) -> None:
        for gone in self.kept.due(now):
            LOG.info("kept job %s is past its time; removing it", gone.job_id)
            self._unkeep(gone, now)
        for entry in list(self.unkeeping):
            task, gone, at = entry
            if task is None and now >= at:
                self.unkeeping.remove(entry)
                self._unkeep(gone, now)
            elif task is not None and task.done:
                self.unkeeping.remove(entry)
                if task.error is None:
                    self.ports.release(gone.home)
                else:
                    LOG.error("could not remove kept job %s (trying again): %s", gone.job_id,
                              task.error)
                    self.unkeeping.append((None, gone, now + RETRY_S))

    def _unkeep(self, gone: Kept, now: float) -> None:
        self.unkeeping.append((background.start_thread(lambda: self._clean_kept(gone)), gone, now))

    def _clean_kept(self, gone: Kept) -> None:
        """Remove a kept job's containers and folders; MuleboxError means try again."""
        self.cleaner.clean(gone.project, gone.home, True, gone.tree)
        if gone.job_id != gone.home:  # a rerun that failed again: its own log folder
            self.cleaner.clean(gone.project, gone.job_id, False)

    def _kept_before(self, job: ActiveJob, claim: dict[str, Any]) -> list[Kept]:
        """A rerun takes what it reuses; any other job of the branch removes what is kept there
        first (returned, to be removed before it starts), as the containers mount its folder."""
        if claim.get("reuses") and claim.get("from_stage"):
            job.reused = self.kept.take(claim["reuses"])
        return self.kept.of_branch(job.project, claim.get("branch"))

    def _clean_all_kept(self, gone: list[Kept]) -> None:
        for entry in gone:
            self._clean_kept(entry)

    def _released(self, gone: list[Kept]) -> None:
        for entry in gone:
            self.ports.release(entry.home)

    def _rerun_claim(self, job: ActiveJob, claim: dict[str, Any], tree: Any) -> dict[str, Any]:
        """The claim this job runs as, and what it may keep if it fails: a rerun with what it
        reuses (rerun.py), or from the start with a note why it cannot."""
        files = compose.COMPOSE_FILES_KEY in (claim.get("env") or {})
        if files and isolation.CAPABILITY not in (claim.get("needs") or ()):
            job.rerun_key = rerun.key(tree, claim)
        if not claim.get("reuses") or not claim.get("from_stage"):
            return claim
        why = rerun.problem(job.reused, claim, tree, self.docker)
        if why is None:
            job.home, job.kept_env = job.reused.home, job.reused.env
            job.tailer.note(rerun.note(job.reused, claim))
            return rerun.as_run(claim)
        job.tailer.note(rerun.fallback_note(why))
        if job.reused is not None:
            self._clean_kept(job.reused)  # its containers and ports go before this job's start
            self.ports.release(job.reused.home)
        job.reused = None
        return claim

    def _keep(self, job: ActiveJob) -> bool:
        """Keep a failed job's containers instead of removing them, when the node keeps any."""
        minutes, asked, job.keep = self.node.storage.keep_failed_min, job.keep, False  # once
        if minutes <= 0 or not asked or job.rerun_key is None or job.kept_env is None:
            return False
        kept = Kept(job.job_id, job.home or job.job_id, job.project, job.branch,
                    self.clock() + minutes * 60.0, job.rerun_key, job.kept_env, job.tree,
                    job.meter.memory)
        for gone in self.kept.keep(kept, max(1, self.node.slots)):
            LOG.info("keeping %s; removing the oldest kept job, %s", job.job_id, gone.job_id)
            self._unkeep(gone, self.clock())
        LOG.info("keeping the containers of %s for %d min", job.job_id, minutes)
        return True

    @staticmethod
    def _keepable(job: ActiveJob) -> bool:
        return kept_jobs.keepable(job.outcome, job.exit_code, job.steps.stage,
                                  job.rerun_key is not None, False)
