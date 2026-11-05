"""Request dispatch for every non-streaming request (docs/interfaces-m1.md, Wire usage).

`handle` is pure: no stdin/stdout, the time comes in as `now`. The worker's local link
calls it directly; `rpc` calls it for one decoded line. Every failure becomes an `error`
reply with code not_found, bad_request, conflict, too_large or internal.
"""

from collections.abc import Callable
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, Message, MessageType, ProtocolError
from mulebox.coordinator import (
    attendance,
    leases,
    needs,
    projects,
    queue,
    runner_api,
    steps,
    usual,
    worker_api,
    workers,
)
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request, error_message
from mulebox.coordinator.errors import BadRequest, CoordinatorError, NoWorker
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.views import (
    job_dict,
    running_ahead,
    status_body,
    status_facts,
    waiting_for,
)
from mulebox.version import get_version

_log = get_logger(__name__)
DEFAULT_TIMEOUT_MIN = 30
MAX_TIMEOUT_MIN = 240


def handle(store: Store, staging: Staging, msg: Message, now: float, *,
           cluster_slots: int = 1, dashboard: dict[str, Any] | None = None) -> Message:
    """Answer one request message. Never raises for a bad request; replies `error`."""
    try:
        handler = _HANDLERS.get(msg.type)
        if handler is None:
            raise BadRequest(f"'{msg.type}' is not a request the coordinator answers here")
        return handler(Request(store, staging, msg, now, cluster_slots, dashboard))
    except CoordinatorError as exc:
        return error_message(msg.request_id, exc.code, str(exc))
    except (ProtocolError, ValueError) as exc:
        return error_message(msg.request_id, "bad_request", str(exc))
    except Exception as exc:  # noqa: BLE001 - a request must never crash the caller
        _log.exception("internal error handling %s", msg.type)
        return error_message(msg.request_id, "internal", f"internal error: {type(exc).__name__}")


def submit(req: Request) -> Message:
    body = req.body
    fields = {
        "project": v.text(body, "project"),
        "job": v.text(body, "job"),
        "argv": v.strings(body, "argv", non_empty=True),
        "idempotency_key": v.text(body, "idempotency_key"),
        "fingerprint": v.text(body, "fingerprint"),
        "base_commit": v.text(body, "base_commit"),
        "client": v.text(body, "client"),
        "branch": v.text(body, "branch", None),
        "setup": v.text(body, "setup", None),
        "toolchain": v.string_map(body, "toolchain"),
        "env": v.string_map(body, "env"),
        "env_order": v.strings(body, "env_order"),
        "needs": needs.required(v.strings(body, "needs"), v.string_map(body, "env")),
        "timeout_min": v.integer(body, "timeout_min", DEFAULT_TIMEOUT_MIN, 1, MAX_TIMEOUT_MIN),
        "detached": v.flag(body, "detached"),
    }
    with req.store.write() as conn:
        job = st.find_by_key(conn, fields["idempotency_key"])
        if job is None:
            refused = needs.refusal(workers.listing(conn), fields["needs"])
            if refused:
                raise NoWorker(refused)
            job = st.insert_job(conn, {
                **fields, "job_id": new_id("job"), "state": JobState.UPLOADING,
                "created_at": req.now, "client_lease_until": req.now + leases.CLIENT_LEASE_S,
            })
        left = _unattended_in(conn, fields["project"], req.now)
    # `detached` is echoed: a client must not leave a job behind that a coordinator too old to
    # know the flag would cancel 5 minutes later.
    return req.reply(MessageType.SUBMIT_OK, {"job_id": job["job_id"], "state": job["state"],
                                             "detached": job["detached"], "unattended": left,
                                             "dashboard": req.dashboard})


def _unattended_in(conn: Any, project: str, now: float) -> list[dict[str, Any]]:
    """This project's jobs nobody is watching, for the warning a submitting client prints."""
    limits = attendance.read_limits(conn)
    rows = st.select_jobs(conn, "project = ? AND detached = 1 AND state != ?",
                          (project, JobState.FINISHED.value))
    return [{**job_dict(job), **fields} for job in rows
            if (fields := attendance.fields(job, now, limits))]


