"""The `watch` stream (docs/interfaces-m1.md, Wire usage).

After the `watch` request the client keeps stdin open and sends a `heartbeat` line
(lease `client`) every 20 s; a reader thread renews the client lease for each one when the
request asked for `lease: true`. The loop polls every 0.5 s and writes `log_chunk` lines
for new log bytes and `status_ok` when the state (or queue position) changes, and ends with
one `result` line once the job is finished and its whole log has been sent. With `log: false`
(`mulebox events`) there are no `log_chunk` lines.

Anyone watching a detached job holds its lease, whatever `lease` asked for: that is what makes
it attended (attendance.py). A job with a client keeps its one lease holder. A watcher that
finds a job unattended is told so once, and that the job is back. Every `timeout_min` of a
running job a `status_ok` carries `check_in`, and a new stream gets the latest one, so someone
who reconnects still hears it; a client tells them apart by number. `mulebox events` also gets a
`status_ok` with `stage` as a job enters each stage; a stream with the log already shows that.

Streams, clock and sleep are injected so the loop runs in tests without real stdin.
"""

import threading
import time
from collections.abc import Callable
from typing import BinaryIO

from mulebox.common.log import get_logger
from mulebox.common.protocol import JobState, Message, MessageType, ProtocolError, decode
from mulebox.coordinator import api, attendance, leases, queue, steps, usual
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.errors import CoordinatorError, NotFound
from mulebox.coordinator.lineio import read_line, write_message
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.views import result_body, running_ahead, status_body, waiting_for

_log = get_logger(__name__)
POLL_S = 0.5


class HeartbeatReader(threading.Thread):
    """Reads heartbeat lines from the client; renews the client lease when asked to."""

    def __init__(self, stdin: BinaryIO, store: Store, job_id: str, renew: bool,
                 clock: Callable[[], float]) -> None:
        super().__init__(name=f"heartbeats-{job_id}", daemon=True)
        self.stdin, self.store, self.job_id = stdin, store, job_id
        self.renew, self.clock = renew, clock
        self.renewals = 0

    def run(self) -> None:
        while True:
            try:
                line = read_line(self.stdin)
            except (CoordinatorError, OSError, ValueError) as exc:
                _log.warning("watch %s: stopped reading heartbeats: %s", self.job_id, exc)
                return
            if line is None:
                return
            try:
                msg = decode(line)
            except ProtocolError as exc:
                _log.warning("watch %s: ignoring bad heartbeat line: %s", self.job_id, exc)
                continue
            if (self.renew and msg.type is MessageType.HEARTBEAT
                    and msg.body.get("lease") == "client"):
                try:
                    leases.renew_client(self.store, self.job_id, self.clock())
                    self.renewals += 1
                except CoordinatorError as exc:
                    _log.warning("watch %s: heartbeat failed: %s", self.job_id, exc)


def watch(store: Store, staging: Staging, msg: Message, stdin: BinaryIO, stdout: BinaryIO,
          *, clock: Callable[[], float] = time.time,
          sleep: Callable[[float], None] = time.sleep, poll_s: float = POLL_S) -> int:
    """Stream the job until it is finished; return 0. Raises CoordinatorError up front
    (unknown job, bad fields) before anything is streamed."""
    job_id = v.job_id(msg.body)
    offset = v.integer(msg.body, "offset", low=0)
    renew = v.flag(msg.body, "lease", False)
    with_log = v.flag(msg.body, "log", True)
    found = store.get_job(job_id)
    if found is None:
        raise NotFound(f"no job {job_id}")
    renew = renew or found["detached"]
    started = clock()
    with store.read() as conn:
        came_back = attendance.unattended(found, started, attendance.read_limits(conn))
    if renew:
        leases.renew_client(store, job_id, started)
    HeartbeatReader(stdin, store, job_id, renew, clock).start()

    def send(type_: MessageType, body: dict) -> None:
        write_message(stdout, Message(type_, msg.request_id, body))

    last: tuple[str, int | None, str | None] | None = None
    checked_in = 0
    stage_seq: int | None = None
    while True:
        now = clock()
        with store.read() as conn:  # state before log: finished means the log is complete
            job = st.require_job(conn, job_id)
            place = queue.position(conn, job)
            reason = waiting_for(conn, job, now)
            failed = steps.failed_stage(conn, job)
        while with_log:
            body = api.log_chunk_body(staging, job, offset)
            if body["next_offset"] == offset:
                break
            send(MessageType.LOG_CHUNK, body)
            offset = body["next_offset"]
        if (job["state"], place, reason) != last:
            with store.read() as conn:
                estimate = {**usual.estimate(job, usual.for_job(conn, job)),
                            **running_ahead(conn, job)}
            send(MessageType.STATUS_OK, status_body(job, place, reason, **estimate, **failed))
            last = (job["state"], place, reason)
            if came_back:
                send(MessageType.STATUS_OK, status_body(
                    job, place, reason, **estimate, unattended={**came_back, "taken_back": True}))
                came_back = None
        number = attendance.check_in_number(job, now)
        if number > checked_in:
            checked_in = number
            with store.read() as conn:
                rows = steps.for_job(conn, job_id)
            send(MessageType.STATUS_OK, status_body(job, check_in={
                **attendance.activity(job, rows, now), "number": number}))
        if not with_log and job["state"] != JobState.FINISHED:
            with store.read() as conn:
                rows = steps.for_job(conn, job_id)
            if rows and rows[-1]["seq"] != stage_seq:
                stage_seq = rows[-1]["seq"]
                send(MessageType.STATUS_OK, status_body(job, stage={
                    "stage": rows[-1]["stage"], "number": stage_seq,
                    "started_at": rows[-1]["started_at"]}))
        if job["state"] == JobState.FINISHED:
            send(MessageType.RESULT, result_body(job, **failed))
            return 0
        sleep(poll_s)
