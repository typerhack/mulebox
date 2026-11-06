"""The `mulebox setup` command (client/setup.py)."""

from __future__ import annotations

import argparse
import sys

from mulebox.client import setup
from mulebox.client.commands import guarded


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("setup", help="install mulebox on a build machine and use it from here")
    parser.add_argument("host", help="ssh target: a Host alias or alice@192.168.1.50")
    parser.add_argument("--now", action="store_true", help="do not wait for running jobs")
    parser.set_defaults(func=guarded(_setup))


def _say(line: str) -> None:
    print(f"mulebox: {line}", file=sys.stderr, flush=True)


def _setup(args: argparse.Namespace) -> int:
    try:
        setup.run(args.host, _say, now=args.now)
    except setup.SetupError as exc:
        _say(f"error: {exc}")
        return 1
    return 0
