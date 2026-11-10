"""`mulebox project`: project folders on the build machine, from the laptop.

    mulebox project clean [--days N] [--yes]
    mulebox project reset <project> [--branch NAME] [--caches] [--yes]
    mulebox project pause <project>... [--minutes N]   none of its jobs or CI runs starts
    mulebox project resume <project>...
    mulebox project paused

Clean and reset are `mulebox project-home` on the machine (worker/project_commands.py); without
`--yes` they only say what would go. Pause, resume and paused are coordinator requests
(coordinator/project_pause.py): a paused project's jobs wait and keep their place, the rest of
the queue goes on, and a pause ends by itself after its minutes.
"""

from __future__ import annotations

import argparse
import sys
import time

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.common.protocol import MessageType


def register(sub: argparse._SubParsersAction) -> None:
    project = sub.add_parser("project", help="clean up project folders on the build machine")
    actions = project.add_subparsers(dest="project_command", metavar="<action>", required=True)
    clean = actions.add_parser("clean", help="remove branch folders not used for a while")
    clean.add_argument("--days", type=int, default=14, help="unused for this long (default 14)")
    clean.add_argument("--yes", action="store_true", help="really remove them")
    clean.set_defaults(func=guarded(_clean))
    reset = actions.add_parser("reset", help="remove a project's folder, so it starts clean")
    reset.add_argument("project")
    reset.add_argument("--branch", help="only this branch")
    reset.add_argument("--caches", action="store_true", help="its package caches too")
    reset.add_argument("--yes", action="store_true", help="really remove it")
    reset.set_defaults(func=guarded(_reset))
    pause = actions.add_parser("pause", help="start none of a project's jobs or CI runs for a while")
    pause.add_argument("projects", nargs="+", help="names as `mulebox projects` shows them")
    pause.add_argument("--minutes", type=int, default=60, help="ends by itself after (default 60)")
    pause.set_defaults(func=guarded(_pause), action="pause")
    resume = actions.add_parser("resume", help="let paused projects start jobs again")
    resume.add_argument("projects", nargs="+")
    resume.set_defaults(func=guarded(_pause), action="resume", minutes=None)
    listing = actions.add_parser("paused", help="list paused projects")
    listing.set_defaults(func=guarded(_pause), action="list", projects=[], minutes=None)


def _on_machine(*argv: str) -> int:
    result = connect().project_home(*argv)
    sys.stdout.write(result.stdout.decode("utf-8", errors="replace"))
    return 0


def _clean(args: argparse.Namespace) -> int:
    yes = ("--yes",) if args.yes else ()
    return _on_machine("clean", "--days", str(args.days), *yes)


def _reset(args: argparse.Namespace) -> int:
    extra = [*(("--branch", args.branch) if args.branch else ()),
             *(("--caches",) if args.caches else ()), *(("--yes",) if args.yes else ())]
    return _on_machine("reset", args.project, *extra)


def _pause(args: argparse.Namespace) -> int:
    body = {"action": args.action, "projects": args.projects}
    if args.minutes is not None:
        body["minutes"] = args.minutes
    paused = connect().call(request(MessageType.PROJECT_PAUSE, **body)).body["paused"]
    if not paused:
        print("mulebox: no project is paused", file=sys.stderr)
    for project, until in sorted(paused.items()):
        print(f"{project}\tpaused until {time.strftime('%H:%M', time.localtime(until))}")
    return 0
