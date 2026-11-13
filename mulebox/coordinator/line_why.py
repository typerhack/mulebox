"""Why each waiting row is where it is in the line (line.py): `order` and `place_reason`, for
`mulebox queue`, `status` and the dashboard (docs/design.md, Order of the line).

A reason changes only when the order behind it does: aging is said in whole steps ("waited 30m
or more +1"), not in minutes, so a view that redraws on a changed reason (common/status.py
`fingerprint`) does not redraw every minute for every waiting job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mulebox.coordinator.line_rules import Rules

UPGRADE_KIND = "upgrade"
LEGACY_TEXT = "in the order last set by hand"


def minutes(seconds: float) -> str:
    whole = max(0, int(round(seconds / 60)))
    if whole < 1:
        return f"{max(0, int(seconds))}s"
    return f"{whole // 60}h {whole % 60}m" if whole >= 60 else f"{whole}m"


def part_text(part: dict[str, Any]) -> str:
    sign = f"{part['level']:+d}"
    if part["rule"] in ("project", "branch", "workflow"):
        return f"{part['rule']} {part['name']} {sign}"
    if part["rule"] == "github":
        return f"GitHub run {sign}"
    return f"waited {minutes(part['over'] * 60)} or more {sign}"


def pin_text(row: dict[str, Any], side: str, anchor: str | None, in_line: bool) -> str:
    if side == "front":
        return ("an upgrade, sent to go first" if row["kind"] == UPGRADE_KIND
                else "moved to the front by hand")
    where = "ahead of" if side == "before" else "behind"
    if in_line:
        return f"moved by hand, just {where} {anchor}"
    return f"moved by hand {where} {anchor}, which has left the line, so in its place"


@dataclass
class Context:
    """What one reading of the line knows, to explain any of its rows."""

    rules: Rules
    now: float
    length: dict[str, float | None]
    fill: float | None  # what a row with no usual length counts as (shortest first)
    turn: dict[str, int]
    pins: dict[str, tuple[str, str | None, float]]
    in_line: dict[str, dict[str, Any]]

    def why(self, row: dict[str, Any]) -> dict[str, Any]:
        """`order` and `place_reason`; nothing for a row in arrival order with no rule on."""
        from mulebox.coordinator.line import levels  # line imports this module

        pin = self.pins.get(row["job_id"])
        if not self.rules.ordering() and pin is None and not row["priority"]:
            return {}
        parts = levels(self.rules, row, self.now)
        order: dict[str, Any] = {"by_hand": bool(pin or row["priority"]),
                                 "level": sum(p["level"] for p in parts), "levels": parts}
        if self.rules.fair_turns:
            found = None if pin else self.turn.get(row["job_id"])
            order["turn"] = None if found is None else found + 1
        length = self.length.get(row["job_id"])
        if self.rules.shortest_first:
            order["usual_s"] = length
            if length is None and self.fill is not None:
                order["counted_as_s"] = self.fill
        if pin is not None:
            side, anchor, _ = pin
            in_line = anchor in self.in_line
            order["moved"] = {"side": side, "job_id": anchor, "in_line": in_line or side == "front"}
            return {"order": order, "place_reason": pin_text(row, side, anchor, in_line)}
        if row["priority"]:
            return {"order": order, "place_reason": LEGACY_TEXT}
        return {"order": order, "place_reason": self._rules_text(row, parts, length)}

    def _rules_text(self, row: dict[str, Any], parts: list[dict[str, Any]],
                    length: float | None) -> str:
        said = [part_text(part) for part in parts]
        if self.rules.fair_turns and (turn := self.turn.get(row["job_id"])) is not None:
            said.append(f"turn {turn + 1} of {row['project']}")
        if self.rules.shortest_first:
            if length is not None:
                said.append(f"usually {minutes(length)}")
            elif self.fill is not None:
                said.append(f"no usual length yet, counted as the line's median {minutes(self.fill)}")
            else:
                said.append("no usual length in line yet")
        said.append("then by arrival")
        return "; ".join(said)
