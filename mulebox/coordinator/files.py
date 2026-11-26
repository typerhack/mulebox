"""Files a job keeps for `mulebox fetch` (docs/design.md, Files back): kept, then handed out.

The worker packs what a job's `keep:` named into one tar.gz and sends it once with
`rpc-upload-files <job> <sha256>`, before the result, while the job is still active; it lands at
`<staging>/files/<job_id>.tar.gz` through Staging.write_verified (checked, then renamed). The
result says what went in (`files`: count, bytes, what was left out), kept on the job's row.
`rpc-download-files <job>` hands the pack to a dev machine. Packs go `files_days` after their
job finished, in the same sweep as logs (retention.py).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, BinaryIO

from mulebox.common import keep_files
from mulebox.common.protocol import JobState
from mulebox.common.safepath import ensure_dir, remove_tree
from mulebox.coordinator import store as st
from mulebox.coordinator import validate as v
from mulebox.coordinator.errors import BadRequest, Conflict, NotFound
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import ACTIVE_STATES, Store
from mulebox.coordinator.validate import check_job_id

FOLDER = "files"
SUFFIX = ".tar.gz"
MAX_BYTES = 1 << 30  # a pack, compressed; the worker's keep_files_max is on the files' own size
_ACTIVE = {state.value for state in ACTIVE_STATES}


def asked(body: dict[str, Any]) -> list[str]:
    """The submit's `keep` entries, checked as the client and worker check them."""
    try:
        return list(keep_files.checked(v.strings(body, "keep")))
    except ValueError as exc:
        raise BadRequest(str(exc)) from None


def folder(staging: Staging) -> Path:
    return ensure_dir(staging.root / FOLDER, staging.roots)


def _name(job_id: str) -> str:
    return f"{check_job_id(job_id)}{SUFFIX}"


def receive(store: Store, staging: Staging, job_id: str, sha256: str,
            stream: BinaryIO) -> dict[str, Any]:
    """Take a job's pack from its worker; only while the job runs and asked to keep files."""
    job = store.get_job(job_id)
    if job is None:
        raise NotFound(f"no job {job_id}")
    if job["state"] not in _ACTIVE:
        raise Conflict(f"job {job_id} is {job['state']}; its files come before its result")
    if not job.get("keep_files"):
        raise Conflict(f"job {job_id} keeps no files")
    size = staging.write_verified(folder(staging), _name(job_id), stream, sha256, MAX_BYTES)
    return {"job_id": job_id, "state": job["state"], "bytes": size}


def kept(body: dict[str, Any]) -> dict[str, Any] | None:
    """A result's `files`, in the shape the job's row keeps; None when there is none."""
    said = body.get("files")
    if not isinstance(said, dict):
        return None
    left = [str(name)[:400] for name in said.get("left_out") or [] if isinstance(name, str)]
    return {"count": _count(said, "count"), "bytes": _count(said, "bytes"),
            "left_out": left[:keep_files.MAX_LISTED],
            "left_out_count": max(_count(said, "left_out_count"), len(left)),
            "packed": said.get("packed") is True}


def _count(said: dict[str, Any], name: str) -> int:
    value = said.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def record(conn: sqlite3.Connection, job: dict[str, Any], body: dict[str, Any]) -> None:
    """What the job kept, from its result, on its row."""
    if job.get("keep_files") and (said := kept(body)) is not None:
        st.update_job(conn, job["job_id"], files=said)


def send(store: Store, staging: Staging, job_id: str, out: BinaryIO) -> int:
    """Write a finished job's pack to `out`; the number of bytes."""
    job = store.get_job(job_id)
    if job is None:
        raise NotFound(f"no job {job_id}")
    if job["state"] != JobState.FINISHED:
        raise Conflict(f"job {job_id} is still {job['state']}; fetch its files once it ended")
    missing = (f"job {job_id} has no kept files: it named none, kept none, or they went after "
               "the coordinator's files_days")
    total = 0
    if not job.get("keep_files"):
        raise NotFound(missing, error_code="job.no_files")
    try:
        with staging.open_in(folder(staging), _name(job_id), missing) as handle:
            while chunk := handle.read(1 << 20):
                out.write(chunk)
                total += len(chunk)
    except NotFound:  # only opening raises it
        raise NotFound(missing, error_code="job.no_files") from None
    return total


def job_ids(staging: Staging) -> list[str]:
    """The jobs that have a pack here."""
    found = []
    for name in os.listdir(folder(staging)):
        job_id = name[: -len(SUFFIX)] if name.endswith(SUFFIX) else ""
        try:
            found.append(check_job_id(job_id))
        except BadRequest:
            continue
    return sorted(found)


def remove(staging: Staging, job_id: str) -> None:
    remove_tree(folder(staging) / _name(job_id), staging.roots)


def status_fields(job: dict[str, Any]) -> dict[str, Any]:
    """`keep` and `files` for status and results, once a job keeps files."""
    if not job.get("keep_files"):
        return {}
    return {"keep": list(job["keep_files"]), **({"files": job["files"]} if job.get("files") else {})}
