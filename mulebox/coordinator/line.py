"""The order of the line: every queued row, of every kind, first to last (docs/design.md,
Order of the line).

The order, each step breaking the ties of the one before:

1. The owner's moves (`priority`, job_control.py), higher first.
2. Levels from the rules (line_rules.py): the project's, the branch's, a GitHub run's, plus
   one for every `aging_min` minutes in line. Higher first. An upgrade takes only aging.
3. Fair turns, when on: a project's waiting rows count from what it already runs, so one
   project's burst does not hold back another project's single job.
4. Shortest first, when on: what the job usually takes (usual.py), shorter first; a job with
   no history comes after the ones with one.
5. Arrival: `queued_at`, then `seq`.

With no rule on this is `ARRIVAL_ORDER` in SQL, as the line was before the rules. Read once
per transaction (`read`): `queue.claim` takes the first row it may start in this order, in the
same `BEGIN IMMEDIATE` that starts it. Each placed row also says why it is where it is
(`explain`), for `mulebox queue`, `status` and the dashboard.
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter
from fnmatch import fnmatchcase
from typing import Any

from mulebox.common.protocol import JobState
from mulebox.coordinator import line_rules, usual
from mulebox.coordinator import store as st
from mulebox.coordinator.line_rules import Rules
from mulebox.coordinator.store import ACTIVE_STATES

ARRIVAL_ORDER = "priority DESC, queued_at, seq"
UPGRADE_KIND = "upgrade"  # upgrades.UPGRADE_KIND; upgrades imports this module's users
RUNNER_KIND = "runner"


class Line:
    """The queued rows in order, and why each is where it is (only while a rule is on)."""

    def __init__(self, rows: list[dict[str, Any]], why: dict[str, dict[str, Any]]) -> None:
        self.rows = rows
        self.why = why
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
        """`order` and `place_reason` for a queued row while a rule is on; else nothing."""
        return dict(self.why.get(job["job_id"], {}))


def read(conn: sqlite3.Connection, now: float | None = None) -> Line:
    """The line as it stands at `now` (aging depends on it)."""
    rows = st.select_jobs(conn, "state = ?", (JobState.QUEUED.value,), ARRIVAL_ORDER)
    rules = line_rules.read(conn)
    if not rules.ordering():
        return Line(rows, {})
    return Line(*_ordered(conn, rows, rules, time.time() if now is None else now))


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
    waited = now - (job["queued_at"] if job["queued_at"] is not None else now)
    if rules.aging_min and (steps := int(waited // (rules.aging_min * 60))) > 0:
        parts.append({"rule": "waited", "minutes": int(waited // 60), "level": steps})
    return parts


def _running(conn: sqlite3.Connection) -> Counter[str]:
    marks = ", ".join("?" for _ in ACTIVE_STATES)
    rows = conn.execute(f"SELECT project FROM jobs WHERE state IN ({marks}) "
                        "AND kind IN ('job', 'runner')", [s.value for s in ACTIVE_STATES])
    return Counter(row["project"] for row in rows)


def _ordered(conn: sqlite3.Connection, rows: list[dict[str, Any]], rules: Rules,
             now: float) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    parts = {row["job_id"]: levels(rules, row, now) for row in rows}
    level = {job_id: sum(p["level"] for p in found) for job_id, found in parts.items()}
    lengths = ({row["job_id"]: (usual.job_seconds(conn, row)
                                if row["kind"] != UPGRADE_KIND else None) for row in rows}
               if rules.shortest_first else {})
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:  # in arrival order within each group
        groups.setdefault((row["priority"], level[row["job_id"]]), []).append(row)
    seen = _running(conn) if rules.fair_turns else Counter()
    turn: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for key in sorted(groups, reverse=True):
        group, counted = groups[key], Counter()
        for row in group:
            if rules.fair_turns and row["kind"] != UPGRADE_KIND:
                turn[row["job_id"]] = seen[row["project"]] + counted[row["project"]]
                counted[row["project"]] += 1
        seen.update(counted)

        def place(row: dict[str, Any]) -> tuple:
            length = lengths.get(row["job_id"])
            return (turn.get(row["job_id"], 0), (1, 0.0) if length is None else (0, length),
                    row["queued_at"], row["seq"])

        out += sorted(group, key=place)
    why = {row["job_id"]: _why(row, rules, parts[row["job_id"]], level[row["job_id"]],
                               turn.get(row["job_id"]), lengths.get(row["job_id"]))
           for row in out}
    return out, why


def _minutes(seconds: float) -> str:
    whole = max(0, int(round(seconds / 60)))
    if whole < 1:
        return f"{max(0, int(seconds))}s"
    return f"{whole // 60}h {whole % 60}m" if whole >= 60 else f"{whole}m"


def _part_text(part: dict[str, Any]) -> str:
    sign = f"{part['level']:+d}"
    if part["rule"] == "project":
        return f"project {part['name']} {sign}"
    if part["rule"] == "branch":
        return f"branch {part['name']} {sign}"
    if part["rule"] == "github":
        return f"GitHub run {sign}"
    return f"waited {_minutes(part['minutes'] * 60)} {sign}"


def _why(row: dict[str, Any], rules: Rules, parts: list[dict[str, Any]], total: int,
         turn: int | None, length: float | None) -> dict[str, Any]:
    order: dict[str, Any] = {"by_hand": bool(row["priority"]), "level": total, "levels": parts}
    if rules.fair_turns:
        order["turn"] = None if turn is None else turn + 1
    if rules.shortest_first:
        order["usual_s"] = length
    if row["priority"]:
        text = ("an upgrade, sent to go first" if row["kind"] == UPGRADE_KIND
                else "in the order last set by hand")
        return {"order": order, "place_reason": text}
    said = [_part_text(part) for part in parts]
    if turn is not None:
        said.append(f"turn {turn + 1} of {row['project']}")
    if rules.shortest_first:
        said.append(f"usually {_minutes(length)}" if length is not None
                    else "no usual length yet, after jobs with one")
    said.append("then by arrival")
    return {"order": order, "place_reason": "; ".join(said)}
