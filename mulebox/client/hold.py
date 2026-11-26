"""`mulebox hold <node> [-- cmd]` and `mulebox release <id>` (docs/design.md, Holding a node).

The hold waits in line on the coordinator (coordinator/node_hold.py); this side asks for its turn
every few seconds, renews it every 30 s once the node is held, runs the command if one was
given, and lets go at its end, on Ctrl-C, or when the coordinator says it ended (released from
elsewhere, or its time was up).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
from typing import Any, TextIO

from mulebox.client import report
from mulebox.client.commands import UsageError, connect, guarded
from mulebox.client.remote import request
from mulebox.common import units
from mulebox.common.protocol import MessageType

ASK_EVERY_S = 3.0
RENEW_EVERY_S = 30.0
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(m|min|h)\s*$", re.IGNORECASE)


def register(sub: argparse._SubParsersAction) -> None:
    held = sub.add_parser("hold", help="hold a node for yourself: for a command, or until Ctrl-C")
    held.add_argument("node", help="the node, as `mulebox machine list` names it")
    held.add_argument("--slots", type=int, default=0, metavar="N",
                      help="take N of its slots, not the whole node")
    held.add_argument("--for", dest="for_", default="2h", metavar="TIME",
                      help="the most it is held, such as 30m or 4h (default 2h, at most 24h)")
    held.add_argument("--next", action="store_true", help="go first in line, not behind")
    held.add_argument("argv", nargs="*", metavar="-- CMD",
                      help="a command to run on this machine while the node is held, after --")
    held.set_defaults(func=guarded(_hold))
    let_go = sub.add_parser("release", help="let go of a hold")
    let_go.add_argument("job_id")
    let_go.set_defaults(func=guarded(_release))


def seconds(text: str) -> int:
    found = _DURATION.match(text)
    if not found:
        raise UsageError(f"--for must be a time such as 30m or 2h, got {text!r}")
    value = float(found.group(1)) * (3600 if found.group(2).lower() == "h" else 60)
    if not 60 <= value <= 24 * 3600:
        raise UsageError("--for must be between 1m and 24h")
    return int(value)


def _hold(args: argparse.Namespace) -> int:
    argv = args.argv
    if args.slots < 0:
        raise UsageError("--slots must be 1 or more; leave it out for the whole node")
    remote = connect()
    made = _ask(remote, action="make", node=args.node, slots=args.slots,
                for_s=seconds(args.for_), next=args.next)
    return Holder(remote, made["job_id"], sys.stderr).run(argv, made)


def _release(args: argparse.Namespace) -> int:
    said = _ask(connect(), action="release", job_id=args.job_id)
    report.status(sys.stderr, f"hold {args.job_id}: {said.get('ended') or said.get('state')}")
    return 0


def _ask(remote: Any, **body: Any) -> dict[str, Any]:
    return remote.call(request(MessageType.HOLD, **body)).body


class Holder:
    """One hold, from waiting to letting go."""

    def __init__(self, remote: Any, job_id: str, err: TextIO,
                 sleep=time.sleep, run=subprocess.run) -> None:
        self.remote, self.job_id, self.err = remote, job_id, err
        self.sleep, self._run = sleep, run
        self.ended: str | None = None

    def run(self, argv: list[str], said: dict[str, Any]) -> int:
        try:
            said = self._wait(said)
            if said is None:
                return 1
            if not argv:
                self._keep()
                return 0
            renewing = threading.Thread(target=self._keep, daemon=True)
            renewing.start()
            return self._run(argv, check=False).returncode
        except KeyboardInterrupt:
            return 130
        finally:
            self._let_go()

    def _wait(self, said: dict[str, Any]) -> dict[str, Any] | None:
        node, last = said["node"], None
        while not said.get("go"):
            if said.get("state") == "finished":
                report.status(self.err, f"hold {self.job_id} ended while waiting: "
                              f"{said.get('ended')}")
                self.ended = said.get("ended")
                return None
            line = f"waiting for {node}: #{said.get('position')} in line; {said.get('waiting_for')}"
            if line != last:
                report.status(self.err, line)
                last = line
            self.sleep(ASK_EVERY_S)
            said = _ask(self.remote, action="turn", job_id=self.job_id)
        until = time.strftime("%H:%M", time.localtime(said["until"]))
        report.status(self.err, f"{node} is yours ({said['holds']}) until {until}, as "
                      f"{self.job_id}; Ctrl-C or `mulebox release {self.job_id}` lets go")
        return said

    def _keep(self) -> None:
        """Renew until the hold ends on the coordinator; Ctrl-C ends it from here."""
        while self.ended is None:
            self.sleep(RENEW_EVERY_S)
            if self.ended is not None:
                return
            try:
                said = _ask(self.remote, action="turn", job_id=self.job_id)
            except Exception as exc:  # a lost link: the lease gives 2 minutes
                report.status(self.err, f"could not renew the hold, trying again: {exc}")
                continue
            if said.get("state") == "finished":
                self.ended = said.get("ended") or "ended"
                report.status(self.err, f"hold {self.job_id} ended: {self.ended}")

    def _let_go(self) -> None:
        if self.ended is not None:
            return
        self.ended = "let go"
        try:
            said = _ask(self.remote, action="release", job_id=self.job_id)
            took = units.duration(said.get("duration_s")) if said.get("duration_s") else None
            report.status(self.err, f"let go of {said.get('node')}"
                          + (f" after {took}" if took else ""))
        except Exception as exc:
            report.status(self.err, f"could not let go ({exc}); it ends by itself within 2 min")
