"""What a `watch` stream tells of a job that looks stuck (common/stuck.py): a `stuck` notice
when a verdict other than `working` starts, and `moving` when the job works again, once each.

A stream that connects late hears the verdict in force, so an agent that reconnects is told
too; `number` counts the spells in this stream, so a client tells a new one from a repeat.
The verdict is looked at every LOOK_S, about as often as a worker reports.
"""

from __future__ import annotations

from typing import Any

from mulebox.common.stuck import QUIET
from mulebox.coordinator import attendance

LOOK_S = 3.0
TOLD = (*QUIET, "slow")


class Teller:
    def __init__(self, limits: attendance.Limits) -> None:
        self.limits = limits
        self.told: str | None = None
        self.number = 0
        self.looked_at: float | None = None

    def notices(self, job: dict[str, Any], rows: list[dict[str, Any]] | None,
                now: float) -> list[tuple[str, dict[str, Any]]]:
        """(`stuck` or `moving`, its body) to send now; usually none."""
        if self.looked_at is not None and now - self.looked_at < LOOK_S:
            return []
        self.looked_at = now
        seen = attendance.looks(job, rows or [], now, self.limits)
        kind = seen["verdict"] if seen else None
        if kind in TOLD and kind != self.told:
            self.told, self.number = kind, self.number + 1
            return [("stuck", {**(seen or {}), "number": self.number})]
        if kind == "working" and self.told in TOLD:
            self.told = kind
            return [("moving", {"number": self.number, "since": round(now, 1),
                                "stage": (seen or {}).get("stage")})]
        return []
