"""The node's side of an isolated runner's job-started hook (place_hook.py).

The container writes the job's GitHub values to `io/request.json` and its event to
`io/event.json`, then waits for `io/answer.json`. The node reads them once, before any step
of the job has run, never through a symlink and only up to a size, keeps only GitHub's own
names, runs the guard (guard.py) on them, and on a pass reserves the build slot as a host
runner's hook does (hooks.started), under the place's own name, so the reservation file,
supervision and the dashboard find it in the place's folder.
"""

from __future__ import annotations

import io as _io
import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mulebox.runners import guard, hooks, layout
from mulebox.runners.place_hook import ANSWER, EVENT, REQUEST
from mulebox.worker.link import CoordinatorLink
from mulebox.worker.paths import NodePaths

MAX_REQUEST_BYTES = 256 * 1024
_NAME = re.compile(r"(GITHUB_[A-Z0-9_]{1,60}|RUNNER_NAME)")


def read_request(io_dir: Path) -> dict[str, str] | None:
    """The request, or None while there is none (or it is not one JSON object of strings)."""
    try:
        fd = os.open(io_dir / REQUEST, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    with os.fdopen(fd, "rb") as fh:
        data = fh.read(MAX_REQUEST_BYTES + 1)
    if len(data) > MAX_REQUEST_BYTES:
        return {}
    try:
        raw = json.loads(data)
    except ValueError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items()
            if isinstance(k, str) and _NAME.fullmatch(k) and isinstance(v, str)}


def answer(paths: NodePaths, io_dir: Path, ok: bool, message: str) -> None:
    """Write the answer the container waits for (0o644: its user is not the node's)."""
    layout.write_file(paths, io_dir / ANSWER, json.dumps({"ok": ok, "message": message}),
                      0o644)


def job_env(request: dict[str, str], io_dir: Path, place: str) -> dict[str, str]:
    """The job's values as the guard and the slot see them: the event read from the node's
    copy, and the place's name, not the one-job runner's, as the runner."""
    return {**request, "GITHUB_EVENT_PATH": str(io_dir / EVENT), "RUNNER_NAME": place}


def handle(request: dict[str, str], *, folder: Path, io_dir: Path, worker: str,
           link: CoordinatorLink, paths: NodePaths,
           reserve: Callable[..., int] = hooks.started) -> tuple[bool, str]:
    """Decide on one job: the guard, then the slot. Returns (allowed, message for the job)."""
    meta: Any = guard.runner_meta(folder)
    env = job_env(request, io_dir, folder.name)
    reason = guard.refusal(env, meta) if request else "a job whose request cannot be read"
    if reason:
        return False, (f"mulebox: this runner refuses {reason}: it runs only its own "
                       "repository's jobs, started by the accounts it was registered for")
    out = _io.StringIO()
    code = reserve(env, worker, link, paths, out=out)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return code == 0, lines[-1] if lines else ""
