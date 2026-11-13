"""Files a passed run brings back (`mulebox run --take`, common/take_paths.py), on the worker.

Once the command passed, each named file is read from the job's worktree: a regular file
inside it, reached without a symlink, within the size caps. What is not there, or not allowed,
is noted in the job's log and skipped; the client says so too. The files then go to the
coordinator in chunks before the result (`send`), from where they left off after a lost link.
"""

from __future__ import annotations

import base64
import os
import stat
from collections.abc import Callable
from pathlib import Path

from mulebox.common import units
from mulebox.common.mounts import is_within
from mulebox.common.protocol import Message, MessageType
from mulebox.common.take_paths import CHUNK_BYTES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, problem
from mulebox.worker.link import request

Taken = list[tuple[int, bytes]]  # (index in the job's `take` list, the file's bytes)


def _read(tree: Path, path: str) -> bytes | str:
    """The file's bytes, or why it is not taken."""
    why = problem(path)
    if why:
        return why
    full = tree / path
    try:
        info = os.lstat(full)
        real = Path(os.path.realpath(full))
    except OSError:
        return "is not there after the command"
    if not is_within(real, Path(os.path.realpath(tree))) or real != Path(os.path.realpath(tree)) / path:
        return "goes through a link"
    if not stat.S_ISREG(info.st_mode):
        return "is not a plain file"
    if info.st_size > MAX_FILE_BYTES:
        return f"is over {units.size(MAX_FILE_BYTES)}"
    try:
        with open(full, "rb", opener=lambda p, f: os.open(p, f | os.O_NOFOLLOW)) as fh:
            return fh.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        return f"cannot be read ({exc.strerror})"


def read_files(tree: Path, paths: list[str], note: Callable[[str], None]) -> Taken:
    found: Taken = []
    total = 0
    for index, path in enumerate(paths):
        data = _read(Path(tree), path)
        if isinstance(data, bytes) and total + len(data) > MAX_TOTAL_BYTES:
            data = f"would pass {units.size(MAX_TOTAL_BYTES)} with the others"
        if isinstance(data, str):
            note(f"mulebox: not taken back: {path} {data}\n")
            continue
        total += len(data)
        found.append((index, data))
        note(f"mulebox: taken back: {path} ({units.size(len(data))})\n")
    return found


def chunks(taken: Taken) -> list[tuple[int, int, bytes]]:
    """(index, offset, bytes) to send, in order; an empty file is one empty chunk."""
    return [(index, offset, data[offset:offset + CHUNK_BYTES])
            for index, data in taken for offset in range(0, max(len(data), 1), CHUNK_BYTES)]


def send(job_id: str, attempt_id: str, pending: list[tuple[int, int, bytes]],
         call: Callable[[Message], Message]) -> None:
    """Send the pending chunks in order, removing each once it got through: after a lost link
    (LinkError propagates) the next try starts where this one stopped."""
    while pending:
        index, offset, data = pending[0]
        call(request(MessageType.TAKEN, job_id=job_id, attempt_id=attempt_id, index=index,
                     offset=offset, data=base64.b64encode(data).decode("ascii")))
        pending.pop(0)
