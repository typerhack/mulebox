"""The machines panel's view of the cluster: who is there and what is free.

`free_slots` in the workers table is what the worker last said in a claim, and a busy
worker does not claim, so that value goes stale; free slots are counted from the jobs
that hold a slot instead. An offline machine offers nothing, whatever it last reported.
"""

from __future__ import annotations

from typing import Any

OFFLINE_AFTER_S = 15.0  # workers poll every 1 s, or heartbeat every 3 s while busy
AVAILABLE, BUSY, OFFLINE = "available", "busy", "offline"
JOB_FIELDS = ("job_id", "project", "job", "kind")


def machine(worker: dict[str, Any], jobs: list[dict[str, Any]], now: float) -> dict[str, Any]:
    slots = worker["slots"] if worker["slots"] is not None else max(len(jobs), 1)
    online = now - worker["last_seen"] <= OFFLINE_AFTER_S
    free = max(0, slots - len(jobs)) if online else 0
    state = OFFLINE if not online else AVAILABLE if free else BUSY
    return {"name": worker["worker"], "state": state, "slots": slots, "free_slots": free,
            "capabilities": worker["capabilities"], "last_seen": worker["last_seen"],
            "jobs": [{field: job[field] for field in JOB_FIELDS} for job in jobs]}


def snapshot(workers: list[dict[str, Any]], active: list[dict[str, Any]],
             now: float) -> dict[str, Any]:
    """The whole panel. `active` is every job holding a slot."""
    rows = [machine(w, [j for j in active if j["worker"] == w["worker"]], now)
            for w in workers]
    return {"machines": rows, "total": len(rows),
            "online": sum(row["state"] != OFFLINE for row in rows),
            "free_slots": sum(row["free_slots"] for row in rows)}


def fingerprint(panel: dict[str, Any]) -> tuple:
    """What changes the panel. `last_seen` is left out: it moves every second."""
    return tuple((row["name"], row["state"], row["slots"], row["free_slots"],
                  tuple(row["capabilities"]), tuple(j["job_id"] for j in row["jobs"]))
                 for row in panel["machines"])
