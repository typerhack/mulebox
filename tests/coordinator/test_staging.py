import io
import os

import pytest

from mulebox.coordinator.errors import BadRequest, Conflict, NotFound, TooLarge
from mulebox.coordinator.staging import Staging

from .helpers import snapshot

JOB = "job-01JC3X0000000000000000000Z"


def test_layout(staging, root_map):
    base = os.path.realpath(root_map["staging"])
    assert str(staging.db_path) == f"{base}/state/mulebox.db"
    assert str(staging.upload_path(JOB)) == f"{base}/uploads/{JOB}.tar.gz"
    assert str(staging.log_path(JOB)) == f"{base}/logs/{JOB}.log"


def test_bad_job_id_never_reaches_a_path(staging):
    for bad in ("../x", "job-..", "job-01JC3X0000000000000000000Z/../a", ""):
        with pytest.raises(BadRequest):
            staging.upload_path(bad)


def test_upload_roundtrip(staging):
    data, digest = snapshot(b"x" * 3_000_000)
    assert staging.write_upload(JOB, io.BytesIO(data), digest) == len(data)
    out = io.BytesIO()
    assert staging.copy_upload(JOB, out) == len(data)
    assert out.getvalue() == data
    assert os.listdir(staging.uploads_dir) == [f"{JOB}.tar.gz"]


def test_upload_hash_mismatch_leaves_nothing(staging):
    _, digest = snapshot(b"other")
    with pytest.raises(BadRequest, match="mismatch"):
        staging.write_upload(JOB, io.BytesIO(b"data"), digest)
    assert os.listdir(staging.uploads_dir) == []


def test_upload_bad_sha_format(staging):
    with pytest.raises(BadRequest):
        staging.write_upload(JOB, io.BytesIO(b"data"), "ABC")


def test_upload_size_cap(staging):
    data, digest = snapshot(b"y" * 2048)
    with pytest.raises(TooLarge):
        staging.write_upload(JOB, io.BytesIO(data), digest, max_bytes=1024)
    assert os.listdir(staging.uploads_dir) == []


def test_upload_does_not_follow_symlink_at_final_name(staging, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    os.symlink(outside, staging.upload_path(JOB))
    data, digest = snapshot()
    staging.write_upload(JOB, io.BytesIO(data), digest)  # replaces the link itself
    assert outside.read_text() == "keep"
    assert not os.path.islink(staging.upload_path(JOB))


def test_remove_upload_and_missing(staging):
    data, digest = snapshot()
    staging.write_upload(JOB, io.BytesIO(data), digest)
    staging.remove_upload(JOB)
    staging.remove_upload(JOB)  # no-op
    with pytest.raises(NotFound):
        staging.copy_upload(JOB, io.BytesIO())


def test_upload_entries_and_temp_removal(staging):
    (staging.uploads_dir / f".{JOB}.abcd.part").write_bytes(b"partial")
    (staging.uploads_dir / f"{JOB}.tar.gz").write_bytes(b"done")
    (staging.uploads_dir / "notes.txt").write_text("ignored")
    assert sorted(staging.upload_entries()) == [(JOB, False), (JOB, True)]
    staging.remove_upload_entry(JOB, True)
    assert sorted(os.listdir(staging.uploads_dir)) == [f"{JOB}.tar.gz", "notes.txt"]


def test_append_log_is_offset_idempotent(staging):
    assert staging.append_log(JOB, 0, b"hello ") == 6
    assert staging.append_log(JOB, 0, b"hello ") == 6  # resent chunk
    assert staging.append_log(JOB, 3, b"lo world") == 11  # partial overlap
    assert staging.read_log(JOB, 0) == b"hello world"
    with pytest.raises(Conflict):
        staging.append_log(JOB, 20, b"gap")
    with pytest.raises(BadRequest):
        staging.append_log(JOB, -1, b"x")


def test_append_log_stores_bytes_unredacted(staging):
    staging.append_log(JOB, 0, b"token=ghp_abcdefghijklmnopqrstuvwxyz0123456789\n")
    assert b"ghp_" in staging.read_log(JOB, 0)


def test_read_log_offsets_and_utf8_boundary(staging):
    staging.append_log(JOB, 0, "abé€".encode())  # 2 + 2 + 3 bytes
    assert staging.read_log(JOB, 2) == "é€".encode()
    assert staging.read_log(JOB, 0, max_bytes=5) == b"ab\xc3\xa9"
    assert staging.read_log(JOB, 0, max_bytes=3) == b"ab"
    assert staging.read_log(JOB, 100) == b""
    assert staging.read_log("job-01JC3X0000000000000000001Z", 0) == b""
    assert staging.log_size(JOB) == 7


def test_staging_outside_roots_refused(root_map, tmp_path):
    from mulebox.common.safepath import PathOutsideRoots, Roots

    other = tmp_path / "elsewhere"
    other.mkdir()
    with pytest.raises(PathOutsideRoots):
        Staging(Roots.from_config(root_map), other)
