"""State of one claimed job on this worker, from claim until its result is delivered."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mulebox.common.protocol import Outcome
from mulebox.worker.logtail import LogTailer


@dataclass
class ActiveJob:
    job_id: str
    attempt_id: str
    project: str
    tailer: LogTailer
    started_at: float  # agent clock
    last_heartbeat: float
    handle: Any = None  # executor handle once the process runs
    outcome: Outcome | None = None  # set when the job ended
    exit_code: int | None = None
    duration_s: float = 0.0
    cleaned: bool = False
    cleaning_sent: bool = False
    result_sent: bool = False


def outcome_for(exit_code: int, timed_out: bool) -> Outcome:
    if timed_out:
        return Outcome.TIMED_OUT
    return Outcome.PASSED if exit_code == 0 else Outcome.FAILED
