"""Requests from workers: claim, heartbeat (lease worker), job_update, log_chunk, steps, result.

Every message about a job must carry the job's current `attempt_id`; a stale attempt gets
`conflict`. Runner reservations have no attempt: only `heartbeat` applies to them (it
renews their worker lease); they end through `release` (runner_api.py). A valid message renews the worker lease. Replies to job messages carry
`cancel: true` when the worker should stop (cancel requested, or the job already ended).
"""

from typing import Any

from mulebox.common.protocol import JobState, Message, MessageType, Outcome
from mulebox.coordinator import leases, queue, recovery, steps, workers
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.queue import RUNNER_KIND
from mulebox.coordinator.views import status_body


def claim(req: Request) -> Message:
    worker = v.text(req.body, "worker")
    capabilities = v.strings(req.body, "capabilities")
    free_slots = v.integer(req.body, "free_slots", low=0)
    if req.body.get("restarted") is True:  # first claim after a worker (re)start
        recovery.release_worker(req.store, worker, req.now)
    job = queue.claim(req.store, worker, capabilities, free_slots, req.cluster_slots,
                      now=req.now, toolchains=v.versions_by_name(req.body, "toolchains"),
                      version=v.text(req.body, "version", None))
    if job is None:
        return req.reply(MessageType.CLAIM_NONE, {})
    return req.reply(MessageType.CLAIM_OK, queue.claim_body(job))


def _status(req: Request, job: dict[str, Any], **extra: Any) -> Message:
    cancel = bool(job["cancel_requested"]) or job["state"] == JobState.FINISHED
    return req.reply(MessageType.STATUS_OK, status_body(job, cancel=cancel, **extra))


def _current_job(conn: Any, req: Request, reservations: bool = False) -> dict[str, Any]:
    job = st.require_job(conn, v.job_id(req.body))
    if job["kind"] == RUNNER_KIND:
        if not reservations:
            raise BadRequest(f"job {job['job_id']} is a runner reservation; use release")
        return job
    leases.check_attempt(job, req.body.get("attempt_id"))
    return job


def heartbeat(req: Request) -> Message:
    with req.store.write() as conn:
        job = _current_job(conn, req, reservations=True)
        job = leases.renew_worker_in(conn, job, req.now)
        workers.touch(conn, job["worker"], req.now)
    return _status(req, job)


def job_update(req: Request) -> Message:
    new = JobState(v.text(req.body, "state"))
    if new is JobState.FINISHED:
        raise BadRequest("report the end of a job with a result message")
    with req.store.write() as conn:
        job = _current_job(conn, req)
        job = st.transition(conn, job, new)
        job = leases.renew_worker_in(conn, job, req.now)
    return _status(req, job)


def log_chunk(req: Request) -> Message:
    offset = v.integer(req.body, "offset", low=0)
    data = req.body.get("data")
    if not isinstance(data, str):
        raise BadRequest("field 'data' must be a string")
    with req.store.write() as conn:
        job = _current_job(conn, req)
        if job["state"] not in st.ACTIVE_STATES:
            raise Conflict(f"job {job['job_id']} is {job['state']}; log chunks are not accepted")
        size = req.staging.append_log(job["job_id"], offset, data.encode("utf-8"))
        st.update_job(conn, job["job_id"], log_size=size)
        job = leases.renew_worker_in(conn, st.require_job(conn, job["job_id"]), req.now)
    return _status(req, job, log_size=size)


def report_steps(req: Request) -> Message:
    rows = steps.rows_from(req.body)
    with req.store.write() as conn:
        job = _current_job(conn, req)
        steps.save(conn, job["job_id"], rows)
    return _status(req, job)


def result(req: Request) -> Message:
    outcome = Outcome(v.text(req.body, "outcome"))
    exit_code = v.integer(req.body, "exit_code", None)
    duration_s = v.number(req.body, "duration_s", None)
    with req.store.write() as conn:
        job = _current_job(conn, req)
        if job["state"] == JobState.FINISHED:
            raise Conflict(f"job {job['job_id']} already finished ({job['outcome']})")
        job = st.finish(conn, job, outcome, req.now, exit_code=exit_code, duration_s=duration_s)
    req.staging.remove_upload(job["job_id"])
    return _status(req, job)
