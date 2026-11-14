import os

from mulebox.common.tree_size import size_of, sizes


def test_a_folder_and_its_parts_are_sized_in_one_walk(tmp_path):
    (tmp_path / "trees" / "main").mkdir(parents=True)
    (tmp_path / "trees" / "dev").mkdir()
    (tmp_path / "repo.git").mkdir()
    (tmp_path / "repo.git" / "pack").write_bytes(b"x" * 100)
    (tmp_path / "trees" / "main" / "a").write_bytes(b"x" * 10)
    (tmp_path / "trees" / "dev" / "b").write_bytes(b"x" * 20)
    main, dev = tmp_path / "trees" / "main", tmp_path / "trees" / "dev"
    total, each = sizes(tmp_path, [main, dev])
    assert total == 130
    assert each == {main: 10, dev: 20}


def test_a_file_with_several_hard_links_counts_once_as_du_counts_it(tmp_path):
    (tmp_path / "store").write_bytes(b"x" * 1000)
    (tmp_path / "node_modules").mkdir()
    os.link(tmp_path / "store", tmp_path / "node_modules" / "pkg")
    os.link(tmp_path / "store", tmp_path / "node_modules" / "pkg2")
    assert size_of(tmp_path) == 1000


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "big").write_bytes(b"x" * 5000)
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "link").symlink_to(outside, target_is_directory=True)
    assert size_of(inside) < 5000


def test_an_empty_or_missing_part_is_zero(tmp_path):
    missing = tmp_path / "trees" / "gone"
    assert sizes(tmp_path, [missing]) == (0, {missing: 0})
