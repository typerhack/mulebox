"""safepath.confirm_dir: what may be handed to a bind mount. Fixtures: conftest.py."""

import pytest

from mulebox.common import mounts, safepath
from mulebox.common.safepath import PathOutsideRoots, UnsafePath, confirm_dir


def test_a_real_directory_inside_the_root(root, roots):
    (root / "a" / "b").mkdir(parents=True)
    assert confirm_dir(root / "a" / "b", roots) == root / "a" / "b"


def test_the_root_itself_is_refused(root, roots):
    with pytest.raises(UnsafePath, match="root"):
        confirm_dir(root, roots)


def test_outside_the_root_is_refused(outside, roots):
    with pytest.raises(PathOutsideRoots):
        confirm_dir(outside, roots)


def test_the_parent_of_the_root_is_refused(root, roots):
    with pytest.raises(PathOutsideRoots):
        confirm_dir(root.parent, roots)


def test_relative_is_refused(roots):
    with pytest.raises(UnsafePath, match="not absolute"):
        confirm_dir("a/b", roots)


def test_dotdot_is_refused_even_when_it_lands_inside(root, roots):
    (root / "a").mkdir()
    (root / "b").mkdir()
    with pytest.raises(UnsafePath, match=r"'\.\.'"):
        confirm_dir(root / "a" / ".." / "b", roots)


def test_dotdot_out_of_the_root_is_refused(root, roots):
    with pytest.raises(UnsafePath, match=r"'\.\.'"):
        confirm_dir(root / ".." / "outside", roots)


def test_a_symlink_to_outside_is_refused(root, roots, outside):
    (root / "link").symlink_to(outside)
    with pytest.raises(UnsafePath, match="symlink"):
        confirm_dir(root / "link", roots)


def test_a_symlink_to_inside_is_refused_too(root, roots):
    (root / "real").mkdir()
    (root / "link").symlink_to(root / "real")
    with pytest.raises(UnsafePath, match="symlink"):
        confirm_dir(root / "link", roots)


def test_a_symlink_on_the_way_is_refused(root, roots, outside):
    (root / "link").symlink_to(outside)
    with pytest.raises(UnsafePath, match="symlink"):
        confirm_dir(root / "link" / "sub", roots)


def test_a_file_is_refused(root, roots):
    (root / "file").write_text("x")
    with pytest.raises(UnsafePath, match="not a directory"):
        confirm_dir(root / "file", roots)


def test_missing_is_refused(root, roots):
    with pytest.raises(UnsafePath, match="does not exist"):
        confirm_dir(root / "gone", roots)


@pytest.mark.parametrize("where", ["a", "a/b", "a/b/c"])
def test_a_mount_at_in_or_above_is_refused(monkeypatch, root, roots, where):
    (root / "a" / "b" / "c").mkdir(parents=True)
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: [root / where])
    with pytest.raises(UnsafePath, match="mount"):
        confirm_dir(root / "a" / "b", roots)


def test_a_mounted_root_is_fine(monkeypatch, root, roots):
    (root / "a").mkdir()
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: [root])
    assert confirm_dir(root / "a", roots) == root / "a"


def test_an_unreadable_mount_table_is_refused(monkeypatch, root, roots):
    (root / "a").mkdir()

    def boom():
        raise OSError("no mountinfo")

    monkeypatch.setattr(mounts, "linux_mount_points", boom)
    with pytest.raises(UnsafePath, match="mount table"):
        confirm_dir(root / "a", roots)


def test_a_component_swapped_after_the_mount_check_is_refused(monkeypatch, root, roots, outside):
    (root / "a").mkdir()
    real = safepath._refuse_mounts

    def check_then_swap(target, root_path):
        real(target, root_path)
        (root / "a").rename(root / "moved")
        (root / "a").symlink_to(outside)

    monkeypatch.setattr(safepath, "_refuse_mounts", check_then_swap)
    with pytest.raises(UnsafePath, match="symlink"):
        confirm_dir(root / "a", roots)


def test_a_replaced_root_is_refused(tmp_path, root, roots):
    (root / "a").mkdir()
    root.rename(tmp_path / "old")
    root.mkdir()
    (root / "a").mkdir()
    with pytest.raises(UnsafePath, match="replaced"):
        confirm_dir(root / "a", roots)
