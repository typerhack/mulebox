"""safepath: resolve_inside, remove_tree, ensure_dir (normal and hostile input).

Everything happens under tmp_path. Roots: test_roots.py. Races and mounts:
test_safepath_attacks.py. Fixtures: conftest.py.
"""

import os
import stat
from pathlib import Path

import pytest

from mulebox.common.safepath import (
    PathOutsideRoots,
    RemovalDenied,
    UnsafePath,
    ensure_dir,
    remove_tree,
    resolve_inside,
)


def make_tree(base: Path) -> None:
    (base / "src" / "pkg").mkdir(parents=True)
    (base / "src" / "pkg" / "a.py").write_text("a")
    (base / "build").mkdir()
    (base / "build" / "out.bin").write_bytes(b"\0" * 64)
    (base / "top.txt").write_text("t")


# resolve_inside


def test_resolve_inside_ok(root, roots):
    (root / "job").mkdir()
    assert resolve_inside(root / "job", roots) == root / "job"
    assert resolve_inside(root / "not-yet", roots) == root / "not-yet"


def test_resolve_inside_refuses_root_relative_and_outside(tmp_path, root, roots):
    with pytest.raises(UnsafePath, match="itself"):
        resolve_inside(root, roots)
    with pytest.raises(UnsafePath, match="absolute"):
        resolve_inside(Path("jobs/x"), roots)
    with pytest.raises(PathOutsideRoots):
        resolve_inside(tmp_path / "elsewhere", roots)
    with pytest.raises(UnsafePath, match="NUL"):
        resolve_inside(Path(f"{root}/a\0b"), roots)


def test_prefix_lookalike_is_outside(tmp_path, roots):
    (tmp_path / "jobs2").mkdir()
    with pytest.raises(PathOutsideRoots):
        resolve_inside(tmp_path / "jobs2" / "x", roots)


def test_dotdot_and_symlink_escapes(root, roots, outside):
    with pytest.raises(PathOutsideRoots):
        resolve_inside(root / "a" / ".." / ".." / "outside", roots)
    with pytest.raises(UnsafePath, match="itself"):
        resolve_inside(root / "a" / "..", roots)
    (root / "escape").symlink_to(outside)
    with pytest.raises(PathOutsideRoots):
        resolve_inside(root / "escape" / "keep.txt", roots)


# remove_tree


def test_remove_tree_deletes_tree(root, roots):
    make_tree(root / "job")
    remove_tree(root / "job", roots)
    assert not (root / "job").exists()
    assert root.is_dir()


def test_remove_tree_single_file_and_missing(root, roots):
    (root / "f").write_text("x")
    remove_tree(root / "f", roots)
    assert not (root / "f").exists()
    remove_tree(root / "f", roots)
    remove_tree(root / "no" / "such" / "thing", roots)


def test_remove_tree_refuses_root_and_outside(tmp_path, root, roots, outside):
    make_tree(root / "job")
    with pytest.raises(UnsafePath, match="itself"):
        remove_tree(root, roots)
    with pytest.raises(PathOutsideRoots):
        remove_tree(outside, roots)
    with pytest.raises(PathOutsideRoots):
        remove_tree(outside / "keep.txt", roots)
    with pytest.raises(UnsafePath):
        remove_tree(Path("jobs/job"), roots)
    with pytest.raises(UnsafePath):
        remove_tree(root / "job" / "..", roots)
    assert (root / "job" / "top.txt").exists()
    assert (outside / "keep.txt").exists()


def test_remove_tree_prefix_lookalike(tmp_path, roots):
    (tmp_path / "jobs2" / "x").mkdir(parents=True)
    with pytest.raises(PathOutsideRoots):
        remove_tree(tmp_path / "jobs2" / "x", roots)
    assert (tmp_path / "jobs2" / "x").is_dir()


def test_remove_tree_dotdot_escape(root, roots, outside):
    (root / "a").mkdir()
    with pytest.raises(PathOutsideRoots):
        remove_tree(root / "a" / ".." / ".." / "outside" / "keep.txt", roots)
    assert (outside / "keep.txt").exists()


def test_symlinked_parent_pointing_outside(root, roots, outside):
    (root / "link").symlink_to(outside)
    with pytest.raises(PathOutsideRoots):
        remove_tree(root / "link" / "keep.txt", roots)
    assert (outside / "keep.txt").exists()


def test_symlink_inside_tree_is_not_followed(root, roots, outside):
    make_tree(root / "job")
    (root / "job" / "dirlink").symlink_to(outside)
    (root / "job" / "src" / "filelink").symlink_to(outside / "keep.txt")
    remove_tree(root / "job", roots)
    assert not (root / "job").exists()
    assert (outside / "keep.txt").read_text() == "keep"


