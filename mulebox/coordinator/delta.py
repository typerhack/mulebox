"""Uploads of only what changed, over a slow link (docs/design.md, Job lifecycle).

The coordinator keeps a project's last snapshot (`Staging.keep_base`). `plan` compares it with
the client's file list and answers which files to send; `accept` rebuilds the whole snapshot
from that base and the files sent, checks the result against the client's list, and hands it to
`uploads.accept_upload`, so the rest of the job sees an ordinary upload. Any trouble ends in an
error, and the client then sends everything.
"""

import hashlib
import json
import tarfile
from typing import Any, BinaryIO

from mulebox.common import manifest
from mulebox.coordinator import uploads
from mulebox.coordinator.errors import BadRequest, Conflict
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store
from mulebox.coordinator.validate import check_job_id

MAX_LIST_BYTES = 16 << 20
MAX_NAMED = 2000  # more than this, and the reply outgrows what a full upload would save
_COMPRESS_LEVEL = 1  # on the node, for a file that crosses no slow link


def _job(store: Store, job_id: str) -> dict[str, Any]:
    check_job_id(job_id)
    job = store.get_job(job_id)
    uploads.require_uploading(job, job_id)
    return job


def plan(store: Store, staging: Staging, job_id: str, stream: BinaryIO) -> dict[str, Any]:
    """`need` and `gone` paths, or `need: None` for a full upload."""
    job = _job(store, job_id)
    data = stream.read(MAX_LIST_BYTES + 1)
    if len(data) > MAX_LIST_BYTES:
        raise BadRequest("file list too large")
    try:
        wanted = manifest.decode(data)
        base = staging.open_base(job["project"])
        if base is None:
            return {"need": None}
        with base:
            have = manifest.read(base)
    except (manifest.ManifestError, tarfile.TarError, EOFError):
        return {"need": None}
    need = sorted(path for path, digest in wanted.items() if have.get(path) != digest)
    gone = sorted(have.keys() - wanted.keys())
    if len(need) + len(gone) > MAX_NAMED:
        return {"need": None}
    return {"need": need, "gone": gone}


def _take_delta(delta: BinaryIO, out: tarfile.TarFile) -> tuple[set[str], set[str]]:
    """Copy the files sent into `out`; return (their names, the names to leave out)."""
    sent, gone = set(), set()
    with tarfile.open(fileobj=delta, mode="r|gz") as tar:
        for member in tar:
            if member.name == manifest.GONE_MEMBER:
                gone = set(json.load(tar.extractfile(member)))
                continue
            sent.add(member.name)
            out.addfile(member, tar.extractfile(member) if member.isfile() else None)
    return sent, gone


def _take_base(base: BinaryIO, out: tarfile.TarFile, skip: set[str]) -> None:
    with tarfile.open(fileobj=base, mode="r|gz") as tar:
        for member in tar:
            if member.name not in skip:
                out.addfile(member, tar.extractfile(member) if member.isfile() else None)


def _rebuild(staging: Staging, project: str, delta: BinaryIO) -> BinaryIO:
    base = staging.open_base(project)
    if base is None:
        raise Conflict("the last snapshot is gone")
    whole = staging.scratch()
    try:
        with base, tarfile.open(fileobj=whole, mode="w:gz", format=tarfile.PAX_FORMAT,
                                compresslevel=_COMPRESS_LEVEL) as out:
            sent, gone = _take_delta(delta, out)
            _take_base(base, out, sent | gone)
    except (OSError, EOFError, ValueError, tarfile.TarError) as exc:
        whole.close()
        raise Conflict(f"cannot rebuild the snapshot: {exc}") from None
    return whole


def _checked(whole: BinaryIO, wanted_digest: str) -> str:
    """The sha256 of `whole`, once it holds exactly what the client listed."""
    whole.seek(0)
    if manifest.digest(manifest.read(whole)) != wanted_digest:
        raise Conflict("the rebuilt snapshot differs from the client's")
    whole.seek(0)
    sha256 = hashlib.file_digest(whole, "sha256").hexdigest()
    whole.seek(0)
    return sha256


def accept(store: Store, staging: Staging, job_id: str, sha256: str, wanted_digest: str,
           stream: BinaryIO, now: float) -> tuple[dict[str, Any], int | None]:
    """Rebuild the snapshot from the base and the files in `stream`, and queue the job."""
    job = _job(store, job_id)
    with staging.receive(stream, sha256) as delta, _rebuild(
            staging, job["project"], delta) as whole:
        return uploads.accept_upload(store, staging, job_id, _checked(whole, wanted_digest),
                                     whole, now)
