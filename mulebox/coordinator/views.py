"""How jobs appear on the wire: queue_ok job dicts, status_ok and result bodies."""

from typing import Any

from mulebox.common.protocol import JobState
from mulebox.coordinator import needs, workers

JOB_FIELDS = (
    "job_id", "project", "job", "branch", "client", "state", "outcome", "exit_code",
    "worker", "created_at", "started_at", "finished_at", "kind", "detached",
)


def job_dict(job: dict[str, Any], position: int | None = None,
             waiting: str | None = None) -> dict[str, Any]:
    """The public job dict (queue_ok entries, result body). `position` only when queued;
    `waiting_for` only when a queued job cannot start."""
    data = {name: job[name] for name in JOB_FIELDS}
    data["position"] = position if job["state"] == JobState.QUEUED else None
    if waiting:
        data["waiting_for"] = waiting
    return data


def waiting_for(conn: Any, job: dict[str, Any], now: float) -> str | None:
    """Why a queued agent job cannot start yet (needs.py); None for anything else."""
    if job["state"] != JobState.QUEUED or job["kind"] != "job":
        return None
    return needs.waiting_for(workers.listing(conn), job["needs"], now)


def status_body(job: dict[str, Any], position: int | None = None,
                waiting: str | None = None, **extra: Any) -> dict[str, Any]:
    """status_ok body: job_id, state, plus outcome/exit_code/duration_s when finished, position
    when queued, and `waiting_for` when a queued job cannot start."""
    body: dict[str, Any] = {"job_id": job["job_id"], "state": job["state"]}
    if job["state"] == JobState.FINISHED:
        body["outcome"] = job["outcome"]
        body["exit_code"] = job["exit_code"]
        body["duration_s"] = job["duration_s"]
    if job["state"] == JobState.QUEUED and position is not None:
        body["position"] = position
    if waiting:
        body["waiting_for"] = waiting
    body.update(extra)
    return body


def result_body(job: dict[str, Any]) -> dict[str, Any]:
    """The final `result` line of a watch stream: the job dict plus duration_s, and the
    fingerprint, so `mulebox wait` can tell whether the result is stale."""
    return {**job_dict(job), "duration_s": job["duration_s"], "fingerprint": job["fingerprint"]}


RESERVATION_FIELDS = ("kind", "pinned_worker", "runner", "run_url")


def reservation_dict(job: dict[str, Any], position: int | None = None) -> dict[str, Any]:
    """A runner_jobs entry: the public job dict plus the reservation fields."""
    return {**job_dict(job, position), **{name: job[name] for name in RESERVATION_FIELDS}}
