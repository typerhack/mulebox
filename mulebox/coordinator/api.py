"""Request dispatch for every non-streaming request (docs/interfaces-m1.md, Wire usage).

`handle` is pure: no stdin/stdout, the time comes in as `now`. The worker's local link
calls it directly; `rpc` calls it for one decoded line. Every failure becomes an `error`
reply with code not_found, bad_request, conflict, too_large or internal.
"""

from collections.abc import Callable
from typing import Any

from mulebox.common.ids import new_id
from mulebox.common.log import get_logger
from mulebox.common import take_paths
from mulebox.common.protocol import JobState, Message, MessageType, ProtocolError
from mulebox.coordinator import (
    attendance,
    clients,
    holds,
    leases,
    machine_api,
    needs,
    projects,
    queue,
    reuse,
    runner_api,
    steps,
    taken,
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
from mulebox.coordinator.reach import reach
from mulebox.coordinator.views import (
    job_dict,
    result_body,
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


def _take(body: dict[str, Any]) -> list[str]:
    try:
        return list(take_paths.checked(v.strings(body, "take")))
    except ValueError as exc:
        raise BadRequest(str(exc)) from None


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
        "client_os": (v.text(body, "client_os", None) or "")[:20] or None,
        "branch": v.text(body, "branch", None),
        "setup": v.text(body, "setup", None),
        "install": v.text(body, "install", None),
        "toolchain": v.string_map(body, "toolchain"),
        "env": v.string_map(body, "env"),
        "env_order": v.strings(body, "env_order"),
        "needs": needs.required(v.strings(body, "needs"), v.string_map(body, "env")),
        "timeout_min": v.integer(body, "timeout_min", DEFAULT_TIMEOUT_MIN, 1, MAX_TIMEOUT_MIN),
        "detached": v.flag(body, "detached"),
        "take": _take(body),
    }
    said = clients.fields(body)
    with req.store.write() as conn:
        if said:  # first, as a repeat answered from an earlier result returns early
            clients.seen(conn, fields["client"], said, req.now)
        job = st.find_by_key(conn, fields["idempotency_key"])
        same = reuse.earlier(conn, fields, req.now) if job is None and v.flag(body, "reuse") else None
        if same is not None:
            return _already(req, conn, same, fields)
        if job is None:
            refused = needs.refusal(workers.listing(conn), fields["needs"])
            if refused:
                raise NoWorker(refused)
            job = st.insert_job(conn, {
                **fields, "job_id": new_id("job"), "state": JobState.UPLOADING,
                "created_at": req.now, "client_lease_until": req.now + leases.CLIENT_LEASE_S,
            })
        news = _news(conn, fields["project"], req.now)
    # `detached` is echoed: a client must not leave a job behind that a coordinator too old to
    # know the flag would cancel 5 minutes later.
    return req.reply(MessageType.SUBMIT_OK, {"job_id": job["job_id"], "state": job["state"],
                                             "detached": job["detached"], **news,
                                             "dashboard": req.dashboard})


def _already(req: Request, conn: Any, job: dict[str, Any], fields: dict[str, Any]) -> Message:
    """`submit` found the same job (reuse.py): no new job, and this one's id and result."""
    reuse.told(conn, [job] if job["state"] == JobState.FINISHED else [], req.now)
    return req.reply(MessageType.SUBMIT_OK, {
        "job_id": job["job_id"], "state": job["state"], "detached": fields["detached"],
        "already": result_body(job), **_news(conn, fields["project"], req.now),
        "dashboard": req.dashboard})


def _news(conn: Any, project: str, now: float) -> dict[str, Any]:
    """What a client from this project has to hear: questions waiting for an answer, and results
    of jobs that finished without it. Telling a result here is what marks it told."""
    limits = attendance.read_limits(conn)
    rows = st.select_jobs(conn, "project = ? AND state != ?", (project, JobState.FINISHED.value))
    finished = reuse.untold(conn, project)
    reuse.told(conn, finished, now)
    return {"questions": [{**job_dict(job), **found} for job in rows
                          if (found := attendance.fields(job, now, limits))],
            "finished_away": [result_body(job) for job in finished],
            "low_disks": workers.low_disks(conn, now)}


def job_ok(req: Request) -> Message:
    """The agent says a long job is fine: the count towards stopping it starts over."""
    with req.store.write() as conn:
        job = st.require_job(conn, v.job_id(req.body))
        st.update_job(conn, job["job_id"], check_in_ok=attendance.answer(job, req.now))
        job = st.require_job(conn, job["job_id"])
    return req.reply(MessageType.STATUS_OK, status_body(job))


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
    project = v.text(req.body, "news_for", None)
    with req.store.read() as conn:
        limits = attendance.read_limits(conn)
        rows = [{**job_dict(job, pos, waiting_for(conn, job, req.now)),
                 **running_ahead(conn, job), **attendance.fields(job, req.now, limits)}
                for job, pos in queue.listing(conn, limit)]
    news: dict[str, Any] = {}
    if project:
        with req.store.write() as conn:
            news = _news(conn, project, req.now)
    return req.reply(MessageType.QUEUE_OK, {"jobs": rows, **news, "dashboard": req.dashboard})


def project_list(req: Request) -> Message:
    with req.store.read() as conn:
        rows = projects.listing(conn)
    return req.reply(MessageType.PROJECTS_OK, {"projects": rows})


def machine_list(req: Request) -> Message:
    with req.store.read() as conn:
        rows = [workers.report(worker, req.now) for worker in workers.listing(conn)]
    return req.reply(MessageType.MACHINES_OK, {"version": get_version(), "workers": rows,
                                               "dashboard": req.dashboard})


def drain(req: Request) -> Message:
    seconds = v.integer(req.body, "seconds", low=0, high=holds.MAX_DRAIN_S)
    if seconds == 0:
        holds.undrain(req.store)
        return req.reply(MessageType.DRAIN_OK, {"running": []})
    return req.reply(MessageType.DRAIN_OK, {"running": holds.drain(req.store, req.now + seconds)})


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
    MessageType.JOB_OK: job_ok,
    MessageType.HEARTBEAT: heartbeat,
    MessageType.QUEUE: queue_list,
    MessageType.PROJECTS: project_list,
    MessageType.REACH: reach,
    MessageType.MACHINES: machine_list,
    MessageType.DRAIN: drain,
    MessageType.MACHINE: machine_api.machine,
    MessageType.LOGS: logs,
    MessageType.TAKE: taken.take,
    MessageType.TAKEN: taken.taken,
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
