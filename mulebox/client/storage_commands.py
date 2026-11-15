"""What mulebox holds on each node, and the user's keep marks (design.md, Project folders, Disk
use and cleanup on its own).

    mulebox storage [--json]                      each node: disk, mulebox's folders, what goes when
    mulebox storage --history [N]                 the last N cleanups of every node, newest first
    mulebox storage clean [--node N] [--no-docker] the cleanup now, as the hourly one, even when
                                                  the node's automatic cleanup is off
    mulebox project keep <project> [--branch B]   no automatic rule removes it, on any node
    mulebox project keep <project> [--branch B] --off

The numbers are each node's last sweep (worker/storage_sweep.py), an hour old at most.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.common import units
from mulebox.common.protocol import MessageType

FATES = {"running": "a job runs in it", "kept": "kept by you", "latest": "kept: latest",
         "remove": "goes at the next sweep", "stays": "stays"}


def register(sub: argparse._SubParsersAction) -> None:
    show = sub.add_parser("storage", help="what mulebox holds on each node, and what goes when")
    show.add_argument("--json", action="store_true", help="the coordinator's reply as JSON")
    show.add_argument("--history", nargs="?", type=int, const=20, metavar="N",
                      help="the last N cleanups (20)")
    show.set_defaults(func=guarded(_show))
    actions = show.add_subparsers(dest="action", metavar="clean")
    clean = actions.add_parser("clean", help="run the cleanup now on every node, or one")
    clean.add_argument("--node", help="this node only")
    clean.add_argument("--no-docker", action="store_true", help="leave Docker as it is")
    clean.set_defaults(func=guarded(_clean))


def register_keep(actions: argparse._SubParsersAction) -> None:
    keep = actions.add_parser("keep", help="keep a project's folders, or one branch's, on every node")
    keep.add_argument("project")
    keep.add_argument("--branch", help="only this branch's folder")
    keep.add_argument("--off", action="store_true", help="drop the mark: the usual rules apply")
    keep.set_defaults(func=guarded(_keep))


def _ago(when: float | None, now: float) -> str:
    if when is None:
        return "no job seen"
    days = (now - when) / 86400
    return "today" if days < 1 else f"{int(days)} day{'s' if int(days) != 1 else ''} ago"


def _fate(folder: dict[str, Any]) -> str:
    if folder.get("fate") == "stays" and folder.get("removed_in") is not None:
        days = max(1, round(folder["removed_in"]))
        return f"goes in {days} day{'s' if days != 1 else ''}"
    return FATES.get(folder.get("fate"), str(folder.get("fate")))


def next_line(report: dict[str, Any], now: float) -> str | None:
    """What a cleanup would remove now: the folders planned to go, and when that happens."""
    due = [f for p in report.get("projects", []) for f in p.get("folders", [])
           if f.get("fate") == "remove"]
    if not due:
        return None
    what = f"{len(due)} branch folder(s), {units.size(sum(f['size'] for f in due))}"
    if (report.get("policy") or {}).get("auto_clean") is False:
        return f"would go: {what} (automatic cleanup is off; `mulebox storage clean` removes them)"
    upcoming = report.get("next_sweep")
    when = (f"in {max(1, round((upcoming - now) / 60))} min" if isinstance(upcoming, (int, float))
            else "at the next cleanup")
    return f"goes {when}: {what} (`mulebox storage clean` removes them now)"


def node_lines(node: dict[str, Any], names: dict[str, dict[str, str]], now: float) -> list[str]:
    """One node's report in words."""
    report = node.get("report")
    state = "online" if node.get("online") else "offline"
    if report is None:
        return [f"{node['node']}: {state}, no report yet (a mulebox older than 1.24, or its first "
                "sweep has not run; it runs a minute after the worker starts)"]
    disk = report["disk"]
    minutes = max(0, int((now - report.get("measured_at", report["at"])) / 60))
    out = [f"{node['node']}: {state}, measured {minutes} min ago",
           f"  disk: {units.size(disk['total'] - disk['free'])} used of {units.size(disk['total'])}, "
           f"{units.size(disk['free'])} free, keeping {units.size(disk['reserve'])} free"]
    due = next_line(report, now)
    if due:
        out.append(f"  {due}")
    for project in report.get("projects", []):
        folders = project.get("folders", [])
        total = sum(f["size"] for f in folders) + project.get("home", 0)
        out.append(f"  {project['project']}: {units.size(total)} in {len(folders)} branch "
                   f"folder(s), caches {units.size(project.get('caches', 0))}")
        named = names.get(project["project"], {})
        for folder in sorted(folders, key=lambda f: -(f.get("last_used") or 0)):
            out.append(f"    {named.get(folder['folder'], folder['folder'])}: "
                       f"{units.size(folder['size'])}, last job {_ago(folder.get('last_used'), now)}, "
                       f"{_fate(folder)}")
    shared = report.get("shared", {})
    if shared:
        out.append("  shared: " + ", ".join(f"{key.replace('_', ' ')} {units.size(value)}"
                                            for key, value in shared.items() if value))
    for kind, row in sorted((report.get("docker") or {}).items()):
        out.append(f"  docker {kind.replace('_', ' ')}: {units.size(row.get('size') or 0)}, "
                   f"{units.size(row.get('reclaimable') or 0)} unused (all of Docker, not only "
                   "mulebox's)")
    removed = report.get("removed") or {}
    if removed.get("count"):
        out.append(f"  last sweep removed {removed['count']} folder(s), "
                   f"{units.size(removed['bytes'])}")
    for idle in report.get("idle", []):
        out.append(f"  suggestion: {idle['project']} had no job for {idle['days']} days; its "
                   f"folders take {units.size(idle['size'])}: `mulebox project reset "
                   f"{idle['project']} --yes` removes them, or keep them")
    short = report.get("short")
    if short:
        out.append(f"  short of space: {units.size(short['need'])} under what it keeps free; "
                   f"these could go ({units.size(short['could_free'])}), your call:")
        for folder in short["folders"]:
            name = names.get(folder["project"], {}).get(folder["folder"], folder["folder"])
            out.append(f"    `mulebox project reset {folder['project']} --branch {name} --yes`, "
                       f"{units.size(folder['size'])}")
    return out


