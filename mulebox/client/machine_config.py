"""`mulebox machine config`: read or change a node's settings from the dev machine.

    mulebox machine config <name>                      what it has, what waits, the suggestion
    mulebox machine config <name> --slots 3 --priority preferred [--wait]
    mulebox machine config <name> --dev on|off         dev mode: only jobs sent `--on` it
    mulebox machine config <name> --keep-cores 2 --keep-memory 4GB   room kept for the owner
    mulebox machine config <name> --keep-free 20% --unused-days 7 --keep-latest on --idle-days 14
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
    config = actions.add_parser("config", help="show or change a machine's slots, priority, dev "
                                "mode and disk cleanup")
    config.add_argument("name")
    config.add_argument("--slots", type=int, help=f"jobs at once, {ns.MIN_SLOTS} to {ns.MAX_SLOTS}")
    config.add_argument("--priority", choices=ns.PRIORITIES,
                        help="preferred nodes take jobs first, fallback ones last")
    config.add_argument("--dev", choices=("on", "off"),
                        help="dev mode: the node takes only jobs sent to it with --on")
    config.add_argument("--keep-cores", type=float,
                        help="cores kept for the node's owner, out of what sized jobs share")
    config.add_argument("--keep-memory", help='memory kept for the owner, such as "4GB"')
    config.add_argument("--keep-free", help='free space to leave: a share ("10%%") or a size ("50GB")')
    config.add_argument("--unused-days", type=int, help="remove a branch folder unused this long")
    config.add_argument("--keep-latest", choices=("on", "off"),
                        help="keep each project's latest folder however old")
    config.add_argument("--idle-days", type=int, help="suggest cleaning a project idle this long")
    config.add_argument("--slim-hours", type=int, help="slim a branch folder unused this long: "
                        "what git ignores in it goes, the checkout stays (0: never)")
    config.add_argument("--auto-clean", choices=("on", "off"),
                        help="remove on its own; off, it only says what would go")
    config.add_argument("--docker-clean", choices=("on", "off"),
                        help="also remove Docker build cache and images unused that long")
    config.add_argument("--max-size", help='space for mulebox: the most it may hold; past it the '
                        'oldest folders are slimmed, then removed; agents are told from 80%% of it '
                        '("20GB", or off)')
    config.add_argument("--min-free", help='free space under which the node takes no job and '
                        'rests, after its cleanup ("5GB")')
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
        if "keep_cores" in current:
            kept = f"{current['keep_cores']:g} cores, {current['keep_memory']}"
            out.append("owner:     " + ("keeps nothing back from jobs"
                                        if not current["keep_cores"]
                                        and current["keep_memory"] in ("0GB", "0MB", "0TB")
                                        else f"keeps {kept} out of what sized jobs share"))
        if "keep_free" in current:
            out.append(f"disk:      keeps {current['keep_free']} free; removes branch folders "
                       f"unused {current['unused_days']} days, "
                       f"{'keeping' if current['keep_latest'] else 'not keeping'} each "
                       f"project's latest; suggests cleaning after {current['idle_days']} days")
        if "auto_clean" in current:
            out.append("cleanup:   " + ("on its own" if current["auto_clean"] else
                                        "off: nothing goes on its own, it only says what would")
                       + "; Docker " + ("too" if current["docker_clean"] else "never")
                       + "; space for mulebox " + str(current.get("max_size", "off")).lower()
                       + ("" if str(current.get("max_size", "off")).upper() == "OFF"
                          else ", agents told from 80% of it"))
        if "slim_hours" in current:
            hours = current["slim_hours"]
            out.append("slimming:  " + (f"a branch folder unused {hours} hours loses what git "
                                        "ignores in it" if hours else "off"))
        if "min_free" in current:
            out.append(f"rests:     with under {current['min_free']} free (`mulebox machine check`)")
    if tip:
        out.append(f"suggested: {tip['slots']} slot(s), from {tip['reason']}")
    if pending:
        said = ", ".join(f"{key} {_word(value)}" for key, value in sorted(pending.items()))
        where = "when it is back online" if not view.get("online") else "within seconds"
        out.append(f"waiting:   {said}; the machine applies it {where}")
    if view.get("error"):
        out.append(f"could not apply: {view['error']}")
    return out


def _whole(value: float | None) -> float | int | None:
    return int(value) if value is not None and value == int(value) else value


def _flag(value: str | None) -> bool | None:
    return None if value is None else value == "on"


def _word(value: Any) -> str:
    return ("on" if value else "off") if isinstance(value, bool) else str(value)


def _config(args: argparse.Namespace) -> int:
    remote = connect()
    body: dict[str, Any] = {key: value for key, value in
                            (("slots", args.slots), ("priority", args.priority),
                             ("dev", None if args.dev is None else args.dev == "on"),
                             ("keep_cores", _whole(args.keep_cores)),
                             ("keep_memory", args.keep_memory),
                             ("keep_free", args.keep_free), ("unused_days", args.unused_days),
                             ("keep_latest", None if args.keep_latest is None
                              else args.keep_latest == "on"), ("idle_days", args.idle_days),
                             ("auto_clean", _flag(args.auto_clean)),
                             ("docker_clean", _flag(args.docker_clean)),
                             ("max_size", args.max_size),
                             ("slim_hours", args.slim_hours), ("min_free", args.min_free))
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
