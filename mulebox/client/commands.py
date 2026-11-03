"""CLI subcommands of the client package (docs/interfaces-m1.md, CLI).

Exit codes for client failures: 2 usage/config error, 3 build machine unreachable,
4 protocol/remote error, 130 Ctrl-C. Job failures return the job's own exit code.
A build machine that cannot be reached is reported as such; mulebox never runs the job
anywhere else instead.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from mulebox.client import report, tui
from mulebox.client.remote import CoordinatorError, Remote, request
from mulebox.client.snapshot import SnapshotError
from mulebox.client.submit import Streams, Watcher, run_job
from mulebox.common.config import (
    ConfigError,
    ProjectConfig,
    find_project_config,
    load_client_config,
    load_project_config,
)
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType, ProtocolError
from mulebox.common.redact import Redactor
from mulebox.common.ssh import RemoteTimeout, SSHError, SSHUnavailable

QUEUE_LIMIT = 20
Handler = Callable[[argparse.Namespace], int]


class UsageError(MuleboxError):
    """The command line asks for something that does not exist."""


def register(sub: argparse._SubParsersAction) -> None:
    """Add this package's subcommands. Each sets func=handler(args) -> int."""
    check = sub.add_parser("check", help="run a job from .mulebox.yml on a build machine")
    check.add_argument("job", nargs="?", default="check", help="job name (default: check)")
    check.set_defaults(func=_guarded(_check))

    run = sub.add_parser("run", help="run an ad-hoc command on a build machine")
    run.add_argument("argv", nargs=argparse.REMAINDER, help="-- command and arguments")
    run.set_defaults(func=_guarded(_run))

    queue = sub.add_parser("queue", help="list running, waiting and recent jobs")
    queue.add_argument("--watch", action="store_true", help="full-screen live view")
    queue.set_defaults(func=_guarded(_queue))

    logs = sub.add_parser("logs", help="show a job's log")
    logs.add_argument("job_id")
    logs.add_argument("-f", "--follow", action="store_true", help="follow until it finishes")
    logs.set_defaults(func=_guarded(_logs))

    cancel = sub.add_parser("cancel", help="cancel a job")
    cancel.add_argument("job_id")
    cancel.set_defaults(func=_guarded(_cancel))


def _guarded(handler: Handler) -> Handler:
    """Turn expected errors into one clear stderr line and the contract's exit code."""

    def run(args: argparse.Namespace) -> int:
        try:
            return handler(args)
        except KeyboardInterrupt:
            return report.EXIT_CANCELLED
        except (ConfigError, SnapshotError, UsageError) as exc:
            return _fail(str(exc), report.EXIT_USAGE)
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


def _project() -> tuple[ProjectConfig, Path]:
    path = find_project_config(Path.cwd())
    return load_project_config(path), path.parent


def _remote() -> Remote:
    return Remote(load_client_config())


def _check(args: argparse.Namespace) -> int:
    project, root = _project()
    if args.job not in project.jobs:
        names = ", ".join(sorted(project.jobs))
        raise UsageError(f"no job {args.job!r} in .mulebox.yml (jobs: {names})")
    return run_job(project, args.job, root, _remote())


def _run(args: argparse.Namespace) -> int:
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise UsageError("nothing to run; use `mulebox run -- <command> [args...]`")
    project, root = _project()
    return run_job(project, argv, root, _remote())


def _queue(args: argparse.Namespace) -> int:
    remote = _remote()

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


def _logs(args: argparse.Namespace) -> int:
    remote = _remote()
    watcher = Watcher(remote, Streams())
    watcher.job_id = args.job_id
    if args.follow:
        result = watcher.follow(lease=False)
        report.status(sys.stderr, report.outcome_line(args.job_id, result))
        return report.exit_code_for(result)
    while True:
        offset = watcher.offset
        reply = remote.call(request(MessageType.LOGS, job_id=args.job_id, offset=offset))
        watcher.write_log(reply.body)
        if reply.body.get("eof", True) or watcher.offset == offset:
            return 0


def _cancel(args: argparse.Namespace) -> int:
    reply = _remote().call(request(MessageType.CANCEL, job_id=args.job_id))
    state = reply.body.get("state", "unknown")
    report.status(sys.stderr, f"cancel requested for job {args.job_id} (state {state})")
    return 0