def history_lines(sweeps: list[dict[str, Any]], now: float) -> list[str]:
    """Each cleanup in a line, newest first, and what it removed under it."""
    out = []
    for sweep in sweeps:
        freed = sweep.get("free_after", 0) - sweep.get("free_before", 0)
        docker = sweep.get("docker") or {}
        took = (docker.get("build_cache") or 0) + (docker.get("images") or 0)
        out.append(f"{sweep['node']}: {_ago(sweep.get('started'), now)}, {sweep.get('trigger')}: "
                   f"{sweep.get('count', 0)} folder(s), {units.size(sweep.get('bytes', 0))}"
                   + (f", docker {units.size(took)}" if docker else "")
                   + f"; free {units.size(sweep.get('free_before', 0))} to "
                   f"{units.size(sweep.get('free_after', 0))} ({units.size(max(freed, 0))} more)"
                   + ("" if sweep.get("auto", True) else
                      f"; automatic cleanup off, {sweep.get('would_remove', 0)} would go"))
        for folder in sweep.get("removed", []):
            out.append(f"    {folder['project']} {folder['folder']}: {units.size(folder['size'])}, "
                       f"{WHY.get(folder.get('why'), folder.get('why'))}")
        out += [f"    could not: {error}" for error in sweep.get("errors", [])]
    return out or ["no cleanup has run yet (nodes on 1.26 or later keep a history)"]


WHY = {"gone": "its branch is on no dev machine", "unused": "no job for the set days",
       "size": "over the node's size limit"}


def _clean(args: argparse.Namespace) -> int:
    from mulebox.client.project_commands import follow
    body = {"action": "sweep", "docker": not args.no_docker,
            **({"node": args.node} if args.node else {})}
    return follow(connect(), body)


def _show(args: argparse.Namespace) -> int:
    body = connect().call(request(MessageType.STORAGE, **(
        {"history": args.history} if args.history else {}))).body
    if args.history and not args.json:
        print("\n".join(history_lines(body.get("history") or [], time.time())))
        return 0
    if args.json:
        sys.stdout.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
        return 0
    now = time.time()
    out = []
    for node in body["nodes"]:
        out += node_lines(node, body.get("branches") or {}, now)
    if body.get("keeps"):
        out.append("kept by you: " + ", ".join(
            k["project"] + (f" {k['branch']}" if k.get("branch") else "") for k in body["keeps"]))
    print("\n".join(out) if out else "no node has reported yet")
    return 0


def _keep(args: argparse.Namespace) -> int:
    body = {"project": args.project, "keep": not args.off,
            **({"branch": args.branch} if args.branch else {})}
    marks = connect().call(request(MessageType.STORAGE_KEEP, **body)).body["keeps"]
    what = args.project + (f" {args.branch}" if args.branch else "")
    print(f"{what}: {'no longer kept; the usual rules apply' if args.off else 'kept on every node'}")
    print("kept: " + (", ".join(m["project"] + (f" {m['branch']}" if m.get("branch") else "")
                               for m in marks) or "nothing"))
    return 0
