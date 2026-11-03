"""Single entry point: `mulebox <command>`.

Commands are registered here as they are implemented (see docs/phases.md). This module only
parses arguments and dispatches; the work happens in the client, coordinator and worker
packages.
"""

import argparse
import sys
from collections.abc import Sequence

from mulebox.version import get_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mulebox",
        description="Run your agents' builds and tests on build machines through one queue.",
    )
    parser.add_argument("--version", action="version", version=f"mulebox {get_version()}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("version", help="print the mulebox version")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "version":
        print(get_version())
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
