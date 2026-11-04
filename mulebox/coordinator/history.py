"""How long a queued job usually runs, worked out from the job history.

The median of the last few passed runs with the same project, job name and command. Only
passed runs count, because a failed one may stop at any point. The command counts, so a
changed job and the ad-hoc `mulebox run` commands, which share one job name, do not mix.
With too few runs there is no estimate. It says nothing about how long the jobs ahead take.
"""

from __future__ import annotations

import json
import sqlite3
from statistics import median
from typing import Any

from mulebox.common.protocol import JobState, Outcome

RUNS = 10
MIN_RUNS = 3
_SQL = ("SELECT duration_s FROM jobs WHERE project = ? AND job = ? AND argv = ? AND kind = 'job' "
        "AND outcome = ? AND duration_s IS NOT NULL ORDER BY seq DESC LIMIT ?")


def estimate(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    """`estimate_s` and `estimate_runs` for a queued job, or nothing."""
    if job["state"] != JobState.QUEUED or job["kind"] != "job":
        return {}
    argv = json.dumps(job["argv"], sort_keys=True)  # as the store encodes it
    params = (job["project"], job["job"], argv, Outcome.PASSED.value, RUNS)
    durations = [row[0] for row in conn.execute(_SQL, params)]
    if len(durations) < MIN_RUNS:
        return {}
    return {"estimate_s": round(median(durations), 1), "estimate_runs": len(durations)}
