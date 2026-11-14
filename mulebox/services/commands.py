"""`mulebox service`: mulebox's own services on this node, the same words on Linux and macOS.

    mulebox service install [--config FILE]   write them all, (re)start what node.toml's roles run
    mulebox service restart <name>...
    mulebox service stop <name>...            and keep them from starting again
    mulebox service status [<name>...]
    mulebox service logs [-f] [<name>...]     journalctl on Linux, the log files on macOS

install.sh runs `install`; messages elsewhere name `restart` and `stop` rather than `systemctl`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from mulebox.common.config import load_node_config
from mulebox.common.errors import MuleboxError
from mulebox.services.base import SERVICES, check_name, settled_state, wanted
from mulebox.services.manager import for_platform


def register(sub: argparse._SubParsersAction) -> None:
    service = sub.add_parser("service", help="mulebox's own services on this node")
    actions = service.add_subparsers(dest="service_command", metavar="<action>", required=True)
    install = actions.add_parser("install", help="write the services, (re)start the node's own")
    install.add_argument("--config", help="node config file (default ~/.config/mulebox/node.toml)")
    install.set_defaults(func=_install)
    for action, text in (("restart", "restart services"),
                         ("stop", "stop services and keep them stopped")):
        cmd = actions.add_parser(action, help=text)
        cmd.add_argument("names", nargs="+", choices=SERVICES, metavar="name",
                         help=", ".join(SERVICES))
        cmd.set_defaults(func=_each, action=action)
    status = actions.add_parser("status", help="whether each service runs")
    status.add_argument("names", nargs="*", metavar="name", help=", ".join(SERVICES))
    status.set_defaults(func=_status)
    logs = actions.add_parser("logs", help="the services' recent logs")
    logs.add_argument("names", nargs="*", metavar="name", help=", ".join(SERVICES))
    logs.add_argument("-f", "--follow", action="store_true", help="go on with new lines")
    logs.set_defaults(func=_logs)


def _fail(exc: Exception) -> int:
    print(f"mulebox service: error: {exc}", file=sys.stderr)
    return 1


def _install(args: argparse.Namespace) -> int:
    try:
        node = load_node_config(Path(args.config) if args.config else None)
        manager = for_platform()
        runs = wanted(node.roles)
        manager.install(node.roles, print)
        for name in runs:
            print(f"  service:  {name} ({settled_state(manager, name)})")
        print(f"Logs: mulebox service logs {' '.join(runs)}")
        note = manager.boot_note()
    except MuleboxError as exc:
        return _fail(exc)
    if note:
        print(f"\n{note}")
    return 0


def _each(args: argparse.Namespace) -> int:
    """`restart` or `stop` on each named service, in the order given."""
    try:
        manager = for_platform()
        for name in args.names:
            getattr(manager, args.action)(name)
    except MuleboxError as exc:
        return _fail(exc)
    return 0


def _status(args: argparse.Namespace) -> int:
    try:
        manager = for_platform()
        for name in args.names or SERVICES:
            check_name(name)
            print(f"{name}\t{manager.state(name)}")
    except MuleboxError as exc:
        return _fail(exc)
    return 0


def _logs(args: argparse.Namespace) -> int:
    try:
        names = [check_name(name) for name in args.names] or list(SERVICES)
        argv = for_platform().logs_argv(names, args.follow)
        os.execvp(argv[0], argv)
    except (MuleboxError, OSError) as exc:
        return _fail(exc)
    return 0  # not reached: exec replaced this process
