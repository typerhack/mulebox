"""CLI for a job that is already there: `mulebox wait`, later `events` and `status`.

None of these holds the job's client lease, so none can cancel it by going away, and Ctrl-C
only stops the waiting.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from mulebox.client import report
from mulebox.client.commands import connect, guarded, project_here
from mulebox.client.submit import Streams, Watcher, stale_check
from mulebox.common.config import ConfigError


def register(sub: argparse._SubParsersAction) -> None:
    wait = sub.add_parser("wait", help="wait for a job and return what an attached check would")
    wait.add_argument("job_id")
    wait.set_defaults(func=guarded(_wait))


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
    _warn_if_stale(result, io)
    return report.exit_code_for(result)
