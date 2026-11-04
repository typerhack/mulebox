"""The `job_steps` table: one row per stage of a job, as its worker reports them.

A row is replaced whole, by (job_id, seq), so a report sent twice changes nothing and a stage
is written when it starts and again when it ends. Raw logs stay in files (staging.py). A
job that ended without its worker, by a lease or a restart, keeps its last row open.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.status import MAX_FAILING_LINE, STAGES
from mulebox.coordinator import validate as v
from mulebox.coordinator.errors import BadRequest

MAX_ROWS = 64  # in one report; far more than a job has stages
COLUMNS = ("seq", "stage", "started_at", "finished_at", "exit_code", "bytes_downloaded",
           "failing_line")


def _row(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BadRequest("every step must be an object")
    stage = v.text(raw, "stage")
    if stage not in STAGES:
        raise BadRequest(f"unknown stage {stage!r}")
    line = v.text(raw, "failing_line", None)
    return {
        "seq": v.integer(raw, "seq", low=0), "stage": stage,
        "started_at": v.number(raw, "started_at"),
        "finished_at": v.number(raw, "finished_at", None),
        "exit_code": v.integer(raw, "exit_code", None),
        "bytes_downloaded": v.integer(raw, "bytes_downloaded", None, 0),
        "failing_line": line[:MAX_FAILING_LINE] if line else None,
    }


def rows_from(body: dict[str, Any]) -> list[dict[str, Any]]:
    """The checked `steps` of a report."""
    rows = body.get("steps")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        raise BadRequest(f"field 'steps' must be a list of at most {MAX_ROWS} rows")
    return [_row(raw) for raw in rows]


def save(conn: sqlite3.Connection, job_id: str, rows: list[dict[str, Any]]) -> None:
    names = ", ".join(COLUMNS)
    marks = ", ".join("?" for _ in COLUMNS)
    conn.executemany(f"INSERT OR REPLACE INTO job_steps (job_id, {names}) VALUES (?, {marks})",
                     [(job_id, *(row[name] for name in COLUMNS)) for row in rows])


def for_job(conn: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    """A job's rows in the order they happened."""
    names = ", ".join(COLUMNS)
    cursor = conn.execute(f"SELECT {names} FROM job_steps WHERE job_id = ? ORDER BY seq",
                          (job_id,))
    return [dict(row) for row in cursor]
