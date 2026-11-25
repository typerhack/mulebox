"""`mulebox machine check <name>` and a node's health in `mulebox machine list` (design.md, A
node that rests).

`check` asks the node to run its checks now, then waits for its answer (its `answers` go up:
a check started after the ask, not one already running) and prints each failing check with its fix; exit 1 while one fails. A node too old to check
itself (before 1.41) says so.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import Remote, request
from mulebox.common import node_health
from mulebox.common.protocol import MessageType

WAIT_S = 45.0  # a check takes 15 s at most; the node takes the ask within seconds
POLL_S = 1.0


def register(actions: argparse._SubParsersAction) -> None:
    check = actions.add_parser("check", help="run a node's health checks now and show them")
    check.add_argument("name")
    check.set_defaults(func=guarded(_check))


def state(health: dict[str, Any] | None) -> str | None:
    """`resting`, `no docker`, or None for a node that takes every job it offers."""
    if not health:
        return None
    if health.get("resting"):
        return "resting"
    checks = sorted({item["check"] for item in health.get("problems") or ()
                     if item["check"] in node_health.WITHHOLDS})
    return f"no {', no '.join(checks)}" if checks else None


def problem_lines(worker: str, health: dict[str, Any] | None) -> list[str]:
    lines = []
    for item in (health or {}).get("problems") or ():
        lines.append(f"  {worker}: {item['message']} (since {node_health.clock(item['since'])})")
        if item.get("fix"):
            lines.append(f"    fix: {item['fix']}")
    return lines


def _row(remote: Remote, name: str) -> dict[str, Any] | None:
    rows = remote.call(request(MessageType.MACHINES)).body.get("workers", [])
    return next((row for row in rows if row.get("worker") == name), None)


def _round(row: dict[str, Any] | None) -> int | None:
    """Asks the node answered with a check started after them; None from a node before 1.41."""
    health = (row or {}).get("health")
    return health.get("answers") if isinstance(health, dict) else None


def _say(line: str) -> None:
    print(f"mulebox: {line}", file=sys.stderr, flush=True)


def _check(args: argparse.Namespace) -> int:
    remote = connect()
    before = _round(_row(remote, args.name))
    remote.call(request(MessageType.MACHINE, worker=args.name, action="check"))
    _say(f"asked {args.name} to check itself; waiting for its answer")
    deadline = time.monotonic() + WAIT_S
    row = None
    while time.monotonic() < deadline:
        row = _row(remote, args.name)
        found = _round(row)
        if found is not None and (before is None or found > before):
            return _show(args.name, row)
        time.sleep(POLL_S)
    if row is not None and not row.get("online"):
        _say(f"{args.name} is offline: start it on that machine, `mulebox service start worker`")
    elif _round(row) is None:
        _say(f"{args.name} does not check itself: it runs a mulebox older than 1.41; "
             f"`mulebox setup {args.name}` upgrades it")
    else:
        _say(f"{args.name} did not answer in {WAIT_S:.0f} s; `mulebox machine list` shows its "
             "last report")
    return 1


def _show(name: str, row: dict[str, Any]) -> int:
    health = row.get("health") or {}
    lines = problem_lines(name, health)
    if not lines:
        _say(f"{name}: every check passes; it takes jobs")
        return 0
    word = "resting, takes no job" if health.get("resting") else state(health)
    _say(f"{name}: {word}")
    for line in lines:
        print(line)
    return 1
