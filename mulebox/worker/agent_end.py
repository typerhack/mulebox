"""How a job ends in the worker: stop it, flush its log, clean up beside the loop, report.

Split from agent.py: `Agent` provides the rest (`active`, `finishing`, `executor`, `_call`).
"""

from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, MessageType, Outcome
from mulebox.common.status import CLEANUP
from mulebox.worker import background, install_step, pull_failure, take_back
from mulebox.worker.job import ActiveJob, ended_badly
from mulebox.worker.link import LinkError, request

LOG = get_logger("worker.agent")
HEARTBEAT_S = 3.0  # also how fast a cancel is noticed; the lease is still 120 s


class Ending:
    def _end(self, job: ActiveJob, outcome: Outcome, exit_code: int | None, now: float) -> None:
        """Stop the process, flush the log, clean up; reports go out via _deliver."""
        if job.handle is not None and self.executor.poll(job.handle) is None:
            self.executor.stop(job.handle)
        job.duration_s = max(0.0, now - job.started_at)
        job.tailer.finish()
        exit_code = pull_failure.checked(outcome, exit_code, job.tailer)
        exit_code = install_step.checked(outcome, exit_code, job.tailer)
        job.outcome, job.exit_code = outcome, exit_code
        if outcome is Outcome.PASSED and job.take and job.tree is not None:
            job.taking = take_back.chunks(take_back.read_files(job.tree, job.take, job.tailer.note))
        job.steps.close(exit_code, now, ended_badly(outcome))
        self._keep_setup(job)
        job.steps.begin(CLEANUP, now)
        self.active.pop(job.job_id, None)
        self.finishing.append(job)
        LOG.info("job %s ended: %s (exit %s)", job.job_id, outcome, exit_code)
        if self._online(now):
            try:
                self._send_cleaning(job, now)
            except LinkError:
                pass
        self._deliver(job, now)

    def _clean(self, job: ActiveJob) -> None:
        if self.paths.is_safe_job(job.project, job.job_id):
            self.cleaner.clean(job.project, job.job_id, job.uses_docker, job.tree)

    def _cleanup(self, job: ActiveJob) -> None:
        """Start the job's cleanup, or take its outcome; a failed one starts again next step."""
        if job.cleanup is None:
            job.cleanup = background.start_thread(lambda: self._clean(job))
        if not job.cleanup.done:
            return
        task, job.cleanup = job.cleanup, None
        if task.error is not None:
            LOG.error("cleanup of %s failed (retrying): %s", job.job_id, task.error)
            return
        job.cleaned = True
        job.steps.finish_cleanup(self.clock())
        self.ports.release(job.job_id)

    def _keep_lease(self, job: ActiveJob, now: float) -> None:
        """The job counts for its slot until the result; a slow cleanup must not lose it."""
        if now - job.last_heartbeat >= HEARTBEAT_S and self._online(now):
            self._ping(job, now)

    def _send_cleaning(self, job: ActiveJob, now: float) -> None:
        if job.cleaning_sent:
            return
        job.tailer.send(self._sender(now))
        self._call(request(MessageType.JOB_UPDATE, job_id=job.job_id,
                           state=JobState.CLEANING.value, attempt_id=job.attempt_id), now)
        job.cleaning_sent = True

    def _deliver(self, job: ActiveJob, now: float) -> None:
        if not job.cleaned:
            self._cleanup(job)
            if not job.cleaned:
                self._keep_lease(job, now)
                return
        if not self._online(now):
            return
        try:
            self._send_cleaning(job, now)
            job.tailer.send(self._sender(now))
            take_back.send(job.job_id, job.attempt_id, job.taking, self._sender(now))
            self._call(request(
                MessageType.RESULT, job_id=job.job_id, outcome=job.outcome.value,
                exit_code=job.exit_code, duration_s=round(job.duration_s, 3),
                attempt_id=job.attempt_id), now)
        except LinkError:
            return
        job.result_sent = True
        self.finishing.remove(job)
