"""Render the job list from a `queue_ok` reply as text lines (pure; no terminal I/O).

Used by `mulebox queue` (plain table, printed once) and by the live view in tui.py.
Sections (running, queued, recent), their order, the shown state and the elapsed time
come from the shared status model (common/status.py), which the web dashboard uses too.
"""

from __future__ import annotations

import time
from typing import Any

from mulebox.client.report import format_duration, short_id
from mulebox.common.status import elapsed_s, queue_position, sections, shown_state

COLUMNS = ("ID", "PROJECT", "JOB", "BRANCH", "STATE", "ELAPSED", "POS")
PROJECT_COLUMNS = ("PROJECT", "JOBS", "LAST RUN", "LAST RESULT")
_MAX_CELL = {"PROJECT": 20, "JOB": 16, "BRANCH": 28}
_TITLES = {"running": "Running", "queued": "Queued", "recent": "Recent"}


def _elapsed(job: dict[str, Any], now: float) -> str:
    seconds = elapsed_s(job, now)
    return format_duration(seconds) if seconds is not None else "-"


def _cell(text: Any, limit: int | None) -> str:
    value = "-" if text is None or text == "" else str(text)
    value = "".join(ch if ch.isprintable() else "?" for ch in value)  # no escapes from data
    if limit is not None and len(value) > limit:
        value = value[: limit - 1] + "~"
    return value


def job_row(job: dict[str, Any], now: float, full_ids: bool = False) -> list[str]:
    job_id = str(job.get("job_id", ""))
    values = {
        "ID": job_id if full_ids else short_id(job_id),
        "PROJECT": job.get("project"),
        "JOB": job.get("job"),
        "BRANCH": job.get("branch"),
        "STATE": shown_state(job),
        "ELAPSED": _elapsed(job, now),
        "POS": queue_position(job),
    }
    return [_cell(values[c], _MAX_CELL.get(c)) for c in COLUMNS]


def render_projects(projects: list[dict[str, Any]]) -> list[str]:
    """Lines of the `mulebox projects` table, newest first as the coordinator sent them."""
    if not projects:
        return ["No projects have run on this coordinator yet."]
    rows = [[_cell(p.get("project"), None), str(p.get("jobs", "-")),
             time.strftime("%Y-%m-%d %H:%M", time.localtime(p.get("last_run") or 0)),
             _cell(shown_state(p), None)] for p in projects]
    widths = [max(len(line[i]) for line in [list(PROJECT_COLUMNS), *rows])
              for i in range(len(PROJECT_COLUMNS))]
    return ["  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip()
            for line in [list(PROJECT_COLUMNS), *rows]]


def render_table(
    jobs: list[dict[str, Any]], now: float, width: int = 120, full_ids: bool = False
) -> list[str]:
    """Lines of the job table, each cut to `width` characters."""
    groups = [(_TITLES[name], group) for name, group in sections(jobs)]
    rows = [job_row(j, now, full_ids) for _, group in groups for j in group]
    widths = [max([len(c), *(len(r[i]) for r in rows)]) for i, c in enumerate(COLUMNS)]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()[:width]

    out = [line(list(COLUMNS))]
    index = 0
    for title, group in groups:
        out.append(f"{title} ({len(group)})"[:width])
        for _ in group:
            out.append(line(rows[index]))
            index += 1
        if not group:
            out.append("  none"[:width])
    return out


def render_screen(
    jobs: list[dict[str, Any]],
    now: float,
    width: int,
    height: int,
    header: str,
    footer: str,
) -> list[str]:
    """The live view: header, table, footer; exactly `height` lines (padded or cut)."""
    body = render_table(jobs, now, width)
    room = max(0, height - 3)
    if len(body) > room:
        body = body[: max(0, room - 1)] + ["..."[:width]]
    lines = [header[:width], "", *body]
    lines = lines[: max(0, height - 1)]
    lines += [""] * (height - 1 - len(lines))
    return [*lines, footer[:width]] if height > 0 else []
