"""State of one claimed job on this worker, from claim until its result is delivered."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mulebox.common.protocol import Outcome
from mulebox.worker.job_meter import JobMeter
from mulebox.worker.logtail import LogTailer
from mulebox.worker.steps import StepTracker


@dataclass
class ActiveJob:
    job_id: str
    attempt_id: str
    project: str
    tailer: LogTailer
    started_at: float  # agent clock
    last_heartbeat: float
    last_output: float = 0.0  # agent clock: the last bytes in the job's raw log
    handle: Any = None  # executor handle once the process runs
    uses_docker: bool = False  # a `compose:` job: its Docker resources are torn down
    outcome: Outcome | None = None  # set when the job ended
    exit_code: int | None = None
    duration_s: float = 0.0
    cleanup: Any = None  # the background.Task in progress
    install: Any = None  # the background.Task installing the job's toolchain
    launch: Any = None  # starts the job once that is done
    cleaned: bool = False
    cleaning_sent: bool = False
    result_sent: bool = False
    meter: JobMeter = field(default_factory=JobMeter)
    branch: str | None = None
    tree: Any = None  # the Path of the project's worktree this job runs in
    setup_key: str | None = None  # set when this job's `setup` counts once it has passed
    install_key: str | None = None  # the same for its `install`
    take: list[str] = field(default_factory=list)  # files `mulebox run --take` brings back
    taking: list[tuple[int, int, bytes]] = field(default_factory=list)  # chunks yet to send

    @property
    def steps(self) -> StepTracker:
        return self.tailer.steps


def ended_badly(outcome: Outcome) -> bool:
    """A stage that ended this way has a failing line; a cancelled one does not."""
    return outcome in (Outcome.FAILED, Outcome.TIMED_OUT)


def outcome_for(exit_code: int, timed_out: bool) -> Outcome:
    if timed_out:
        return Outcome.TIMED_OUT
    return Outcome.PASSED if exit_code == 0 else Outcome.FAILED
