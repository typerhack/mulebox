"""Job minutes: how long jobs ran, for `mulebox stats` and the dashboard's Statistics page.

The one measure is wall time on a machine, added up: two jobs side by side for ten minutes
count twenty. It is not CPU time, and not time saved. What counts:

- Agent jobs (`kind = 'job'`) from their start to the end of their command (`duration_s`, so
  cleanup after it is not counted), and GitHub runs (`kind = 'runner'`) from the slot being
  granted to its release. Upgrades are not jobs and are left out.
- A run still going counts up to now, and is also given apart (`running`), as it will grow.
- A run that ended with no recorded length (most often `interrupted` by a restart) is counted
  in `unknown`, never as zero and never guessed from `finished_at`.
- Frozen time is in it: the store keeps that a job is paused, not when it was.
- A run is cut at the edges of the range asked for, so a job across midnight counts on both
  days. The ranges come from the caller in epoch seconds: "today" is the caller's own day, as
  only it knows its time zone and summer time.

Job rows are kept for ever (retention.py), so the totals since the first job stay exact after
logs and stage rows are gone.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.protocol import JobState

KINDS = ("job", "runner")
GROUPS = ("project", "job", "client", "worker", "kind")  # also the filters
MAX_DAYS = 400
_GOING = (JobState.STARTING.value, JobState.RUNNING.value)
_END = "CASE WHEN state IN (?, ?) THEN ? ELSE started_at + duration_s END"


def _filters(filters: dict[str, str]) -> tuple[str, tuple]:
    sql, params = f"kind IN ({', '.join('?' * len(KINDS))}) AND started_at IS NOT NULL", KINDS
    for name in GROUPS:
        if filters.get(name):
            sql, params = f"{sql} AND {name} = ?", (*params, filters[name])
    return sql, params


def _ranged(start: float, end: float, now: float, where: str, params: tuple) -> tuple[str, tuple]:
    """Rows that ran inside [start, end), each with `ran`, its seconds inside it, and `going`,
    1 for a run still on. A run of unknown length (`ran` NULL) belongs where it started."""
    sql = (f"SELECT *, MAX(0, MIN({_END}, ?) - MAX(started_at, ?)) AS ran, "
           "state IN (?, ?) AS going FROM jobs "
           f"WHERE {where} AND started_at < ? AND ({_END} > ? OR ({_END} IS NULL AND started_at >= ?))")
    return sql, (*_GOING, now, end, start, *_GOING, *params, end, *_GOING, now, start,
                 *_GOING, now, start)


def _sums(conn: sqlite3.Connection, sql: str, params: tuple, group: str | None) -> list[sqlite3.Row]:
    key = f"{group} AS key, " if group else ""
    tail = f" GROUP BY {group} ORDER BY seconds DESC, key" if group else ""
    return conn.execute(
        f"SELECT {key}COALESCE(SUM(ran), 0) AS seconds, COUNT(ran) AS runs, "
        "COALESCE(SUM(CASE WHEN going THEN ran END), 0) AS running_seconds, "
        "COALESCE(SUM(going), 0) AS running, COUNT(*) - COUNT(ran) AS unknown "
        f"FROM ({sql}){tail}", params).fetchall()


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {"seconds": round(row["seconds"], 1), "runs": row["runs"], "running": row["running"],
            "running_seconds": round(row["running_seconds"], 1), "unknown": row["unknown"]}


def summary(conn: sqlite3.Connection, start: float, end: float, now: float,
            filters: dict[str, str] | None = None, by: tuple[str, ...] = GROUPS,
            day_starts: list[float] | None = None) -> dict[str, Any]:
    """Job minutes in [start, end) with `filters` (GROUPS names to one value each): the total,
    one breakdown per name in `by`, and per day when `day_starts` (ascending, the first at or
    after `start`) is given, each day ending at the next start or at `end`."""
    where, params = _filters(filters or {})
    sql, ranged = _ranged(start, end, now, where, params)
    first = conn.execute(f"SELECT MIN(started_at) FROM jobs WHERE {where}", params).fetchone()[0]
    days = []
    edges = [*(day_starts or []), end]
    for day, after in zip(edges, edges[1:]):
        day_sql, day_params = _ranged(day, after, now, where, params)
        days.append({"from": day, **_row(_sums(conn, day_sql, day_params, None)[0])})
    return {
        "from": start, "to": end, "now": now, "first_started_at": first,
        "filters": {name: value for name, value in (filters or {}).items() if value},
        "total": _row(_sums(conn, sql, ranged, None)[0]),
        "by": {group: [{"key": row["key"], **_row(row)} for row in _sums(conn, sql, ranged, group)]
               for group in by},
        "days": days,
    }


def choices(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Every value each filter can take, from the job history."""
    where, params = _filters({})
    return {group: [row[0] for row in conn.execute(
        f"SELECT DISTINCT {group} FROM jobs WHERE {where} AND {group} IS NOT NULL "
        f"ORDER BY {group}", params)] for group in GROUPS}