def status(req: Request) -> Message:
    with req.store.read() as conn:
        job = st.require_job(conn, v.job_id(req.body))
        place = queue.position(conn, job)
        reason = waiting_for(conn, job, req.now)
        rows = steps.for_job(conn, job["job_id"])
        typical = usual.for_job(conn, job)
        failed = steps.failed_stage(conn, job)
        limits = attendance.read_limits(conn)
        ahead = running_ahead(conn, job)
    return req.reply(MessageType.STATUS_OK, {
        **status_body(job, place, reason, steps=rows, usual=typical,
                      **usual.estimate(job, typical), **ahead, **failed),
        **status_facts(job), **attendance.status_fields(job, rows, req.now, limits),
        "dashboard": req.dashboard})


def cancel(req: Request) -> Message:
    with req.store.write() as conn:
        before = st.require_job(conn, v.job_id(req.body))
        job = leases.cancel(conn, before, req.now)
    if before["state"] != JobState.FINISHED and job["state"] == JobState.FINISHED:
        req.staging.remove_upload(job["job_id"])
    return req.reply(MessageType.STATUS_OK, status_body(job, cancel_requested=job["cancel_requested"]))


def heartbeat(req: Request) -> Message:
    lease = req.body.get("lease")
    if lease == "worker":
        return worker_api.heartbeat(req)
    if lease != "client":
        raise BadRequest("field 'lease' must be 'client' or 'worker'")
    job = leases.renew_client(req.store, v.job_id(req.body), req.now)
    return req.reply(MessageType.STATUS_OK, status_body(job))


def queue_list(req: Request) -> Message:
    limit = v.integer(req.body, "limit", queue.DEFAULT_FINISHED_LIMIT, 0, 1000)
    with req.store.read() as conn:
        limits = attendance.read_limits(conn)
        rows = [{**job_dict(job, pos, waiting_for(conn, job, req.now)),
                 **attendance.fields(job, req.now, limits)}
                for job, pos in queue.listing(conn, limit)]
    return req.reply(MessageType.QUEUE_OK, {"jobs": rows, "dashboard": req.dashboard})


def project_list(req: Request) -> Message:
    with req.store.read() as conn:
        rows = projects.listing(conn)
    return req.reply(MessageType.PROJECTS_OK, {"projects": rows})


def machine_list(req: Request) -> Message:
    with req.store.read() as conn:
        rows = [workers.report(worker, req.now) for worker in workers.listing(conn)]
    return req.reply(MessageType.MACHINES_OK, {"version": get_version(), "workers": rows,
                                               "dashboard": req.dashboard})


def logs(req: Request) -> Message:
    offset = v.integer(req.body, "offset", low=0)
    with req.store.read() as conn:
        job = st.require_job(conn, v.job_id(req.body))
    return req.reply(MessageType.LOG_CHUNK, log_chunk_body(req.staging, job, offset))


def log_chunk_body(staging: Staging, job: dict[str, Any], offset: int) -> dict[str, Any]:
    """log_chunk body from `offset`: `data`, `next_offset`, and `eof` once the job is
    finished and no bytes follow. Pass a job read before the log, so a finished state
    means every log byte is already stored."""
    data = staging.read_log(job["job_id"], offset)
    next_offset = offset + len(data)
    eof = job["state"] == JobState.FINISHED and next_offset >= staging.log_size(job["job_id"])
    return {
        "job_id": job["job_id"], "offset": offset, "next_offset": next_offset,
        "data": data.decode("utf-8", errors="replace"), "eof": eof, "state": job["state"],
    }


_HANDLERS: dict[MessageType, Callable[[Request], Message]] = {
    MessageType.SUBMIT: submit,
    MessageType.STATUS: status,
    MessageType.CANCEL: cancel,
    MessageType.HEARTBEAT: heartbeat,
    MessageType.QUEUE: queue_list,
    MessageType.PROJECTS: project_list,
    MessageType.MACHINES: machine_list,
    MessageType.LOGS: logs,
    MessageType.CLAIM: worker_api.claim,
    MessageType.JOB_UPDATE: worker_api.job_update,
    MessageType.LOG_CHUNK: worker_api.log_chunk,
    MessageType.STEPS: worker_api.report_steps,
    MessageType.RESULT: worker_api.result,
    MessageType.RESERVE: runner_api.reserve,
    MessageType.ACQUIRE: runner_api.acquire,
    MessageType.RELEASE: runner_api.release,
    MessageType.RUNNER_JOBS: runner_api.runner_jobs,
}
