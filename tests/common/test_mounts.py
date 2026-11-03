"""mounts: mountinfo and fdinfo parsing (sample text, so it runs on macOS too)."""

import os
import sys
from pathlib import Path

import pytest

from mulebox.common import mounts

SAMPLE = (
    "22 1 8:1 / / rw,relatime shared:1 - ext4 /dev/sda1 rw\n"
    "25 22 0:5 / /dev rw,nosuid shared:2 - devtmpfs udev rw\n"
    "40 22 8:1 /srv/data /srv/mulebox/jobs/job-1/with\\040space rw - ext4 /dev/sda1 rw\n"
    "41 22 8:1 /x /srv/a\\011tab\\012nl\\134back rw shared:9 master:3 - ext4 /dev/sda1 rw\n"
    "\n"
)


def test_parse_mountinfo_sample():
    assert mounts.parse_mountinfo(SAMPLE) == [
        Path("/"),
        Path("/dev"),
        Path("/srv/mulebox/jobs/job-1/with space"),
        Path("/srv/a\ttab\nnl\\back"),
    ]
    assert mounts.parse_mountinfo(SAMPLE.encode()) == mounts.parse_mountinfo(SAMPLE)


def test_unescape_leaves_other_backslashes():
    assert mounts.unescape(b"/a\\040b") == "/a b"
    assert mounts.unescape(b"/a\\9xx") == "/a\\9xx"
    assert mounts.unescape(b"/a\\400") == "/a\\400"


@pytest.mark.parametrize("line", ["garbage", "1 2 3:4 / relative rw - ext4 x rw"])
def test_parse_mountinfo_malformed(line):
    with pytest.raises(ValueError):
        mounts.parse_mountinfo(line)


def test_parse_fdinfo():
    assert mounts.parse_fdinfo_mnt_id(b"pos:\t0\nflags:\t02100000\nmnt_id:\t31\n") == 31
    assert mounts.parse_fdinfo_mnt_id(b"pos:\t0\n") is None


def test_is_within_uses_components():
    assert mounts.is_within(Path("/srv/jobs/a"), Path("/srv/jobs"))
    assert mounts.is_within(Path("/srv/jobs"), Path("/srv/jobs"))
    assert not mounts.is_within(Path("/srv/jobs2"), Path("/srv/jobs"))
    assert not mounts.is_within(Path("/srv"), Path("/srv/jobs"))


def test_blocking_mounts():
    root, target = Path("/r"), Path("/r/a/job")
    points = [Path("/"), Path("/r"), Path("/r/a"), Path("/r/a/job/x"), Path("/r/a/jobx"),
              Path("/r/b"), Path("/r/a/job")]
    assert mounts.blocking_mounts(target, root, points) == [
        Path("/r/a"), Path("/r/a/job/x"), Path("/r/a/job"),
    ]
    assert mounts.blocking_mounts(target, root, [Path("/"), Path("/r")]) == []


def test_same_mount():
    assert mounts.same_mount((1, None), (1, None))
    assert mounts.same_mount((1, 5), (1, 5))
    assert not mounts.same_mount((1, 5), (1, 6))
    assert not mounts.same_mount((1, 5), (1, None))
    assert not mounts.same_mount((1, None), (2, None))


def test_non_linux_has_no_mount_table(monkeypatch):
    monkeypatch.setattr(mounts.sys, "platform", "darwin")
    assert mounts.linux_mount_points() is None
    assert mounts.fd_mount_id(0) is None


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_real_linux_mount_table():
    assert Path("/") in mounts.linux_mount_points()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert isinstance(mounts.fd_mount_id(fd), int)
    finally:
        os.close(fd)
