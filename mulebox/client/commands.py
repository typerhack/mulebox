"""CLI subcommands of the client package (docs/interfaces-m1.md, CLI).

Exit codes for client failures: 2 usage/config error, 3 build machine unreachable,
4 protocol/remote error, 5 job could not start, 130 Ctrl-C. Job failures return the job's
own exit code.
A build machine that cannot be reached is reported as such; mulebox never runs the job
anywhere else instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from mulebox.client import contract, queue_view, report, summary, tui
from mulebox.client.remote import CoordinatorError, Remote, request
from mulebox.client.snapshot import SnapshotError
from mulebox.client.submit import Streams, Watcher, WatchLost, run_job
from mulebox.common.config import (
    ConfigError,
    ProjectConfig,
    ProjectNotFound,
    find_project_config,
    load_client_config,
    load_project_config,
)
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType, ProtocolError
from mulebox.common.redact import Redactor
from mulebox.common.ssh import RemoteTimeout, SSHError, SSHUnavailable
from mulebox.version import get_version

QUEUE_LIMIT = 20
Handler = Callable[[argparse.Namespace], int]


class UsageError(MuleboxError):
    """The command line asks for something that does not exist."""


def register(sub: argparse._SubParsersAction) -> None:
    """Add this package's subcommands. Each sets func=handler(args) -> int."""
    check = sub.add_parser("check", help="run a job from .mulebox.yml on a build machine")
    check.add_argument("job", nargs="?", default="check", help="job name (default: check)")
    check.add_argument("--detach", action="store_true",
                       help="print the job id once it is queued and leave it running")
    check.set_defaults(func=guarded(_check))

    run = sub.add_parser("run", help="run an ad-hoc command on a build machine")
    run.add_argument("--detach", action="store_true",
                     help="print the job id once it is queued and leave it running")
    run.add_argument("argv", nargs=argparse.REMAINDER, help="-- command and arguments")
    run.set_defaults(func=guarded(_run))

    queue = sub.add_parser("queue", help="list running, waiting and recent jobs")
    queue.add_argument("--watch", action="store_true", help="full-screen live view")
    queue.set_defaults(func=guarded(_queue))

    known = sub.add_parser("projects", help="list every project that has run here")
    known.add_argument("--json", action="store_true", help="stable keys for tools")
    known.set_defaults(func=guarded(_projects))

    logs = sub.add_parser("logs", help="show a job's log")
    logs.add_argument("job_id")
    logs.add_argument("-f", "--follow", action="store_true", help="follow until it finishes")
    logs.add_argument("--summary", action="store_true",
                      help="only why it failed: stage, exit code, last relevant lines")
    logs.set_defaults(func=guarded(_logs))

    cancel = sub.add_parser("cancel", help="cancel a job")
    cancel.add_argument("job_id")
    cancel.set_defaults(func=guarded(_cancel))

    terms = sub.add_parser("contract", help="print how to work in this project through "
                           "mulebox, for agents")
    terms.add_argument("--json", action="store_true", help="stable keys for tools")
    terms.set_defaults(func=guarded(_contract))


def guarded(handler: Handler) -> Handler:
    """Turn expected errors into one clear stderr line and the contract's exit code."""

    def run(args: argparse.Namespace) -> int:
        try:
            return handler(args)
        except KeyboardInterrupt:
            return report.EXIT_CANCELLED
        except (ConfigError, SnapshotError, UsageError) as exc:
            return _fail(str(exc), report.EXIT_USAGE)
        except WatchLost as exc:
            return _fail(str(exc), report.EXIT_UNREACHABLE)
        except (SSHUnavailable, RemoteTimeout) as exc:
            return _fail(
                f"build machine unreachable: {exc} The job was not run; "
                "fix the connection to the build machine and retry.",
                report.EXIT_UNREACHABLE,
            )
        except (CoordinatorError, ProtocolError, SSHError) as exc:
            return _fail(str(exc), report.EXIT_REMOTE)

    return run


def _fail(message: str, code: int) -> int:
    report.status(sys.stderr, f"error: {Redactor().redact(message)}")
    return code


def project_here() -> tuple[ProjectConfig, Path]:
    path = find_project_config(Path.cwd())
    return load_project_config(path), path.parent


def connect() -> Remote:
    return Remote(load_client_config())


def _contract(args: argparse.Namespace) -> int:
    try:
        config = project_here()[0]
    except ProjectNotFound:
        config = None
    terms = contract.build(config, get_version())
    sys.stdout.write(json.dumps(terms, indent=2) + "\n" if args.json
                     else contract.render(terms))
    return 0


def _check(args: argparse.Namespace) -> int:
    project, root = project_here()
    if args.job not in project.jobs:
        names = ", ".join(sorted(project.jobs))
        raise UsageError(f"no job {args.job!r} in .mulebox.yml (jobs: {names})")
    return run_job(project, args.job, root, connect(), detach=args.detach)


def _run(args: argparse.Namespace) -> int:
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise UsageError("nothing to run; use `mulebox run -- <command> [args...]`")
    project, root = project_here()
    return run_job(project, argv, root, connect(), detach=args.detach)


def _queue(args: argparse.Namespace) -> int:
    remote = connect()

    def fetch() -> list[dict]:
        reply = remote.call(request(MessageType.QUEUE, limit=QUEUE_LIMIT))
        jobs = reply.body.get("jobs")
        if not isinstance(jobs, list):
            raise CoordinatorError("the queue reply has no job list")
        return [j for j in jobs if isinstance(j, dict)]

    if args.watch:
        return tui.watch(fetch, remote.target)
    tui.show_once(fetch, sys.stdout)
    return 0


def _projects(args: argparse.Namespace) -> int:
    rows = connect().call(request(MessageType.PROJECTS)).body.get("projects")
    if not isinstance(rows, list):
        raise CoordinatorError("the projects reply has no project list")
    if args.json:
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
    else:
        sys.stdout.write("\n".join(queue_view.render_projects(rows)) + "\n")
    return 0


def _logs(args: argparse.Namespace) -> int:
    remote = connect()
    watcher = Watcher(remote, Streams())
    watcher.job_id = args.job_id
    if args.summary:
        return _log_summary(remote, args.job_id)
    if args.follow:
        result = watcher.attach()
        watcher.finish(result)
        return report.exit_code_for(result)
    _read_log(remote, args.job_id, 0, watcher.write_log)
    return 0


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
        print("\n".join(summary.render(job_id, body, summary.relevant_lines(tail))))
    return 0


def _cancel(args: argparse.Namespace) -> int:
    reply = connect().call(request(MessageType.CANCEL, job_id=args.job_id))
    state = reply.body.get("state", "unknown")
    report.status(sys.stderr, f"cancel requested for job {args.job_id} (state {state})")
    return 0
