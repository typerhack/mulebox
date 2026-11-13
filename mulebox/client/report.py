"""What the client tells the user: exit codes, durations, status lines (interfaces-m1.md).

Pure functions only, shared by `run_job`, `logs` and the queue view.
"""

from __future__ import annotations

from typing import Any, TextIO

from mulebox.common.config import DEFAULT_LOG_DAYS
from mulebox.common.dashboard_address import hint
from mulebox.common.protocol import Outcome
from mulebox.common.status import (
    SHOWN_STOPPED,
    STOP_TEXT,
    current_stage,
    duration_of,
    number,
    step_duration_s,
    stopped,
)

__all__ = ["duration_of"]  # re-exported: the shared status model owns it

EXIT_USAGE = 2  # usage or config error
EXIT_UNREACHABLE = 3  # node unreachable
EXIT_REMOTE = 4  # protocol or remote error
EXIT_NOT_STARTED = 5  # the job never ran: the machine could not set it up
EXIT_CANCELLED = 130
EXIT_TIMED_OUT = 124
EXIT_INTERRUPTED = 75
EXIT_STOPPED = 76  # stuck, and the agent did not answer: the check said nothing

PREFIX = "mulebox: "
LONG_QUEUE_POSITION = 2  # jobs ahead in line, not only one running
LONG_JOB_S = 300.0


def status(err: TextIO, text: str) -> None:
    """One mulebox status line on stderr (never mixed into the job log on stdout)."""
    err.write(f"{PREFIX}{text}\n")
    err.flush()


def dashboard_hint(err: TextIO, body: dict[str, Any], job_id: str | None = None) -> None:
    """Where to see this, from a coordinator reply; silent when the reply does not say."""
    line = hint(body.get("dashboard"), job_id)
    if line:
        status(err, line)


def exit_code_for(result: dict[str, Any]) -> int:
    """Map a finished job to the exit code `mulebox check` returns."""
    if stopped(result):
        return EXIT_STOPPED
    outcome = result.get("outcome")
    code = result.get("exit_code")
    valid = isinstance(code, int) and not isinstance(code, bool) and 0 <= code <= 255
    if outcome == Outcome.PASSED:
        return code if valid else 0
    if outcome == Outcome.FAILED:
        if code is None:  # no command ran, so no code of the project's own to pass on
            return EXIT_NOT_STARTED
        return code if valid and code != 0 else 1
    if outcome == Outcome.TIMED_OUT:
        return EXIT_TIMED_OUT
    if outcome == Outcome.CANCELLED:
        return EXIT_CANCELLED
    return EXIT_INTERRUPTED  # interrupted, or an outcome this client does not know


def format_duration(seconds: float | None) -> str:
    """`42s`, `3m 05s`, `1h 02m`; `-` when unknown."""
    if seconds is None:
        return "-"
    total = int(max(0, round(seconds)))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def outcome_line(job_id: str, result: dict[str, Any]) -> str:
    took = format_duration(duration_of(result))
    if stopped(result):
        reason = STOP_TEXT.get(result["stop_reason"], result["stop_reason"])
        return f"job {job_id} {SHOWN_STOPPED} after {took}: {reason}; it is not a failed check"
    outcome = result.get("outcome", "unknown")
    code = result.get("exit_code")
    detail = ""
    if outcome == Outcome.FAILED:
        detail = " (could not start)" if code is None else f" (exit {code})"
    if outcome == Outcome.TIMED_OUT:
        detail = " (job timeout reached)"
    return f"job {job_id} {outcome}{detail} in {took}"


def log_expired(body: dict[str, Any]) -> bool:
    """Did this job write a log? Asked once reading it gave nothing: the coordinator keeps a
    job's row after it has removed its log, so the size says there was one."""
    size = number(body.get("log_size"))
    return size is not None and size > 0


def expired_line(job_id: str) -> str:
    return (f"the log of job {job_id} has expired: nodes remove old logs (after "
            f"{DEFAULT_LOG_DAYS} days by default). `mulebox status {job_id}` still has the result")


def waiting_reason(body: dict[str, Any]) -> str | None:
    """Why a queued job has not started: nothing can run it, its branch is taken, or the
    machines are busy. None: nothing holds it, and a worker is about to take it."""
    if body.get("waiting_for"):
        return str(body["waiting_for"])
    if body.get("branch_busy"):
        return f"{short_id(body['branch_busy'])} is running on this branch"
    ahead = body.get("running_ahead") or []
    if ahead:
        return f"the machines are busy with {len(ahead)} job{'s' if len(ahead) > 1 else ''}"
    return None


def place_lines(body: dict[str, Any]) -> list[str]:
    """Why a waiting job is where it is in line, while an order rule is on (coordinator/line.py);
    nothing when arrival alone placed it."""
    reason = body.get("place_reason")
    return [f"place: {reason}"] if body.get("state") == "queued" and reason else []


def state_line(body: dict[str, Any]) -> str | None:
    """Status line for a state change seen on the watch stream (None: nothing to say)."""
    state = body.get("state")
    if state == "uploading":
        return None
    if state == "queued":
        position = body.get("position")
        line = f"queued, position {position}" if position is not None else "queued"
        estimate = _estimate(body)
        line = f"{line}; {estimate}" if estimate else line
        reason = waiting_reason(body)
        return f"{line}; waiting: {reason}" if reason else line
    if state in ("starting", "running"):
        worker = body.get("worker")
        return f"{state}" + (f" on {worker}" if worker else "")
    if state == "cleaning":
        return "cleaning up"
    return None


def _estimate(body: dict[str, Any]) -> str | None:
    seconds, runs = number(body.get("estimate_s")), body.get("estimate_runs")
    if seconds is None:
        return None
    return f"estimate: runs about {format_duration(seconds)} once started ({runs} past runs)"


def long_wait(body: dict[str, Any]) -> bool:
    """Is this a wait worth leaving? Known only from the line and the job's past runs: a job
    at position 1 behind a long job looks short, as nothing says how long that one takes."""
    if body.get("state") != "queued":
        return False
    place, estimate = number(body.get("position")), number(body.get("estimate_s"))
    return (place or 0) >= LONG_QUEUE_POSITION or (estimate or 0) >= LONG_JOB_S


def stage_lines(body: dict[str, Any], now: float) -> list[str]:
    """A job's stages for `mulebox status`, each beside its usual length. What is usual is only
    what past runs took, not how far along this one is, so nothing here is a percentage."""
    rows = [row for row in body.get("steps") or [] if isinstance(row, dict)]
    typical = body.get("usual") if isinstance(body.get("usual"), dict) else {}
    stages = typical.get("stages") if isinstance(typical.get("stages"), dict) else {}
    running = current_stage(body, rows)
    lines = []
    for row in rows:
        is_open = running is not None and row is rows[-1]
        took = format_duration(step_duration_s(row, now if is_open else None))
        usual = number(stages.get(row.get("stage")))
        line = f"  {row.get('stage')}: {took}{' so far' if is_open else ''}"
        lines.append(f"{line} (usual {format_duration(usual)})" if usual is not None else line)
    seconds = number(typical.get("job_s"))
    if seconds is not None:
        lines.append(f"  usual for this job: {format_duration(seconds)} "
                     f"({typical.get('runs')} past runs)")
    return lines


def short_id(job_id: str, length: int = 8) -> str:
    """The random tail of a job id; the ULID head is the same for jobs of one moment."""
    return job_id[-length:] if len(job_id) > length else job_id
