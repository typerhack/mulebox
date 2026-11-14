"""CLI subcommands of the client package (docs/interfaces-m1.md, CLI).

Exit codes for client failures: 2 usage/config error, 3 node unreachable,
4 protocol/remote error, 5 job could not start, 76 stopped as stuck with no answer from the agent,
130 Ctrl-C. Job failures return the job's own exit code.
A node that cannot be reached is reported as such; mulebox never runs the job
anywhere else instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.client import (attention, contract, github_status, queue_view, report,
                            skill_install, take_back, tui)
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
from mulebox.common.config_jobs import BARE
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
    check = sub.add_parser("check", help="run a job from .mulebox.yml on a node")
    check.add_argument("job", nargs="?", default="check", help="job name (default: check)")
    check.add_argument("--detach", action="store_true",
                       help="print the job id once it is queued and leave it running")
    check.add_argument("--again", action="store_true",
                       help="run even if these exact files were already tested")
    _on(check)
    check.set_defaults(func=guarded(_check))

    warm = sub.add_parser("warm", help="prepare a job ahead of time: toolchains, images, caches, "
                          "install; no command")
    warm.add_argument("job", nargs="?", default="check", help="job name (default: check)")
    warm.add_argument("--detach", action="store_true",
                      help="print the job id once it is queued and leave it running")
    _on(warm)
    warm.set_defaults(func=guarded(_warm, notices=True))

    run = sub.add_parser("run", help="run an ad-hoc command on a node")
    run.add_argument("--detach", action="store_true",
                     help="print the job id once it is queued and leave it running")
    run.add_argument("--in", dest="service", metavar="SERVICE",
                     help="run it inside this compose service")
    run.add_argument("--bare", action="store_true",
                     help="the command alone: no containers, install or setup")
    run.add_argument("--take", action="append", default=[], metavar="PATH",
                     help="once the command passed, copy this file back into the project "
                          "(repeat for more), e.g. --take api/composer.lock")
    _on(run)
    run.add_argument("argv", nargs=argparse.REMAINDER, help="-- command and arguments")
    run.set_defaults(func=guarded(_run))

    queue = sub.add_parser("queue", help="list running, waiting and recent jobs")
    queue.add_argument("--watch", action="store_true", help="full-screen live view")
    queue.set_defaults(func=guarded(_queue))

    known = sub.add_parser("projects", help="list every project that has run here")
    known.add_argument("--json", action="store_true", help="stable keys for tools")
    known.set_defaults(func=guarded(_projects, notices=True))

    cancel = sub.add_parser("cancel", help="cancel a job")
    cancel.add_argument("job_id")
    cancel.set_defaults(func=guarded(_cancel, notices=True))

    terms = sub.add_parser("contract", help="print how to work in this project through "
                           "mulebox, for agents")
    terms.add_argument("--json", action="store_true", help="stable keys for tools")
    terms.set_defaults(func=guarded(_contract))


def _on(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--on", metavar="NODE",
                        help="run it on this node only, as `mulebox machine list` names it")


def guarded(handler: Handler, notices: bool = False) -> Handler:
    """Turn expected errors into one clear stderr line and the contract's exit code. `notices`:
    a command that reached the machine also tells this project's questions and results."""

    def run(args: argparse.Namespace) -> int:
        try:
            code = handler(args)
            if notices:
                attention.tell_here(sys.stderr)
            return code
        except KeyboardInterrupt:
            return report.EXIT_CANCELLED
        except (ConfigError, SnapshotError, UsageError) as exc:
            return _fail(str(exc), report.EXIT_USAGE)
        except WatchLost as exc:
            return _fail(str(exc), report.EXIT_UNREACHABLE)
        except (SSHUnavailable, RemoteTimeout) as exc:
            return _fail(
                f"node unreachable: {exc} The job was not run; "
                "fix the connection to the node and retry.",
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
    if stale := skill_install.stale_here():
        report.status(sys.stderr, stale)
    sys.stdout.write(json.dumps(terms, indent=2) + "\n" if args.json
                     else contract.render(terms))
    return 0


def _named_job(name: str) -> tuple[ProjectConfig, Path]:
    project, root = project_here()
    if name not in project.jobs:
        names = ", ".join(sorted(project.jobs))
        raise UsageError(f"no job {name!r} in .mulebox.yml (jobs: {names})")
    return project, root


def _check(args: argparse.Namespace) -> int:
    project, root = _named_job(args.job)
    return github_status.around(
        project, root, args.job, args.detach, sys.stderr,
        lambda: run_job(project, args.job, root, connect(), detach=args.detach, again=args.again,
                        on=args.on))


def _warm(args: argparse.Namespace) -> int:
    project, root = _named_job(args.job)
    return run_job(project, args.job, root, connect(), detach=args.detach, warm=True, on=args.on)


def _run(args: argparse.Namespace) -> int:
    argv = list(args.argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise UsageError("nothing to run; use `mulebox run -- <command> [args...]`")
    project, root = project_here()
    if args.service:
        if args.bare:
            raise UsageError("--in runs in a service, which --bare does not start")
        if not project.compose:
            raise UsageError("--in needs `compose:` in .mulebox.yml")
        argv = ["docker", "compose", "exec", "-T", args.service, *argv]
    if args.take and args.detach:
        raise UsageError("--take brings files back at the end, so it waits; drop --detach")
    try:
        take = take_back.check(args.take, project.exclude)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    return run_job(project, argv, root, connect(), detach=args.detach,
                   options=BARE if args.bare else None, take=take, on=args.on)


def _queue(args: argparse.Namespace) -> int:
    remote = connect()
    latest: dict[str, Any] = {}

    def fetch() -> list[dict]:
        reply = remote.call(request(MessageType.QUEUE, limit=QUEUE_LIMIT))
        latest.update(reply.body)
        jobs = reply.body.get("jobs")
        if not isinstance(jobs, list):
            raise CoordinatorError("the queue reply has no job list")
        return [j for j in jobs if isinstance(j, dict)]

    if args.watch:
        return tui.watch(fetch, remote.target)
    tui.show_once(fetch, sys.stdout)
    report.dashboard_hint(sys.stderr, latest)
    return 0


def _with_folders(remote: Remote, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """`rows` with each project's folder and size; the job history alone from an older machine."""
    try:
        folders = json.loads(remote.project_home("list", "--json").stdout)
    except (MuleboxError, ValueError):
        return rows
    known = {row["project"]: row for row in folders}
    return [{**row, **{k: v for k, v in known.get(row["project"], {}).items() if k != "project"}}
            for row in rows]


def _projects(args: argparse.Namespace) -> int:
    remote = connect()
    rows = remote.call(request(MessageType.PROJECTS)).body.get("projects")
    if not isinstance(rows, list):
        raise CoordinatorError("the projects reply has no project list")
    rows = _with_folders(remote, rows)
    if args.json:
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
    else:
        sys.stdout.write("\n".join(queue_view.render_projects(rows)) + "\n")
    return 0


def _cancel(args: argparse.Namespace) -> int:
    reply = connect().call(request(MessageType.CANCEL, job_id=args.job_id))
    state = reply.body.get("state", "unknown")
    report.status(sys.stderr, f"cancel requested for job {args.job_id} (state {state})")
    return 0
