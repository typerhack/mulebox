"""`mulebox check --from-stage <stage>`: which kept job a rerun takes over (docs/design.md, Rerun
from the failed stage).

At submit the coordinator looks for the last job of the same project, job name and branch that a
node still keeps (kept.py). Found, the new job goes to that node alone (as `--on`) and its claim
names the kept job in `reuses`; the worker checks the rest (worker/rerun.py). Not found, the job
runs from the start, and the reply says why, as a rerun is a saving and never a reason to fail.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.status import COMMAND, INSTALL, SETUP
from mulebox.coordinator import kept, workers
from mulebox.coordinator.errors import BadRequest

STAGES = (INSTALL, SETUP, COMMAND)  # the stages that run with a job's containers up
LOOK_BACK = 20  # jobs of the same name and branch looked at: more than any node keeps


def asked(body: dict[str, Any]) -> str | None:
    """`from_stage` of a submit, checked; None when not asked."""
    stage = body.get("from_stage")
    if stage is None:
        return None
    if stage not in STAGES:
        raise BadRequest(f"field 'from_stage' must be one of {', '.join(STAGES)}")
    return stage


def _candidates(conn: sqlite3.Connection, fields: dict[str, Any]) -> list[sqlite3.Row]:
    branch = fields.get("branch")
    where = "branch IS NULL" if branch is None else "branch = ?"
    args = (fields["project"], fields["job"], *(() if branch is None else (branch,)), LOOK_BACK)
    return conn.execute(
        f"SELECT job_id FROM jobs WHERE project = ? AND job = ? AND {where} "
        "AND kind = 'job' AND state = 'finished' ORDER BY seq DESC LIMIT ?", args).fetchall()


def plan(conn: sqlite3.Connection, fields: dict[str, Any], now: float) -> dict[str, Any]:
    """What a submit with `from_stage` becomes: `reuses` and the node, or a `note` saying why
    it runs from the start. `fields` gets `reuses` and `pinned_worker` when found."""
    stage, on = fields["from_stage"], fields.get("pinned_worker")
    held = kept.every(conn, now)
    for row in _candidates(conn, fields):
        if row["job_id"] not in held:
            continue
        worker, entry = held[row["job_id"]]
        node = workers.get(conn, worker)
        if node is None or not workers.is_online(node, now):
            return _from_start(fields, stage, f"{row['job_id']} is kept on {worker}, which is "
                               "offline")
        if on and on != worker:
            return _from_start(fields, stage, f"{row['job_id']} is kept on {worker}, not on {on}")
        fields.update(reuses=row["job_id"], pinned_worker=worker)
        return {"from_stage": stage, "reuses": row["job_id"], "node": worker,
                "kept_until": entry["until"]}
    return _from_start(fields, stage, "no failed job of this name and branch is kept on any "
                       "node (kept jobs go after the node's keep_failed_min, or when another job "
                       "of the branch starts)")


def _from_start(fields: dict[str, Any], stage: str, why: str) -> dict[str, Any]:
    fields["from_stage"] = None  # a plain job, as far as the node is concerned
    return {"from_stage": stage, "note": f"{why}, so this job runs from the start"}


def claim_fields(job: dict[str, Any]) -> dict[str, Any]:
    """What a claim of a rerun tells the worker; nothing for any other job."""
    if not job.get("reuses") or not job.get("from_stage"):
        return {}
    return {"reuses": job["reuses"], "from_stage": job["from_stage"]}


def status_fields(conn: sqlite3.Connection, job: dict[str, Any], now: float) -> dict[str, Any]:
    """`kept_until` and the node of a failed job that is kept; `reuses` and `from_stage` of a
    rerun."""
    out: dict[str, Any] = {}
    if job.get("reuses"):
        out.update(reuses=job["reuses"], from_stage=job.get("from_stage"))
    found = kept.find(conn, job["job_id"], now) if job.get("state") == "finished" else None
    if found is not None:
        out.update(kept_on=found[0], kept_until=found[1]["until"])
    return out
