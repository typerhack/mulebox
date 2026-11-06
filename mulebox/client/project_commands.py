"""`mulebox project`: project folders on the build machine, from the laptop.

    mulebox project clean [--days N] [--yes]
    mulebox project reset <project> [--branch NAME] [--caches] [--yes]

The work is `mulebox project-home` on the machine (worker/project_commands.py). Without `--yes`
they only say what would go.
"""

from __future__ import annotations

import argparse
import sys

from mulebox.client.commands import connect, guarded


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
