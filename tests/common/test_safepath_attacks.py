"""safepath under attack: swap races and mount points (simulated, nothing is mounted).

Each test proves that the files outside the root survive. Everything stays in tmp_path.
Fixtures (root, roots, outside): conftest.py.
"""

import os
from pathlib import Path

import pytest

from mulebox.common import mounts, safepath
from mulebox.common.safepath import UnsafePath, ensure_dir, remove_tree


def assert_outside_intact(outside: Path) -> None:
    assert (outside / "keep.txt").read_text() == "keep"
    assert (outside / "sub" / "keep.txt").read_text() == "keep"


def swap_for_symlink(path: Path, target: Path) -> None:
    """What an attacker does: move a directory away and put a symlink in its place."""
    path.rename(path.with_name(path.name + "-moved"))
    path.symlink_to(target)


@pytest.fixture
def no_mounts(monkeypatch):
    """Pretend the mount table is empty (Linux path), so only the race is exercised."""
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: [])


# Races


def test_parent_swapped_after_validation(monkeypatch, root, roots, outside, no_mounts):
    (root / "a").mkdir()
    (root / "a" / "keep.txt").write_text("job file")
    real_check = safepath._refuse_mounts

    def check_then_swap(target, root_path):
        real_check(target, root_path)
        swap_for_symlink(root / "a", outside)  # validation passed; now the parent is a link

    monkeypatch.setattr(safepath, "_refuse_mounts", check_then_swap)
    with pytest.raises(UnsafePath, match="symlink"):
        remove_tree(root / "a" / "keep.txt", roots)
    assert_outside_intact(outside)


def test_deeper_parent_swapped_after_validation(monkeypatch, root, roots, outside, no_mounts):
    (root / "a" / "b" / "c").mkdir(parents=True)
    real_check = safepath._refuse_mounts

    def check_then_swap(target, root_path):
        real_check(target, root_path)
        swap_for_symlink(root / "a" / "b", outside)

    monkeypatch.setattr(safepath, "_refuse_mounts", check_then_swap)
    with pytest.raises(UnsafePath, match="symlink"):
        remove_tree(root / "a" / "b" / "sub", roots)
    assert_outside_intact(outside)


def test_target_swapped_for_symlink_after_validation(monkeypatch, root, roots, outside,
                                                     no_mounts):
    (root / "job" / "f").mkdir(parents=True)
    real_check = safepath._refuse_mounts

    def check_then_swap(target, root_path):
        real_check(target, root_path)
        swap_for_symlink(root / "job", outside)

    monkeypatch.setattr(safepath, "_refuse_mounts", check_then_swap)
    remove_tree(root / "job", roots)  # the link itself is removed, never followed
    assert not os.path.lexists(root / "job")
    assert_outside_intact(outside)


def test_subdirectory_swapped_during_walk(monkeypatch, root, roots, outside, no_mounts):
    (root / "job" / "sub").mkdir(parents=True)
    (root / "job" / "sub" / "f").write_text("x")
    (root / "job" / "z.txt").write_text("x")
    real_list = safepath._list_entries

    def list_then_swap(fd, where):
        entries = real_list(fd, where)
        if where == root / "job":
            swap_for_symlink(root / "job" / "sub", outside / "sub")
        return entries

    monkeypatch.setattr(safepath, "_list_entries", list_then_swap)
    with pytest.raises(UnsafePath, match="symlink"):
        remove_tree(root / "job", roots)
    assert_outside_intact(outside)


def test_all_descriptors_closed(root, roots, outside, monkeypatch, no_mounts):
    fd_dir = "/dev/fd" if os.path.isdir("/dev/fd") else "/proc/self/fd"
    before = len(os.listdir(fd_dir))
    for i in range(5):
        (root / "job" / f"d{i}" / "x").mkdir(parents=True)
    (root / "bad" / "sub").mkdir(parents=True)
    swap_for_symlink(root / "bad" / "sub", outside)
    remove_tree(root / "job", roots)
    ensure_dir(root / "made" / "deep", roots)
    with pytest.raises(UnsafePath):
        ensure_dir(root / "bad" / "sub" / "x", roots)
    monkeypatch.setattr(mounts, "fd_identity", lambda fd: (fd, None))  # all differ
    with pytest.raises(UnsafePath):
        remove_tree(root / "made" / "deep", roots)
    assert len(os.listdir(fd_dir)) == before
    assert_outside_intact(outside)


