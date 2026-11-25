"""The `usage` request: what jobs really used (usage_report.py has the measure).

Body: `job_id` for one run; else the filters named as usage_report.FILTERS, `runs` (the last N
finished runs of each job, default 20) and `all` (failed and cancelled runs too). The reply
always carries `machines`, each machine's cores and memory.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import usage_report
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.store import Store


def answer(store: Store, body: dict[str, Any], now: float) -> dict[str, Any]:
    """The reply body; the dashboard's `/api/usage` gives the same (dashboard/data.py)."""
    job_id = v.text(body, "job_id", None)
    filters = {name: v.text(body, name, None) for name in usage_report.FILTERS}
    if filters["kind"] and filters["kind"] not in usage_report.KINDS:
        raise BadRequest(f"field 'kind' must be one of {', '.join(usage_report.KINDS)}")
    runs = v.integer(body, "runs", None, low=1)
    runs = usage_report.DEFAULT_RUNS if runs is None else min(runs, usage_report.MAX_RUNS)
    every = body.get("all") is True
    with store.read() as conn:
        found: dict[str, Any] = {"machines": usage_report.machines(conn)}
        if job_id is not None:
            found["run"] = usage_report.run(conn, job_id, now)
        else:
            found.update(jobs=usage_report.summary(conn, filters, runs, every), runs=runs,
                         all=every)
    return found


def usage(req: Request) -> Message:
    return req.reply(MessageType.USAGE_OK, answer(req.store, req.body, req.now))
