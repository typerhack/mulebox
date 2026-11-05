"""Who is watching a job, and when nobody is, how long it has left (docs/design.md, Time limits).

Nothing here has a state of its own. The client lease says who is there: every watcher of a
detached job (`wait`, `events`, `logs -f`) renews it, as an attached `check` renews its own. A
detached job whose lease has run out is `unattended`, counted from that moment, so renewing the
lease is all it takes to get a job back and the count starts over.

- A running unattended job stops after `idle_s` without activity, a queued or running one after
  `max_s` whatever it does. A job never goes without warning: the idle clock of a job that was
  already quiet starts when it became unattended.
- Activity is what the worker reports (worker/activity.py). `active_at` is NULL while it cannot
  tell (an older worker, no /proc, a stage it cannot see into), and then only `max_s` applies:
  not knowing never counts as idle.
- A job with a client (`detached = 0`) has the lease rule of leases.py instead, a runner
  reservation has GitHub, and a cancelled job is ending anyway: none is ever unattended.

The limits belong to the coordinator's machine. The service writes them to `meta` when it
starts, so a `mulebox rpc` process and the read-only dashboard read the same values.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from mulebox.common.config import DEFAULT_UNATTENDED_IDLE_MIN, DEFAULT_UNATTENDED_MAX_HOURS
from mulebox.common.protocol import JobState
from mulebox.common.status import STOP_IDLE, STOP_LIMIT, STOP_QUEUED, STOP_TEXT, current_stage
from mulebox.coordinator.store import Store

_IDLE_KEY, _MAX_KEY = "unattended_idle_s", "unattended_max_s"
_OPEN = (JobState.QUEUED, JobState.STARTING, JobState.RUNNING)
_REPORTED = ("output_idle_s", "idle_s", "job_cpu_pct", "cpu_pct", "net_kib_s")
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


def unattended(job: dict[str, Any], now: float, limits: Limits) -> dict[str, Any] | None:
    """Why and when this job stops if nobody takes it back; None when it is not unattended."""
    lease = job["client_lease_until"]
    if (job["kind"] != "job" or not job["detached"] or job["cancel_requested"]
            or job["state"] not in _OPEN or lease is None or now < lease):
        return None
    reason = STOP_QUEUED if job["state"] == JobState.QUEUED else STOP_LIMIT
    stop_at = lease + limits.max_s
    if job["state"] == JobState.RUNNING and job["active_at"] is not None:
        quiet_end = max(job["active_at"], lease) + limits.idle_s
        if quiet_end < stop_at:
            reason, stop_at = STOP_IDLE, quiet_end
    return {"since": lease, "stop_reason": reason, "reason": STOP_TEXT[reason],
            "stop_at": stop_at, "left_s": max(0.0, round(stop_at - now, 1))}


def fields(job: dict[str, Any], now: float, limits: Limits) -> dict[str, Any]:
    """What a queue row adds: the `unattended` view, only when there is one."""
    view = unattended(job, now, limits)
    return {"unattended": view} if view else {}


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
    """What a `status` reply adds. `attended` is null for a job with nothing to attend."""
    lease = job["client_lease_until"]
    open_job = job["kind"] == "job" and job["state"] in _OPEN
    return {"attended": (lease is not None and now < lease) if open_job else None,
            "unattended": unattended(job, now, limits),
            "activity": activity(job, rows, now) if job["state"] in _OPEN[1:] else None}


def check_in_number(job: dict[str, Any], now: float) -> int:
    """How many `timeout_min` periods a running job has passed; 0 for any other job."""
    started = job["started_at"]
    if job["kind"] != "job" or job["state"] not in _OPEN[1:] or not started:
        return 0
    return int((now - started) // (job["timeout_min"] * 60.0))
