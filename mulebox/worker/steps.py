"""Which stage a job is in, from the worker's own calls and from marks in the job's output.

The worker itself runs `prepare`, `environment` and `cleanup`. The rest happens inside the
job's script, so the script says when each stage starts: a line of its own in the output,
`::mulebox-step:<marker>:<time>:<stage>`, removed again here before anything is stored. Being
in the output keeps it in order with what the stage printed, so the last line before a failure
is the failing line of that stage. The marker is random per job, so a project's output cannot
produce one by accident. A forged one could only make a row wrong, and a job is trusted.

`set -e` is on, so a stage that is followed by another one passed. The last stage ends when
the process does, with its exit code. That needs no trap, and a project's own trap or `exit`
in `setup` cannot break it. A failing job's report on its containers says `end` first, so it
counts neither as time nor as the failing line of the stage.

Lines come here redacted, so nothing here can hold a secret that the log would not.

The script must not contain `${`: systemd expands that in a unit's command line, inside
a long argument as well.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from mulebox.common.status import CLEANUP, MAX_FAILING_LINE, STAGES

END = "end"
SHELL_NAME = "mulebox_step"
_PREFIX = "::mulebox-step:"


def new_marker() -> str:
    return secrets.token_hex(8)


def shell_function(marker: str) -> str:
    """The script line defining `mulebox_step <stage>`. A failed write must not end the job."""
    return (f'{SHELL_NAME}() {{ local now=$EPOCHREALTIME; [ -n "$now" ] || now=$(date +%s); '
            f'echo "{_PREFIX}{marker}:$now:$1" || true; }}')


class StepTracker:
    def __init__(self, marker: str = "") -> None:
        self.marker = marker or new_marker()
        self._mark = re.compile(
            re.escape(f"{_PREFIX}{self.marker}:") + r"(\d+(?:[.,]\d+)?):([a-z]+)[\r\n]*\Z")
        self._rows: list[dict[str, Any]] = []
        self._changed: set[int] = set()
        self._last_line: str | None = None
        self._ended_at: float | None = None

    @property
    def _open(self) -> dict[str, Any] | None:
        row = self._rows[-1] if self._rows else None
        return row if row is not None and row["finished_at"] is None else None

    def begin(self, stage: str, at: float) -> None:
        """Start `stage`; one still open passed."""
        self.close(0, at, failed=False)
        self._rows.append({"seq": len(self._rows), "stage": stage, "started_at": at,
                           "finished_at": None, "exit_code": None, "bytes_downloaded": None,
                           "failing_line": None})
        self._changed.add(len(self._rows) - 1)
        self._last_line, self._ended_at = None, None

    def close(self, exit_code: int | None, at: float, failed: bool) -> None:
        """End the open stage, if any. `failed` keeps the last line it printed."""
        row = self._open
        if row is None:
            return
        end = at if self._ended_at is None else self._ended_at
        row["finished_at"] = max(row["started_at"], end)
        row["exit_code"] = exit_code
        row["failing_line"] = self._last_line if failed else None
        self._changed.add(row["seq"])

    def line(self, text: str) -> str:
        """One redacted line of output; returns what stays of it in the log."""
        found = self._mark.search(text)
        if found is None:
            self._remember(text)
            return text
        at, stage = float(found[1].replace(",", ".")), found[2]
        if stage == END:
            self._ended_at = at
        elif stage in STAGES:
            self.begin(stage, at)
        kept = text[:found.start()]  # output that did not end in a line break
        return f"{kept}\n" if kept else ""

    def _remember(self, text: str) -> None:
        stripped = text.strip()
        if stripped and self._ended_at is None:
            self._last_line = stripped[:MAX_FAILING_LINE]

    def add_bytes(self, count: int) -> None:
        """Downloaded while the open stage ran."""
        row = self._open
        if count and row is not None:
            row["bytes_downloaded"] = (row["bytes_downloaded"] or 0) + count
            self._changed.add(row["seq"])

    @property
    def stage(self) -> str | None:
        """The stage in progress, as far as this tracker knows."""
        return self._open["stage"] if self._open is not None else None

    def finish_cleanup(self, at: float) -> None:
        if self._open is not None and self._open["stage"] == CLEANUP:
            self.close(0, at, failed=False)

    def pending(self) -> list[dict[str, Any]]:
        """Rows changed since the last `sent`, whole: the coordinator replaces them."""
        return [dict(self._rows[seq]) for seq in sorted(self._changed)]

    def sent(self) -> None:
        self._changed.clear()
