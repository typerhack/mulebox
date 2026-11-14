"""`mulebox machine config`: read or change a node's settings from the dev machine.

    mulebox machine config <name>                      what it has, what waits, the suggestion
    mulebox machine config <name> --slots 3 --priority preferred [--wait]
    mulebox machine config <name> --dev on|off         dev mode: only jobs sent `--on` it
    mulebox machine config <name> --cancel             drop a change that has not applied yet

The coordinator holds the change and the node writes it into its own node.toml with its next
claim or heartbeat, within seconds while it is online; it counts from its next job, and running
jobs keep their slots (coordinator/node_settings.py, design.md, Node settings).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import Remote, request
from mulebox.common import node_settings as ns
from mulebox.common.protocol import MessageType

WAIT_S = 30.0
POLL_S = 1.0


def register(actions: argparse._SubParsersAction) -> None:
    config = actions.add_parser("config", help="show or change a machine's slots, priority and dev mode")
    config.add_argument("name")
    config.add_argument("--slots", type=int, help=f"jobs at once, {ns.MIN_SLOTS} to {ns.MAX_SLOTS}")
    config.add_argument("--priority", choices=ns.PRIORITIES,
                        help="preferred nodes take jobs first, fallback ones last")
    config.add_argument("--dev", choices=("on", "off"),
                        help="dev mode: the node takes only jobs sent to it with --on")
    config.add_argument("--cancel", action="store_true", help="drop a change still waiting")
    config.add_argument("--wait", action="store_true",
                        help=f"return once the machine applied it (up to {WAIT_S:.0f} s)")
    config.add_argument("--json", action="store_true", help="the coordinator's reply as JSON")
    config.set_defaults(func=guarded(_config))


def _ask(remote: Remote, name: str, **body: Any) -> dict[str, Any]:
    return remote.call(request(MessageType.NODE_SETTINGS, worker=name, **body)).body


def lines(view: dict[str, Any]) -> list[str]:
    """The reply in words, one fact a line."""
    current, pending, tip = view.get("current"), view.get("pending"), view.get("suggested")
    state = "online" if view.get("online") else "offline"
    out = [f"{view['worker']}: {state}, {view.get('running', 0)} job(s) running"]
    if current is None:
        out.append("settings: not reported (a mulebox older than this one, or no claim yet)")
    else:
        out.append(f"slots:     {current['slots']}")
        out.append(f"priority:  {current['priority']}")
        out.append("dev mode:  " + ("on, it takes only jobs sent to it with --on"
                                    if current.get("dev") else "off"))
    if tip:
        out.append(f"suggested: {tip['slots']} slot(s), from {tip['reason']}")
    if pending:
        said = ", ".join(f"{key} {_word(value)}" for key, value in sorted(pending.items()))
        where = "when it is back online" if not view.get("online") else "within seconds"
        out.append(f"waiting:   {said}; the machine applies it {where}")
    if view.get("error"):
        out.append(f"could not apply: {view['error']}")
    return out


def _word(value: Any) -> str:
    return ("on" if value else "off") if isinstance(value, bool) else str(value)


def _config(args: argparse.Namespace) -> int:
    remote = connect()
    body: dict[str, Any] = {key: value for key, value in
                            (("slots", args.slots), ("priority", args.priority),
                             ("dev", None if args.dev is None else args.dev == "on"))
                            if value is not None}
    if args.cancel:
        body["cancel"] = True
    view = _ask(remote, args.name, **body)
    deadline = time.monotonic() + WAIT_S
    while args.wait and view.get("pending") and not view.get("error") and view.get("online") \
            and time.monotonic() < deadline:
        time.sleep(POLL_S)
        view = _ask(remote, args.name)
    if args.json:
        sys.stdout.write(json.dumps(view, indent=2, sort_keys=True) + "\n")
    else:
        print("\n".join(lines(view)))
    return 1 if args.wait and view.get("pending") else 0
