"""What the client says about reruns (docs/design.md, Rerun from the failed stage): what a
`--from-stage` submit became, and, under a failed job's summary, how long it is kept and the
command that reruns it."""

from __future__ import annotations

import time
from typing import Any

from mulebox.client.job_body import RUN_JOB_NAME

STAGES = ("install", "setup", "command")  # coordinator/rerun.py


def submitted(body: dict[str, Any], stage: str | None) -> str | None:
    """The line for a submit reply of a `--from-stage` job, or None for any other."""
    if not stage:
        return None
    said = body.get("rerun")
    if not isinstance(said, dict):
        return ("the node's mulebox cannot rerun from a stage (it is older than 1.46), so this "
                "job runs from the start; `mulebox setup <host>` upgrades it")
    if said.get("reuses"):
        return (f"rerun from {stage} in the containers of {said['reuses']}, kept on "
                f"{said.get('node')}")
    return str(said.get("note") or "nothing is kept for a rerun, so this job runs from the start")


def kept_lines(job: str | None, result: dict[str, Any], now: float | None = None) -> list[str]:
    """Under a failed job's summary: how long its containers stay, and the rerun command."""
    until = result.get("kept_until")
    if not isinstance(until, (int, float)) or isinstance(until, bool):
        return []
    left = max(0, round((until - (time.time() if now is None else now)) / 60))
    stage = result.get("stage") if result.get("stage") in STAGES else "command"
    command = (f"mulebox run --from-stage {stage} -- <command>" if job == RUN_JOB_NAME
               else f"mulebox check{f' {job}' if job and job != 'check' else ''} --from-stage "
               f"{stage}")
    where = f" on {result['kept_on']}" if result.get("kept_on") else ""
    return [f"its containers are kept{where} for {left} min: after a fix, `{command}` reruns it "
            f"from {stage}, with no new images, services or stages before it"]
