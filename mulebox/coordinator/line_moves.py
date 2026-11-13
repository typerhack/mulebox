"""Moves by hand in the line (`mulebox first|up|down|last`, the dashboard's arrows): the pin
the moved row gets (line.py). Only that row gets a new place; every other row stays where the
rules put it.

A row goes to the gap its move asks for, and is pinned to the place of the row right after
that gap (`before` it), or, at the end of the line, of the row right before it (`after` it).
When that neighbour is itself pinned, the moved row joins it at the same place, just ahead of
or behind it (`pin_order`). `first` pins to the front. So in a first-come line `up` gives the
row the place just ahead of the one it passed, `down` just behind it, and `last` just behind
the last row, ahead of jobs sent later; if that row starts first, the moved row takes its place.

A pin leaves the row's own `priority` (set by hand before pins existed) as it is: the pin decides
the moved row's place, and a row others are pinned to keeps its place by the rules, priority
included. Between two rows of one place the moved row takes the middle of their `pin_order`s;
when floating point has no middle left, the rows of that place are numbered again, 0, 1, 2, and
those numbers go under `OTHERS` for the caller to write (`write`).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mulebox.coordinator import store as st
from mulebox.coordinator.line import AFTER, BEFORE, FRONT, Line

MOVES = ("first", "up", "down", "last")
OTHERS = "others"  # {job_id: pin_order} of rows of the moved row's place, numbered again


def front(order: Line, job: dict[str, Any]) -> dict[str, Any]:
    """The columns that put `job` ahead of every row at the front, or nothing if it leads."""
    ahead = [pin[2] for job_id, pin in order.pins.items()
             if pin[0] == FRONT and job_id != job["job_id"]]
    if order.pins.get(job["job_id"], (None,))[0] == FRONT and order.rank.get(job["job_id"]) == 0:
        return {}
    return pinned(FRONT, None, min(ahead) - 1 if ahead else 0.0)


def pinned(side: str, anchor: str | None, value: float) -> dict[str, Any]:
    return {"pin_side": side, "pin_job": anchor, "pin_order": value}


def write(conn: sqlite3.Connection, job_id: str, fields: dict[str, Any]) -> None:
    """Store what `move` or `front` gave: the moved row's columns, and any rows numbered again."""
    fields = dict(fields)
    for other, value in fields.pop(OTHERS, {}).items():
        st.update_job(conn, other, pin_order=value)
    st.update_job(conn, job_id, **fields)


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
    return _between(order, job["job_id"], before, after)


def _between(order: Line, moved: str, prev: dict[str, Any] | None,
             nxt: dict[str, Any] | None) -> dict[str, Any]:
    def pin(row: dict[str, Any] | None) -> tuple[str, str | None, float] | None:
        return None if row is None else order.pins.get(row["job_id"])

    had = pin(prev)
    if nxt is not None:
        found = pin(nxt)
        if found is None:  # a row in its place by the rules: just ahead of it
            same = had is not None and had[:2] == (BEFORE, nxt["job_id"])
            return pinned(BEFORE, nxt["job_id"], had[2] + 1 if same else 0.0)
        side, anchor, value = found
        if had is None or had[:2] != (side, anchor):
            return pinned(side, anchor, value - 1)
        middle = (had[2] + value) / 2
        if had[2] < middle < value:
            return pinned(side, anchor, middle)
        return _renumbered(order, moved, side, anchor, nxt["job_id"])
    assert prev is not None  # a line of one row has nowhere to move
    if had is None:
        return pinned(AFTER, prev["job_id"], 0.0)
    return pinned(had[0], had[1], had[2] + 1)


def _renumbered(order: Line, moved: str, side: str, anchor: str | None, nxt: str
                ) -> dict[str, Any]:
    """`moved` just ahead of `nxt` in their place, with every row there numbered again."""
    place = [row["job_id"] for row in order.rows if row["job_id"] != moved
             and order.pins.get(row["job_id"], (None, None))[:2] == (side, anchor)]
    place.insert(place.index(nxt), moved)
    numbers = {job_id: float(n) for n, job_id in enumerate(place)}
    others = {job_id: value for job_id, value in numbers.items()
              if job_id != moved and order.pins[job_id][2] != value}
    return {**pinned(side, anchor, numbers[moved]), OTHERS: others}
