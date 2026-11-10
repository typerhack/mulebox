"""Requests about runner reservations: reserve, acquire, release, runner_jobs.

Wire bodies: docs/interfaces-m3.md (Wire messages). The logic lives in reservations.py;
this module validates request bodies and builds the replies.
"""

from typing import Any

from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.coordinator import reservations as rs
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.views import reservation_dict, status_body


def _ident(body: dict[str, Any], name: str) -> str:
    """A GitHub run number: a non-empty string or a non-negative integer, as a string."""
    value = body.get(name)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return str(value)
    return v.text(body, name)


def reserve(req: Request) -> Message:
    body = req.body
    repository = v.text(body, "repository")
    worker = rs.check_name(body.get("worker"), "worker")
    runner = rs.check_name(body.get("runner"), "runner")
    job = v.text(body, "job")
    run_id, run_attempt = _ident(body, "run_id"), _ident(body, "run_attempt")
    fields = {
        "pinned_worker": worker,
        "project": rs.project_name(repository),
        "job": job,
        "runner": runner,
        "branch": v.text(body, "branch", None),
        "run_url": v.text(body, "run_url", None),
        "idempotency_key": v.text(
            body, "idempotency_key", rs.default_key(repository, run_id, run_attempt, job, runner)
        ),
    }
    with req.store.write() as conn:
        found = rs.create(conn, fields, req.now)
    return req.reply(MessageType.SUBMIT_OK, {"job_id": found["job_id"], "state": found["state"]})


def acquire(req: Request) -> Message:
    with req.store.write() as conn:
        job = rs.require(conn, v.job_id(req.body))
        job = rs.try_grant(conn, job, req.now, req.cluster_slots)
        place = rs.ahead(conn, job, req.now) + 1 if job["state"] == JobState.QUEUED else None
    return req.reply(MessageType.STATUS_OK, status_body(job, place))


def release(req: Request) -> Message:
    try:
        outcome = Outcome(v.text(req.body, "outcome"))
    except ValueError:
        raise BadRequest("field 'outcome' is not a known outcome") from None
    with req.store.write() as conn:
        job = rs.release(conn, rs.require(conn, v.job_id(req.body)), outcome, req.now,
                         v.ci_result(req.body))
    return req.reply(MessageType.STATUS_OK, status_body(job))


def runner_jobs(req: Request) -> Message:
    worker = rs.check_name(req.body.get("worker"), "worker")
    with req.store.read() as conn:
        rows = rs.unfinished(conn, worker)
    return req.reply(MessageType.QUEUE_OK, {"jobs": [reservation_dict(job) for job in rows]})
