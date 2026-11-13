"""The machines panel's view of the cluster: who is there and what is free.

`free_slots` in the workers table is what the worker last said in a claim, and a busy
worker does not claim, so that value goes stale; free slots are counted from the jobs
that hold a slot instead. An offline machine offers nothing, whatever it last reported, and a
draining one (`mulebox machine drain`) nothing new.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.status import left_mark
from mulebox.coordinator.workers import OFFLINE_AFTER_S, is_online

__all__ = ["AVAILABLE", "BUSY", "DRAINING", "OFFLINE", "OFFLINE_AFTER_S", "fingerprint", "machine",
           "readings", "snapshot", "with_readings"]

AVAILABLE, BUSY, DRAINING, OFFLINE = "available", "busy", "draining", "offline"
JOB_FIELDS = ("job_id", "project", "job", "kind")
READINGS = ("cpu_pct", "mem_pct")


def _job(job: dict[str, Any]) -> dict[str, Any]:
    """A job on a machine's row; `question` only when one is waiting for an answer."""
    view = job.get("question")
    return {**{field: job[field] for field in JOB_FIELDS}, **({"question": view} if view else {})}


def machine(worker: dict[str, Any], jobs: list[dict[str, Any]], now: float,
            host: str | None = None) -> dict[str, Any]:
    """A row. `host` is true on the row of the dashboard's own machine (the worker called `host`)
    and `version` is the mulebox the worker last reported, null before it did. `cpu_pct`, `mem_pct`, `cores` and the network in and out (`net_in_kib_s`,
    `net_out_kib_s`, M14.2) are what the worker last reported with a claim or heartbeat
    (`workers.load`, M5.3), null while it is offline or has not said; the
    dashboard's own machine gets its finer live sample on top (`with_readings`)."""
    slots = worker["slots"] if worker["slots"] is not None else max(len(jobs), 1)
    online = is_online(worker, now)
    draining = bool(worker.get("draining"))  # absent in a store not yet upgraded
    free = max(0, slots - len(jobs)) if online and not draining else 0
    state = (OFFLINE if not online else DRAINING if draining else AVAILABLE if free else BUSY)
    return {"name": worker["worker"], "state": state, "slots": slots, "free_slots": free,
            "capabilities": worker["capabilities"], "last_seen": worker["last_seen"],
            "host": host is not None and worker["worker"] == host, "version": worker.get("version"),
            # node settings (coordinator/node_settings.py): null priority before a worker reports
            "priority": (worker.get("settings") or {}).get("priority"),
            "settings_pending": bool(worker.get("wanted")),
            **_load(worker.get("load") if online else None),
            "jobs": [_job(job) for job in jobs]}


def _load(load: dict[str, Any] | None) -> dict[str, Any]:
    return {key: (load or {}).get(key)
            for key in ("cpu_pct", "mem_pct", "cores", "net_in_kib_s", "net_out_kib_s")}


def readings(sample: dict[str, Any] | None) -> dict[str, float | None]:
    """`cpu_pct` (average over the cores) and `mem_pct` from a metrics sample (hub.py)."""
    cpu, memory = (sample or {}).get("cpu"), (sample or {}).get("memory")
    return {
        "cpu_pct": round(sum(cpu) / len(cpu), 1) if cpu else None,
        "cores": len(cpu) if cpu else None,
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
             now: float, host: str | None = None) -> dict[str, Any]:
    """The whole panel. `active` is every job holding a slot; `host` the dashboard's machine."""
    rows = [machine(w, [j for j in active if j["worker"] == w["worker"]], now, host)
            for w in workers]
    return {"machines": rows, "total": len(rows),
            "online": sum(row["state"] != OFFLINE for row in rows),
            "free_slots": sum(row["free_slots"] for row in rows)}


def fingerprint(panel: dict[str, Any]) -> tuple:
    """What changes the panel. `last_seen` is left out: it moves every second. Readings
    count to the whole percent, so a live meter moves without a flood of events, and
    a waiting question's time left to the whole minute: browsers tick it."""
    whole = (lambda v: None if v is None else round(v))
    return tuple((row["name"], row["state"], row["slots"], row["free_slots"], row.get("version"),
                  row.get("priority"), row.get("settings_pending"),
                  tuple(row["capabilities"]), tuple((j["job_id"], left_mark(j)) for j in row["jobs"]),
                  *(whole(row.get(key)) for key in READINGS))
                 for row in panel["machines"]) + tuple(
        (n["kind"], n["level"], n["name"], n["text"]) for n in panel.get("notices", []))
