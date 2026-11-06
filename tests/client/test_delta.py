"""The client side of a delta upload: what it sends, and that trouble means a whole upload."""

import io
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest

from mulebox.client import delta
from mulebox.client.snapshot import Snapshot
from mulebox.common import manifest
from mulebox.common.protocol import Message, MessageType
from mulebox.common.ssh import SSHUnavailable


def member(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


@pytest.fixture
def snap(tmp_path) -> Snapshot:
    path = tmp_path / "snapshot.tar.gz"
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        member(tar, "a.txt", b"a\n")
        member(tar, "big.bin", bytes(range(256)) * 40000)
    return Snapshot(path, "0" * 64, "f", "c", "main", 2, 11 * delta.MIN_BYTES)


class Fake:
    def __init__(self, plan):
        self.plan = plan
        self.listing = None
        self.sent = None

    def upload_plan(self, job_id, path: Path):
        if isinstance(self.plan, Exception):
            raise self.plan
        self.listing = manifest.decode(path.read_bytes())
        return Message(MessageType.UPLOAD_PLAN_OK, "r", self.plan)

    def upload_delta(self, job_id, path: Path, sha256, digest):
        with tarfile.open(path, "r:gz") as tar:
            self.sent = tar.getnames()
        return Message(MessageType.STATUS_OK, "r", {"job_id": job_id, "state": "queued"})


def test_only_what_is_needed_goes(snap):
    remote = Fake({"need": ["a.txt"], "gone": ["old.txt"]})
    notes = []
    assert delta.send(remote, "job", snap, notes.append) is True
    assert sorted(remote.listing) == ["a.txt", "big.bin"]
    assert remote.sent == [manifest.GONE_MEMBER, "a.txt"]
    assert "sending 1 of 2 files" in notes[0]


def test_no_base_means_a_whole_upload(snap):
    assert delta.send(Fake({"need": None}), "job", snap, [].append) is False


def test_a_small_snapshot_goes_whole_with_no_call(snap):
    small = replace(snap, size=delta.MIN_BYTES - 1)
    remote = Fake(RuntimeError("must not be called"))
    assert delta.send(remote, "job", small, [].append) is False


def test_a_delta_near_the_full_size_goes_whole(snap):
    tiny = replace(snap, size=delta.MIN_BYTES)  # the file list says all of it changed
    remote = Fake({"need": ["a.txt", "big.bin"], "gone": []})
    path = snap.path
    assert path.stat().st_size < delta.MIN_BYTES
    assert delta.send(remote, "job", replace(tiny, size=path.stat().st_size), [].append) is False
    assert remote.sent is None


def test_trouble_means_a_whole_upload(snap):
    notes = []
    assert delta.send(Fake(SSHUnavailable("no route")), "job", snap, notes.append) is False
    assert "whole snapshot" in notes[0]
