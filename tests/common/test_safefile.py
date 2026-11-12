"""safefile: small files inside the roots, never through a symlink. Fixtures: conftest.py."""

import os

import pytest

from mulebox.common.safefile import read_text, write_text
from mulebox.common.safepath import PathOutsideRoots, UnsafePath


def test_written_and_read_back_with_its_mode(root, roots):
    (root / "a").mkdir()
    write_text(root / "a" / "f", "one", roots, 0o600)
    write_text(root / "a" / "f", "two", roots, 0o600)
    assert read_text(root / "a" / "f", roots) == "two"
    assert (root / "a" / "f").stat().st_mode & 0o777 == 0o600
    assert sorted(os.listdir(root / "a")) == ["f"]  # no temporary file left


def test_missing_reads_as_none(root, roots):
    (root / "a").mkdir()
    assert read_text(root / "a" / "nothing", roots) is None
    assert read_text(root / "no-folder" / "f", roots) is None


def test_a_symlink_at_the_name_is_replaced_not_followed(root, outside, roots):
    target = outside / "keep.txt"
    (root / "a").mkdir()
    (root / "a" / "f").symlink_to(target)
    with pytest.raises(UnsafePath):
        read_text(root / "a" / "f", roots)
    write_text(root / "a" / "f", "new", roots)
    assert target.read_text() == "keep" and not (root / "a" / "f").is_symlink()


def test_a_folder_that_is_a_symlink_is_refused(root, outside, roots):
    (root / "a").symlink_to(outside)
    with pytest.raises(UnsafePath, match="symlink"):
        write_text(root / "a" / "f", "x", roots)
    with pytest.raises(UnsafePath, match="symlink"):
        read_text(root / "a" / "f", roots)
    assert sorted(p.name for p in outside.iterdir()) == ["keep.txt", "sub"]


def test_outside_the_roots_is_refused(outside, roots):
    with pytest.raises(PathOutsideRoots):
        write_text(outside / "f", "x", roots)


def test_only_a_regular_file_is_read(root, roots):
    (root / "a").mkdir()
    os.mkfifo(root / "a" / "pipe")
    with pytest.raises(UnsafePath, match="regular"):
        read_text(root / "a" / "pipe", roots)


def test_the_root_itself_holds_no_such_file(root, roots):
    with pytest.raises(UnsafePath, match="root"):
        write_text(root / "f", "x", roots)
