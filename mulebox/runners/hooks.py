"""GitHub Actions job hooks: hold a mulebox build slot for the length of a runner job.

`started` (ACTIONS_RUNNER_HOOK_JOB_STARTED) runs after the guard (guard.py `admit`, called first
by the CLI) has let the job in. It sends `reserve`, stores the job id in the
runner folder, then sends `acquire` every 2 s until the slot is granted, printing the
queue position at most every 30 s. It gives up after MULEBOX_HOOK_TIMEOUT_MIN minutes
(default 120): it cancels the reservation and exits 1, which fails the GitHub job.

`completed` (ACTIONS_RUNNER_HOOK_JOB_COMPLETED) sends `release` with the job's result and removes
the file. GitHub does not give the hook that result, so it is read from the runner's diary
(diary.py), with the step that failed and GitHub's message on it as `ci_result`. It
always exits 0: a release that did not get through is cleaned up by the worker's
supervision (supervise.py).

Both talk to the coordinator through a worker `CoordinatorLink`. The wait loop takes its
clock and sleep as arguments so tests run it without waiting.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TextIO

from mulebox.common.errors import MuleboxError
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.runners import diary, reservation_file
from mulebox.runners.diary import JobResult
from mulebox.worker.link import CoordinatorLink, LinkError, request
from mulebox.worker.paths import NodePaths

LOG = get_logger("runners.hooks")
POLL_S = 2.0
NOTICE_S = 30.0
DEFAULT_TIMEOUT_MIN = 120
TIMEOUT_ENV = "MULEBOX_HOOK_TIMEOUT_MIN"
_STATUS_OUTCOMES = {"success": Outcome.PASSED, "cancelled": Outcome.CANCELLED}


class HookError(MuleboxError):
    """The hook cannot do its job (missing environment, refused request)."""


# Set by the node for an isolated runner's job only, never read from a job: the jobs of one
# matrix share their run, attempt, job name and the runner's name, so the derived key would
# give the second the first's reservation. A one-job runner's name is new for every job.
KEY_ENV = "MULEBOX_RESERVATION_KEY"

@dataclass(frozen=True)
class GitHubJob:
    repository: str
    run_id: str
    run_attempt: str
    job: str
    runner: str
    branch: str | None = None
    run_url: str | None = None
    key: str | None = None  # an isolated runner's own (place_bridge.KEY_ENV), else derived

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> GitHubJob:
        names = ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB",
                 "RUNNER_NAME")
        missing = [name for name in names if not env.get(name)]
        if missing:
            raise HookError(f"missing environment variable(s): {', '.join(missing)}; "
                            "is this running as a GitHub Actions runner hook?")
        server = env.get("GITHUB_SERVER_URL")
        run_url = (f"{server.rstrip('/')}/{env['GITHUB_REPOSITORY']}/actions/runs/"
                   f"{env['GITHUB_RUN_ID']}") if server else None
        return cls(env["GITHUB_REPOSITORY"], env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"],
                   env["GITHUB_JOB"], env["RUNNER_NAME"], env.get("GITHUB_REF_NAME") or None,
                   run_url, env.get(KEY_ENV) or None)


def timeout_minutes(env: Mapping[str, str]) -> float:
    raw = env.get(TIMEOUT_ENV)
    if not raw:
        return DEFAULT_TIMEOUT_MIN
    try:
        value = float(raw)
    except ValueError:
        raise HookError(f"{TIMEOUT_ENV} must be a number of minutes, got {raw!r}") from None
    if value <= 0:
        raise HookError(f"{TIMEOUT_ENV} must be positive, got {raw!r}")
    return value


def outcome_from_status(status: str | None) -> Outcome:
    """GITHUB_JOB_STATUS -> outcome. Unset: passed (the runner reached its completed hook);
    any other value than success/cancelled: failed."""
    if not status:
        return Outcome.PASSED
    return _STATUS_OUTCOMES.get(status.strip().lower(), Outcome.FAILED)


def job_result(env: Mapping[str, str], paths: NodePaths, runner: str) -> JobResult | None:
    """The job's result: GITHUB_JOB_STATUS if GitHub ever sets it, else the runner's diary;
    None when neither says (the release then says passed, as it always did)."""
    if env.get("GITHUB_JOB_STATUS"):
        return JobResult(outcome_from_status(env["GITHUB_JOB_STATUS"]))
    try:
        return diary.read_result(reservation_file.runner_dir(paths, runner))
    except MuleboxError:
        return None


def _say(out: TextIO, text: str) -> None:
    print(f"mulebox: {text}", file=out, flush=True)


def _refused(reply: Message) -> bool:
    return reply.type is MessageType.ERROR


def started(env: Mapping[str, str], worker: str, link: CoordinatorLink, paths: NodePaths, *,
            clock: Callable[[], float] = time.monotonic,
            sleep: Callable[[float], None] = time.sleep, out: TextIO | None = None) -> int:
    """Reserve a slot on `worker` and wait until it is granted; return the exit code."""
    out = out or sys.stdout
    try:
        gh = GitHubJob.from_env(env)
        minutes = timeout_minutes(env)
        deadline = clock() + minutes * 60
        reservation_file.runner_dir(paths, gh.runner)
    except MuleboxError as exc:
        _say(out, f"cannot reserve a build slot: {exc}")
        return 1
    reserve = request(MessageType.RESERVE, worker=worker, repository=gh.repository,
                      job=gh.job, run_id=gh.run_id, run_attempt=gh.run_attempt,
                      runner=gh.runner, branch=gh.branch, run_url=gh.run_url,
                      **({"idempotency_key": gh.key} if gh.key else {}))
    # No idempotency_key: the coordinator derives it from the run, so a retried hook
    # finds its reservation (reservations.default_key).
    job_id: str | None = None
    noticed_at: float | None = None
    while True:
        try:
            if job_id is None:
                reply = link.call(reserve)
                if _refused(reply):
                    _say(out, f"the coordinator refused the reservation: "
                              f"{reply.body.get('message')}")
                    return 1
                job_id = reply.body["job_id"]
                reservation_file.write(paths, gh.runner, job_id)
            reply = link.call(request(MessageType.ACQUIRE, job_id=job_id))
        except LinkError as exc:
            LOG.warning("coordinator unreachable, retrying: %s", exc)
            reply = None
        except (MuleboxError, OSError) as exc:
            _say(out, f"cannot reserve a build slot: {exc}")
            return 1
        if reply is not None:
            if _refused(reply):
                _say(out, f"the coordinator refused the slot: {reply.body.get('message')}")
                return 1
            state = reply.body.get("state")
            if state == JobState.RUNNING:
                _say(out, f"build slot granted ({job_id})")
                return 0
            if state == JobState.FINISHED:
                _say(out, f"reservation {job_id} ended ({reply.body.get('outcome')}) before "
                          "it got a slot")
                return 1
            now = clock()
            if noticed_at is None or now - noticed_at >= NOTICE_S:
                _say(out, f"waiting for a build slot (position {reply.body.get('position')})")
                noticed_at = now
        if clock() >= deadline:
            _give_up(link, paths, gh.runner, job_id, minutes, out)
            return 1
        sleep(POLL_S)


def _give_up(link: CoordinatorLink, paths: NodePaths, runner: str, job_id: str | None,
             minutes: float, out: TextIO) -> None:
    _say(out, f"gave up waiting for a build slot after {minutes:g} minutes "
              f"({TIMEOUT_ENV}); check `mulebox queue` for what holds the slots")
    if job_id is None:
        return
    try:
        link.call(request(MessageType.RELEASE, job_id=job_id, outcome=Outcome.CANCELLED.value))
        reservation_file.remove(paths, runner)
    except (MuleboxError, OSError) as exc:
        LOG.warning("could not cancel reservation %s: %s", job_id, exc)


def completed(env: Mapping[str, str], link: CoordinatorLink, paths: NodePaths, *,
              out: TextIO | None = None) -> int:
    """Release the runner's reservation and remove its file. Always returns 0."""
    out = out or sys.stdout
    runner = env.get("RUNNER_NAME")
    try:
        job_id = reservation_file.read(paths, runner) if runner else None
    except (MuleboxError, OSError) as exc:
        LOG.warning("cannot read the reservation file: %s", exc)
        job_id = None
    if job_id is None:
        _say(out, "no build slot reservation to release")
        return 0
    result = job_result(env, paths, runner)
    outcome = result.outcome if result else Outcome.PASSED
    known = {"ci_result": result.fields()} if result else {}
    try:
        reply = link.call(request(MessageType.RELEASE, job_id=job_id, outcome=outcome.value,
                                  **known))
        if _refused(reply):
            LOG.warning("release of %s refused: %s", job_id, reply.body.get("message"))
        else:
            _say(out, f"build slot released ({job_id}, {outcome.value})")
    except MuleboxError as exc:
        LOG.warning("release of %s failed (supervision will release it): %s", job_id, exc)
    try:
        reservation_file.remove(paths, runner)
    except (MuleboxError, OSError) as exc:
        LOG.warning("cannot remove the reservation file: %s", exc)
    return 0
