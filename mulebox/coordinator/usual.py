"""How long a job of a project usually takes, from its past stage rows.

The median of its last passed runs, for the whole job and for each stage. Only passed runs
count, because a run that failed stopped early and says nothing about the full length. A
median, because a first run that downloads everything should not move what is usual once
caches are warm. No history gives None, and this never turns into a percentage: how far a
running job has come is not something past runs can tell.

For one job (`for_job`) the command counts too, so a changed job and the ad-hoc `mulebox run`
commands, which share one job name, do not mix. `estimate` is the same figure for a job still
in the queue, once there are enough runs. It says nothing about how long the jobs ahead take.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from statistics import median
from typing import Any

from mulebox.common.protocol import JobState

RUNS = 20  # recent enough to follow a project as it changes
MIN_RUNS = 3  # fewer say too little to tell someone in the queue

_RECENT = ("SELECT j.job_id FROM jobs j WHERE j.project = ? AND j.job = ? AND j.kind = 'job' "
           "AND j.outcome = 'passed' AND (? IS NULL OR j.argv = ?) AND EXISTS (SELECT 1 FROM "
           "job_steps s WHERE s.job_id = j.job_id) ORDER BY j.seq DESC LIMIT ?")


def _rows(conn: sqlite3.Connection, project: str, job: str,
          argv: str | None) -> dict[str, list[sqlite3.Row]]:
    runs: dict[str, list[sqlite3.Row]] = defaultdict(list)
    sql = ("SELECT job_id, stage, started_at, finished_at FROM job_steps "
           f"WHERE job_id IN ({_RECENT}) AND finished_at IS NOT NULL")
    for row in conn.execute(sql, (project, job, argv, argv, RUNS)):
        runs[row["job_id"]].append(row)
    return runs


def _per_stage(rows: list[sqlite3.Row]) -> dict[str, float]:
    """A stage that appears twice in a run counts as its sum."""
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row["stage"]] += row["finished_at"] - row["started_at"]
    return totals


def usual(conn: sqlite3.Connection, project: str, job: str,
          argv: list[str] | None = None) -> dict[str, Any] | None:
    """`{"runs": n, "job_s": seconds, "stages": {stage: seconds}}`, or None without history.
    A stage appears if any of those runs had it, with the median of the runs that did."""
    encoded = None if argv is None else json.dumps(argv, sort_keys=True)  # as the store does
    runs = _rows(conn, project, job, encoded)
    if not runs:
        return None
    lengths, stages = [], defaultdict(list)
    for rows in runs.values():
        lengths.append(max(r["finished_at"] for r in rows) - min(r["started_at"] for r in rows))
        for stage, seconds in _per_stage(rows).items():
            stages[stage].append(seconds)
    return {"runs": len(runs), "job_s": round(median(lengths), 3),
            "stages": {stage: round(median(values), 3) for stage, values in stages.items()}}


def for_job(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any] | None:
    """`usual` for past runs of this job's project, name and command."""
    return usual(conn, job["project"], job["job"], job["argv"])


def estimate(job: dict[str, Any], typical: dict[str, Any] | None) -> dict[str, Any]:
    """`estimate_s` and `estimate_runs` for a queued job, or nothing; `typical` is `for_job`."""
    if job["state"] != JobState.QUEUED or job["kind"] != "job":
        return {}
    if typical is None or typical["runs"] < MIN_RUNS:
        return {}
    return {"estimate_s": round(typical["job_s"], 1), "estimate_runs": typical["runs"]}