def test_final_symlink_is_unlinked_not_followed(root, roots, outside):
    (root / "dirlink").symlink_to(outside)
    (root / "filelink").symlink_to(outside / "keep.txt")
    (root / "dangling").symlink_to(root / "missing")
    for name in ("dirlink", "filelink", "dangling"):
        remove_tree(root / name, roots)
        assert not os.path.lexists(root / name)
    assert (outside / "keep.txt").read_text() == "keep"


def test_hard_link_to_outside_file_only_drops_the_link(root, roots, outside):
    (root / "job").mkdir()
    try:
        os.link(outside / "keep.txt", root / "job" / "hard")
    except OSError:
        pytest.skip("hard links not supported here")
    remove_tree(root / "job", roots)
    assert (outside / "keep.txt").read_text() == "keep"


def test_deep_tree(root, roots):
    deep = root / "job"
    for i in range(120):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    (deep / "leaf.txt").write_text("x")
    remove_tree(root / "job", roots)
    assert not (root / "job").exists()


def test_wide_tree(root, roots):
    for i in range(40):
        (root / "job" / f"d{i}" / "sub").mkdir(parents=True)
        (root / "job" / f"d{i}" / "sub" / "f").write_text("x")
    remove_tree(root / "job", roots)
    assert not (root / "job").exists()


def test_read_only_files_and_directories(root, roots):
    make_tree(root / "job")
    ro_file = root / "job" / "src" / "pkg" / "a.py"
    ro_file.chmod(0o444)
    (root / "job" / "src" / "pkg").chmod(0o555)
    (root / "job" / "src").chmod(0o555)
    remove_tree(root / "job", roots)
    assert not (root / "job").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_permission_denied_is_reported_not_escalated(root, roots):
    (root / "job" / "locked").mkdir(parents=True)
    (root / "job" / "locked" / "f").write_text("x")
    (root / "job" / "locked").chmod(0)
    try:
        with pytest.raises(RemovalDenied):
            remove_tree(root / "job", roots)
    finally:
        (root / "job" / "locked").chmod(0o700)
    assert (root / "job" / "locked" / "f").exists()


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores permissions")
def test_read_only_parent_of_target_is_not_changed(root, roots):
    (root / "ro" / "job").mkdir(parents=True)
    (root / "ro").chmod(0o555)
    try:
        with pytest.raises(RemovalDenied):
            remove_tree(root / "ro" / "job", roots)
        assert stat.S_IMODE((root / "ro").stat().st_mode) == 0o555
    finally:
        (root / "ro").chmod(0o755)


def test_root_replaced_after_configuration(tmp_path, root, roots):
    root.rename(tmp_path / "old-jobs")
    root.mkdir()
    (root / "job").mkdir()
    with pytest.raises(UnsafePath, match="replaced"):
        remove_tree(root / "job", roots)
    with pytest.raises(UnsafePath, match="replaced"):
        ensure_dir(root / "new", roots)
    assert (root / "job").is_dir()


# ensure_dir


def test_ensure_dir_creates_with_mode(root, roots):
    old = os.umask(0o077)
    try:
        made = ensure_dir(root / "a" / "b" / "c", roots)
    finally:
        os.umask(old)
    assert made == root / "a" / "b" / "c"
    for path in (root / "a", root / "a" / "b", made):
        assert path.is_dir()
        assert stat.S_IMODE(path.stat().st_mode) == 0o750
    assert ensure_dir(made, roots) == made


def test_ensure_dir_refuses_symlink_components(root, roots, outside):
    (root / "inner").mkdir()
    (root / "out").symlink_to(outside)
    (root / "in").symlink_to(root / "inner")
    for path in (root / "out" / "new", root / "in" / "new", root / "out"):
        with pytest.raises(UnsafePath, match="symlink"):
            ensure_dir(path, roots)
    assert sorted(p.name for p in outside.iterdir()) == ["keep.txt", "sub"]
    assert list((root / "inner").iterdir()) == []


def test_ensure_dir_refuses_bad_paths(tmp_path, root, roots):
    (root / "file").write_text("x")
    with pytest.raises(UnsafePath, match="not a directory"):
        ensure_dir(root / "file" / "sub", roots)
    with pytest.raises(UnsafePath, match="itself"):
        ensure_dir(root, roots)
    with pytest.raises(UnsafePath, match=r"\.\."):
        ensure_dir(root / "a" / ".." / ".." / "outside", roots)
    with pytest.raises(UnsafePath, match="absolute"):
        ensure_dir(Path("jobs/a"), roots)
    for bad in (tmp_path / "elsewhere", tmp_path / "jobs2" / "a"):
        with pytest.raises(PathOutsideRoots):
            ensure_dir(bad, roots)
    assert not (tmp_path / "elsewhere").exists()
    assert not (tmp_path / "jobs2").exists()
