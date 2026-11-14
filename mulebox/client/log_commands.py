"""`mulebox logs`: a job's log, followed or whole, or why it failed (split from commands.py)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from mulebox.client import report, summary
from mulebox.client.commands import connect, guarded
from mulebox.client.remote import Remote, request
from mulebox.client.submit import Streams, Watcher
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType


def register(sub: argparse._SubParsersAction) -> None:
    logs = sub.add_parser("logs", help="show a job's log")
    logs.add_argument("job_id")
    logs.add_argument("-f", "--follow", action="store_true", help="follow until it finishes")
    logs.add_argument("--summary", action="store_true",
                      help="only why it failed: stage, exit code, last relevant lines")
    logs.set_defaults(func=guarded(_logs, notices=True))


def _logs(args: argparse.Namespace) -> int:
    remote = connect()
    watcher = Watcher(remote, Streams())
    watcher.job_id = args.job_id
    if args.summary:
        return _log_summary(remote, args.job_id)
    if args.follow:
        result = watcher.attach()
        note_expired_log(watcher)
        watcher.finish(result)
        return report.exit_code_for(result)
    _read_log(remote, args.job_id, 0, watcher.write_log)
    note_expired_log(watcher)
    return 0


def note_expired_log(watcher: Watcher) -> None:
    """A log that printed nothing may be gone rather than empty. Only a remark: losing the
    connection here must not cost `wait` the job's exit code."""
    if watcher.offset:
        return
    try:
        body = watcher.remote.call(request(MessageType.STATUS, job_id=watcher.job_id)).body
    except (MuleboxError, OSError):
        return
    if report.log_expired(body):
        report.status(watcher.io.err, report.expired_line(watcher.job_id))


def _read_log(remote: Remote, job_id: str, offset: int, sink: Callable[[dict], None]) -> None:
    while True:
        reply = remote.call(request(MessageType.LOGS, job_id=job_id, offset=offset))
        sink(reply.body)
        next_offset = reply.body.get("next_offset", offset)
        if reply.body.get("eof", True) or next_offset == offset:
            return
        offset = next_offset


def _log_summary(remote: Remote, job_id: str) -> int:
    body = remote.call(request(MessageType.STATUS, job_id=job_id)).body
    state = body.get("state")
    if state != "finished":
        print(f"job {job_id} is {state}; a summary needs it to end")
    elif not summary.wanted(body):
        print(report.outcome_line(job_id, body))
    else:
        tail = summary.LogTail()
        size = body.get("log_size")
        start = max(0, size - summary.TAIL_BYTES) if isinstance(size, int) else 0
        tail.cut = start > 0
        _read_log(remote, job_id, start, lambda chunk: tail.feed(chunk.get("data") or ""))
        if not tail.text and report.log_expired(body):
            report.status(sys.stderr, report.expired_line(job_id))
        print("\n".join(summary.render(job_id, body, summary.relevant_lines(tail))))
    return 0
