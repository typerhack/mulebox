"""A job whose images could not be fetched never ran, so it must not read as a failed check.

`docker compose up --no-start` runs in the job's script (compose_job.py), so a registry out of
reach ends the job like a failing command: exit 1, as if the project were broken. An agent would
then go looking for a bug in its code. The job's last line in the `images` stage tells the two
apart. The texts are real ones from Docker 29 and Compose 5.6, and the usual Go network errors.

A build fails with `did not complete successfully`, whatever its command printed: there the
project's own code ran, and it stays a failed job. So does an image that does not exist: the
registry answered, and the project has to fix the name.
"""

from __future__ import annotations

import re

from mulebox.common.protocol import Outcome
from mulebox.common.status import IMAGES, NOT_STARTED_NOTE
from mulebox.worker.logtail import LogTailer

REASON = "no image could be fetched: the machine's network or the registry failed"
_BUILD_STEP = "did not complete successfully"
_NETWORK = re.compile("|".join((
    r"dial tcp", r"no such host", r"connection refused", r"connection reset", r"i/o timeout",
    r"TLS handshake timeout", r"context deadline exceeded", r"name resolution",
    r"server misbehaving", r"network is unreachable", r"no route to host", r"unexpected EOF",
    r"toomanyrequests", r"\b50[234]\b.*(Bad Gateway|Service Unavailable|Gateway Time)",
)), re.IGNORECASE)


def network_failed(stage: str | None, last_line: str | None) -> bool:
    """Whether a job that failed in `stage`, printing `last_line`, failed on the network."""
    if stage != IMAGES or not last_line or _BUILD_STEP in last_line:
        return False
    return _NETWORK.search(last_line) is not None


def checked(outcome: Outcome, exit_code: int | None, tailer: LogTailer) -> int | None:
    """The code to report for a finished job, after `tailer.finish()`. None: it never ran."""
    steps = tailer.steps
    if outcome is not Outcome.FAILED or not network_failed(steps.stage, steps.last_line):
        return exit_code
    tailer.note(f"{NOT_STARTED_NOTE} {REASON}\n")
    tailer.finish()
    return None
