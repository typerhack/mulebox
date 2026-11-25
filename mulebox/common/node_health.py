"""A node's health as it reports it, read the same way by worker, coordinator and client
(design.md, A node that rests).

A worker checks itself (worker/health.py) and sends `health` with every claim and heartbeat:

    {"resting": true, "until": 1764075600.0 | null,
     "problems": [{"check": "docker", "message": "...", "fix": "...", "since": 1764075000.0}],
     "withheld": ["compose-v1", "docker", "isolated"], "round": 12, "answers": 1}

`resting`: it takes no job at all (disk, roots, git, the executor, or a streak of failed starts).
`withheld`: capabilities it leaves out of its claims while one part is down (Docker, Xcode); it
still offers the rest. `round` counts the checks it has run, so `mulebox machine check` can tell a
fresh answer; `answers` counts the asks it answered with a check started after them. A healthy worker sends no problems; one older than 1.41 sends nothing.
"""

from __future__ import annotations

import time
from typing import Any

from mulebox.common import compose, isolation

# Checks that stop every claim, and those that withhold only some capabilities.
WHOLE = ("disk", "roots", "git", "executor", "streak")
WITHHOLDS = {"docker": (compose.DOCKER_CAPABILITY, compose.COMPOSE_CAPABILITY, isolation.CAPABILITY),
             "xcode": ("xcode", "simulator")}
CHECKS = (*WHOLE, *WITHHOLDS)
MAX_TEXT = 300
MAX_PROBLEMS = len(CHECKS)


def problem(check: str, message: str, fix: str, since: float) -> dict[str, Any]:
    return {"check": check, "message": message[:MAX_TEXT], "fix": fix[:MAX_TEXT], "since": since}


def _text(value: Any) -> str | None:
    return value[:MAX_TEXT] if isinstance(value, str) and value else None


def _number(value: Any) -> float | None:
    ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    return float(value) if ok else None


def checked(value: Any) -> dict[str, Any] | None:
    """A well-formed health report, or None for a missing or broken one: a report must never
    fail a claim."""
    if not isinstance(value, dict):
        return None
    problems = []
    for item in value.get("problems") or []:
        if not isinstance(item, dict) or item.get("check") not in CHECKS:
            continue
        message, since = _text(item.get("message")), _number(item.get("since"))
        if message is None or since is None:
            continue
        problems.append(problem(item["check"], message, _text(item.get("fix")) or "", since))
    withheld = sorted({name for name in value.get("withheld") or []
                       if isinstance(name, str) and name in _ALL_WITHHELD})
    return {"resting": value.get("resting") is True, "until": _number(value.get("until")),
            "problems": problems[:MAX_PROBLEMS], "withheld": withheld,
            "round": _count(value.get("round")), "answers": _count(value.get("answers"))}


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


_ALL_WITHHELD = frozenset(name for names in WITHHOLDS.values() for name in names)


def withheld_by(checks: set[str], offered: list[str] | tuple[str, ...]) -> list[str]:
    """The capabilities of `offered` that failing `checks` take out of claims."""
    names = {name for check in checks for name in WITHHOLDS.get(check, ())}
    return sorted(name for name in offered if name in names)


def clock(at: float) -> str:
    return time.strftime("%H:%M", time.localtime(at))


def reason(worker: str, health: dict[str, Any] | None) -> str | None:
    """`build-1 is resting: Docker does not answer (since 10:42); start Docker ...`, or None."""
    if not health or not health.get("problems"):
        return None
    word = "is resting" if health.get("resting") else "holds back some jobs"
    parts = []
    for item in health["problems"]:
        fix = f"; {item['fix']}" if item.get("fix") else ""
        parts.append(f"{item['message']} (since {clock(item['since'])}){fix}")
    return f"{worker} {word}: " + "; ".join(parts)


def blocks(health: dict[str, Any] | None, needs: list[str] | tuple[str, ...]) -> bool:
    """Whether a node with `health` cannot take a job with `needs` now."""
    if not health:
        return False
    return bool(health.get("resting")) or bool(set(health.get("withheld") or ()) & set(needs))
