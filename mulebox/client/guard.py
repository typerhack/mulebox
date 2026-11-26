"""How every client command ends: `guarded` turns an error into its code, message and fix
(common/error_report.py) with the contract's exit code, tells a project's notices after
commands that reach the node, and gives the one end object of `--json` (json_end.py)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from mulebox.client import attention, json_end, report
from mulebox.client.remote import CoordinatorError
from mulebox.client.snapshot import SnapshotError
from mulebox.client.submit import WatchLost
from mulebox.common import error_report
from mulebox.common.config import ConfigError, ProjectNotFound
from mulebox.common.error_report import Kinds
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import ProtocolError
from mulebox.common.ssh import RemoteTimeout, SSHError, SSHUnavailable

Handler = Callable[[argparse.Namespace], int]


class UsageError(MuleboxError):
    """The command line asks for something that does not exist."""

    error_code = "usage.invalid"


def guarded(handler: Handler, notices: bool = False, kinds: Kinds = ()) -> Handler:
    """Turn expected errors into their code, message and fix on stderr (and on stdout as JSON
    for a command given --json) with the contract's exit code (common/error_report.py).
    `notices`: a command that reached the machine also tells this project's questions and
    results. `kinds`: a command's own errors, as in _KINDS, looked at first."""

    def plain(args: argparse.Namespace) -> int:
        code = handler(args)
        if notices:
            attention.tell_here(sys.stderr)
        return code

    def run(args: argparse.Namespace) -> int:
        caught: BaseException | None = None
        try:
            if not json_end.wanted(args):
                return plain(args)
            with json_end.collecting(sys.stdout) as end:  # output on stderr until it ends
                try:
                    code = plain(args)
                except Exception as exc:  # noqa: BLE001 - told below, with stdout back
                    caught = exc
            if caught is None:
                end(code)
                return code
        except KeyboardInterrupt:
            return report.EXIT_CANCELLED
        except Exception as exc:  # noqa: BLE001 - every error gets its code and fix
            caught = exc
        return fail(caught, args, kinds=kinds)

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
