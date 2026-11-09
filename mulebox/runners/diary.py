"""How a GitHub runner job went, read from the runner's own diary, `<runner>/_diag/Worker_*.log`.

GitHub does not tell a job-completed hook the job's result: GITHUB_JOB_STATUS is not set there
(129 of 129 real reservations were stored as passed before this). The runner writes it down,
though, before it runs that hook:

- `Processing step: DisplayName='<name>'` as each step starts (also read by live_log.py),
- `Step result: Failed` (or `Cancelled`) when one ends badly, followed by a telemetry block whose
  `errorMessages` holds what GitHub shows on the step, such as `Process completed with exit
  code 1.`,
- `Current state: job state = '<state>'` before each later step, and `Update job result with
  current step result '<state>'` when a step changes it. A step with `continue-on-error` fails
  without changing it, so the job's state, not a failed step, decides the outcome.

The diary is only read, never changed. Anything not found is unknown (None), never a guess.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from mulebox.common.protocol import Outcome

STEP = re.compile(r"Processing step: DisplayName='(.*)'\s*$")
FAILED = re.compile(r"Step result: (Failed|Cancell?ed)\b")
_STATE = re.compile(r"(?:job state = |current step result )'(\w+)'")
_OUTCOMES = {"succeeded": Outcome.PASSED, "succeededwithissues": Outcome.PASSED,
             "failed": Outcome.FAILED, "canceled": Outcome.CANCELLED,
             "cancelled": Outcome.CANCELLED}
_IGNORED = {"skipped"}
MAX_MESSAGE = 500
MAX_STEP = 200


@dataclass(frozen=True)
class JobResult:
    outcome: Outcome
    step: str | None = None  # the first step that failed, as GitHub names it
    message: str | None = None  # what GitHub says on that step

    def fields(self) -> dict[str, str]:
        """The `ci_result` of a release request: the outcome, and the step and message when known.
        Never empty, as an empty one is how a reservation of an older mulebox reads."""
        found = {"outcome": self.outcome.value, "step": self.step, "message": self.message}
        return {name: value for name, value in found.items() if value}


def newest(runner_dir: Path) -> Path | None:
    """The runner's current diary: the newest `Worker_<time>.log`, named so they sort."""
    try:
        found = sorted((Path(runner_dir) / "_diag").glob("Worker_*.log"))
    except OSError:
        return None
    return found[-1] if found else None


def _messages(lines: list[str], start: int) -> str | None:
    """`errorMessages` of the telemetry block after a failed step's result line."""
    for index in range(start, min(start + 40, len(lines))):
        if '"errorMessages"' not in lines[index]:
            continue
        block = [lines[index].split(":", 1)[1]]
        for line in lines[index + 1:index + 20]:
            if "]" in block[-1]:
                break
            block.append(line)
        try:
            found = json.loads("".join(block).rstrip().rstrip(","))
        except ValueError:
            return None
        text = " ".join(str(item) for item in found if item) if isinstance(found, list) else ""
        return text[:MAX_MESSAGE] or None
    return None


def job_result(text: str) -> JobResult | None:
    """The job's outcome so far, from a diary's text; None if it says nothing about one."""
    lines = text.splitlines()
    outcome: Outcome | None = None
    step = failed_step = message = None
    for index, line in enumerate(lines):
        if found := STEP.search(line):
            step = found[1]
        elif failed_step is None and step and FAILED.search(line):
            failed_step = step[:MAX_STEP]
            message = _messages(lines, index + 1)
        elif found := _STATE.search(line):
            state = found[1].lower()
            if state not in _IGNORED:
                outcome = _OUTCOMES.get(state, outcome)
    if outcome is None:
        return None
    if outcome is Outcome.PASSED:
        return JobResult(outcome)
    return JobResult(outcome, failed_step, message)


def read_result(runner_dir: Path) -> JobResult | None:
    """The result of the runner's current job, from its newest diary; None if unknown."""
    path = newest(runner_dir)
    if path is None:
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return job_result(text)
