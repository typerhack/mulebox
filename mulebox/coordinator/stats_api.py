"""The `stats` request: job minutes for `mulebox stats` (stats.py has the measure).

Body: `from` and `to` in epoch seconds (`to` defaults to now, `from` to the first job),
optional filters named as stats.GROUPS, `by` (breakdowns, default all) and `day_starts`.
The reply also lists every value each filter can take, so a caller can offer them.
"""

from __future__ import annotations

from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import stats
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.store import Store


def ask(body: dict, now: float) -> dict:
    """The arguments of stats.summary from a request body, checked."""
    end = v.number(body, "to", None)
    start = v.number(body, "from", None)
    filters = {name: v.text(body, name, None) for name in stats.GROUPS}
    if filters["kind"] and filters["kind"] not in stats.KINDS:
        raise BadRequest(f"field 'kind' must be one of {', '.join(stats.KINDS)}")
    by = tuple(v.strings(body, "by")) if "by" in body else stats.GROUPS
    if set(by) - set(stats.GROUPS):
        raise BadRequest(f"field 'by' takes {', '.join(stats.GROUPS)}")
    days = [float(day) for day in body.get("day_starts") or []]
    if len(days) > stats.MAX_DAYS or days != sorted(days):
        raise BadRequest(f"field 'day_starts' must be ascending, at most {stats.MAX_DAYS}")
    end = now if end is None else end
    return {"start": 0.0 if start is None else start, "end": end, "now": now,
            "filters": filters, "by": by, "day_starts": days}


def answer(store: Store, body: dict, now: float) -> dict:
    """The reply body; the dashboard's `/api/stats` gives the same (dashboard/data.py)."""
    asked = ask(body, now)
    with store.read() as conn:
        return {**stats.summary(conn, **asked), "choices": stats.choices(conn)}


def summary(req: Request) -> Message:
    return req.reply(MessageType.STATS_OK, answer(req.store, req.body, req.now))
