"""Finding and packing the files a job keeps (files_out.py)."""

import os
import tarfile

from mulebox.common.safepath import Roots
from mulebox.worker import files_out


def make(tree, files):
    for name, data in files.items():
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def names(gathered):
    return [name for name, _ in gathered.files]


def test_a_file_a_folder_and_a_pattern(tmp_path):
    make(tmp_path, {"coverage/lcov.info": b"x" * 10, "test-results/a/shot.png": b"p",
                    "test-results/a/trace.zip": b"t" * 50, "test-results/b/shot.png": b"q",
                    "logs/one.log": b"1", "logs/deep/two.log": b"2", "src/app.py": b"code"})
    got = files_out.gather(tmp_path, ["coverage/lcov.info", "test-results/", "logs/*.log"], 10**6)
    assert names(got) == ["coverage/lcov.info", "logs/one.log", "test-results/a/shot.png",
                          "test-results/a/trace.zip", "test-results/b/shot.png"]
    assert got.left_out == [] and got.size == 63


def test_double_star_reaches_any_depth(tmp_path):
    make(tmp_path, {"r/a.png": b"1", "r/x/y/b.png": b"2", "r/x/c.txt": b"3", "top.png": b"4"})
    got = files_out.gather(tmp_path, ["r/**/*.png", "**/top.png"], 10**6)
    assert names(got) == ["r/a.png", "r/x/y/b.png", "top.png"]


def test_links_are_named_and_never_followed(tmp_path):
    outside = tmp_path / "outside"
    make(outside, {"secret.txt": b"no"})
    tree = tmp_path / "tree"
    make(tree, {"report/index.html": b"ok"})
    os.symlink(outside / "secret.txt", tree / "report" / "secret.txt")
    os.symlink(outside, tree / "report" / "away")
    os.symlink(outside, tree / "linked")
    got = files_out.gather(tree, ["report/", "linked/"], 10**6)
    assert names(got) == ["report/index.html"]
    assert sorted(got.left_out) == ["linked/: goes through a link, not followed",
                                    "report/away: is a link, not followed",
                                    "report/secret.txt: is a link, not followed"]


def test_what_matches_nothing_is_said(tmp_path):
    make(tmp_path, {"a.txt": b"1"})
    got = files_out.gather(tmp_path, ["missing/", "*.png"], 10**6)
    assert got.files == [] and got.left_out == ["missing/: matches nothing",
                                                "*.png: matches nothing"]


def test_past_the_cap_the_smallest_go_in_first(tmp_path):
    make(tmp_path, {"r/big.zip": b"b" * 900, "r/one.png": b"1" * 100, "r/two.png": b"2" * 100,
                    "r/index.html": b"h" * 50})
    got = files_out.gather(tmp_path, ["r/"], 300)
    assert names(got) == ["r/index.html", "r/one.png", "r/two.png"]
    assert got.left_out_count == 1 and got.left_out[0].startswith("r/big.zip: past keep_files_max")
    assert got.report(True) == {"count": 3, "bytes": 250, "left_out": got.left_out,
                                "left_out_count": 1, "packed": True}


def test_the_pack_holds_the_files_by_their_project_paths_and_no_owner(tmp_path):
    tree, staging = tmp_path / "tree", tmp_path / "staging"
    staging.mkdir()
    make(tree, {"r/a.txt": b"alpha", "r/b/c.txt": b"gamma"})
    got = files_out.gather(tree, ["r/"], 10**6)
    roots = Roots((staging,))
    path, sha = files_out.pack(tree, got, staging, roots, "job-01HZZZZZZZZZZZZZZZZZZZZZZZ")
    assert path.parent == staging / files_out.OUT and len(sha) == 64
    with tarfile.open(path) as tar:
        members = {m.name: m for m in tar.getmembers()}
        assert sorted(members) == ["r/a.txt", "r/b/c.txt"]
        assert all(m.uid == 0 and m.uname == "" and m.isfile() for m in members.values())
        assert tar.extractfile("r/b/c.txt").read() == b"gamma"
    assert files_out.leftovers(staging, roots) == 1 and not path.exists()
