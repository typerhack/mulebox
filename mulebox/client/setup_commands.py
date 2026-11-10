"""The `mulebox setup` command (client/setup.py)."""

from __future__ import annotations

import argparse
import sys

from mulebox.client import setup, setup_queued, setup_worker, skill_install
from mulebox.client.commands import guarded


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("setup", help="install mulebox on a build machine and use it from here")
    parser.add_argument("host", help="ssh target: a Host alias or alice@192.168.1.50")
    parser.add_argument("--now", action="store_true", help="stop running jobs and upgrade now")
    parser.add_argument("--when-idle", action="store_true",
                        help="wait for running jobs to end; new jobs wait in line meanwhile")
    parser.add_argument("--queued", action="store_true",
                        help="put the upgrade in the machine's line and return: nothing new "
                             "starts there, the running jobs end, it installs, the line goes on")
    parser.add_argument("--behind", action="store_true",
                        help="with --queued: behind the jobs already waiting, not next")
    parser.add_argument("--worker-of", metavar="COORDINATOR",
                        help="make the host one more worker of this coordinator machine")
    parser.add_argument("--coordinator-address", metavar="TARGET",
                        help="how the worker reaches the coordinator, if not as this laptop does")
    parser.set_defaults(func=guarded(_setup))


def _say(line: str) -> None:
    print(f"mulebox: {line}", file=sys.stderr, flush=True)


def _setup(args: argparse.Namespace) -> int:
    try:
        if args.behind and not args.queued:
            raise setup.SetupError("--behind goes with --queued")
        if args.queued:
            setup_queued.run(args.host, _say, behind=args.behind)
        elif args.worker_of:
            setup_worker.run(args.host, args.worker_of, _say, args.coordinator_address,
                             now=args.now)
        else:
            setup.run(args.host, _say, now=args.now, when_idle=args.when_idle)
    except setup.SetupError as exc:
        _say(f"error: {exc}")
        return 1
    for line in skill_install.refresh_here():
        _say(line)
    return 0
