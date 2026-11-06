"""The machines panel's view of the cluster: who is there and what is free.

`free_slots` in the workers table is what the worker last said in a claim, and a busy
worker does not claim, so that value goes stale; free slots are counted from the jobs
that hold a slot instead. An offline machine offers nothing, whatever it last reported.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.status import left_mark
from mulebox.coordinator.workers import OFFLINE_AFTER_S, is_online

__all__ = ["AVAILABLE", "BUSY", "OFFLINE", "OFFLINE_AFTER_S", "fingerprint", "machine",
           "readings", "snapshot", "with_readings"]

AVAILABLE, BUSY, OFFLINE = "available", "busy", "offline"
JOB_FIELDS = ("job_id", "project", "job", "kind")
READINGS = ("cpu_pct", "mem_pct")


def _job(job: dict[str, Any]) -> dict[str, Any]:
    """A job on a machine's row; `question` only when one is waiting for an answer."""
    view = job.get("question")
    return {**{field: job[field] for field in JOB_FIELDS}, **({"question": view} if view else {})}


def machine(worker: dict[str, Any], jobs: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """A row. `cpu_pct` and `mem_pct` are null until something measures the machine: today
    only the machine the dashboard runs on (`with_readings`); other workers report theirs
    in M5.3, and the page needs no change for that."""
    slots = worker["slots"] if worker["slots"] is not None else max(len(jobs), 1)
    online = is_online(worker, now)
    free = max(0, slots - len(jobs)) if online else 0
    state = OFFLINE if not online else AVAILABLE if free else BUSY
    return {"name": worker["worker"], "state": state, "slots": slots, "free_slots": free,
            "capabilities": worker["capabilities"], "last_seen": worker["last_seen"],
            "cpu_pct": None, "mem_pct": None,
            "jobs": [_job(job) for job in jobs]}


def readings(sample: dict[str, Any] | None) -> dict[str, float | None]:
    """`cpu_pct` (average over the cores) and `mem_pct` from a metrics sample (hub.py)."""
    cpu, memory = (sample or {}).get("cpu"), (sample or {}).get("memory")
    return {
        "cpu_pct": round(sum(cpu) / len(cpu), 1) if cpu else None,
        "mem_pct": round(memory["used"] / memory["total"] * 100, 1)
        if memory and memory.get("total") else None,
    }


def with_readings(panel: dict[str, Any], name: str | None,
                  sample: dict[str, Any] | None) -> dict[str, Any]:
    """`panel` with the row called `name` carrying the readings of `sample`, in place.
    A name the panel does not list (no worker on the dashboard's machine) changes nothing."""
    for row in panel["machines"]:
        if row["name"] == name:
            row.update(readings(sample))
    return panel


def snapshot(workers: list[dict[str, Any]], active: list[dict[str, Any]],
             now: float) -> dict[str, Any]:
    """The whole panel. `active` is every job holding a slot."""
    rows = [machine(w, [j for j in active if j["worker"] == w["worker"]], now)
            for w in workers]
    return {"machines": rows, "total": len(rows),
            "online": sum(row["state"] != OFFLINE for row in rows),
            "free_slots": sum(row["free_slots"] for row in rows)}


def fingerprint(panel: dict[str, Any]) -> tuple:
    """What changes the panel. `last_seen` is left out: it moves every second. Readings
    count to the whole percent, so a live meter moves without a flood of events, and
    a waiting question's time left to the whole minute: browsers tick it."""
    whole = (lambda v: None if v is None else round(v))
    return tuple((row["name"], row["state"], row["slots"], row["free_slots"],
                  tuple(row["capabilities"]), tuple((j["job_id"], left_mark(j)) for j in row["jobs"]),
                  *(whole(row.get(key)) for key in READINGS))
                 for row in panel["machines"])
