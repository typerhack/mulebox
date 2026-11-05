"""The short failure summary an agent reads instead of a huge log.

Pure: `LogTail` keeps the end of a log, `relevant_lines` picks what is worth reading from it
and `render` makes the summary. What is left out:

- everything after the worker's "containers" line: on a failed compose job the log ends with
  the logs of every container, which are rarely the failure and would push it out of view;
- progress: progress bars, download sizes, image layers, compose start-up lines, and text a
  terminal would have overwritten (`\\r`);
- runs of a line that differs only in its numbers, kept once with a count.

The stage comes from the result: the coordinator works it out from the job's stage rows
(`common/status.py`, `failed_step`). Without one, from an older worker or a job that left no
rows, the only stage a log can show is a job that never started.
"""

from __future__ import annotations

import re
from typing import Any

from mulebox.client import report
from mulebox.common.status import CONTAINER_LOGS_NOTE, ENDED_BADLY, NOT_STARTED_NOTE

TAIL_BYTES = 256 * 1024  # room for the container logs (50 lines per service) and what precedes
MAX_LINES = 20
MAX_WIDTH = 300
SIMILAR_RUN = 3  # shorter runs of similar lines stay: they may be different test failures
STAGE_START = "start"

_ANSI = re.compile(r"\x1b(\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(\x07|\x1b\\)|[@-Z\\^_])")
_DIGITS = re.compile(r"\d+")
_LAYER_WORDS = ("Pulling fs layer|Pulling|Waiting|Downloading|Verifying Checksum|Extracting|"
                "Pull complete|Download complete|Already exists")
_COMPOSE_WORDS = ("Creating|Created|Starting|Started|Waiting|Healthy|Running|Pulling|Pulled|"
                  "Stopping|Stopped|Removing|Removed|Recreated|Recreate")
_PROGRESS = re.compile("|".join((
    r"\[[=#>.\- ]{4,}\]",  # [=====>    ]
    r"[█▉▊▋▌▍▎▏░▒▓]{2,}",  # bars
    r"^\s*\d{1,3}(\.\d+)?%",  # 45% ...
    r"\b\d+(\.\d+)?\s*[kKMG]?i?B\s*/\s*\d",  # 12MB/40MB
    r"^\s*Progress: resolved\b",  # pnpm
    r"^\s*(Downloading|Extracting|Fetching)\b",
    rf"^[0-9a-f]{{12}}: ({_LAYER_WORDS})\b",  # image layers
    rf"^\W*(Container|Network|Volume|Image) \S+\s+({_COMPOSE_WORDS})\s*$",  # compose up
)))


class LogTail:
    """The last `keep` characters of a log, fed in pieces."""

    def __init__(self, keep: int = TAIL_BYTES) -> None:
        self.keep = keep
        self.text = ""
        self.cut = False

    def feed(self, text: str) -> None:
        joined = self.text + text
        self.cut = self.cut or len(joined) > self.keep
        self.text = joined[-self.keep:]


def _printable(line: str) -> str:
    return "".join(ch if ch.isprintable() or ch == "\t" else "?" for ch in line)


def _clean(raw: str) -> str:
    """What a terminal would show of one line: the last `\\r` piece, without escapes."""
    shown = _ANSI.sub("", raw).rstrip("\r")
    return _printable(shown.rsplit("\r", 1)[-1]).rstrip()


def _before_containers(text: str) -> str:
    """Without the container logs, but with the worker's last word when it stands after them."""
    at = text.find(CONTAINER_LOGS_NOTE)
    if at < 0:
        return text
    last = text.rstrip().rsplit("\n", 1)[-1]
    return f"{text[:at]}{last}" if last.startswith(NOT_STARTED_NOTE) else text[:at]


def _collapse(lines: list[str]) -> list[str]:
    """A run of SIMILAR_RUN or more lines alike but for numbers becomes its last line."""
    out: list[str] = []
    index = 0
    while index < len(lines):
        shape = _DIGITS.sub("#", lines[index])
        end = index + 1
        while end < len(lines) and _DIGITS.sub("#", lines[end]) == shape:
            end += 1
        run = lines[index:end]
        out += run if len(run) < SIMILAR_RUN else [f"{run[-1]} (and {len(run) - 1} like it)"]
        index = end
    return out


def relevant_lines(tail: LogTail, limit: int = MAX_LINES) -> list[str]:
    """The last `limit` lines worth reading, oldest first."""
    text = _before_containers(tail.text)
    raw = text.split("\n")
    if tail.cut:
        raw = raw[1:]  # its start is gone
    lines = [_clean(line) for line in raw]
    kept = [line for line in lines if line and not _PROGRESS.search(line)]
    return [line[:MAX_WIDTH] for line in _collapse(kept)[-limit:]]


def wanted(result: dict[str, Any]) -> bool:
    """Passed and cancelled jobs have nothing to summarize."""
    return result.get("outcome") in ENDED_BADLY


def _stage(result: dict[str, Any], lines: list[str]) -> str | None:
    stage = result.get("stage")
    if isinstance(stage, str) and stage:
        return stage
    return STAGE_START if any(ln.startswith(NOT_STARTED_NOTE) for ln in lines) else None


def render(job_id: str, result: dict[str, Any], lines: list[str]) -> list[str]:
    """The summary as text lines; the exit code is the one this job's commands return."""
    out = [f"failure summary of job {job_id}"]
    stage = _stage(result, lines)
    if stage:
        out.append(f"failed stage: {stage}")
    out.append(f"outcome: {result.get('outcome')}, exit code {report.exit_code_for(result)}")
    if lines:
        out.append(f"last lines of the log, without progress and container logs "
                   f"(full log: mulebox logs {job_id}):")
        out += [f"| {line}" for line in lines]
    else:
        out.append("the log has nothing else to show")
    return out
