"""Is a long job fine? The agent is asked, and only a stuck job with no answer is stopped.

A job never stops because nobody is watching it. Every `timeout_min` of a running job the agent
is asked whether all is well (`check_in`), and answers with `mulebox ok` or `mulebox cancel`.

- A job that is working goes on, answered or not, however long it takes. If the agent has gone,
  the result waits for it (reuse.py).
- A job is stuck when the oldest question has gone unanswered for a `timeout_min`, and the job
  has done nothing for a `timeout_min` or `idle_s`, whichever is shorter: no output, no CPU of
  its own, no traffic from its services. Only that stops it. An answer starts the count over.
  So `timeout_min` is the one setting a project needs: asked at 30 minutes, stopped at 60.
- Activity is what the worker reports (worker/activity.py). `active_at` is NULL while it cannot
  tell (no /proc, a stage it cannot see into). Not knowing never counts as idle, so such a job
  has only `max_s`, and still only with its question unanswered.
- A paused job (job_control.py) is not asked and never stopped; resuming it answers every
  question so far and counts as activity, so it is not stopped for its pause.
- A queued job is never stopped. A runner reservation belongs to GitHub, and a cancelled job is
  ending anyway.

The limits belong to the coordinator's machine. The service writes them to `meta` when it
starts, so a `mulebox rpc` process and the read-only dashboard read the same values.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from mulebox.common.config import DEFAULT_UNATTENDED_IDLE_MIN, DEFAULT_UNATTENDED_MAX_HOURS
from mulebox.common.protocol import JobState
from mulebox.common.status import STOP_STUCK, STOP_TEXT, STOP_UNKNOWN, current_stage
from mulebox.coordinator.store import Store

_IDLE_KEY, _MAX_KEY = "unattended_idle_s", "unattended_max_s"
_RUNNING = (JobState.STARTING, JobState.RUNNING)
_REPORTED = ("output_idle_s", "idle_s", "job_cpu_pct", "cpu_pct", "net_kib_s",
             "last_line")
LIMITS_BY_COORDINATOR = "coordinator"  # in claim_ok: the worker sets no runtime limit of its own


@dataclass(frozen=True)
class Limits:
    idle_s: float = DEFAULT_UNATTENDED_IDLE_MIN * 60.0
    max_s: float = DEFAULT_UNATTENDED_MAX_HOURS * 3600.0


def save_limits(store: Store, limits: Limits) -> None:
    with store.write() as conn:
        conn.executemany("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                         ((_IDLE_KEY, str(limits.idle_s)), (_MAX_KEY, str(limits.max_s))))


def read_limits(conn: sqlite3.Connection) -> Limits:
    """What the service saved; the defaults before it first ran."""
    rows = dict(conn.execute("SELECT key, value FROM meta WHERE key IN (?, ?)",
                             (_IDLE_KEY, _MAX_KEY)).fetchall())
    defaults = Limits()
    return Limits(float(rows.get(_IDLE_KEY, defaults.idle_s)),
                  float(rows.get(_MAX_KEY, defaults.max_s)))


def question(job: dict[str, Any], now: float, limits: Limits) -> dict[str, Any] | None:
    """The oldest unanswered question of a running job, and when the job stops if it stays
    stuck; None when nothing is waiting for an answer."""
    started = job["started_at"]
    if (job["kind"] != "job" or job["cancel_requested"] or job["state"] not in _RUNNING
            or not started or job.get("paused")):
        return None  # a paused job is still on purpose: resuming answers what was asked
    number = job["check_in_ok"] + 1
    period = job["timeout_min"] * 60.0
    asked = started + number * period
    if now < asked:
        return None
    if job["active_at"] is None:
        reason, stop_at = STOP_UNKNOWN, max(asked + period, started + limits.max_s)
    else:
        quiet = min(period, limits.idle_s)
        reason, stop_at = STOP_STUCK, max(asked + period, job["active_at"] + quiet)
    return {"number": number, "since": asked, "stop_reason": reason, "reason": STOP_TEXT[reason],
            "stop_at": stop_at, "left_s": max(0.0, round(stop_at - now, 1))}


def fields(job: dict[str, Any], now: float, limits: Limits) -> dict[str, Any]:
    """What a queue row adds: the `question` view, only when there is one."""
    view = question(job, now, limits)
    return {"question": view} if view else {}


def answer(job: dict[str, Any], now: float) -> int:
    """`check_in_ok` after the agent said all is well: every question asked so far is settled."""
    return max(job["check_in_ok"], check_in_number(job, now))


def activity(job: dict[str, Any], rows: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """A running job for someone deciding whether it is stuck. The readings are the worker's
    last report, null when it could not measure them; CPU and network are the machine's."""
    report = job["activity"] or {}
    started = job["started_at"]
    return {"elapsed_s": round(now - started, 1) if started else None,
            "stage": current_stage(job, rows),
            **{name: report.get(name) for name in _REPORTED}}


def status_fields(job: dict[str, Any], rows: list[dict[str, Any]], now: float,
                  limits: Limits) -> dict[str, Any]:
    """What a `status` reply adds."""
    return {"question": question(job, now, limits),
            "activity": activity(job, rows, now) if job["state"] in _RUNNING else None}


def check_in_number(job: dict[str, Any], now: float) -> int:
    """How many `timeout_min` periods a running job has passed; 0 for any other job."""
    started = job["started_at"]
    if job["kind"] != "job" or job["state"] not in _RUNNING or not started:
        return 0
    return int((now - started) // (job["timeout_min"] * 60.0))
