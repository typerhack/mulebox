"""The shared status model: how a job dict is classified and shown (docs/interfaces-m2.md).

Used by the terminal view (client/queue_view.py) and the web dashboard (dashboard/), so
both agree on sections, order, shown state and elapsed time. Input is a public job dict
(coordinator/views.py `job_dict`, as in a `queue_ok` reply); everything here is pure and
tolerant of missing or malformed fields, because the client reads them off the wire.

- Sections: `running` (starting, running, cleaning), `queued` (uploading, queued, in
  queue position order) and `recent` (finished, newest first).
- Shown state: the outcome for a finished job, else the state. A finished runner
  reservation (`kind = runner`) that passed or failed shows `released`: it only held a
  slot, the job's real result is on GitHub.
- Elapsed: waiting time for queued jobs, running time for active ones and the run time
  (`duration_s`, else finished_at - started_at) for finished ones.
- Stopped: a job nobody watched was stopped by the time limits. On the wire and in the store it
  stays outcome `cancelled` with a `stop_reason`, so an older client or worker reads a cancelled
  job and nothing worse; every view here shows `stopped: stuck`, and `outcome_of` says
  `stopped` wherever an outcome is printed for a reader.
- Event: what a state change means to a follower (`job_event`, `mulebox events`). `check_in` and
  `stage` are events too: the reply that carries one means that and not a state change.
- Steps: the rows of `steps` in a `status_ok` reply, one per stage of a job. An open row has
  no `finished_at`; only a job still active is really in that stage.
"""

from __future__ import annotations

from typing import Any

ACTIVE = ("starting", "running", "cleaning")
WAITING = ("uploading", "queued")
FINISHED = "finished"
SECTIONS = ("running", "queued", "recent")
RUNNER_KIND = "runner"
RELEASED = "released"
ENDED_BADLY = ("failed", "timed_out", "interrupted")  # outcomes that have a failure to explain
EVENT_VERSION = 1  # of `job_event` lines; raised only when a key changes meaning
# Lines the worker writes into a job's log; the client's failure summary looks for them.
CONTAINER_LOGS_NOTE = "mulebox: the job failed; the state and last log lines of its containers:"
NOT_STARTED_NOTE = "mulebox: the job could not start:"
TOOLCHAIN, PREPARE, ENVIRONMENT = "toolchain", "prepare", "environment"
IMAGES, SERVICES = "images", "services"
INSTALL, SETUP, COMMAND, CLEANUP = "install", "setup", "command", "cleanup"
STAGES = (TOOLCHAIN, PREPARE, ENVIRONMENT, IMAGES, SERVICES, INSTALL, SETUP, COMMAND, CLEANUP)
FETCHING = (IMAGES, INSTALL, SETUP)  # where a lost connection is the machine's, not the project's
MAX_FAILING_LINE = 500
STOPPED = "stopped"
SHOWN_STOPPED = "stopped: stuck"
STOP_STUCK, STOP_UNKNOWN = "stuck", "stuck_unknown"
STOP_TEXT = {STOP_STUCK: "no activity and no answer from the agent",
             STOP_UNKNOWN: "no answer from the agent, and its activity cannot be read"}
NOTICES = ("check_in", "stage")


