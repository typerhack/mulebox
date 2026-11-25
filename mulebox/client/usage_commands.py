"""`mulebox usage`: what jobs really used, as the base for job sizes (docs/design.md, Job usage).

    mulebox usage [--project NAME] [--job NAME] [--machine NAME] [--kind job|ci]
                  [--runs N] [--all] [--json]
    mulebox usage <job-id> [--json]

Peak cores are the busiest 10 s of a run, peak memory its largest working set; both count the
job's own processes and its compose services.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from mulebox.client.commands import connect, guarded
from mulebox.client.remote import request
from mulebox.client.report import format_duration
from mulebox.common import units
from mulebox.common.protocol import MessageType

KIND_NAMES = {"job": "job", "ci": "runner"}
SHOWN_KIND = {"job": "mulebox", "runner": "GitHub"}
NOT_MEASURED = "not measured (its node was older than this mulebox)"


def register(sub: argparse._SubParsersAction) -> None:
    usage = sub.add_parser("usage", help="peak cores and memory jobs really used")
    usage.add_argument("job_id", nargs="?", help="one run's numbers")
    usage.add_argument("--project", help="only this project")
    usage.add_argument("--job", help="only this job")
    usage.add_argument("--machine", help="only runs on this machine")
    usage.add_argument("--kind", choices=sorted(KIND_NAMES), help="mulebox's own jobs or CI runs")
    usage.add_argument("--runs", type=int, default=20,
                       help="the last N finished runs of each job (default 20)")
    usage.add_argument("--all", action="store_true",
                       help="failed and cancelled runs too, not only passed ones")
    usage.add_argument("--json", action="store_true", help="the coordinator's reply as JSON")
    usage.set_defaults(func=guarded(_usage))


def cores(value: Any) -> str:
    return "-" if not isinstance(value, (int, float)) else f"{value:.1f}"


def memory(value: Any) -> str:
    return "-" if not isinstance(value, (int, float)) else units.size(value)


def peaks_line(usage: dict[str, Any] | None, average: float | None = None) -> str:
    """One run's peaks in words, for `usage <id>` and `status`."""
    if not usage:
        return NOT_MEASURED
    parts = []
    if usage.get("peak_cores") is None:
        parts.append("cores: too short to measure")
    else:
        stage = usage.get("peak_cores_stage")
        parts.append(f"peak {cores(usage['peak_cores'])} cores" + (f" in {stage}" if stage else ""))
    if usage.get("peak_memory") is not None:
        stage = usage.get("peak_memory_stage")
        parts.append(f"peak {memory(usage['peak_memory'])} memory" + (f" in {stage}" if stage else ""))
    if average is not None:
        parts.append(f"average {cores(average)} cores")
    return ", ".join(parts)


def _spread(found: dict[str, Any] | None, show: Any) -> str:
    return "-" if not found else f"{show(found['median'])} / {show(found['max'])}"


def _fits(found: dict[str, Any] | None) -> str:
    if not found:
        return "-"
    parts = []
    if found.get("cores") is not None:
        parts.append(f"{found['cores']} core{'' if found['cores'] == 1 else 's'}")
    if found.get("memory") is not None:
        parts.append(memory(found["memory"]))
    return ", ".join(parts) or "-"


def render_jobs(found: dict[str, Any]) -> list[str]:
    jobs = found.get("jobs") or []
    which = "finished" if found.get("all") else "passed"
    if not jobs:
        return [f"No {which} run fits these filters yet."]
    head = ("project", "job", "kind", "runs", "cores (median / peak)",
            "memory (median / peak)", "fits every run")
    rows = [(j["project"], j["job"], SHOWN_KIND.get(j["kind"], j["kind"]),
             f"{j['measured']} of {j['runs']}", _spread(j.get("cores"), cores),
             _spread(j.get("memory"), memory), _fits(j.get("fits"))) for j in jobs]
    widths = [max(len(str(r[i])) for r in (head, *rows)) for i in range(len(head))]
    line = lambda r: "  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip()  # noqa: E731
    lines = [f"Peaks of the last {found.get('runs')} {which} runs of each job: the busiest 10 s "
             "of cores, the largest working set of memory.", "", line(head), *map(line, rows)]
    sizes = [f"{name} {m.get('cores') or '?'} cores, {memory(m.get('memory'))}"
             for name, m in (found.get("machines") or {}).items()]
    if sizes:
        lines += ["", "machines: " + "; ".join(sizes)]
    if any(j["not_measured"] for j in jobs):
        lines.append("runs counted as 'n of m': only n were measured, the rest ran on an older node")
    return lines


def render_run(found: dict[str, Any]) -> list[str]:
    run = found["run"]
    took = format_duration(run["run_s"]) if run.get("run_s") else "-"
    return [f"{run['job_id']}  {run['project']} {run['job']}  on {run.get('worker') or '-'}, "
            f"{run.get('outcome') or run['state']}, {took}",
            f"  usage: {peaks_line(run.get('usage'), run.get('average_cores'))}"]


def body(args: argparse.Namespace) -> dict[str, Any]:
    if args.job_id:
        return {"job_id": args.job_id}
    filters = {"project": args.project, "job": args.job, "worker": args.machine,
               "kind": KIND_NAMES.get(args.kind) if args.kind else None}
    return {**{k: v for k, v in filters.items() if v}, "runs": max(1, args.runs),
            **({"all": True} if args.all else {})}


def _usage(args: argparse.Namespace) -> int:
    found = connect().call(request(MessageType.USAGE, **body(args))).body
    if args.json:
        sys.stdout.write(json.dumps(found, indent=2) + "\n")
    else:
        lines = render_run(found) if args.job_id else render_jobs(found)
        sys.stdout.write("\n".join(lines) + "\n")
    return 0
