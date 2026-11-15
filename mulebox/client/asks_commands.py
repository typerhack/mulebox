"""Agents asking for more space, the owner's answer, the settings history and the Agents option
(coordinator/setting_asks.py; design.md, Agents asking for more space).

    mulebox storage ask --size 30GB --reason "..." [--node N] [--job ID]
                                     an agent, with its user's yes: more space for mulebox
    mulebox storage requests         what waits for an answer
    mulebox storage approve [--node N] [--size S]    the owner: yes, at the size asked or another
    mulebox storage decline [--node N] [--note T]    the owner: no, with a note for the agent
    mulebox storage changes [N]      the settings history: who asked, why, who confirmed
    mulebox storage undo <change>    back to the value before that change
    mulebox agents [ask|allow]       whether an agent's request needs the owner's yes
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.client.report import format_duration
from mulebox.common.protocol import MessageType

OPTION_WORDS = {"ask": "ask me first: a request waits for the owner's answer",
                "allow": "allow, and record it: a request is applied at once and recorded"}
HOW = {"owner": "changed by the owner", "approved": "approved as asked",
       "approved_other": "approved at another value", "declined": "declined",
       "allowed": "applied without asking, as allowed", "undo": "undone",
       "agents": "Agents option changed"}


def register_actions(actions: argparse._SubParsersAction) -> None:
    ask = actions.add_parser("ask", help="an agent: ask for more space for mulebox on a node, "
                                         "only with the user's yes")
    ask.add_argument("--size", required=True, help="the space asked for, such as 30GB")
    ask.add_argument("--reason", required=True, help="why, in a sentence the user reads")
    ask.add_argument("--node", help="the node (needed when there are several)")
    ask.add_argument("--job", help="the job that needs it")
    ask.set_defaults(func=guarded(_ask))
    listed = actions.add_parser("requests", help="requests for more space that wait for an answer")
    listed.add_argument("--json", action="store_true")
    listed.set_defaults(func=guarded(_requests))
    for name, yes in (("approve", True), ("decline", False)):
        answer = actions.add_parser(name, help=f"the owner: {name} the request waiting")
        answer.add_argument("--node", help="the node (needed when several have requests)")
        if yes:
            answer.add_argument("--size", help="another size than asked")
        else:
            answer.add_argument("--note", help="a word for the agent")
        answer.set_defaults(func=guarded(_answer), approve=yes)
    changes = actions.add_parser("changes", help="the settings history of every node")
    changes.add_argument("count", nargs="?", type=int, default=20)
    changes.add_argument("--json", action="store_true")
    changes.set_defaults(func=guarded(_changes))
    undo = actions.add_parser("undo", help="undo a change from the settings history")
    undo.add_argument("change", help="its id, from `mulebox storage changes`")
    undo.set_defaults(func=guarded(_undo))


def register(sub: argparse._SubParsersAction) -> None:
    agents = sub.add_parser("agents", help="whether an agent's request for a setting needs your yes")
    agents.add_argument("option", nargs="?", choices=("ask", "allow"))
    agents.set_defaults(func=guarded(_agents))


def _by(command: str) -> str:
    return f"`mulebox storage {command}` on {socket.gethostname() or 'a dev machine'}"


def _call(**body: Any) -> dict[str, Any]:
    return connect().call(request(MessageType.ASKS, **body)).body


def _project() -> str | None:
    from mulebox.client.commands import ProjectNotFound, project_here
    from mulebox.common.config import ConfigError
    try:
        return project_here()[0].project
    except (ConfigError, ProjectNotFound):  # outside a project the request names none
        return None


def _ask(args: argparse.Namespace) -> int:
    body = _call(action="ask", value=args.size, reason=args.reason, project=_project(),
                 client=socket.gethostname() or None,
                 **{key: value for key, value in (("node", args.node), ("job_id", args.job))
                    if value})
    asked = body["ask"]
    if asked["state"] == "applied":
        print(f"{asked['node']}: mulebox may now use {asked['value']}; the owner allows agents "
              "to change it, and the change is recorded")
    else:
        print(f"{asked['node']}: asked for {asked['value']}; it waits for the owner's answer on "
              "the dashboard. Keep working; your next command from this project tells the answer")
    return 0


def ask_line(item: dict[str, Any], now: float) -> str:
    who = " ".join(filter(None, (item.get("project"), item.get("client") and
                                 f"from {item['client']}", item.get("job_id"))))
    return (f"{item['node']}: {item['value']} asked {format_duration(now - item['asked_at'])} ago"
            f"{f' by {who}' if who else ''}: {item['reason']}")


def _requests(args: argparse.Namespace) -> int:
    body = _call(action="read", history=1)
    if args.json:
        sys.stdout.write(json.dumps(body["asks"], indent=2, sort_keys=True) + "\n")
        return 0
    now = time.time()
    print("\n".join(ask_line(item, now) for item in body["asks"]) or "no request waits")
    print(f"agents: {OPTION_WORDS[body['agents']]}")
    return 0


def _answer(args: argparse.Namespace) -> int:
    extra = {"value": args.size} if args.approve and args.size else {}
    if not args.approve and args.note:
        extra["note"] = args.note
    body = _call(action="answer", approve=args.approve, by=_by("approve" if args.approve
                                                                else "decline"),
                 **({"node": args.node} if args.node else {}), **extra)
    change = next((row for row in body["changes"] if row["id"] == body["change_id"]), {})
    print(change_line(change, time.time()))
    return 0


def change_line(row: dict[str, Any], now: float) -> str:
    when = format_duration(now - float(row.get("at") or now))
    what = (f"{row.get('node')}, {row.get('setting')}: {row.get('old')} to {row.get('new')}"
            if row.get("how") != "declined" else f"{row.get('node')}, {row.get('setting')}: "
            f"stays {row.get('old')}")
    if row.get("how") == "agents":
        what = f"agents: {row.get('old')} to {row.get('new')}"
    asked = row.get("asked") or {}
    tail = f"; asked {asked['value']}" if asked.get("value") else ""
    by = f"; by {row['by']}" if row.get("by") else "; nobody confirmed"
    note = f"; note: {asked['note']}" if asked.get("note") else ""
    undo = f"  (undo: mulebox storage undo {row['id']})" if row.get("undoable") else ""
    return f"{when} ago  {what}, {HOW.get(str(row.get('how')), row.get('how'))}{tail}{by}{note}{undo}"


def _changes(args: argparse.Namespace) -> int:
    body = _call(action="read", history=max(1, min(args.count, 500)))
    if args.json:
        sys.stdout.write(json.dumps(body["changes"], indent=2, sort_keys=True) + "\n")
        return 0
    now = time.time()
    print("\n".join(change_line(row, now) for row in body["changes"]) or "no change recorded yet")
    return 0


def _undo(args: argparse.Namespace) -> int:
    body = _call(action="undo", change=args.change, by=_by("undo"))
    change = next((row for row in body["changes"] if row["id"] == body["change_id"]), {})
    print(change_line(change, time.time()))
    return 0


def _agents(args: argparse.Namespace) -> int:
    if args.option:
        body = _call(action="agents", option=args.option,
                     by=f"`mulebox agents` on {socket.gethostname() or 'a dev machine'}")
    else:
        body = _call(action="read", history=1)
    print(f"agents: {OPTION_WORDS[body['agents']]}")
    return 0
