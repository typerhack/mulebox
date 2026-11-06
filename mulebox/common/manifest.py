"""What a snapshot holds, file by file, so two snapshots can be compared cheaply.

A manifest maps each path in a snapshot archive to a short hash of its permission bits and
content (or link target). The client and the coordinator read archives with this one function,
so they agree on what "the same file" means. `GONE_MEMBER` carries the removed paths in a delta
upload: a snapshot never holds it, as `.mulebox/` is always excluded (client/excludes.py).
"""

import gzip
import hashlib
import json
import tarfile
from typing import BinaryIO

GONE_MEMBER = ".mulebox/gone.json"
DIGEST_CHARS = 24  # 96 bits: a mistake here only costs a full upload, the snapshot is verified
_CHUNK = 1 << 20


class ManifestError(ValueError):
    """An archive holds something a snapshot never does, or a file list is broken."""


def read(archive: BinaryIO) -> dict[str, str]:
    """The manifest of a tar.gz, read from its current position to its end."""
    manifest = {}
    with tarfile.open(fileobj=archive, mode="r|gz") as tar:
        for member in tar:
            manifest[member.name] = _hash(tar, member)
    return manifest


def _hash(tar: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    digest = hashlib.sha256(f"{member.mode:o}\0".encode())
    if member.issym():
        digest.update(b"link\0" + member.linkname.encode("utf-8", "surrogateescape"))
    elif member.isfile():
        content = tar.extractfile(member)
        while chunk := content.read(_CHUNK):
            digest.update(chunk)
    else:
        raise ManifestError(f"{member.name}: neither a file nor a link")
    return digest.hexdigest()[:DIGEST_CHARS]


def digest(manifest: dict[str, str]) -> str:
    """One hash for a whole manifest."""
    return hashlib.sha256(json.dumps(sorted(manifest.items())).encode()).hexdigest()


def encode(manifest: dict[str, str]) -> bytes:
    return gzip.compress(json.dumps(manifest, separators=(",", ":")).encode(), mtime=0)


def decode(data: bytes) -> dict[str, str]:
    try:
        manifest = json.loads(gzip.decompress(data))
    except (OSError, EOFError, ValueError) as exc:
        raise ManifestError(f"unreadable file list: {exc}") from None
    if not isinstance(manifest, dict) or not all(
            isinstance(value, str) for value in manifest.values()):
        raise ManifestError("unreadable file list")
    return manifest
