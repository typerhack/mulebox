"""The owner's rules for the order of the line (docs/design.md, Order of the line).

    projects        project -> level, -3..3 (`mulebox project priority`); 0 removes it
    branches        branch name or pattern (`release/*`) -> level; 0 removes it
    github          level of every GitHub run's slot, against agent jobs
    workflows       GitHub workflow name (as its runner's hook sends it) -> level; 0 removes it
    aging_min       every so many minutes in line add one level, so nothing waits for ever
    shortest_first  among equals, the job that usually takes least goes first
    fair_turns      among equals, projects take turns, counting what each already runs

Kept in the coordinator's `meta` table as one JSON value, like the project pauses and holds,
so `queue.claim` reads them in the transaction that starts a job. Never in `.mulebox.yml`: a
project must not be able to raise itself. Set from the CLI (`mulebox queue rules`) and the
dashboard, which both send `queue_rules`. With every rule at its default (and aging alone,
which keeps the order of arrival) the line is exactly what it was before them.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from mulebox.common.config_reader import NAME_RE
from mulebox.common.protocol import Message, MessageType
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest

KEY = "line_rules"
LEVEL_MIN, LEVEL_MAX = -3, 3
LEVEL_WORDS = {"low": -1, "normal": 0, "high": 1}
DEFAULT_AGING_MIN = 30
MAX_AGING_MIN = 24 * 60
MAX_ENTRIES = 50
MAX_PATTERN = 100
FIELDS = ("projects", "branches", "github", "workflows", "aging_min", "shortest_first",
          "fair_turns")


@dataclass(frozen=True)
class Rules:
    projects: dict[str, int] = field(default_factory=dict)
    branches: dict[str, int] = field(default_factory=dict)
    github: int = 0
    workflows: dict[str, int] = field(default_factory=dict)
    aging_min: int = DEFAULT_AGING_MIN
    shortest_first: bool = False
    fair_turns: bool = False

    def ordering(self) -> bool:
        """Whether any rule can change the order of arrival. Aging alone cannot: an older job
        has waited at least as long as a younger one."""
        return bool(self.projects or self.branches or self.github or self.workflows
                    or self.shortest_first or self.fair_turns)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def level(value: Any, name: str = "level") -> int:
    """A level from a word (low, normal, high) or a whole number in LEVEL_MIN..LEVEL_MAX."""
    if isinstance(value, str) and value in LEVEL_WORDS:
        return LEVEL_WORDS[value]
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            pass
    if isinstance(value, bool) or not isinstance(value, int) or not LEVEL_MIN <= value <= LEVEL_MAX:
        raise BadRequest(f"{name} must be low, normal, high or a whole number from {LEVEL_MIN} "
                         f"to {LEVEL_MAX}, got {value!r}")
    return value


def _branch_ok(pattern: Any) -> bool:
    return (isinstance(pattern, str) and 0 < len(pattern) <= MAX_PATTERN and pattern.isprintable()
            and not any(ch.isspace() for ch in pattern))


def _workflow_ok(name: Any) -> bool:
    """A workflow's `name:`, which may hold spaces, as GitHub gives it in GITHUB_WORKFLOW."""
    return (isinstance(name, str) and 0 < len(name) <= MAX_PATTERN and name.isprintable()
            and name == name.strip())


def _levels(current: dict[str, int], change: Any, what: str, ok: Any) -> dict[str, int]:
    if not isinstance(change, dict):
        raise BadRequest(f"field '{what}' must map names to levels")
    merged = dict(current)
    for name, value in change.items():
        if not ok(name):
            raise BadRequest(f"'{name}' is not a valid name in '{what}'")
        wanted = level(value, f"the level of {name}")
        if wanted:
            merged[name] = wanted
        else:
            merged.pop(name, None)  # normal: nothing to keep
    if len(merged) > MAX_ENTRIES:
        raise BadRequest(f"at most {MAX_ENTRIES} entries in '{what}'")
    return merged


def merge(rules: Rules, change: Any) -> Rules:
    """`rules` with `change` applied: maps merge entry by entry, the rest replace."""
    if not isinstance(change, dict) or not change.keys() <= set(FIELDS):
        raise BadRequest(f"field 'rules' must be an object with some of {', '.join(FIELDS)}")
    out = rules
    if "projects" in change:
        out = replace(out, projects=_levels(
            out.projects, change["projects"], "projects",
            lambda n: isinstance(n, str) and NAME_RE.fullmatch(n) is not None))
    if "branches" in change:
        out = replace(out, branches=_levels(out.branches, change["branches"], "branches", _branch_ok))
    if "workflows" in change:
        out = replace(out, workflows=_levels(out.workflows, change["workflows"], "workflows",
                                             _workflow_ok))
    if "github" in change:
        out = replace(out, github=level(change["github"], "github"))
    if "aging_min" in change:
        out = replace(out, aging_min=v.integer(change, "aging_min", low=0, high=MAX_AGING_MIN))
    for name in ("shortest_first", "fair_turns"):
        if name in change:
            if not isinstance(change[name], bool):
                raise BadRequest(f"field '{name}' must be true or false")
            out = replace(out, **{name: change[name]})
    return out


def read(conn: sqlite3.Connection) -> Rules:
    """The stored rules; the defaults when none were set or the value is unreadable."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (KEY,)).fetchone()
    if row is None:
        return Rules()
    try:
        return merge(Rules(), json.loads(row["value"]))
    except (ValueError, BadRequest):
        return Rules()


def write(conn: sqlite3.Connection, rules: Rules) -> None:
    if rules == Rules():
        conn.execute("DELETE FROM meta WHERE key = ?", (KEY,))
        return
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                 (KEY, json.dumps(rules.as_dict())))


def known_projects(conn: sqlite3.Connection) -> list[str]:
    """Every project that has sent a job or a GitHub run, to choose a level for."""
    rows = conn.execute("SELECT DISTINCT project FROM jobs WHERE kind IN ('job', 'runner') "
                        "ORDER BY project")
    return [row["project"] for row in rows]


def body(conn: sqlite3.Connection) -> dict[str, Any]:
    """The `queue_rules_ok` body, and the dashboard's `GET /api/queue/rules`."""
    return {"rules": read(conn).as_dict(), "defaults": Rules().as_dict(),
            "levels": {"min": LEVEL_MIN, "max": LEVEL_MAX, "words": LEVEL_WORDS},
            "projects": known_projects(conn)}


def control(req: Request) -> Message:
    """`queue_rules`: action `get`, `set` (with `rules`, a partial change) or `reset`."""
    action = v.text(req.body, "action", "get")
    if action not in ("get", "set", "reset"):
        raise BadRequest("field 'action' must be one of get, set, reset")
    with req.store.write() as conn:
        if action == "set":
            write(conn, merge(read(conn), req.body.get("rules")))
        elif action == "reset":
            write(conn, Rules())
        reply = body(conn)
    return req.reply(MessageType.QUEUE_RULES_OK, reply)
