"""The order of the line: every queued row, of every kind, first to last (docs/design.md,
Order of the line).

The rules' order, each step breaking the ties of the one before:

1. `priority`, higher first: only rows moved by hand before 1.16.1 still carry one.
2. Levels from the rules (line_rules.py): the project's, the branch's, a GitHub run's and its
   workflow's, plus one for every `aging_min` minutes in line. Higher first. An upgrade takes
   only aging.
3. Fair turns, when on: a project's waiting rows count from what it already runs, so one
   project's burst does not hold back another project's single job.
4. Shortest first, when on: what the job usually takes (usual.py), shorter first; a job with
   no history counts as the median of the known lengths in line (none known: arrival decides).
5. Arrival: `queued_at`, then `seq`.

Moves by hand pin only the moved row (`pin_side`, `pin_job`, `pin_order`, set by line_moves.py):
`front` goes before everything, `before` or `after` a job sits just ahead of or behind that
job's place by the rules, whether that job is still in line, moved itself, or has left the line
(then the pinned row takes its place). Every other row stays ordered by the rules, so a later
rule change still applies to them. Rows pinned to one place keep their `pin_order` there.

With no rule on and no row pinned this is `ARRIVAL_ORDER` in SQL, as the line was before the
rules. Read once per transaction (`read`), in a fixed number of queries however long the line
is: `queue.claim` takes the first row it may start in this order, in the same `BEGIN IMMEDIATE`
that starts it. Each placed row also says why it is where it is (line_why.py).
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter
from fnmatch import fnmatchcase
from statistics import median_low
from typing import Any

from mulebox.common.protocol import JobState
from mulebox.coordinator import line_rules, line_why, usual
from mulebox.coordinator import store as st
from mulebox.coordinator.line_rules import Rules
from mulebox.coordinator.store import ACTIVE_STATES

ARRIVAL_ORDER = "priority DESC, queued_at, seq"
UPGRADE_KIND = "upgrade"  # upgrades.UPGRADE_KIND; upgrades imports this module's users
RUNNER_KIND = "runner"
FRONT, BEFORE, AFTER = "front", "before", "after"

Pin = tuple[str, str | None, float]  # (side, the job whose place it is pinned to, order there)


class Line:
    """The queued rows in order, why each is where it is, and the pins in force."""

    def __init__(self, rows: list[dict[str, Any]], why: dict[str, dict[str, Any]],
                 pins: dict[str, Pin] | None = None) -> None:
        self.rows = rows
        self.why = why
        self.pins = pins or {}
        self.rank = {row["job_id"]: index for index, row in enumerate(rows)}

    def before(self, a: dict[str, Any], b: dict[str, Any]) -> bool:
        """Whether queued row `a` comes before queued row `b`."""
        if a["job_id"] in self.rank and b["job_id"] in self.rank:
            return self.rank[a["job_id"]] < self.rank[b["job_id"]]
        return st.line_key(a) < st.line_key(b)  # one not in line: arrival decides

    def position(self, job: dict[str, Any]) -> int | None:
        """1-based place of a queued row; None for any other state."""
        if job["state"] != JobState.QUEUED or job["job_id"] not in self.rank:
            return None
        return self.rank[job["job_id"]] + 1

    def explain(self, job: dict[str, Any]) -> dict[str, Any]:
        """`order` and `place_reason` for a queued row while a rule is on or it was moved."""
        return dict(self.why.get(job["job_id"], {}))


def read(conn: sqlite3.Connection, now: float | None = None) -> Line:
    """The line as it stands at `now` (aging depends on it)."""
    rows = st.select_jobs(conn, "state = ?", (JobState.QUEUED.value,), ARRIVAL_ORDER)
    rules = line_rules.read(conn)
    if not rules.ordering() and not any(row["pin_side"] for row in rows):
        return Line(rows, {})
    return _ordered(conn, rows, rules, time.time() if now is None else now)


def _branch(rules: Rules, branch: str | None) -> tuple[str, int] | None:
    """The branch rule that applies: the exact name, else the longest pattern that matches."""
    if not branch:
        return None
    if branch in rules.branches:
        return branch, rules.branches[branch]
    found = [(p, n) for p, n in rules.branches.items() if fnmatchcase(branch, p)]
    return max(found, key=lambda item: len(item[0])) if found else None


def levels(rules: Rules, job: dict[str, Any], now: float) -> list[dict[str, Any]]:
    """The levels a row gets, each with the rule it comes from."""
    parts: list[dict[str, Any]] = []
    if job["kind"] != UPGRADE_KIND:
        if rules.projects.get(job["project"]):
            parts.append({"rule": "project", "name": job["project"],
                          "level": rules.projects[job["project"]]})
        if (match := _branch(rules, job["branch"])) is not None:
            parts.append({"rule": "branch", "name": match[0], "level": match[1]})
        if job["kind"] == RUNNER_KIND and rules.github:
            parts.append({"rule": "github", "level": rules.github})
        if job["kind"] == RUNNER_KIND and rules.workflows.get(job.get("workflow") or ""):
            parts.append({"rule": "workflow", "name": job["workflow"],
                          "level": rules.workflows[job["workflow"]]})
    waited = now - (job["queued_at"] if job["queued_at"] is not None else now)
    if rules.aging_min and (steps := int(waited // (rules.aging_min * 60))) > 0:
        parts.append({"rule": "waited", "minutes": int(waited // 60),
                      "over": steps * rules.aging_min, "level": steps})
    return parts


def _running(conn: sqlite3.Connection) -> Counter[str]:
    marks = ", ".join("?" for _ in ACTIVE_STATES)
    rows = conn.execute(f"SELECT project FROM jobs WHERE state IN ({marks}) "
                        "AND kind IN ('job', 'runner')", [s.value for s in ACTIVE_STATES])
    return Counter(row["project"] for row in rows)


def _pins(conn: sqlite3.Connection, rows: list[dict[str, Any]]
          ) -> tuple[dict[str, Pin], dict[str, dict[str, Any]]]:
    """The pins in force, and the rows that left the line but still hold a pinned row's place.
    A pin to a job no longer in the store is dropped: that row goes by the rules again."""
    queued = {row["job_id"] for row in rows}
    wanted = {row["pin_job"] for row in rows if row["pin_side"] in (BEFORE, AFTER)} - queued
    gone: dict[str, dict[str, Any]] = {}
    if wanted:
        marks = ", ".join("?" * len(wanted))
        gone = {job["job_id"]: job for job in st.select_jobs(
            conn, f"job_id IN ({marks})", tuple(sorted(wanted)))}
    pins = {row["job_id"]: (row["pin_side"], row["pin_job"], row["pin_order"] or 0.0)
            for row in rows if row["pin_side"] == FRONT
            or (row["pin_side"] in (BEFORE, AFTER)
                and (row["pin_job"] in queued or row["pin_job"] in gone))}
    return pins, gone


def _keys(conn: sqlite3.Connection, slots: list[dict[str, Any]], counted_ids: set[str],
          rules: Rules, now: float, length: dict[str, float | None], fill: float | None
          ) -> tuple[dict[str, tuple], dict[str, int]]:
    """Each slot's sort key by the rules, and the fair turn of each. Only `counted_ids` (rows
    in line at their own place) take a turn; a place held for a pinned row is given the turn
    its project would have there, without taking it."""
    level = {row["job_id"]: sum(p["level"] for p in levels(rules, row, now)) for row in slots}
    seen = _running(conn) if rules.fair_turns else Counter()
    turn: dict[str, int] = {}
    if rules.fair_turns:
        for row in sorted(slots, key=lambda r: (-r["priority"], -level[r["job_id"]],
                                                r["queued_at"] or 0.0, r["seq"])):
            if row["kind"] == UPGRADE_KIND:
                continue
            turn[row["job_id"]] = seen[row["project"]]
            if row["job_id"] in counted_ids:
                seen[row["project"]] += 1
    keys = {}
    for row in slots:
        took = length.get(row["job_id"])
        took = fill if took is None else took
        keys[row["job_id"]] = (-row["priority"], -level[row["job_id"]], turn.get(row["job_id"], 0),
                               (1, 0.0) if took is None else (0, took),
                               row["queued_at"] or 0.0, row["seq"])
    return keys, turn


def _ordered(conn: sqlite3.Connection, rows: list[dict[str, Any]], rules: Rules,
             now: float) -> Line:
    pins, gone = _pins(conn, rows)
    anchors = {pin[1] for pin in pins.values() if pin[0] != FRONT}
    free = [row for row in rows if row["job_id"] not in pins]
    held = [row for row in rows if row["job_id"] in pins and row["job_id"] in anchors]
    slots = free + held + list(gone.values())
    length = usual.lengths(conn, rows + list(gone.values())) if rules.shortest_first else {}
    known = [length[row["job_id"]] for row in rows if length.get(row["job_id"]) is not None]
    fill = median_low(known) if known else None
    keys, turn = _keys(conn, slots, {row["job_id"] for row in free}, rules, now, length, fill)
    groups: dict[tuple[str, str | None], list[str]] = {}
    for job_id, (side, anchor, _) in sorted(pins.items(), key=lambda item: item[1][2]):
        groups.setdefault((side, None if side == FRONT else anchor), []).append(job_id)
    by_id = {row["job_id"]: row for row in rows}
    ids = list(groups.get((FRONT, None), []))
    for slot in sorted(slots, key=lambda row: keys[row["job_id"]]):
        ids += groups.get((BEFORE, slot["job_id"]), [])
        if slot["job_id"] not in pins and slot["job_id"] in by_id:
            ids.append(slot["job_id"])
        ids += groups.get((AFTER, slot["job_id"]), [])
    out = [by_id[job_id] for job_id in ids]
    texts = line_why.Context(rules, now, length, fill, turn, pins, by_id)
    why = {row["job_id"]: found for row in out if (found := texts.why(row))}
    return Line(out, why, pins)
