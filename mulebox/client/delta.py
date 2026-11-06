"""Send only what changed since the project's last upload (coordinator/delta.py).

The link to a build machine can be far slower than the machine, so a snapshot of some size costs
more in upload than the job's own start. Small snapshots go whole: the file list would cost as
much. `send` returning False means nothing was sent and the whole snapshot must go; so does any
failure here, as a job must not fail over a saving.
"""

import json
import os
import tarfile
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from mulebox.client.report import format_size
from mulebox.client.snapshot import Snapshot, sha256_file
from mulebox.common import manifest
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import Message

MIN_BYTES = 1 << 20
_WORTH_IT = 0.5  # of the snapshot's size


class DeltaRemote(Protocol):
    def upload_plan(self, job_id: str, path: Path) -> Message: ...
    def upload_delta(self, job_id: str, path: Path, sha256: str, digest: str) -> Message: ...


@contextmanager
def _temporary(suffix: str) -> Iterator[tuple[Path, BinaryIO]]:
    fd, name = tempfile.mkstemp(prefix="mulebox-delta-", suffix=suffix)
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as file:
            yield path, file
    finally:
        path.unlink(missing_ok=True)


def _write_delta(snapshot: Path, need: set[str], gone: list[str], out: BinaryIO) -> None:
    with snapshot.open("rb") as raw, tarfile.open(fileobj=raw, mode="r|gz") as whole, \
            tarfile.open(fileobj=out, mode="w:gz", format=tarfile.PAX_FORMAT) as delta:
        listing = json.dumps(gone).encode()
        info = tarfile.TarInfo(manifest.GONE_MEMBER)
        info.size = len(listing)
        delta.addfile(info, BytesIO(listing))
        for member in whole:
            if member.name in need:
                delta.addfile(member, whole.extractfile(member) if member.isfile() else None)


def _plan(remote: DeltaRemote, job_id: str, wanted: dict[str, str]) -> dict[str, Any]:
    with _temporary(".list") as (path, file):
        file.write(manifest.encode(wanted))
        file.close()
        return remote.upload_plan(job_id, path).body


def _send(remote: DeltaRemote, job_id: str, snap: Snapshot, status: Callable[[str], None]) -> bool:
    with snap.path.open("rb") as raw:
        wanted = manifest.read(raw)
    plan = _plan(remote, job_id, wanted)
    need = plan.get("need")
    if need is None:
        return False
    with _temporary(".tar.gz") as (path, file):
        _write_delta(snap.path, set(need), plan.get("gone", []), file)
        file.close()
        size = path.stat().st_size
        if size > snap.size * _WORTH_IT:
            return False
        status(f"sending {len(need)} of {snap.files} files, {format_size(size)}")
        remote.upload_delta(job_id, path, sha256_file(path), manifest.digest(wanted))
    return True


def send(remote: DeltaRemote, job_id: str, snap: Snapshot,
         status: Callable[[str], None]) -> bool:
    """True when the coordinator now has the snapshot and queued the job."""
    if snap.size < MIN_BYTES:
        return False
    try:
        return _send(remote, job_id, snap, status)
    except (MuleboxError, OSError, ValueError, EOFError, tarfile.TarError) as exc:
        status(f"sending the whole snapshot: {str(exc).splitlines()[0] if str(exc) else exc!r}")
        return False
