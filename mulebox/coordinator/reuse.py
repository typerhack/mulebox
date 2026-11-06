"""Results an agent need not run again, and results it has not heard yet.

A job is the same job when the project, the job's name, the exact files (`fingerprint`, which
covers uncommitted changes) and what it runs with (argv, setup, toolchain, env) are the same.
Asked with `reuse`, `submit` answers with the same job already running or queued, or with its
result from the last `REUSE_S`, instead of running it twice. `--again` is the way to a fresh run.
Only a job that really ran counts: not a cancelled, stopped or interrupted one, and not one
that never started. A failure counts only from the mulebox running now: after an upgrade it may
have been a fault in mulebox that is gone, while a pass stays a pass. A job with no recorded
version counts as older.

A finished job nobody received the result of is told at the project's next command, so an agent
that went away learns the outcome and need not retest. `told_at` says that was done.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.protocol import JobState, Outcome
from mulebox.coordinator import store as st
from mulebox.version import get_version

REUSE_S = 86400.0
MAX_TOLD = 10
_SAME = ("argv", "setup", "toolchain", "env")
_OPEN = (JobState.QUEUED, JobState.STARTING, JobState.RUNNING)


def _ran(job: dict[str, Any]) -> bool:
    return job["outcome"] == Outcome.PASSED or (job["outcome"] == Outcome.FAILED
                                                and job["exit_code"] is not None
                                                and job["worker_version"] == get_version())


def earlier(conn: sqlite3.Connection, fields: dict[str, Any], now: float
            ) -> dict[str, Any] | None:
    """The same job, running or finished: an open one first, else the latest that ran."""
    rows = st.select_jobs(conn, "project = ? AND job = ? AND fingerprint = ? AND kind = 'job'",
                          (fields["project"], fields["job"], fields["fingerprint"]),
                          order="seq DESC")
    same = [job for job in rows
            if not job["cancel_requested"] and all(job[key] == fields[key] for key in _SAME)]
    return (next((job for job in same if job["state"] in _OPEN), None)
            or next((job for job in same if job["state"] == JobState.FINISHED and _ran(job)
                     and job["finished_at"] > now - REUSE_S), None))


def untold(conn: sqlite3.Connection, project: str) -> list[dict[str, Any]]:
    return st.select_jobs(conn, "project = ? AND state = ? AND kind = 'job' AND told_at IS NULL",
                          (project, JobState.FINISHED.value), order="seq DESC", limit=MAX_TOLD)


def told(conn: sqlite3.Connection, jobs: list[dict[str, Any]], now: float) -> None:
    for job in jobs:
        st.update_job(conn, job["job_id"], told_at=now)


def not_told(conn: sqlite3.Connection, job: dict[str, Any]) -> None:
    st.update_job(conn, job["job_id"], told_at=None)
