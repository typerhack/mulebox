"""A GitHub runner job's steps and output, from the runner's own files, into its slot's log.

A runner reservation only holds a build slot: the job runs inside GitHub's runner, which sends its
output to GitHub. The runner also writes two things on this machine, in `<runner>/_diag/`:

- `Worker_<time>.log`, its own diary, written as it goes, each line with its time to the second:
  the job's message with its `planId` first, then `Processing step: DisplayName='...'` as each
  step starts, `... current step result '<Succeeded|Failed|Canceled|Skipped>'` as it ends, and
  `... web console lines for record '<id>'` while a step prints, which ties that step's record
  id to its name.
- `pages/<plan id>_<record id>_<n>.log`, a step's output. It is written in blocks of about
  4 KB or when the step ends, then deleted once GitHub has it, seconds later.
  The job's own record has a page too, repeating every step; it is skipped.

So the log here has every step as it starts and as it ends, with the diary's times
(`mulebox: step at <time>: <name>`, then `mulebox: step <passed|failed|cancelled|skipped> at
<time>: <name>`, read back by web/src/lib/cilog.ts), and a step's output once the runner writes
it: a busy step in pieces, a quiet one when it ends. A page is kept open from when it appears,
because on Linux an open file can still be read after it is deleted. A step shorter than one
poll can be missed; GitHub has everything. The last step is read once more after the slot is
released, as its completed hook ends the reservation (reservations.LATE_LOG_S). Only reading happens here, nothing in the runner's
folder is changed. Output goes through LogTailer, so it is redacted like any job's log.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import BinaryIO

from mulebox.common.redact import StreamRedactor
from mulebox.runners import diary
from mulebox.runners.diary import STEP
from mulebox.worker.logtail import LogTailer, MakeRequest, Send

READ_BYTES = 256 * 1024
MAX_OPEN = 64  # pages held open at once; a job has one per step
_RECORD = re.compile(r"web console lines for record '([0-9a-f-]{36})'")
_JOB = re.compile(r"\bJob ID ([0-9a-f-]{36})\b")  # its own page repeats every step: skipped
_PLAN = re.compile(r'"planId":\s*"([0-9a-f-]{36})"')
_STAMP = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
_GROUP, _END_GROUP = "##[group]", "##[endgroup]"
_DIARY_TIME = re.compile(r"^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\dZ) ")
_ENDED = re.compile(r"current step result '(\w+)'")
_RESULTS = {"succeeded": "passed", "succeededwithissues": "passed", "failed": "failed",
            "canceled": "cancelled", "cancelled": "cancelled", "skipped": "skipped"}


def _at(line: str) -> str:
    """` at <time>` from a diary line's own time, or nothing when it has none."""
    found = _DIARY_TIME.match(line)
    return f" at {found[1]}T{found[2]}" if found else ""


def _page_line(line: str) -> str | None:
    """A line of a page as GitHub shows it: no time stamp, groups as their title."""
    text = _STAMP.sub("", line)
    if text.startswith(_END_GROUP):
        return None
    return text.removeprefix(_GROUP)


class _Page:
    def __init__(self, fh: BinaryIO, record: str) -> None:
        self.fh, self.record, self.partial = fh, record, b""


class RunnerLog:
    """Follows one runner job. `poll` reads what is new, `send` ships it (LinkError propagates)."""

    def __init__(self, job_id: str, runner_dir: Path, make_request: MakeRequest,
                 redactor: StreamRedactor | None = None) -> None:
        self.diag = Path(runner_dir) / "_diag"
        self.tailer = LogTailer(None, job_id, "", make_request, redactor)
        self._worker_log: Path | None = None
        self._worker_pos = 0
        self._worker_partial = ""
        self._plan: str | None = None
        self._job: str | None = None
        self._step: str | None = None
        self._records: dict[str, str] = {}  # record id -> step name
        self._pages: dict[str, _Page] = {}
        self._done: set[str] = set()  # pages read to their end
        self._shown: str | None = None  # the step whose output was last printed

    def poll(self, started_after: float) -> None:
        """Read new lines of the runner's diary written since `started_after` (wall clock),
        and of that job's pages."""
        if self._worker_log is None:
            self._worker_log = self._find_worker_log(started_after)
        if self._worker_log is not None:
            self._read_worker_log()
        if self._plan is not None:
            self._read_pages()

    @property
    def step(self) -> str | None:
        """The step the runner is on, as GitHub names it."""
        return self._step

    def send(self, send: Send) -> None:
        self.tailer.send(send)

    def close(self) -> None:
        for page in self._pages.values():
            page.fh.close()
        self._pages.clear()

    def _find_worker_log(self, started_after: float) -> Path | None:
        newest = diary.newest(self.diag.parent)
        try:
            return newest if newest and newest.stat().st_mtime >= started_after else None
        except OSError:
            return None

    def _read_worker_log(self) -> None:
        try:
            with open(self._worker_log, "rb") as fh:
                fh.seek(self._worker_pos)
                data = fh.read(READ_BYTES)
        except OSError:
            return
        self._worker_pos += len(data)
        text = self._worker_partial + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self._worker_partial = lines.pop()
        for line in lines:
            self._diary_line(line)

    def _diary_line(self, line: str) -> None:
        if self._plan is None and (plan := _PLAN.search(line)):
            self._plan = plan[1]
        elif self._job is None and (job := _JOB.search(line)):
            self._job = job[1]
        elif step := STEP.search(line):
            self._step = step[1]
            self.tailer.note(f"mulebox: step{_at(line)}: {self._step}\n")
        elif self._step and (record := _RECORD.search(line)):
            self._records.setdefault(record[1], self._step)
        elif self._step and (ended := _ENDED.search(line)):
            if result := _RESULTS.get(ended[1].lower()):
                self.tailer.note(f"mulebox: step {result}{_at(line)}: {self._step}\n")

    def _read_pages(self) -> None:
        try:
            names = sorted(p.name for p in (self.diag / "pages").glob(f"{self._plan}_*.log"))
        except OSError:
            names = []
        for name in names:
            record = name.split("_")[1] if name.count("_") >= 2 else ""
            if record == self._job:
                continue
            if name not in self._pages and name not in self._done and len(self._pages) < MAX_OPEN:
                try:
                    fh = open(self.diag / "pages" / name, "rb")
                except OSError:
                    continue
                self._pages[name] = _Page(fh, record)
        for name, page in list(self._pages.items()):
            if self._read_page(page):
                page.fh.close()
                del self._pages[name]
                self._done.add(name)

    def _read_page(self, page: _Page) -> bool:
        """Print what is new in a page; True once it is deleted and read to its end."""
        data = page.fh.read(READ_BYTES)
        gone = not data and os.fstat(page.fh.fileno()).st_nlink == 0
        page.partial += data
        lines = page.partial.split(b"\n")
        page.partial = b"" if gone else lines.pop()
        shown = [kept for raw in lines if raw
                 if (kept := _page_line(raw.decode("utf-8", errors="replace").rstrip("\r")))
                 is not None]
        if shown:
            step = self._records.get(page.record, "a step")
            if step != self._shown:
                self._shown = step
                self.tailer.note(f"--- output of {step}\n")
            self.tailer.note("".join(f"{line}\n" for line in shown))
        return gone
