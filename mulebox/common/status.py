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
"""

from __future__ import annotations

from typing import Any

ACTIVE = ("starting", "running", "cleaning")
WAITING = ("uploading", "queued")
FINISHED = "finished"
SECTIONS = ("running", "queued", "recent")
RUNNER_KIND = "runner"
RELEASED = "released"
# Lines the worker writes into a job's log; the client's failure summary looks for them.
CONTAINER_LOGS_NOTE = "mulebox: the job failed; the state and last log lines of its containers:"
NOT_STARTED_NOTE = "mulebox: the job could not start:"


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


def shown_state(job: dict[str, Any]) -> Any:
    """What a view shows in its state column (see the module docstring)."""
    state = job.get("outcome") if job.get("state") == FINISHED else job.get("state")
    if job.get("kind") == RUNNER_KIND and state in ("passed", "failed"):
        return RELEASED
    return state


def queue_position(job: dict[str, Any]) -> Any:
    """The queue position for a waiting job, None for any other state."""
    return job.get("position") if job.get("state") in WAITING else None


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
    }


def snapshot(jobs: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """The queue as one dict: `now` plus a list of rows per section."""
    out: dict[str, Any] = {"now": now}
    for name, group in sections(jobs):
        out[name] = [row(job, now) for job in group]
    return out


def fingerprint(jobs: list[dict[str, Any]]) -> tuple:
    """What changes when a view must redraw: ids, states, outcomes and positions.

    Elapsed times are left out on purpose: viewers tick them locally from the timestamps.
    """
    return tuple(
        (j.get("job_id"), j.get("state"), j.get("outcome"), j.get("position"),
         j.get("worker"), j.get("started_at"), j.get("finished_at"))
        for j in jobs
    )
