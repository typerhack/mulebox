"""How jobs appear on the wire: queue_ok job dicts, status_ok and result bodies."""

from typing import Any

from mulebox.common.protocol import JobState
from mulebox.coordinator import holds, needs, workers
from mulebox.coordinator.store import ACTIVE_STATES

JOB_FIELDS = (
    "job_id", "project", "job", "branch", "client", "state", "outcome", "exit_code",
    "worker", "created_at", "started_at", "finished_at", "kind", "detached", "client_os",
)


PAUSED_REASON = "paused by its owner; `mulebox resume <job>` lets it start"

STATUS_FIELDS = ("project", "job", "branch", "kind", "detached", "created_at", "started_at",
                 "finished_at", "log_size", "worker_version")


def job_dict(job: dict[str, Any], position: int | None = None,
             waiting: str | None = None) -> dict[str, Any]:
    """The public job dict (queue_ok entries, result body). `position` only when queued;
    `waiting_for` only when a queued job cannot start."""
    data = {name: job[name] for name in JOB_FIELDS}
    data["position"] = position if job["state"] == JobState.QUEUED else None
    if waiting:
        data["waiting_for"] = waiting
    if job["stop_reason"]:
        data["stop_reason"] = job["stop_reason"]
    data.update(controls(job))
    if job.get("ci_result"):  # how a GitHub job went, as its runner said (runners/diary.py)
        data["ci_result"] = job["ci_result"]
    return data


def controls(job: dict[str, Any]) -> dict[str, Any]:
    """The owner's controls on a job (job_control.py), only those that are on; `moved` is the
    side of a move by hand (front, before or after another job's place, line.py)."""
    found = {name: job[name] for name in ("paused", "boost", "priority") if job.get(name)}
    if job.get("pin_side"):
        found["moved"] = job["pin_side"]
    return found


def waiting_for(conn: Any, job: dict[str, Any], now: float, order: Any = None) -> str | None:
    """Why a queued agent job or upgrade cannot start yet (needs.py, upgrades.py); None for
    anything else. `order`: the line (line.py) when the caller read it already."""
    from mulebox.coordinator import upgrades  # upgrades -> views

    if job["state"] != JobState.QUEUED or job["kind"] not in ("job", upgrades.UPGRADE_KIND):
        return None
    if job["kind"] == upgrades.UPGRADE_KIND:
        return (f"it installs once the jobs running on {job['pinned_worker']} end; "
                "nothing new starts there meanwhile")
    if job.get("paused"):
        return PAUSED_REASON
    from mulebox.coordinator import project_pause

    if (until := project_pause.paused(conn, now).get(job["project"])) is not None:
        return project_pause.reason(job["project"], until)
    if holds.draining(conn, now):
        return holds.DRAIN_REASON
    if (upgrade := upgrades.ahead_of(conn, job, now, order)) is not None:
        return (f"an upgrade of {upgrade['pinned_worker']} to {upgrade['branch']} is ahead of it "
                f"({upgrade['job_id']})")
    return needs.waiting_for(workers.listing(conn), job["needs"], now)


def running_ahead(conn: Any, job: dict[str, Any]) -> dict[str, Any]:
    """The jobs on the machines now, for a queued job: why it has not started when nothing is
    wrong, which `waiting_for` does not say, and `branch_busy`, the one holding this job's
    branch, which it waits for even with a free slot. Nothing for a job in any other state."""
    if job["state"] != JobState.QUEUED:
        return {}
    marks = ", ".join("?" for _ in ACTIVE_STATES)
    rows = conn.execute(f"SELECT job_id, project, branch, kind FROM jobs WHERE state IN ({marks}) "
                        "ORDER BY seq", [state.value for state in ACTIVE_STATES]).fetchall()
    ahead: dict[str, Any] = {"running_ahead": [row["job_id"] for row in rows]}
    for row in rows:
        if (row["kind"], row["project"], row["branch"]) == ("job", job["project"], job["branch"]):
            ahead["branch_busy"] = row["job_id"]
    return ahead


def placement(fleet: list[dict[str, Any]], job: dict[str, Any], now: float) -> dict[str, Any]:
    """Where a waiting agent job may go, for the dashboard's per-machine view.

    `needs`, `can_run_on` (workers whose capabilities cover them, online or not: the same
    test `queue.claim` makes) and `waiting_for` (needs.py) when a queued job cannot start
    now. Nothing is an assignment: the queue is one line, and the first capable worker with
    a free slot takes the job. Empty for anything else: a running job has its `worker`, a
    runner reservation its `pinned_worker`.
    """
    if job["kind"] != "job" or job["state"] not in (JobState.QUEUED, JobState.UPLOADING):
        return {}
    out: dict[str, Any] = {"needs": job["needs"],
                           "can_run_on": [w["worker"] for w in needs.capable(fleet, job["needs"])]}
    reason = needs.waiting_for(fleet, job["needs"], now) if job["state"] == JobState.QUEUED else None
    if reason:
        out["waiting_for"] = reason
    return out


def status_body(job: dict[str, Any], position: int | None = None,
                waiting: str | None = None, **extra: Any) -> dict[str, Any]:
    """status_ok body: job_id, state, plus outcome/exit_code/duration_s when finished, position
    when queued, worker when active, and `waiting_for` when a queued job cannot start."""
    body: dict[str, Any] = {"job_id": job["job_id"], "state": job["state"]}
    if job["state"] == JobState.FINISHED:
        body["outcome"] = job["outcome"]
        body["exit_code"] = job["exit_code"]
        body["duration_s"] = job["duration_s"]
        if job["stop_reason"]:
            body["stop_reason"] = job["stop_reason"]
    if job["state"] == JobState.QUEUED and position is not None:
        body["position"] = position
    if job["state"] in ACTIVE_STATES:
        body["worker"] = job["worker"]
    if waiting:
        body["waiting_for"] = waiting
    body.update(controls(job))  # a worker pauses or boosts a running job from this
    body.update(extra)
    return body


def status_facts(job: dict[str, Any]) -> dict[str, Any]:
    """What a `status` reply adds, for someone who only has a job id."""
    return {name: job[name] for name in STATUS_FIELDS}


def result_body(job: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """The final `result` line of a watch stream: the job dict plus duration_s, the
    fingerprint, so `mulebox wait` can tell whether the result is stale, and `extra`."""
    return {**job_dict(job), "duration_s": job["duration_s"], "fingerprint": job["fingerprint"],
            "base_commit": job["base_commit"], **extra}


RESERVATION_FIELDS = ("kind", "pinned_worker", "runner", "run_url", "workflow")


def reservation_dict(job: dict[str, Any], position: int | None = None) -> dict[str, Any]:
    """A runner_jobs entry: the public job dict plus the reservation fields."""
    return {**job_dict(job, position), **{name: job[name] for name in RESERVATION_FIELDS}}
