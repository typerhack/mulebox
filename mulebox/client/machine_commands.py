"""`mulebox machine`: the nodes of the queue, from the dev machine (docs/install.md).

    mulebox machine list
    mulebox machine drain <name> [--wait]    (also `machine pause`)
    mulebox machine resume <name>
    mulebox machine remove <name>

`drain` lets a machine finish its jobs and take no new ones; `--wait` returns once they ended.
`remove` makes the coordinator forget a machine that is stopped and has no jobs, and takes its
key off the coordinator (coordinator/machine_api.py, coordinator/worker_keys.py).
"""

from __future__ import annotations

import argparse
import sys
import time

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import Remote, request
from mulebox.client.report import format_size
from mulebox.client.setup_worker import marker_name
from mulebox.common import ssh
from mulebox.common.protocol import MessageType

POLL_S = 5.0
KEY_TIMEOUT_S = 30


def register(sub: argparse._SubParsersAction) -> None:
    machine = sub.add_parser("machine", help="list, pause (drain), resume or remove nodes")
    actions = machine.add_subparsers(dest="machine_command", metavar="<action>", required=True)
    actions.add_parser("list", help="every machine, online or not").set_defaults(
        func=guarded(_list))
    drain = actions.add_parser("drain", aliases=["pause"],
                               help="let a machine finish its jobs and take no new ones")
    drain.add_argument("name")
    drain.add_argument("--wait", action="store_true", help="return once its jobs have ended")
    drain.set_defaults(func=guarded(_drain))
    resume = actions.add_parser("resume", help="let a drained machine take jobs again")
    resume.add_argument("name")
    resume.set_defaults(func=guarded(_resume))
    remove = actions.add_parser("remove", help="forget a stopped machine and take its key off")
    remove.add_argument("name")
    remove.set_defaults(func=guarded(_remove))


def _say(line: str) -> None:
    print(f"mulebox: {line}", file=sys.stderr, flush=True)


def _act(remote: Remote, name: str, action: str) -> list[str]:
    reply = remote.call(request(MessageType.MACHINE, worker=name, action=action))
    return list(reply.body["running"])


def state(row: dict) -> str:
    if row.get("draining"):
        return "draining" if row.get("online") else "drained, offline"
    return "online" if row.get("online") else "offline"


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}%"


def per_second(kib_s: float | None) -> str:
    """Network in or out over the machine's physical interfaces (common/netdev.py)."""
    return "-" if kib_s is None else f"{format_size(int(kib_s * 1024))}/s"


def _list(args: argparse.Namespace) -> int:
    rows = connect().call(request(MessageType.MACHINES)).body.get("workers", [])
    if not rows:
        print("no machines yet")
        return 0
    print(f"{'NAME':<20} {'STATE':<17} {'SLOTS':>5} {'CPU':>5} {'MEM':>5} {'NET IN':>13} "
          f"{'NET OUT':>13}  {'VERSION':<9} OFFERS")
    for row in rows:
        load = row.get("load") or {}
        print(f"{row['worker']:<20} {state(row):<17} {row.get('slots') or '-':>5} "
              f"{percent(load.get('cpu_pct')):>5} {percent(load.get('mem_pct')):>5} "
              f"{per_second(load.get('net_in_kib_s')):>13} "
              f"{per_second(load.get('net_out_kib_s')):>13}  "
              f"{row.get('version') or '-':<9} {', '.join(row.get('capabilities') or []) or '-'}")
    return 0


def _drain(args: argparse.Namespace) -> int:
    remote = connect()
    running = _act(remote, args.name, "drain")
    _say(f"{args.name} takes no new jobs; `mulebox machine resume {args.name}` undoes it")
    told = None
    while running and args.wait:
        if len(running) != told:
            told = len(running)
            _say(f"waiting for {told} job(s) on {args.name}: {', '.join(running)}")
        time.sleep(POLL_S)
        running = _act(remote, args.name, "drain")
    if running:
        _say(f"{len(running)} job(s) still on it: {', '.join(running)}")
    else:
        _say(f"{args.name} has no jobs")
    return 0


def _resume(args: argparse.Namespace) -> int:
    _act(connect(), args.name, "resume")
    _say(f"{args.name} takes jobs again")
    return 0


def _remove(args: argparse.Namespace) -> int:
    remote = connect()
    _act(remote, args.name, "remove")
    _say(f"{remote.target} forgot {args.name}")
    result = ssh.run_remote(remote.target, [remote.program, "authorize-worker",
                                            marker_name(args.name), "--remove"],
                            timeout_s=KEY_TIMEOUT_S, connect_timeout_s=remote.connect_timeout_s,
                            check=False)
    note = result.stderr.decode("utf-8", errors="replace").strip()
    _say(note.removeprefix("mulebox: ") if result.exit_code == 0 else
         f"its key could not be taken off ({note}); remove the line ending in "
         f"`mulebox-worker:{marker_name(args.name)}` from ~/.ssh/authorized_keys on {remote.target}")
    return 0
