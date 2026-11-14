"""`mulebox project`: project folders on the node, from the dev machine.

    mulebox project clean [--days N] [--yes]
    mulebox project reset <project> [--branch NAME] [--caches] [--yes]
    mulebox project pause <project>... [--minutes N]   none of its jobs or CI runs starts
    mulebox project resume <project>...
    mulebox project paused
    mulebox project priority <project> [LEVEL]   its level in the line (order_commands.py)

Clean and reset reach every online node: the coordinator hands each an order and the client
prints every node's answer (coordinator/project_orders.py, M25.4); a coordinator older than
that gets the old `mulebox project-home` on its own machine. Without `--yes` they only say what
would go. Pause, resume and paused are coordinator requests
(coordinator/project_pause.py): a paused project's jobs wait and keep their place, the rest of
the queue goes on, and a pause ends by itself after its minutes.
"""

from __future__ import annotations

import argparse
import sys
import time

from mulebox.client import order_commands
from mulebox.client.commands import connect, guarded
from mulebox.client.remote import CoordinatorError, request
from mulebox.common.protocol import MessageType


def register(sub: argparse._SubParsersAction) -> None:
    project = sub.add_parser("project", help="clean up project folders on the node")
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
    order_commands.add_priority(actions)


POLL_S = 1.0


def _on_machine(*argv: str) -> int:
    result = connect().project_home(*argv)
    sys.stdout.write(result.stdout.decode("utf-8", errors="replace"))
    return 0


def _on_every_node(body: dict, *fallback: str) -> int:
    """Send the order to every node and print each answer; the old path on an old coordinator."""
    remote = connect()
    try:
        reply = remote.call(request(MessageType.PROJECT_ORDER, **body)).body
    except CoordinatorError as exc:
        if "project_order" not in str(exc):
            raise
        print("mulebox: the coordinator is older than 1.22.0; only its own machine is reached",
              file=sys.stderr)
        return _on_machine(*fallback)
    group = reply["group"]
    for node in reply.get("offline") or ():
        print(f"{node}: not reached, it is offline; its folders stay")
    if not reply.get("nodes"):
        print("mulebox: no node is online, so nothing was looked at", file=sys.stderr)
        return 1
    while not reply.get("done"):
        time.sleep(POLL_S)
        reply = remote.call(request(MessageType.PROJECT_ORDER, group=group)).body
    return show(reply)


def show(group: dict) -> int:
    """Each node's answer; non-zero when one failed or did not answer."""
    code = 0
    for answer in group.get("answers") or ():
        if answer.get("lost"):
            print(f"{answer['node']}: did not answer; it may run a mulebox older than 1.22.0")
            code = 1
            continue
        print(f"{answer['node']}:")
        for line in (answer.get("output") or "").splitlines():
            print(f"  {line}")
        code = code or (1 if answer.get("exit_code") else 0)
    return code


def _clean(args: argparse.Namespace) -> int:
    yes = ("--yes",) if args.yes else ()
    return _on_every_node({"action": "clean", "days": args.days, "yes": args.yes},
                          "clean", "--days", str(args.days), *yes)


def _reset(args: argparse.Namespace) -> int:
    extra = [*(("--branch", args.branch) if args.branch else ()),
             *(("--caches",) if args.caches else ()), *(("--yes",) if args.yes else ())]
    body = {"action": "reset", "project": args.project, "caches": args.caches, "yes": args.yes,
            **({"branch": args.branch} if args.branch else {})}
    return _on_every_node(body, "reset", args.project, *extra)


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
