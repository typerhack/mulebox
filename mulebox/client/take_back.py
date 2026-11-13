"""`mulebox run --take <path>`: write what a passed run brought back into the project.

The paths were checked before the job went (common/take_paths.py), and one that the snapshot
would never send, such as `.env` or a key, is refused there: taking it back could overwrite a
secret with the node's copy. Each file is fetched in chunks from the coordinator
(coordinator/taken.py), written next to its place and renamed over it, and only inside the
project: a path through a symlink is refused rather than followed.
"""

from __future__ import annotations

import base64
import os
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from mulebox.client import report
from mulebox.client.excludes import Excludes
from mulebox.common import units
from mulebox.common.protocol import MessageType
from mulebox.common.take_paths import MAX_FILE_BYTES, checked

Call = Callable[[Any], Any]


def check(paths: Sequence[str], exclude: Sequence[str] = ()) -> tuple[str, ...]:
    """The paths, or ValueError: shape (take_paths.py), and never what the snapshot keeps here."""
    found = checked(paths)
    rules = Excludes(exclude)
    for path in found:
        if rules.excluded(path):
            raise ValueError(f"--take {path!r}: mulebox never moves this file between machines "
                             "(a secret, or `exclude:` in .mulebox.yml)")
    return found


def _fetch(call: Call, request: Callable[..., Any], job_id: str, index: int) -> bytes | None:
    data, offset = b"", 0
    while True:
        body = call(request(MessageType.TAKE, job_id=job_id, index=index, offset=offset)).body
        if body.get("missing"):
            return None
        chunk = base64.b64decode(body.get("data") or "")
        data += chunk
        offset += len(chunk)
        if body.get("eof") or not chunk or len(data) > MAX_FILE_BYTES:
            return data


def _target(root: Path, path: str) -> Path:
    """Where `path` goes; ValueError if any part of the way is a symlink."""
    current = root
    for part in path.split("/"):
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{path} goes through a symlink here; not written")
    return current


def _write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.mulebox-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if target.exists():
            os.chmod(temp, target.stat().st_mode & 0o777)
        os.replace(temp, target)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def bring_back(call: Call, request: Callable[..., Any], job_id: str, paths: Sequence[str],
               root: Path, err: TextIO) -> int:
    """Write each file into the project; 0 if all came, else 1, with what did not and why."""
    missing = 0
    for index, path in enumerate(paths):
        data = _fetch(call, request, job_id, index)
        if data is None:
            report.status(err, f"not taken back: {path} (not there after the command, or the "
                               "node's mulebox is older; the job's log says which)")
            missing += 1
            continue
        try:
            _write(_target(root, path), data)
        except (ValueError, OSError) as exc:
            report.status(err, f"not taken back: {path}: {exc}")
            missing += 1
            continue
        size = units.size(len(data))
        report.status(err, f"taken back: {path} ({size})")
    return 1 if missing else 0
