"""`mulebox stats`: how long jobs ran on the machines (coordinator/stats.py has the measure).

    mulebox stats [--days N] [--by project|job|source|machine|kind] [--project NAME]
                  [--source NAME] [--machine NAME] [--kind job|ci] [--json]

Wall time, added up: two jobs side by side for ten minutes count twenty. Days are this
dev machine's own, from local midnight; the coordinator only adds up the ranges it is given.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.client.report import format_duration
from mulebox.common.protocol import MessageType

KIND_NAMES = {"job": "job", "ci": "runner"}
SHOWN_KIND = {"job": "mulebox", "runner": "GitHub"}
BY = {"project": "project", "job": "job", "source": "client", "machine": "worker", "kind": "kind"}


def register(sub: argparse._SubParsersAction) -> None:
    stats = sub.add_parser("stats", help="how long jobs ran: today, by day and in total")
    stats.add_argument("--days", type=int, default=7, help="days shown one by one (default 7)")
    stats.add_argument("--by", choices=sorted(BY), default="project",
                       help="the breakdown since the first job (default project)")
    stats.add_argument("--project", help="only this project")
    stats.add_argument("--source", help="only jobs from this dev machine, or github")
    stats.add_argument("--machine", help="only jobs on this machine")
    stats.add_argument("--kind", choices=sorted(KIND_NAMES), help="mulebox's own jobs or CI runs")
    stats.add_argument("--json", action="store_true", help="the coordinator's reply as JSON")
    stats.set_defaults(func=guarded(_stats))


def day_starts(days: int, now: float) -> list[float]:
    """Local midnight of each of the last `days` days, oldest first, today last."""
    today = time.localtime(now)
    return [time.mktime((today.tm_year, today.tm_mon, today.tm_mday - back, 0, 0, 0, 0, 0, -1))
            for back in range(max(1, days) - 1, -1, -1)]


def body(args: argparse.Namespace, now: float) -> dict[str, Any]:
    filters = {"project": args.project, "client": args.source, "worker": args.machine,
               "kind": KIND_NAMES.get(args.kind) if args.kind else None}
    return {**{k: v for k, v in filters.items() if v}, "by": [BY[args.by]],
            "day_starts": day_starts(min(args.days, 400), now)}


def _amount(row: dict[str, Any]) -> str:
    runs = row.get("runs", 0)
    parts = [f"{format_duration(row.get('seconds') or 0):>8}", f"{runs} run{'' if runs == 1 else 's'}"]
    if row.get("running"):
        parts.append(f"{row['running']} running")
    if row.get("unknown"):
        parts.append(f"{row['unknown']} with no length")
    return "  ".join(parts)


def _label(group: str, key: Any) -> str:
    if group == "kind":
        return SHOWN_KIND.get(key, str(key))
    return "GitHub" if group == "client" and key == "github" else str(key or "-")


def render(found: dict[str, Any], by: str) -> list[str]:
    first = found.get("first_started_at")
    if first is None:
        return ["No job has run yet" + (" that fits these filters." if found.get("filters") else ".")]
    since = time.strftime("%Y-%m-%d", time.localtime(first))
    days = found.get("days") or []
    lines = ["Job minutes: wall time on the machines; jobs side by side add up.",
             f"{'since ' + since:<18}{_amount(found['total'])}"]
    if days:
        lines.append(f"{'today':<18}{_amount(days[-1])}")
        lines += ["", "day"]
        lines += [f"  {time.strftime('%a %m-%d', time.localtime(day['from'])):<16}{_amount(day)}"
                  for day in days]
    rows = found.get("by", {}).get(BY[by], [])
    if rows:
        width = max(len(_label(BY[by], row["key"])) for row in rows) + 2
        lines += ["", f"by {by}, since {since}"]
        lines += [f"  {_label(BY[by], row['key']):<{width}}{_amount(row)}" for row in rows]
    return lines


def _stats(args: argparse.Namespace) -> int:
    found = connect().call(request(MessageType.STATS, **body(args, time.time()))).body
    if args.json:
        sys.stdout.write(json.dumps(found, indent=2) + "\n")
    else:
        sys.stdout.write("\n".join(render(found, args.by)) + "\n")
    return 0
