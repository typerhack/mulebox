"""The order rules of the line, from the dev machine (coordinator/line_rules.py).

    mulebox queue rules [--json]                          show them
    mulebox queue rules [--project NAME=LEVEL]... [--branch PATTERN=LEVEL]... [--github LEVEL]
                        [--workflow NAME=LEVEL]... [--aging MIN] [--shortest-first on|off]
                        [--fair-turns on|off]
    mulebox queue rules --reset                           back to arrival order
    mulebox project priority <project> [LEVEL]            one project's level

A level is low, normal, high or a whole number from -3 to 3; normal (0) removes the entry. The
rules live on the coordinator, never in `.mulebox.yml`, so a project cannot raise itself.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from mulebox.client.commands import UsageError, connect, guarded
from mulebox.client.remote import request
from mulebox.common.protocol import MessageType

SWITCH = {"on": True, "off": False}


def register(sub: argparse._SubParsersAction) -> None:
    """`rules` under `mulebox queue` (client/commands.py), which keeps working with no action."""
    actions = sub.choices["queue"].add_subparsers(dest="queue_command", metavar="<action>")
    rules = actions.add_parser("rules", help="show or set the order rules of the line")
    rules.add_argument("--project", action="append", default=[], metavar="NAME=LEVEL",
                       help="a project's level (repeat for more)")
    rules.add_argument("--branch", action="append", default=[], metavar="PATTERN=LEVEL",
                       help="a branch's level, such as main=1 or 'release/*=1' (repeat)")
    rules.add_argument("--github", metavar="LEVEL", help="the level of GitHub runs")
    rules.add_argument("--workflow", action="append", default=[], metavar="NAME=LEVEL",
                       help="a GitHub workflow's level, by its name: such as CI=1 (repeat)")
    rules.add_argument("--aging", type=int, metavar="MIN",
                       help="every MIN minutes in line add one level (0: off)")
    rules.add_argument("--shortest-first", choices=SWITCH, help="shorter usual jobs first")
    rules.add_argument("--fair-turns", choices=SWITCH, help="projects take turns")
    rules.add_argument("--reset", action="store_true", help="every rule back to its default")
    rules.add_argument("--json", action="store_true", help="stable keys for tools")
    rules.set_defaults(func=guarded(_rules))


def add_priority(actions: argparse._SubParsersAction) -> None:
    """`priority` under `mulebox project`."""
    priority = actions.add_parser("priority", help="show or set a project's level in the line")
    priority.add_argument("project", help="the name as `mulebox projects` shows it")
    priority.add_argument("level", nargs="?", help="low, normal, high or -3..3")
    priority.set_defaults(func=guarded(_priority))


def _pairs(values: list[str], what: str) -> dict[str, str]:
    out = {}
    for value in values:
        name, sep, level = value.rpartition("=")
        if not sep or not name:
            raise UsageError(f"--{what} wants NAME=LEVEL, got {value!r}")
        out[name] = level
    return out


def change_from(args: argparse.Namespace) -> dict[str, Any]:
    """The partial change the options ask for; empty when they only ask to show."""
    change: dict[str, Any] = {}
    if args.project:
        change["projects"] = _pairs(args.project, "project")
    if args.branch:
        change["branches"] = _pairs(args.branch, "branch")
    if args.workflow:
        change["workflows"] = _pairs(args.workflow, "workflow")
    if args.github is not None:
        change["github"] = args.github
    if args.aging is not None:
        change["aging_min"] = args.aging
    for name in ("shortest_first", "fair_turns"):
        if getattr(args, name) is not None:
            change[name] = SWITCH[getattr(args, name)]
    return change


def _levels(found: dict[str, int]) -> str:
    return ", ".join(f"{name} {level:+d}" for name, level in sorted(found.items())) or "none"


def render(body: dict[str, Any]) -> list[str]:
    rules = body["rules"]
    aging = rules["aging_min"]
    on = bool(rules["projects"] or rules["branches"] or rules["github"]
              or rules.get("workflows") or rules["shortest_first"] or rules["fair_turns"])
    return [
        "The line, each step breaking the ties of the one before:",
        "  1. moves by hand (mulebox first|up|down|last), each pinning only the moved job",
        "  2. levels, higher first:",
        f"       projects       {_levels(rules['projects'])}",
        f"       branches       {_levels(rules['branches'])}",
        f"       GitHub runs    {rules['github']:+d}",
        f"       workflows      {_levels(rules.get('workflows') or {})}",
        f"       waiting        " + (f"+1 every {aging} min in line" if aging else "off"),
        f"  3. fair turns between projects: {'on' if rules['fair_turns'] else 'off'}",
        f"  4. shortest first: {'on' if rules['shortest_first'] else 'off'}",
        "  5. arrival",
        "Every rule is at its default: first come, first served." if not on else
        "`mulebox queue` and `mulebox status` say why each waiting job is where it is.",
    ]


def _send(body: dict[str, Any]) -> dict[str, Any]:
    return connect().call(request(MessageType.QUEUE_RULES, **body)).body


def _rules(args: argparse.Namespace) -> int:
    change = change_from(args)
    if args.reset and change:
        raise UsageError("--reset goes alone")
    body = (_send({"action": "reset"}) if args.reset else
            _send({"action": "set", "rules": change}) if change else _send({"action": "get"}))
    print(json.dumps(body, indent=2, sort_keys=True) if args.json else "\n".join(render(body)))
    return 0


def _priority(args: argparse.Namespace) -> int:
    if args.level is None:
        body = _send({"action": "get"})
    else:
        body = _send({"action": "set", "rules": {"projects": {args.project: args.level}}})
    level = body["rules"]["projects"].get(args.project, 0)
    print(f"{args.project}\tlevel " + (f"{level:+d}" if level else "0 (normal)"))
    return 0
