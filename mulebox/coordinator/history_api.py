"""Finished jobs, newest first, with the History page's filters (history_query.py): the
`history` request for `mulebox history`, and the dashboard's `/api/history` (dashboard/data.py).

Body: the filters as strings (project, job, client, worker, kind, result, q), `before` (the
last `finished_at` seen, to page) and `limit` (1 to MAX, DEFAULT if left out).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.common.protocol import Message, MessageType
from mulebox.common.status import shown_state
from mulebox.coordinator import history_query, stats
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.views import reservation_dict

DEFAULT = 50
MAX = 200


def page(conn: sqlite3.Connection, chosen: dict[str, str], before: float | None,
         limit: int = DEFAULT) -> dict[str, Any]:
    """One page of finished jobs; the first page also lists every value each filter can take."""
    where, params = history_query.where(chosen, before)
    limit = max(1, min(MAX, limit))
    jobs = st.select_jobs(conn, where, params, "finished_at DESC, seq DESC", limit=limit)
    rows = [{**reservation_dict(job), "duration_s": job["duration_s"]} for job in jobs]
    rows = [{**row, "shown_state": shown_state(row)} for row in rows]
    more = len(rows) == limit
    return {"jobs": rows, "next_before": rows[-1]["finished_at"] if more else None,
            **({"choices": stats.choices(conn)} if before is None else {})}


def history(req: Request) -> Message:
    asked = {name: str(req.body[name]) for name in (*stats.GROUPS, "result", "q")
             if req.body.get(name) not in (None, "")}
    chosen = history_query.filters(asked)
    limit = int(v.number(req.body, "limit", DEFAULT))
    with req.store.read() as conn:
        return req.reply(MessageType.HISTORY_OK,
                         page(conn, chosen, v.number(req.body, "before", None), limit))
