"""Render the job list from a `queue_ok` reply as text lines (pure; no terminal I/O).

Used by `mulebox queue` (plain table, printed once) and by the live view in tui.py.
Sections: running (starting, running, cleaning), queued (uploading, queued) and recent
(finished, newest first). Elapsed is time waiting for queued jobs, time running for
active ones and the run time for finished ones.
"""

from __future__ import annotations

from typing import Any

from mulebox.client.report import duration_of, format_duration, short_id

COLUMNS = ("ID", "PROJECT", "JOB", "BRANCH", "STATE", "ELAPSED", "POS")
ACTIVE = ("starting", "running", "cleaning")
WAITING = ("uploading", "queued")
_MAX_CELL = {"PROJECT": 20, "JOB": 16, "BRANCH": 28}


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _elapsed(job: dict[str, Any], now: float) -> str:
    state = job.get("state")
    if state == "finished":
        return format_duration(duration_of(job))
    since = _number(job.get("started_at")) if state in ACTIVE else None
    since = since if since is not None else _number(job.get("created_at"))
    return format_duration(now - since) if since is not None else "-"


def _cell(text: Any, limit: int | None) -> str:
    value = "-" if text is None or text == "" else str(text)
    value = "".join(ch if ch.isprintable() else "?" for ch in value)  # no escapes from data
    if limit is not None and len(value) > limit:
        value = value[: limit - 1] + "~"
    return value


def job_row(job: dict[str, Any], now: float, full_ids: bool = False) -> list[str]:
    job_id = str(job.get("job_id", ""))
    state = job.get("outcome") if job.get("state") == "finished" else job.get("state")
    position = job.get("position") if job.get("state") in WAITING else None
    values = {
        "ID": job_id if full_ids else short_id(job_id),
        "PROJECT": job.get("project"),
        "JOB": job.get("job"),
        "BRANCH": job.get("branch"),
        "STATE": state,
        "ELAPSED": _elapsed(job, now),
        "POS": position,
    }
    return [_cell(values[c], _MAX_CELL.get(c)) for c in COLUMNS]


def _sections(jobs: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    def created(job: dict[str, Any]) -> float:
        return _number(job.get("created_at")) or 0.0

    active = sorted((j for j in jobs if j.get("state") in ACTIVE), key=created)
    waiting = sorted(
        (j for j in jobs if j.get("state") in WAITING),
        key=lambda j: (_number(j.get("position")) or float("inf"), created(j)),
    )
    done = sorted(
        (j for j in jobs if j.get("state") == "finished"),
        key=lambda j: _number(j.get("finished_at")) or created(j),
        reverse=True,
    )
    return [("Running", active), ("Queued", waiting), ("Recent", done)]


def render_table(
    jobs: list[dict[str, Any]], now: float, width: int = 120, full_ids: bool = False
) -> list[str]:
    """Lines of the job table, each cut to `width` characters."""
    sections = _sections(jobs)
    rows = [job_row(j, now, full_ids) for _, group in sections for j in group]
    widths = [max([len(c), *(len(r[i]) for r in rows)]) for i, c in enumerate(COLUMNS)]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) for c, w in zip(cells, widths)).rstrip()[:width]

    out = [line(list(COLUMNS))]
    index = 0
    for title, group in sections:
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