def number(value: Any) -> float | None:
    """`value` as a float when it is a real number (bools are not), else None."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def duration_of(job: dict[str, Any]) -> float | None:
    """`duration_s` if given, else finished_at - started_at."""
    value = number(job.get("duration_s"))
    if value is not None:
        return value
    start, end = number(job.get("started_at")), number(job.get("finished_at"))
    if start is not None and end is not None:
        return max(0.0, end - start)
    return None


def section_of(job: dict[str, Any]) -> str | None:
    """`running`, `queued`, `recent`, or None for an unknown state."""
    state = job.get("state")
    if state in ACTIVE:
        return "running"
    if state in WAITING:
        return "queued"
    if state == FINISHED:
        return "recent"
    return None


def stopped(job: dict[str, Any]) -> bool:
    """Was this job stopped because nobody watched it? A stop the job beat to the end is not."""
    return bool(job.get("stop_reason")) and job.get("outcome") == "cancelled"


def outcome_of(job: dict[str, Any]) -> Any:
    return STOPPED if stopped(job) else job.get("outcome")


def shown_state(job: dict[str, Any]) -> Any:
    """What a view shows in its state column (see the module docstring)."""
    if stopped(job):
        return SHOWN_STOPPED
    state = job.get("outcome") if job.get("state") == FINISHED else job.get("state")
    if job.get("kind") == RUNNER_KIND and state in ("passed", "failed"):
        return RELEASED
    return state


def queue_position(job: dict[str, Any]) -> Any:
    """The queue position for a waiting job, None for any other state."""
    return job.get("position") if job.get("state") in WAITING else None


def job_event(job: dict[str, Any]) -> dict[str, Any] | None:
    """A status or result body as one event, None for a state with nothing to say.

    `started` covers `starting`, `running` and `cleaning`, so someone who reconnects late
    still learns where the job ran, and sees it once.
    """
    state = FINISHED if "outcome" in job and job.get("state") is None else job.get("state")
    event = {"v": EVENT_VERSION, "job_id": job.get("job_id"), "state": state}
    for name in NOTICES if state != FINISHED else ():  # the end is always `finished`
        if isinstance(job.get(name), dict):
            return {**job[name], **event, "event": name}
    if state == FINISHED:
        return {**event, "event": "finished", "outcome": outcome_of(job),
                "exit_code": job.get("exit_code"), "duration_s": job.get("duration_s"),
                "stage": job.get("stage"), "stop_reason": job.get("stop_reason")}
    if state in ACTIVE:
        return {**event, "state": "running", "event": "started", "machine": job.get("worker")}
    if state in WAITING:
        return {**event, "event": "queued", "position": queue_position(job),
                "waiting_for": job.get("waiting_for"), "estimate_s": job.get("estimate_s"),
                "running_ahead": job.get("running_ahead"),
                "branch_busy": job.get("branch_busy")}
    return None


def elapsed_s(job: dict[str, Any], now: float) -> float | None:
    """Seconds to show as elapsed (see the module docstring); None when unknown."""
    state = job.get("state")
    if state == FINISHED:
        return duration_of(job)
    since = number(job.get("started_at")) if state in ACTIVE else None
    since = since if since is not None else number(job.get("created_at"))
    return now - since if since is not None else None


def _created(job: dict[str, Any]) -> float:
    return number(job.get("created_at")) or 0.0


def sections(jobs: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """[(section, jobs)] in SECTIONS order, each sorted as the module docstring says."""
    active = sorted((j for j in jobs if section_of(j) == "running"), key=_created)
    waiting = sorted(
        (j for j in jobs if section_of(j) == "queued"),
        key=lambda j: (number(j.get("position")) or float("inf"), _created(j)),
    )
    done = sorted(
        (j for j in jobs if section_of(j) == "recent"),
        key=lambda j: number(j.get("finished_at")) or _created(j),
        reverse=True,
    )
    return [("running", active), ("queued", waiting), ("recent", done)]


def row(job: dict[str, Any], now: float) -> dict[str, Any]:
    """The job dict plus the derived fields every view shows (dashboard JSON rows)."""
    return {
        **job,
        "section": section_of(job),
        "shown_state": shown_state(job),
        "position": queue_position(job),
        "elapsed_s": elapsed_s(job, now),
        **({"outcome": STOPPED} if stopped(job) else {}),
    }


def snapshot(jobs: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """The queue as one dict: `now` plus a list of rows per section."""
    out: dict[str, Any] = {"now": now}
    for name, group in sections(jobs):
        out[name] = [row(job, now) for job in group]
    return out


def step_duration_s(step: dict[str, Any], now: float | None = None) -> float | None:
    """Seconds of a finished stage, or so far with `now`; None when unknown."""
    start = number(step.get("started_at"))
    end = number(step.get("finished_at"))
    end = end if end is not None else now
    return max(0.0, end - start) if start is not None and end is not None else None


def current_stage(job: dict[str, Any], steps: list[dict[str, Any]]) -> str | None:
    """The stage an active job is in, or None."""
    if job.get("state") not in ACTIVE or not steps or steps[-1].get("finished_at") is not None:
        return None
    return steps[-1].get("stage")


def failed_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The stage a job failed in: the first with a failing line or a non-zero exit code."""
    for step in steps:
        if step.get("failing_line") or step.get("exit_code") not in (None, 0):
            return step
    return None


def fingerprint(jobs: list[dict[str, Any]]) -> tuple:
    """What changes when a view must redraw: ids, states, outcomes, positions, for a
    waiting job where it may go (`can_run_on`, `waiting_for`, when the rows carry them), a
    waiting question's reason and whole minutes left, and what a job in a slot is doing
    (`doing_mark`), or its card would keep what it showed when the job started.

    Elapsed times are left out on purpose: viewers tick them locally from the timestamps.
    """
    return tuple(
        (j.get("job_id"), j.get("state"), j.get("outcome"), j.get("position"),
         j.get("worker"), j.get("started_at"), j.get("finished_at"),
         j.get("waiting_for"), tuple(j.get("can_run_on") or ()), left_mark(j), doing_mark(j))
        for j in jobs
    )


DOING_CPU_STEP = 10.0  # percent of one core; a finer change is not worth an event


def doing_mark(job: dict[str, Any]) -> tuple[Any, Any, int | None] | None:
    """A card's stage, step and CPU in steps of DOING_CPU_STEP, for a view's fingerprint."""
    doing = job.get("doing")
    if not isinstance(doing, dict):
        return None
    cpu = number(doing.get("cpu_pct"))
    return (doing.get("stage"), doing.get("step"),
            None if cpu is None else int(cpu // DOING_CPU_STEP))


def left_mark(job: dict[str, Any]) -> tuple[Any, int] | None:
    """A waiting question's reason and whole minutes left, for a view's fingerprint."""
    view = job.get("question")
    if not isinstance(view, dict):
        return None
    return view.get("stop_reason"), int((number(view.get("left_s")) or 0.0) // 60)
