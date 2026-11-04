"""Files the coordinator keeps in its staging root: snapshot uploads and job logs.

Layout (docs/interfaces-m1.md): `<staging>/state/mulebox.db`, `<staging>/uploads/
<job_id>.tar.gz`, `<staging>/logs/<job_id>.log`. Folders are created with
`safepath.ensure_dir`, files are removed with `safepath.remove_tree`, and files are opened
relative to their folder's descriptor without following symlinks.

Logs arrive already redacted (the worker redacts); this module stores bytes as given. Old
logs are removed by retention.py, through `remove_log`.
"""

import hashlib
import os
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from mulebox.common.safepath import Roots, ensure_dir, remove_tree
from mulebox.coordinator.errors import BadRequest, Conflict, NotFound, TooLarge
from mulebox.coordinator.validate import check_job_id

UPLOAD_MAX_BYTES = 1 << 30
LOG_READ_MAX_BYTES = 128 * 1024  # JSON escaping can grow it ~6x; stays under 1 MiB lines
_CHUNK = 1 << 20
_FILE_MODE = 0o640
_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_UPLOAD_SUFFIX = ".tar.gz"
_PART_SUFFIX = ".part"


class Staging:
    """The staging root (`roots` must contain it, as `NodeConfig.roots["staging"]`)."""

    def __init__(self, roots: Roots, staging_root: Path) -> None:
        self.roots = roots
        self.root = Path(os.path.realpath(staging_root))
        self.state_dir = self.root / "state"
        self.uploads_dir = self.root / "uploads"
        self.logs_dir = self.root / "logs"
        for folder in (self.state_dir, self.uploads_dir, self.logs_dir):
            ensure_dir(folder, roots)

    @property
    def db_path(self) -> Path:
        return self.state_dir / "mulebox.db"

    def upload_path(self, job_id: str) -> Path:
        return self.uploads_dir / f"{check_job_id(job_id)}{_UPLOAD_SUFFIX}"

    def log_path(self, job_id: str) -> Path:
        return self.logs_dir / f"{check_job_id(job_id)}.log"

    # Uploads

    def write_upload(self, job_id: str, stream: BinaryIO, sha256: str,
                     max_bytes: int = UPLOAD_MAX_BYTES) -> int:
        """Stream `stream` into the job's upload file; return its size.

        Written to a fresh temp name (O_CREAT|O_EXCL), hashed while writing, capped at
        `max_bytes`, verified against `sha256`, then renamed into place atomically. On any
        failure the temp file is removed and nothing is left at the final name.
        """
        final = self.upload_path(job_id)
        if not isinstance(sha256, str) or not _SHA256_RE.fullmatch(sha256):
            raise BadRequest("sha256 must be 64 lowercase hex characters")
        temp_name = f".{job_id}.{secrets.token_hex(8)}{_PART_SUFFIX}"
        with self._folder(self.uploads_dir) as dir_fd:
            fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                         | os.O_CLOEXEC, _FILE_MODE, dir_fd=dir_fd)
            try:
                size, digest = _copy_hashed(stream, fd, max_bytes)
                os.fsync(fd)
                os.close(fd)
                fd = -1
                if digest != sha256:
                    raise BadRequest(f"sha256 mismatch: expected {sha256}, received {digest}")
                os.replace(temp_name, final.name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            except BaseException:
                if fd >= 0:
                    os.close(fd)
                remove_tree(self.uploads_dir / temp_name, self.roots)
                raise
        return size

    @contextmanager
    def open_upload(self, job_id: str) -> Iterator[BinaryIO]:
        name = self.upload_path(job_id).name
        with self._folder(self.uploads_dir) as dir_fd:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
            except FileNotFoundError:
                raise NotFound(f"no snapshot for job {job_id}") from None
        with os.fdopen(fd, "rb") as handle:
            yield handle

    def copy_upload(self, job_id: str, out: BinaryIO) -> int:
        """Write the job's snapshot to `out`; return the number of bytes."""
        total = 0
        with self.open_upload(job_id) as handle:
            while chunk := handle.read(_CHUNK):
                out.write(chunk)
                total += len(chunk)
        return total

    def remove_upload(self, job_id: str) -> None:
        remove_tree(self.upload_path(job_id), self.roots)

    def upload_entries(self) -> list[tuple[str, bool]]:
        """(job_id, is_temp) for every file in the uploads folder that looks like ours."""
        entries = []
        for name in sorted(os.listdir(self.uploads_dir)):
            if name.startswith(".") and name.endswith(_PART_SUFFIX):
                entries.append((name[1:].split(".", 1)[0], True))
            elif name.endswith(_UPLOAD_SUFFIX):
                entries.append((name[: -len(_UPLOAD_SUFFIX)], False))
        return entries

    def remove_upload_entry(self, job_id: str, is_temp: bool) -> None:
        """Remove a final upload, or every temp upload, of `job_id`."""
        check_job_id(job_id)
        if not is_temp:
            self.remove_upload(job_id)
            return
        prefix = f".{job_id}."
        for name in os.listdir(self.uploads_dir):
            if name.startswith(prefix) and name.endswith(_PART_SUFFIX):
                remove_tree(self.uploads_dir / name, self.roots)

    # Logs

    def append_log(self, job_id: str, offset: int, data: bytes) -> int:
        """Append `data`, which starts at byte `offset` of the log; return the new size.

        Idempotent: bytes below the current size are skipped as already stored (a resent
        chunk changes nothing). An offset past the end would leave a gap: Conflict.
        """
        if offset < 0:
            raise BadRequest("offset must not be negative")
        name = self.log_path(job_id).name
        with self._folder(self.logs_dir) as dir_fd:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
                         | os.O_CLOEXEC, _FILE_MODE, dir_fd=dir_fd)
        try:
            size = os.fstat(fd).st_size
            if offset > size:
                raise Conflict(f"log offset {offset} is past the end of the log ({size})")
            fresh = data[size - offset:]
            while fresh:
                written = os.write(fd, fresh)
                fresh = fresh[written:]
            return os.fstat(fd).st_size
        finally:
            os.close(fd)

    def read_log(self, job_id: str, offset: int, max_bytes: int = LOG_READ_MAX_BYTES) -> bytes:
        """Up to `max_bytes` from `offset`, cut back to a whole UTF-8 character."""
        if offset < 0:
            raise BadRequest("offset must not be negative")
        name = self.log_path(job_id).name
        with self._folder(self.logs_dir) as dir_fd:
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
            except FileNotFoundError:
                return b""
        try:
            data = os.pread(fd, max_bytes, offset)
        finally:
            os.close(fd)
        return _whole_utf8(data)

    def log_job_ids(self) -> list[str]:
        """Job ids with a log: regular files directly in the logs folder, named for a valid id."""
        found = []
        with os.scandir(self.logs_dir) as entries:
            for entry in entries:
                name = entry.name.removesuffix(".log")
                if name != entry.name and entry.is_file(follow_symlinks=False) and _is_id(name):
                    found.append(name)
        return sorted(found)

    def remove_log(self, job_id: str) -> None:
        remove_tree(self.log_path(job_id), self.roots)

    def log_size(self, job_id: str) -> int:
        try:
            return os.stat(self.log_path(job_id), follow_symlinks=False).st_size
        except FileNotFoundError:
            return 0

    @contextmanager
    def _folder(self, folder: Path) -> Iterator[int]:
        ensure_dir(folder, self.roots)
        fd = os.open(folder, _DIR_FLAGS)
        try:
            yield fd
        finally:
            os.close(fd)


def _is_id(name: str) -> bool:
    try:
        check_job_id(name)
    except BadRequest:
        return False
    return True


def _copy_hashed(stream: BinaryIO, fd: int, max_bytes: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    total = 0
    while chunk := stream.read(_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise TooLarge(f"upload exceeds the limit of {max_bytes} bytes")
        digest.update(chunk)
        view = memoryview(chunk)
        while view:
            view = view[os.write(fd, view):]
    return total, digest.hexdigest()


def _whole_utf8(data: bytes) -> bytes:
    """Drop a trailing incomplete UTF-8 sequence (at most 3 bytes)."""
    for back in range(1, min(4, len(data)) + 1):
        byte = data[-back]
        if byte & 0xC0 != 0x80:  # ASCII or a lead byte
            return data if _seq_len(byte) <= back else data[:-back]
    return data


def _seq_len(lead: int) -> int:
    if lead >= 0xF0:
        return 4
    if lead >= 0xE0:
        return 3
    if lead >= 0xC0:
        return 2
    return 1
