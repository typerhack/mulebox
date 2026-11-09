"""Files a run brings back (`mulebox run --take`, common/take_paths.py): kept, then handed out.

`<staging>/taken/<job_id>.<index>` holds the file at position `index` of the job's `take` list,
as the worker sent it (`taken`), in chunks at increasing offsets; a resent chunk changes nothing.
The client reads it (`take`) once the job passed. A file the command did not leave is simply not
there. Files go with the job's log (retention.py). Folders are made with `safepath.ensure_dir`,
files opened relative to the folder without following symlinks, removed with `remove_tree`.
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from mulebox.common.protocol import Message, MessageType
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.common.take_paths import CHUNK_BYTES, MAX_FILE_BYTES, MAX_FILES
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.context import Request
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.validate import check_job_id

_FLAGS = os.O_NOFOLLOW | os.O_CLOEXEC


def folder(staging: Staging) -> Path:
    return ensure_dir(staging.root / "taken", staging.roots)


def _name(job_id: str, index: int) -> str:
    if not 0 <= index < MAX_FILES:
        raise BadRequest(f"field 'index' must be 0 to {MAX_FILES - 1}")
    return f"{check_job_id(job_id)}.{index}"


def put(staging: Staging, job_id: str, index: int, offset: int, data: bytes) -> int:
    """Store `data` at `offset` of the file; return its size. A gap is a Conflict."""
    fd = os.open(folder(staging) / _name(job_id, index), os.O_WRONLY | os.O_CREAT | _FLAGS, 0o640)
    try:
        size = os.fstat(fd).st_size
        if offset > size:
            raise Conflict(f"offset {offset} is past the end of the file ({size})")
        if offset + len(data) > MAX_FILE_BYTES:
            raise BadRequest(f"a file taken back may hold at most {MAX_FILE_BYTES} bytes")
        fresh = data[size - offset:]
        if fresh:
            os.pwrite(fd, fresh, size)
        return os.fstat(fd).st_size
    finally:
        os.close(fd)


def read(staging: Staging, job_id: str, index: int, offset: int) -> tuple[bytes, int] | None:
    """(bytes from `offset`, the file's size), or None if the file never came."""
    try:
        fd = os.open(folder(staging) / _name(job_id, index), os.O_RDONLY | _FLAGS)
    except FileNotFoundError:
        return None
    try:
        return os.pread(fd, CHUNK_BYTES, offset), os.fstat(fd).st_size
    finally:
        os.close(fd)


def remove(staging: Staging, job_id: str) -> None:
    for index in range(MAX_FILES):
        remove_tree(folder(staging) / _name(job_id, index), staging.roots)


def job_ids(staging: Staging) -> set[str]:
    with os.scandir(folder(staging)) as entries:
        return {entry.name.rsplit(".", 1)[0] for entry in entries
                if entry.is_file(follow_symlinks=False) and "." in entry.name}


def _data(body: dict) -> bytes:
    data = body.get("data")
    if not isinstance(data, str):
        raise BadRequest("field 'data' must be a string")
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise BadRequest("field 'data' must be base64") from None


def taken(req: Request) -> Message:
    """Worker: a chunk of a file, while the job it ran in is not yet finished."""
    index = v.integer(req.body, "index", low=0)
    offset = v.integer(req.body, "offset", low=0)
    with req.store.read() as conn:
        job = st.require_job(conn, v.job_id(req.body))
    if job["attempt_id"] != req.body.get("attempt_id") or job["state"] not in st.ACTIVE_STATES:
        raise Conflict(f"job {job['job_id']} does not take files from this attempt now")
    if index >= len(job["take"]):
        raise BadRequest(f"job {job['job_id']} asked for {len(job['take'])} file(s)")
    size = put(req.staging, job["job_id"], index, offset, _data(req.body))
    return req.reply(MessageType.STATUS_OK, {"job_id": job["job_id"], "state": job["state"],
                                             "size": size})


def take(req: Request) -> Message:
    """Client: a chunk of a file its run brought back; `missing` when the command left none."""
    job_id = v.job_id(req.body)
    index = v.integer(req.body, "index", low=0)
    offset = v.integer(req.body, "offset", low=0)
    with req.store.read() as conn:
        st.require_job(conn, job_id)
    found = read(req.staging, job_id, index, offset)
    if found is None:
        return req.reply(MessageType.TAKE_OK, {"data": "", "size": 0, "eof": True,
                                               "missing": True})
    data, size = found
    return req.reply(MessageType.TAKE_OK, {"data": base64.b64encode(data).decode("ascii"),
                                           "size": size, "eof": offset + len(data) >= size})