# Mount points (Linux mountinfo simulated)


@pytest.mark.parametrize("mount", ["job", "job/sub", "job/sub/deep", "a"])
def test_mount_at_under_or_above_target_refused(monkeypatch, root, roots, mount):
    (root / "job" / "sub" / "deep").mkdir(parents=True)
    (root / "a" / "b").mkdir(parents=True)
    target = root / ("a/b" if mount == "a" else "job")
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: [Path("/"), root / mount])
    with pytest.raises(UnsafePath, match="mount point"):
        remove_tree(target, roots)
    assert target.is_dir()
    assert (root / "job" / "sub" / "deep").is_dir()


def test_unrelated_mounts_and_root_mount_allowed(monkeypatch, tmp_path, root, roots):
    (root / "job" / "x").mkdir(parents=True)
    (root / "jobx").mkdir()
    points = [Path("/"), tmp_path, root, root / "other", root / "jobx"]
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: points)
    remove_tree(root / "job", roots)
    assert not (root / "job").exists()


def test_unreadable_mount_table_fails_closed(monkeypatch, root, roots):
    (root / "job").mkdir()

    def broken():
        raise OSError("no /proc")

    monkeypatch.setattr(mounts, "linux_mount_points", broken)
    with pytest.raises(UnsafePath, match="mount table"):
        remove_tree(root / "job", roots)
    assert (root / "job").is_dir()


def test_macos_fallback_refuses_mount_point(monkeypatch, root, roots):
    (root / "vol").mkdir()
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: None)
    monkeypatch.setattr(mounts, "is_mount_point", lambda path: path == root / "vol")
    with pytest.raises(UnsafePath, match="mount point"):
        remove_tree(root / "vol", roots)
    assert (root / "vol").is_dir()


def fake_identity_for(monkeypatch, victim: Path, identity):
    """Report a different device or mount id for one directory, as a mount would."""
    victim_ino = victim.stat().st_ino
    real = mounts.fd_identity

    def fake(fd):
        if os.fstat(fd).st_ino == victim_ino:
            return identity
        return real(fd)

    monkeypatch.setattr(mounts, "fd_identity", fake)


def test_device_crossing_found_during_walk(monkeypatch, root, roots, no_mounts):
    (root / "job" / "mnt").mkdir(parents=True)
    (root / "job" / "mnt" / "data.txt").write_text("other device")
    fake_identity_for(monkeypatch, root / "job" / "mnt", (-1, None))
    with pytest.raises(UnsafePath, match="another device or mount"):
        remove_tree(root / "job", roots)
    assert (root / "job" / "mnt" / "data.txt").read_text() == "other device"


def test_same_device_bind_mount_found_by_mount_id(monkeypatch, root, roots, no_mounts):
    (root / "job" / "bind").mkdir(parents=True)
    (root / "job" / "bind" / "data.txt").write_text("bind source")
    monkeypatch.setattr(mounts, "fd_mount_id", lambda fd: 1)  # every fd on mount 1 ...
    bind_dev = (root / "job" / "bind").stat().st_dev
    fake_identity_for(monkeypatch, root / "job" / "bind", (bind_dev, 2))  # ... but this one
    with pytest.raises(UnsafePath, match="another device or mount"):
        remove_tree(root / "job", roots)
    assert (root / "job" / "bind" / "data.txt").read_text() == "bind source"


def test_ensure_dir_will_not_cross_a_mount(monkeypatch, root, roots):
    (root / "mnt").mkdir()
    fake_identity_for(monkeypatch, root / "mnt", (-1, None))
    with pytest.raises(UnsafePath, match="another device or mount"):
        ensure_dir(root / "mnt" / "new", roots)
    assert not (root / "mnt" / "new").exists()
