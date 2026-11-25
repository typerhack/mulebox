"""What jobs really used, for `mulebox usage` and the dashboard (docs/design.md, Job usage).

Per project and job (a GitHub run's job is its workflow job), over its last `runs` finished runs:
how many there were, how many carry a measurement, the median and highest peak of cores and of
memory, and the size that would have fitted every one of them (`fits`: the highest peaks, cores
rounded up to a whole core, memory up to 0.5 GB). Only passed runs count unless `all` is asked:
a failure can end early and look small. A run with no `usage` (a worker older than this) is
counted in `not_measured`, never as 0.

`run(conn, job_id)` gives one run's numbers. The machines' sizes come with every answer, from
their last reports, so a reader can set a job beside the node it runs on.
"""

from __future__ import annotations

import json
import math
import sqlite3
from statistics import median
from typing import Any

from mulebox.common.protocol import JobState, Outcome
from mulebox.common.usage import average_cores
from mulebox.coordinator import store as st

KINDS = ("job", "runner")
FILTERS = ("project", "job", "worker", "kind")
DEFAULT_RUNS = 20
MAX_RUNS = 500
MEMORY_STEP = 500_000_000  # 0.5 GB, decimal like every size shown


def fits(peak_cores: float | None, peak_memory: int | None) -> dict[str, Any] | None:
    """The size that fits these peaks: whole cores, memory in 0.5 GB steps."""
    if peak_cores is None and peak_memory is None:
        return None
    return {"cores": None if peak_cores is None else max(1, math.ceil(peak_cores - 1e-9)),
            "memory": None if peak_memory is None
            else max(1, math.ceil(peak_memory / MEMORY_STEP)) * MEMORY_STEP}


def _where(filters: dict[str, str | None], every: bool) -> tuple[str, list[Any]]:
    sql = f"state = ? AND kind IN ({', '.join('?' * len(KINDS))})"
    params: list[Any] = [JobState.FINISHED.value, *KINDS]
    if not every:
        sql, params = f"{sql} AND outcome = ?", [*params, Outcome.PASSED.value]
    for name in FILTERS:
        if filters.get(name):
            sql, params = f"{sql} AND {name} = ?", [*params, filters[name]]
    return sql, params


def _spread(values: list[float]) -> dict[str, float] | None:
    return {"median": median(values), "max": max(values)} if values else None


def _group(rows: list[sqlite3.Row]) -> dict[str, Any]:
    measured = [json.loads(row["usage"]) for row in rows if row["usage"] not in (None, "{}")]
    cores = [u["peak_cores"] for u in measured if isinstance(u.get("peak_cores"), (int, float))]
    memory = [u["peak_memory"] for u in measured if isinstance(u.get("peak_memory"), int)]
    first = rows[0]
    peak_cores, peak_memory = _spread(cores), _spread(memory)
    return {"project": first["project"], "job": first["job"], "kind": first["kind"],
            "runs": len(rows), "measured": len(measured), "not_measured": len(rows) - len(measured),
            "no_cores": len(measured) - len(cores), "cores": peak_cores, "memory": peak_memory,
            "fits": fits(peak_cores and peak_cores["max"], peak_memory and peak_memory["max"]),
            "machines": sorted({row["worker"] for row in rows if row["worker"]}),
            "last_finished_at": first["finished_at"]}


def summary(conn: sqlite3.Connection, filters: dict[str, str | None], runs: int = DEFAULT_RUNS,
            every: bool = False) -> list[dict[str, Any]]:
    """One entry per project and job, the most recently run first."""
    where, params = _where(filters, every)
    rows = conn.execute(
        "SELECT project, job, kind, worker, usage, finished_at FROM ("
        "SELECT *, ROW_NUMBER() OVER (PARTITION BY project, job, kind "
        "ORDER BY finished_at DESC, seq DESC) AS nth "
        f"FROM jobs WHERE {where}) WHERE nth <= ? "
        "ORDER BY project, job, kind, finished_at DESC, seq DESC", (*params, runs)).fetchall()
    groups: dict[tuple, list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault((row["project"], row["job"], row["kind"]), []).append(row)
    found = [_group(group) for group in groups.values()]
    return sorted(found, key=lambda g: -(g["last_finished_at"] or 0))


def machines(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Each machine's cores and memory, from what it last reported."""
    out = {}
    for row in conn.execute("SELECT worker, load FROM workers ORDER BY worker"):
        load = json.loads(row["load"]) if row["load"] else {}
        out[row["worker"]] = {"cores": load.get("cores"),
                              "memory": (load.get("memory") or {}).get("total")}
    return out


def run(conn: sqlite3.Connection, job_id: str, now: float) -> dict[str, Any]:
    """One run: its peaks so far (or in all), its average cores and what it ran on."""
    job = st.require_job(conn, job_id)
    measured = job["usage"] or {}
    going = job["state"] != JobState.FINISHED.value
    ran = (now - job["started_at"]) if going and job["started_at"] else job["duration_s"]
    return {"job_id": job["job_id"], "project": job["project"], "job": job["job"],
            "kind": job["kind"], "worker": job["worker"], "state": job["state"],
            "outcome": job["outcome"], "run_s": ran, "usage": measured,
            "average_cores": average_cores(measured, ran)}
