"""What `check`, `wait`, `events` and `status` say of a job that looks stuck (common/stuck.py).

The verdict's own sentence comes from the coordinator, so the dashboard and every command say
the same; this adds who it is about and what can be done.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.units import duration

GOES_ON = ("slow", "waiting")  # it still moves, or says why it does not


def next_steps(job_id: str, verdict: str | None) -> str:
    if verdict in GOES_ON:
        return (f"It goes on by itself; to look: mulebox logs {job_id}, "
                f"to stop it: mulebox cancel {job_id}")
    return (f"Do not send it again. Look: mulebox logs {job_id}; then keep waiting, or stop it: "
            f"mulebox cancel {job_id}")


def stuck_line(job_id: str, seen: dict[str, Any], prefix: str = "") -> str:
    text = str(seen.get("text") or "").strip()
    return f"{prefix}job {job_id}: {text} {next_steps(job_id, seen.get('verdict'))}"


def moving_line(job_id: str, moving: dict[str, Any]) -> str:
    stage = f" in stage {moving['stage']}" if moving.get("stage") else ""
    return f"job {job_id} is working again{stage}"


def status_line(job_id: str, seen: dict[str, Any] | None) -> str | None:
    """`mulebox status`: the verdict when there is one to tell, None while it works."""
    if not isinstance(seen, dict) or seen.get("verdict") in (None, "working"):
        return None
    limit = seen.get("limit_s")
    after = f" (after {duration(limit)} with nothing moving)" if limit else ""
    return f"  {seen['verdict']}{after}: {stuck_line(job_id, seen)}"
