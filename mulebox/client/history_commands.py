"""`mulebox history`: finished jobs, newest first, with the dashboard History page's filters
(coordinator/history_api.py). In a project it shows that project's jobs unless `--all`.

    mulebox history [--all | --project NAME] [--job NAME] [--result passed|failed|cancelled]
                    [--search TEXT] [--source NAME] [--machine NAME] [--kind job|ci]
                    [--limit N] [--before T] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.client.report import format_duration
from mulebox.common.config import ConfigError, find_project_config, load_project_config
from mulebox.common.protocol import MessageType

KINDS = {"job": "job", "ci": "runner"}


def register(sub: argparse._SubParsersAction) -> None:
    found = sub.add_parser("history", help="finished jobs, newest first, with filters")
    which = found.add_mutually_exclusive_group()
    which.add_argument("--all", action="store_true", help="every project, not only this one")
    which.add_argument("--project", help="only this project (default: the one here)")
    found.add_argument("--job", help="only this job, such as check")
    found.add_argument("--result", choices=("passed", "failed", "cancelled"))
    found.add_argument("--search", metavar="TEXT", help="part of a project, job or branch name")
    found.add_argument("--source", help="only jobs from this dev machine, or github")
    found.add_argument("--machine", help="only jobs that ran on this node")
    found.add_argument("--kind", choices=sorted(KINDS), help="mulebox's own jobs or CI runs")
    found.add_argument("--limit", type=int, default=20, help="how many (default 20, at most 200)")
    found.add_argument("--before", type=float, metavar="T",
                       help="older than this finished_at: the next_before of the page before")
    found.add_argument("--json", action="store_true", help="the coordinator's reply as JSON")
    found.set_defaults(func=guarded(_history))


def _here() -> str | None:
    try:
        return load_project_config(find_project_config(Path.cwd())).project
    except ConfigError:
        return None


def body(args: argparse.Namespace) -> dict[str, Any]:
    project = None if args.all else args.project or _here()
    asked = {"project": project, "job": args.job, "result": args.result, "q": args.search,
             "client": args.source, "worker": args.machine,
             "kind": KINDS[args.kind] if args.kind else None,
             "limit": args.limit, "before": args.before}
    return {name: value for name, value in asked.items() if value not in (None, "")}


def line(job: dict[str, Any]) -> str:
    ended = time.strftime("%Y-%m-%d %H:%M", time.localtime(job.get("finished_at") or 0))
    took = format_duration(job["duration_s"]) if job.get("duration_s") is not None else "-"
    code = job.get("exit_code")
    return (f"{job.get('job_id', '')}  {ended}  {job.get('shown_state', ''):<11} "
            f"{'' if code is None else f'exit {code}':<8} {took:>8}  "
            f"{job.get('project', '')}/{job.get('job', '')}  {job.get('branch') or ''}")


def _history(args: argparse.Namespace) -> int:
    asked = body(args)
    reply = connect().call(request(MessageType.HISTORY, **asked)).body
    if args.json:
        print(json.dumps(reply, sort_keys=True))
        return 0
    jobs = reply.get("jobs") or []
    if not jobs:
        print("No finished job fits these filters.", file=sys.stderr)
        return 0
    for job in jobs:
        print(line(job))
    if reply.get("next_before"):
        print(f"more: mulebox history --before {reply['next_before']} with the same filters",
              file=sys.stderr)
    return 0
