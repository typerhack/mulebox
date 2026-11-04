"""CLI for a job that is already there: `mulebox wait`, `events` and `status`.

None of these holds the job's client lease, so none can cancel it by going away, and Ctrl-C
only stops the waiting. `events` exits with the job's exit code, `status` with 0: it answers
a question and does not stand in for the job.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from mulebox.client import events, report
from mulebox.client.commands import connect, guarded, note_expired_log, project_here
from mulebox.client.remote import request
from mulebox.client.submit import Streams, Watcher, stale_check
from mulebox.common import status
from mulebox.common.config import ConfigError
from mulebox.common.protocol import MessageType


def register(sub: argparse._SubParsersAction) -> None:
    wait = sub.add_parser("wait", help="wait for a job and return what an attached check would")
    wait.add_argument("job_id")
    wait.set_defaults(func=guarded(_wait))

    follow = sub.add_parser("events", help="follow a job's state changes as lines, without its log")
    follow.add_argument("--job", required=True, metavar="JOB_ID", dest="job_id")
    follow.add_argument("--json", action="store_true", help="one JSON object per line")
    follow.set_defaults(func=guarded(_events))

    state = sub.add_parser("status", help="show one job's current state")
    state.add_argument("job_id")
    state.add_argument("--json", action="store_true", help="stable keys for tools")
    state.set_defaults(func=guarded(_status))


def _warn_if_stale(result: dict[str, Any], io: Streams) -> None:
    """As `check` does, when run from the job's project; elsewhere there is nothing to compare."""
    fingerprint = result.get("fingerprint")
    try:
        project, root = project_here()
    except ConfigError:
        return
    if fingerprint and project.project == result.get("project"):
        stale_check(root, project, fingerprint, io)


def _wait(args: argparse.Namespace) -> int:
    io = Streams()
    watcher = Watcher(connect(), io)
    watcher.job_id = args.job_id
    try:
        result = watcher.attach()
    except KeyboardInterrupt:
        report.status(sys.stderr, f"stopped waiting; job {args.job_id} keeps running "
                      f"(`mulebox cancel {args.job_id}` stops it)")
        return report.EXIT_CANCELLED
    watcher.finish(result)
    note_expired_log(watcher)
    _warn_if_stale(result, io)
    return report.exit_code_for(result)


def _events(args: argparse.Namespace) -> int:
    stream = events.EventStream(connect(), Streams(),
                                events.as_json if args.json else events.as_text)
    stream.job_id = args.job_id
    try:
        return report.exit_code_for(stream.attach())
    except KeyboardInterrupt:
        return report.EXIT_CANCELLED


def _status_line(job_id: str, body: dict[str, Any]) -> str:
    if body.get("state") == status.FINISHED:
        return report.outcome_line(job_id, body)
    return f"job {job_id}: {report.state_line(body) or body.get('state')}"


def _status(args: argparse.Namespace) -> int:
    body = connect().call(request(MessageType.STATUS, job_id=args.job_id)).body
    if args.json:
        print(json.dumps(status.row(body, time.time()), indent=2, sort_keys=True))
    else:
        print("\n".join([_status_line(args.job_id, body),
                         *report.stage_lines(body, time.time())]))
    return 0
