"""Moves by hand in the line (`mulebox first|up|down|last`, the dashboard's arrows): the pin
the moved row gets (line.py). Only that row is written; every other row stays where the rules
put it.

A row goes to the gap its move asks for, and is pinned to the place of the row right after
that gap (`before` it), or, at the end of the line, of the row right before it (`after` it).
When that neighbour is itself pinned, the moved row joins it at the same place, just ahead of
or behind it (`pin_order`). `first` pins to the front. So in a first-come line `up` gives the
row the place just ahead of the one it passed, `down` just behind it, and `last` just behind
the last row, ahead of jobs sent later; if that row starts first, the moved row takes its place.
"""

from __future__ import annotations

from typing import Any

from mulebox.coordinator.line import AFTER, BEFORE, FRONT, Line

MOVES = ("first", "up", "down", "last")


def front(order: Line, job: dict[str, Any]) -> dict[str, Any]:
    """The columns that put `job` ahead of every row at the front, or nothing if it leads."""
    ahead = [pin[2] for job_id, pin in order.pins.items()
             if pin[0] == FRONT and job_id != job["job_id"]]
    if order.pins.get(job["job_id"], (None,))[0] == FRONT and order.rank.get(job["job_id"]) == 0:
        return {}
    return pinned(FRONT, None, min(ahead) - 1 if ahead else 0.0)


def pinned(side: str, anchor: str | None, value: float) -> dict[str, Any]:
    return {"pin_side": side, "pin_job": anchor, "pin_order": value, "priority": 0}


def move(order: Line, job: dict[str, Any], to: str) -> dict[str, Any]:
    """The columns that move queued `job` `to` (one of MOVES); nothing when it stays put."""
    if to == "first":
        return front(order, job)
    rest = [row for row in order.rows if row["job_id"] != job["job_id"]]
    at = order.rank[job["job_id"]]
    place = {"last": len(rest), "up": max(at - 1, 0), "down": min(at + 1, len(rest))}[to]
    if place == at:
        return {}
    after = rest[place] if place < len(rest) else None
    before = rest[place - 1] if place > 0 else None
    return _between(order, before, after)


def _between(order: Line, prev: dict[str, Any] | None, nxt: dict[str, Any] | None
             ) -> dict[str, Any]:
    def pin(row: dict[str, Any] | None) -> tuple[str, str | None, float] | None:
        return None if row is None else order.pins.get(row["job_id"])

    had = pin(prev)
    if nxt is not None:
        found = pin(nxt)
        if found is None:  # a row in its place by the rules: just ahead of it
            same = had is not None and had[:2] == (BEFORE, nxt["job_id"])
            return pinned(BEFORE, nxt["job_id"], had[2] + 1 if same else 0.0)
        side, anchor, value = found
        same = had is not None and had[:2] == (side, anchor)
        return pinned(side, anchor, (had[2] + value) / 2 if same else value - 1)
    assert prev is not None  # a line of one row has nowhere to move
    if had is None:
        return pinned(AFTER, prev["job_id"], 0.0)
    return pinned(had[0], had[1], had[2] + 1)
