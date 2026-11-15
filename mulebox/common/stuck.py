"""Does a running job look stuck? One verdict with its evidence (docs/design.md, A job that looks
stuck). It stops nothing: coordinator/attendance.py alone stops a job.

The evidence is the worker's last activity report (worker/activity.py), aged to now with `at`,
the coordinator's time of that report:

- `idle_s`: nothing moved, counting output, the job's own CPU and bytes, its services' CPU and
  traffic; null when part of it cannot be read, and not knowing is never stuck;
- `compute_idle_s`: the same without bytes, so a job moving only a trickle of data shows;
- `io_kib_s`: what the job's own processes read and write; null on a Mac node;
- `download`: what its log says it is downloading (common/download_watch.py);
- `last_line`: the last thing it printed, redacted.

Verdicts, in the order they are tried:

- `asking`: nothing moved for the limit, and the last line is a question for input. A job has no
  input, so it will never go on.
- `waiting`: nothing moved for the limit, and the last line says it waits on purpose (a retry, a
  delay). Past WAITING_FOR times the limit with nothing since, it is `stuck`.
- `stuck`: nothing moved for the limit, and the log gives no reason.
- `slow`: something moves, but only a download or data below SLOW_BYTES_S.
- `working`: anything else.

`text` is the sentence the CLI prints and the dashboard shows, so both say the same.
"""

from __future__ import annotations

import re
from typing import Any

from mulebox.common.units import duration, rate, size

STUCK_AFTER_MIN = 2  # the node's default; a project may raise it, never lower it
SLOW_BYTES_S = 50 * 1000.0
WAITING_FOR = 5  # times the limit a job that said it waits may stay still before it is stuck
VERDICTS = ("working", "slow", "waiting", "asking", "stuck")
QUIET = ("waiting", "asking", "stuck")  # nothing moved: these have `since`

_ASKING = re.compile(
    r"(\[\s*(y/n|y/N|Y/n|yes/no)\s*\]|\(\s*(y/n|yes/no)\s*\))\s*[:?]?\s*$"
    r"|\b(password|passphrase|username|token)\b[^:]{0,40}:\s*$"
    r"|\bpress (any key|enter|return)\b"
    r"|^\s*\?\s+\S.*"  # an interactive prompt library's question
    r"|\b(are you sure|do you want|would you like|overwrite|continue)\b[^?]{0,80}\?\s*$",
    re.IGNORECASE)
_WAITING = re.compile(
    r"\b(retry(ing)?|will retry|retrying in|waiting (for|until|on)|sleeping|backing off|"
    r"back-?off|next attempt|attempt \d+\s*(of|/)\s*\d+|trying again)\b", re.IGNORECASE)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _aged(report: dict[str, Any], key: str, age: float) -> float | None:
    value = _number(report.get(key))
    return None if value is None else value + age


def _quote(line: str | None) -> str:
    return f'"{line.strip()}"' if line and line.strip() else "nothing"


def _download_text(item: dict[str, Any]) -> str:
    parts = []
    speed = _number(item.get("rate_bytes_s"))
    if speed is not None:
        parts.append(rate(speed))
    done, total = _number(item.get("done_bytes")), _number(item.get("total_bytes"))
    if done is not None and total:
        parts.append(f"{size(done)} of {size(total)}")
    name = item.get("name")
    what = f" of {name}" if name else ""
    return f"{', '.join(parts)}{what}" if parts else f"{item.get('what') or 'a download'}{what}"


def _slow(report: dict[str, Any], compute_idle: float | None, limit: float) -> dict[str, Any] | None:
    item = report.get("download") if isinstance(report.get("download"), dict) else None
    speed = _number(item.get("rate_bytes_s")) if item else None
    if item and not item.get("stalled") and speed is not None and speed < SLOW_BYTES_S \
            and item.get("waiting_on_network"):
        return {"verdict": "slow", "text": f"Downloading slowly: {_download_text(item)}."}
    io = _number(report.get("io_kib_s"))
    if compute_idle is not None and compute_idle >= limit and io is not None \
            and 0 < io * 1024 < SLOW_BYTES_S:
        return {"verdict": "slow", "text": f"Moving only {rate(io * 1024)} of data, with no "
                f"output and almost no CPU for {duration(compute_idle)}."}
    return None


def _quiet(report: dict[str, Any], idle: float, stage: str | None, limit: float
           ) -> dict[str, Any]:
    line = report.get("last_line") if isinstance(report.get("last_line"), str) else None
    for_how_long, where = duration(idle), f" in stage {stage}" if stage else ""
    if line and _ASKING.search(line):
        return {"verdict": "asking", "text": f"Waiting for an answer it will never get, for "
                f"{for_how_long}: {_quote(line)}. Jobs get no input: cancel it, and make the "
                "command ask nothing."}
    if line and _WAITING.search(line):
        if idle < WAITING_FOR * limit:
            return {"verdict": "waiting", "text": f"Quiet for {for_how_long}, and its last line "
                    f"says it is waiting: {_quote(line)}."}
        return {"verdict": "stuck", "text": f"Looks stuck: it said it was waiting, and nothing "
                f"has moved for {for_how_long}{where}: {_quote(line)}."}
    item = report.get("download") if isinstance(report.get("download"), dict) else None
    if item and item.get("stalled"):
        return {"verdict": "stuck", "text": f"Looks stuck: its download ({_download_text(item)}) "
                f"has not moved, and nothing else has for {for_how_long}{where}."}
    data = ", no CPU and no data moving" if _number(report.get("io_kib_s")) is not None \
        else " and no CPU"
    return {"verdict": "stuck", "text": f"Looks stuck: no output{data} for {for_how_long}"
            f"{where}. Last line: {_quote(line)}."}


def verdict(job: dict[str, Any], report: dict[str, Any] | None, stage: str | None,
            limit_s: float, now: float) -> dict[str, Any] | None:
    """The verdict of a running agent job, or None when there is none to give: not running,
    paused, cancelled, a GitHub run, or no reading yet. `since` is when it went still."""
    if (job.get("kind") != "job" or job.get("state") not in ("starting", "running")
            or job.get("paused") or job.get("cancel_requested") or not report):
        return None
    at = _number(report.get("at"))
    age = max(0.0, now - at) if at is not None else 0.0
    idle, compute_idle = _aged(report, "idle_s", age), _aged(report, "compute_idle_s", age)
    found: dict[str, Any] | None
    if idle is not None and idle >= limit_s:
        found = {**_quiet(report, idle, stage, limit_s), "since": round(now - idle, 1),
                 "quiet_s": round(idle, 1)}
    else:
        found = _slow(report, compute_idle, limit_s)
        if found is None:
            if idle is None:
                return None  # cannot tell, and nothing says slow
            found = {"verdict": "working", "text": ""}
    return {**found, "stage": stage, "last_line": report.get("last_line"),
            "limit_s": limit_s}
