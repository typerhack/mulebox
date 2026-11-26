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
                            rerun_lines, skill_install, take_back, tui)
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
from mulebox.common.error_report import Kinds
from mulebox.common import error_report
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType, ProtocolError
from mulebox.common.ssh import RemoteTimeout, SSHError, SSHUnavailable
from mulebox.version import get_version

QUEUE_LIMIT = 20
Handler = Callable[[argparse.Namespace], int]


class UsageError(MuleboxError):
    """The command line asks for something that does not exist."""

    error_code = "usage.invalid"


def register(sub: argparse._SubParsersAction) -> None:
    """Add this package's subcommands. Each sets func=handler(args) -> int."""
    check = sub.add_parser("check", help="run a job from .mulebox.yml on a node")
    check.add_argument("job", nargs="?", default="check", help="job name (default: check)")
    check.add_argument("--detach", action="store_true",
                       help="print the job id once it is queued and leave it running")
    check.add_argument("--again", action="store_true",
                       help="run even if these exact files were already tested")
    check.add_argument("--fewer-tests", metavar="REASON",
                       help="let this run pass with fewer tests than the last pass, because tests "
                            "were removed on purpose; the reason is kept with the job")
    _on(check)
    _from_stage(check)
    _keep(check)
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
    _from_stage(run)
    _keep(run)
    run.add_argument("argv", nargs=argparse.REMAINDER, help="-- command and arguments")
    run.set_defaults(func=guarded(_run))

    queue = sub.add_parser("queue", help="list running, waiting and recent jobs")
    queue.add_argument("--watch", action="store_true", help="full-screen live view")
    queue.add_argument("--json", action="store_true",
                       help="the coordinator's reply as JSON: every job with its place and reason")
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


def _keep(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--keep", action="append", default=[], metavar="PATH",
                        help="keep this file, folder or pattern for `mulebox fetch`, on any "
                             "outcome, beside the job's own `keep:` (repeat for more)")


def _from_stage(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-stage", choices=rerun_lines.STAGES, metavar="STAGE",
                        help="rerun the last failed job of this name and branch from STAGE "
                             "(install, setup or command) in the containers its node kept, "
                             "skipping images, services and the stages before; runs from the "
                             "start when nothing is kept")


def guarded(handler: Handler, notices: bool = False, kinds: Kinds = ()) -> Handler:
    """Turn expected errors into their code, message and fix on stderr (and on stdout as JSON
    for a command given --json) with the contract's exit code (common/error_report.py).
    `notices`: a command that reached the machine also tells this project's questions and
    results. `kinds`: a command's own errors, as in _KINDS, looked at first."""

    def run(args: argparse.Namespace) -> int:
        try:
            code = handler(args)
            if notices:
                attention.tell_here(sys.stderr)
            return code
        except KeyboardInterrupt:
            return report.EXIT_CANCELLED
        except Exception as exc:  # noqa: BLE001 - every error gets its code and fix
            return fail(exc, args, kinds=kinds)

    return run


# The exit code and default code of each kind of error, first match wins.
_KINDS: Kinds = (
    ((ProjectNotFound,), report.EXIT_USAGE, "config.missing"),
    ((ConfigError,), report.EXIT_USAGE, "config.invalid"),
    ((SnapshotError,), report.EXIT_USAGE, "project.snapshot"),
    ((UsageError,), report.EXIT_USAGE, "usage.invalid"),
    ((WatchLost,), report.EXIT_UNREACHABLE, "node.connection_lost"),
    ((SSHUnavailable,), report.EXIT_UNREACHABLE, "node.unreachable"),
    ((RemoteTimeout,), report.EXIT_UNREACHABLE, "node.timeout"),
    ((CoordinatorError, ProtocolError, SSHError), report.EXIT_REMOTE, "node.protocol"),
)


def fail(exc: BaseException, args: argparse.Namespace | None = None,
         exit_code: int | None = None, default_code: str | None = None,
         kinds: Kinds = ()) -> int:
    """Tell `exc` the one way every command does (common/error_report.py)."""
    return error_report.report(exc, (*kinds, *_KINDS), exit_code=exit_code,
                               default_code=default_code,
                               as_json=bool(getattr(args, "json", False)))


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
                        on=args.on, fewer_tests=args.fewer_tests, from_stage=args.from_stage,
                        keep=tuple(args.keep)),
        rerun=bool(args.from_stage))


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
                   options=BARE if args.bare else None, take=take, on=args.on,
                   from_stage=args.from_stage, keep=tuple(args.keep))


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

    if args.json:
        fetch()
        print(json.dumps(latest, sort_keys=True))
        return 0
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
