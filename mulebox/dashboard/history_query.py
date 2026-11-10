"""The History page's filters: `/api/history` parameters checked, then one SQL where clause.

The filters are the Statistics page's (coordinator/stats.py GROUPS: project, job, client,
worker, kind), each an exact value, plus:
- `result`: passed, failed or cancelled, as the job lists show them (common/status.py
  `shown_state`): failed counts timed out and interrupted runs too (the Failed tab's set), and
  cancelled counts a job stopped as stuck (on the wire a cancelled outcome). A GitHub run
  released by an older mulebox, with no result of its own (`released`), matches none.
- `q`: part of the project, job name or branch, any case; `%`, `_` and `\\` are taken as typed.
Every filter is in the where clause, so paging with `before` keeps them.
"""

from __future__ import annotations

from collections.abc import Mapping

from mulebox.common.protocol import JobState
from mulebox.common.status import ENDED_BADLY, RUNNER_KIND
from mulebox.coordinator.errors import BadRequest
from mulebox.coordinator.stats import GROUPS, KINDS

RESULTS = ("passed", "failed", "cancelled")
MAX_TEXT = 200
_RELEASED = f"(kind = '{RUNNER_KIND}' AND ci_result = '{{}}')"  # status.shown_state: released
_RESULT_SQL = {
    "passed": (f"outcome = 'passed' AND NOT {_RELEASED}", ()),
    "failed": (f"outcome IN ({', '.join('?' * len(ENDED_BADLY))}) "
               f"AND NOT (outcome = 'failed' AND {_RELEASED})", ENDED_BADLY),
    "cancelled": ("outcome = 'cancelled'", ()),
}
_SEARCHED = ("project", "job", "branch")


def filters(query: Mapping[str, str]) -> dict[str, str]:
    """The filters asked for, empty ones left out; BadRequest on a value it cannot take."""
    found = {}
    for name in (*GROUPS, "result", "q"):
        value = query.get(name, "").strip() if name == "q" else query.get(name, "")
        if not value:
            continue
        if len(value) > MAX_TEXT:
            raise BadRequest(f"{name} must be at most {MAX_TEXT} characters")
        if name == "kind" and value not in KINDS:
            raise BadRequest(f"kind must be one of {', '.join(KINDS)}")
        if name == "result" and value not in RESULTS:
            raise BadRequest(f"result must be one of {', '.join(RESULTS)}")
        found[name] = value
    return found


def _like(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def where(chosen: Mapping[str, str], before: float | None = None) -> tuple[str, tuple]:
    """The where clause and its parameters for finished jobs matching `chosen` (`filters`)."""
    sql, params = "state = ?", [JobState.FINISHED.value]
    if before is not None:
        sql += " AND finished_at < ?"
        params.append(before)
    for name in GROUPS:  # constant column names; the values go as parameters
        if chosen.get(name):
            sql += f" AND {name} = ?"
            params.append(chosen[name])
    if chosen.get("result"):
        clause, extra = _RESULT_SQL[chosen["result"]]
        sql += f" AND {clause}"
        params.extend(extra)
    if chosen.get("q"):
        pattern = _like(chosen["q"])
        sql += " AND (" + " OR ".join(f"{name} LIKE ? ESCAPE '\\'" for name in _SEARCHED) + ")"
        params.extend([pattern] * len(_SEARCHED))
    return sql, tuple(params)
