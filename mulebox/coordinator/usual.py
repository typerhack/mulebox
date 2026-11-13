"""How long a job of a project usually takes, from its past stage rows.

The median of its last passed runs, for the whole job and for each stage. Only passed runs
count, because a run that failed stopped early and says nothing about the full length. A
median, because a first run that downloads everything should not move what is usual once
caches are warm; of two middle runs the lower, so the figure is one a real run took. A run that
lost its connection while fetching (worker/steps.py) does not count: it passed, but an outage is
not how long the job takes. No history gives None, and this never turns into a percentage: how far a running job has come is not
something past runs can tell.

For one job (`for_job`) the command counts too, so a changed job and the ad-hoc `mulebox run`
commands, which share one job name, do not mix. Only runs before it count, so `status` on an old
job says what was usual then, and a job is never compared with itself. `estimate` is the same
figure for a job still in the queue, once there are enough runs. It says nothing about how long
the jobs ahead take.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from statistics import median_low
from typing import Any

from mulebox.common.protocol import JobState

RUNS = 20  # recent enough to follow a project as it changes
MIN_RUNS = 3  # fewer say too little to tell someone in the queue

_RECENT = ("SELECT j.job_id FROM jobs j WHERE j.project = ? AND j.job = ? AND j.kind = 'job' "
           "AND j.outcome = 'passed' AND (? IS NULL OR j.argv = ?) AND (? IS NULL OR j.seq < ?) "
           "AND EXISTS (SELECT 1 FROM job_steps s WHERE s.job_id = j.job_id) "
           "AND NOT EXISTS (SELECT 1 FROM job_steps s WHERE s.job_id = j.job_id "
           "AND s.network_lost = 1) "
           "ORDER BY j.seq DESC LIMIT ?")


def _rows(conn: sqlite3.Connection, project: str, job: str, argv: str | None,
          before: int | None) -> dict[str, list[sqlite3.Row]]:
    runs: dict[str, list[sqlite3.Row]] = defaultdict(list)
    sql = ("SELECT job_id, stage, started_at, finished_at FROM job_steps "
           f"WHERE job_id IN ({_RECENT}) AND finished_at IS NOT NULL")
    for row in conn.execute(sql, (project, job, argv, argv, before, before, RUNS)):
        runs[row["job_id"]].append(row)
    return runs


def _per_stage(rows: list[sqlite3.Row]) -> dict[str, float]:
    """A stage that appears twice in a run counts as its sum."""
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[row["stage"]] += row["finished_at"] - row["started_at"]
    return totals


def usual(conn: sqlite3.Connection, project: str, job: str,
          argv: list[str] | None = None, before: int | None = None) -> dict[str, Any] | None:
    """`{"runs": n, "job_s": seconds, "stages": {stage: seconds}}`, or None without history.
    A stage appears if any of those runs had it, with the median of the runs that did."""
    encoded = None if argv is None else json.dumps(argv, sort_keys=True)  # as the store does
    runs = _rows(conn, project, job, encoded, before)
    if not runs:
        return None
    lengths, stages = [], defaultdict(list)
    for rows in runs.values():
        lengths.append(max(r["finished_at"] for r in rows) - min(r["started_at"] for r in rows))
        for stage, seconds in _per_stage(rows).items():
            stages[stage].append(seconds)
    return {"runs": len(runs), "job_s": round(median_low(lengths), 3),
            "stages": {stage: round(median_low(values), 3) for stage, values in stages.items()}}


def for_job(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any] | None:
    """`usual` for runs before this one with the same project, name and command."""
    return usual(conn, job["project"], job["job"], job["argv"], job["seq"])


# The last RUNS passed runs before each lookup's seq, one lookup per distinct (project, job,
# argv, seq) of the rows asked about, all of them in one query passed as JSON: each lookup walks
# the jobs_project index back from its seq and stops at RUNS runs, however long the history.
_LOOKUPS = ("WITH want AS (SELECT key AS n, json_extract(value, '$[0]') AS project, "
            "json_extract(value, '$[1]') AS job, json_extract(value, '$[2]') AS argv, "
            "json_extract(value, '$[3]') AS seq FROM json_each(?)) ")
_JOB_RUNS = (_LOOKUPS + "SELECT w.n, (SELECT MAX(s.finished_at) - MIN(s.started_at) "
             "FROM job_steps s WHERE s.job_id = j.job_id AND s.finished_at IS NOT NULL) AS length "
             "FROM want w JOIN jobs j ON j.job_id IN (SELECT r.job_id FROM jobs r "
             "WHERE r.project = w.project AND r.job = w.job AND r.seq < w.seq AND r.kind = 'job' "
             "AND r.outcome = 'passed' AND r.argv = w.argv "
             "AND EXISTS (SELECT 1 FROM job_steps s WHERE s.job_id = r.job_id) "
             "AND NOT EXISTS (SELECT 1 FROM job_steps s WHERE s.job_id = r.job_id "
             "AND s.network_lost = 1) ORDER BY r.seq DESC LIMIT ?)")
_RUNNER_RUNS = (_LOOKUPS + "SELECT w.n, j.duration_s AS length FROM want w JOIN jobs j "
                "ON j.job_id IN (SELECT r.job_id FROM jobs r WHERE r.project = w.project "
                "AND r.job = w.job AND r.seq < w.seq AND r.kind = 'runner' "
                "AND r.outcome = 'passed' AND r.duration_s IS NOT NULL "
                "ORDER BY r.seq DESC LIMIT ?)")


def _lookup(row: dict[str, Any]) -> tuple:
    """What a row's usual length depends on: its project, job, command and place in time."""
    argv = json.dumps(row["argv"], sort_keys=True) if row["kind"] == "job" else None
    return row["project"], row["job"], argv, row["seq"]


def lengths(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> dict[str, float | None]:
    """`job_seconds` for many rows at once, in one query per kind whatever their number, so the
    line (line.py) and the dashboard can read it for every waiting row inside one transaction."""
    out: dict[str, float | None] = {row["job_id"]: None for row in rows}
    for kind, sql, digits in (("job", _JOB_RUNS, 3), ("runner", _RUNNER_RUNS, 1)):
        mine = [row for row in rows if row["kind"] == kind]
        if not mine:
            continue
        wanted = sorted({_lookup(row) for row in mine})
        found: dict[int, list[float]] = defaultdict(list)
        for run in conn.execute(sql, (json.dumps(wanted), RUNS)):
            if run["length"] is not None:
                found[run["n"]].append(run["length"])
        index = {lookup: n for n, lookup in enumerate(wanted)}
        for row in mine:
            known = found.get(index[_lookup(row)])
            out[row["job_id"]] = round(median_low(known), digits) if known else None
    return out


def job_seconds(conn: sqlite3.Connection, job: dict[str, Any]) -> float | None:
    """What a job like this one usually takes, whole, for a card on the dashboard. A CI slot has
    no stages, so its figure is how long past slots of that repository and job were held."""
    return lengths(conn, [job])[job["job_id"]]


def estimate(job: dict[str, Any], typical: dict[str, Any] | None) -> dict[str, Any]:
    """`estimate_s` and `estimate_runs` for a queued job, or nothing; `typical` is `for_job`."""
    if job["state"] != JobState.QUEUED or job["kind"] != "job":
        return {}
    if typical is None or typical["runs"] < MIN_RUNS:
        return {}
    return {"estimate_s": round(typical["job_s"], 1), "estimate_runs": typical["runs"]}
