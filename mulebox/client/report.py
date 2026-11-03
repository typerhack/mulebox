"""What the client tells the user: exit codes, durations, status lines (interfaces-m1.md).

Pure functions only, shared by `run_job`, `logs` and the queue view.
"""

from __future__ import annotations

from typing import Any, TextIO

from mulebox.common.protocol import Outcome
from mulebox.common.status import duration_of

__all__ = ["duration_of"]  # re-exported: the shared status model owns it

EXIT_USAGE = 2  # usage or config error
EXIT_UNREACHABLE = 3  # build machine unreachable
EXIT_REMOTE = 4  # protocol or remote error
EXIT_CANCELLED = 130
EXIT_TIMED_OUT = 124
EXIT_INTERRUPTED = 75

PREFIX = "mulebox: "


def status(err: TextIO, text: str) -> None:
    """One mulebox status line on stderr (never mixed into the job log on stdout)."""
    err.write(f"{PREFIX}{text}\n")
    err.flush()


def exit_code_for(result: dict[str, Any]) -> int:
    """Map a finished job to the exit code `mulebox check` returns."""
    outcome = result.get("outcome")
    code = result.get("exit_code")
    valid = isinstance(code, int) and not isinstance(code, bool) and 0 <= code <= 255
    if outcome == Outcome.PASSED:
        return code if valid else 0
    if outcome == Outcome.FAILED:
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


def format_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KiB"
    return f"{size / 1024**2:.1f} MiB"


def outcome_line(job_id: str, result: dict[str, Any]) -> str:
    outcome = result.get("outcome", "unknown")
    took = format_duration(duration_of(result))
    code = result.get("exit_code")
    detail = f" (exit {code})" if outcome == Outcome.FAILED and code is not None else ""
    if outcome == Outcome.TIMED_OUT:
        detail = " (job timeout reached)"
    return f"job {job_id} {outcome}{detail} in {took}"


def state_line(body: dict[str, Any]) -> str | None:
    """Status line for a state change seen on the watch stream (None: nothing to say)."""
    state = body.get("state")
    if state == "uploading":
        return None
    if state == "queued":
        position = body.get("position")
        return f"queued, position {position}" if position is not None else "queued"
    if state in ("starting", "running"):
        worker = body.get("worker")
        return f"{state}" + (f" on {worker}" if worker else "")
    if state == "cleaning":
        return "cleaning up"
    return None


def short_id(job_id: str, length: int = 8) -> str:
    """The random tail of a job id; the ULID head is the same for jobs of one moment."""
    return job_id[-length:] if len(job_id) > length else job_id
