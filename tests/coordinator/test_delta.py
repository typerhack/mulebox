"""Uploads of only what changed: the rebuilt snapshot must be the client's, or nothing."""

import hashlib
import io
import json
import tarfile

import pytest

from mulebox.common import manifest
from mulebox.coordinator import delta, uploads
from mulebox.coordinator.errors import Conflict

from .helpers import submit

FILES = {"README.md": b"hello\n", "src/a.py": b"a = 1\n", "src/b.py": b"b = 2\n"}


def archive(files: dict[str, bytes], gone: list[str] | None = None, link: bool = False) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
        if gone is not None:
            listing = json.dumps(gone).encode()
            info = tarfile.TarInfo(manifest.GONE_MEMBER)
            info.size = len(listing)
            tar.addfile(info, io.BytesIO(listing))
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        if link:
            info = tarfile.TarInfo("current")
            info.type, info.linkname = tarfile.SYMTYPE, "README.md"
            tar.addfile(info)
    return raw.getvalue()


def listed(data: bytes) -> dict[str, str]:
    return manifest.read(io.BytesIO(data))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def based(store, staging):
    """A project whose last snapshot is `FILES`, with one link."""
    data = archive(FILES, link=True)
    job_id = submit(store, staging)
    uploads.accept_upload(store, staging, job_id, sha(data), io.BytesIO(data), 1000.0)
    return data


def asked(store, staging, job_id, wanted):
    return delta.plan(store, staging, job_id, io.BytesIO(manifest.encode(wanted)))


def contents(staging, job_id) -> dict[str, bytes | str]:
    found = {}
    with staging.open_upload(job_id) as raw, tarfile.open(fileobj=raw, mode="r|gz") as tar:
        for member in tar:
            found[member.name] = (member.linkname if member.issym()
                                  else tar.extractfile(member).read())
    return found


def test_a_first_upload_is_whole(store, staging):
    assert asked(store, staging, submit(store, staging), listed(archive(FILES))) == {"need": None}


def test_only_changes_are_asked_for(store, staging, based):
    changed = {**FILES, "src/a.py": b"a = 9\n", "new.txt": b"new\n"}
    del changed["src/b.py"]
    wanted = listed(archive(changed, link=True))
    plan = asked(store, staging, submit(store, staging), wanted)
    assert plan == {"need": ["new.txt", "src/a.py"], "gone": ["src/b.py"]}


def test_a_mode_change_counts(store, staging, based):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as tar:
        info = tarfile.TarInfo("README.md")
        info.size, info.mode = len(FILES["README.md"]), 0o755
        tar.addfile(info, io.BytesIO(FILES["README.md"]))
    plan = asked(store, staging, submit(store, staging), listed(raw.getvalue()))
    assert plan["need"] == ["README.md"]


def test_the_snapshot_is_rebuilt_and_queued(store, staging, based):
    changed = {**FILES, "src/a.py": b"a = 9\n", "new.txt": b"new\n"}
    del changed["src/b.py"]
    wanted = listed(archive(changed, link=True))
    job_id = submit(store, staging)
    data = archive({"src/a.py": b"a = 9\n", "new.txt": b"new\n"}, gone=["src/b.py"])
    job, _ = delta.accept(store, staging, job_id, sha(data), manifest.digest(wanted),
                          io.BytesIO(data), 1001.0)
    assert job["state"] == "queued"
    assert contents(staging, job_id) == {**changed, "current": "README.md"}


def test_a_snapshot_that_does_not_add_up_is_refused(store, staging, based):
    wanted = listed(archive({**FILES, "src/a.py": b"a = 9\n"}, link=True))
    job_id = submit(store, staging)
    data = archive({"src/a.py": b"something else\n"}, gone=[])
    with pytest.raises(Conflict):
        delta.accept(store, staging, job_id, sha(data), manifest.digest(wanted),
                     io.BytesIO(data), 1001.0)
    assert store.get_job(job_id)["state"] == "uploading"
    with pytest.raises(Exception, match="no snapshot"):
        contents(staging, job_id)


def test_a_broken_delta_is_refused_not_a_crash(store, staging, based):
    job_id = submit(store, staging)
    with pytest.raises(Conflict):
        delta.accept(store, staging, job_id, sha(b"junk"), "0" * 64, io.BytesIO(b"junk"), 1001.0)


def test_a_new_upload_replaces_the_base_and_it_outlives_the_job(store, staging, based):
    changed = {"only.txt": b"x\n"}
    data = archive(changed)
    job_id = submit(store, staging)
    uploads.accept_upload(store, staging, job_id, sha(data), io.BytesIO(data), 1001.0)
    staging.remove_upload(job_id)
    with staging.open_base("example-app") as base:
        assert manifest.read(base) == listed(data)
