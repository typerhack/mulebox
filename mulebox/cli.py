"""Single entry point: `mulebox <command>`.

Commands are registered here as they are implemented (see docs/phases.md). This module only
parses arguments and dispatches; the work happens in the client, coordinator and worker
packages.
"""

import argparse
import sys
from collections.abc import Sequence

from mulebox.client import commands as client_commands
from mulebox.coordinator import commands as coordinator_commands
from mulebox.runners import commands as runner_commands
from mulebox.version import get_version
from mulebox.worker import commands as worker_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mulebox",
        description="Run your agents' builds and tests on build machines through one queue.",
    )
    parser.add_argument("--version", action="version", version=f"mulebox {get_version()}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("version", help="print the mulebox version")
    for package in (client_commands, coordinator_commands, worker_commands, runner_commands):
        package.register(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "version":
        print(get_version())
        return 0
    handler = getattr(args, "func", None)
    if handler is not None:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
