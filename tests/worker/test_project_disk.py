"""Removing project folders: only what was asked, and nothing outside."""

import subprocess

import pytest

from mulebox.common.ids import new_id
from mulebox.common.safepath import RemovalDenied
from mulebox.worker import project_disk as disk
from mulebox.worker import project_home as home

from .conftest import make_tar

FILES = {".gitignore": "node_modules/\n", "README.md": "hello\n"}


@pytest.fixture
def send(paths, tmp_path):
    def run(branch="main", project="example-app"):
        snapshot = tmp_path / "snapshot.tar.gz"
        make_tar(snapshot, FILES)
        tree = home.prepare(paths, project, branch, new_id("job"), snapshot).tree
        (tree / "node_modules").mkdir(exist_ok=True)
        (tree / "node_modules" / "dep.js").write_text("x" * 1000)
        return tree
    return run


def refuse(path):
    raise AssertionError(f"nothing here needs giving back: {path}")


def test_listing_gives_folders_and_sizes(paths, send):
    tree = send()
    send("feature/a")
    row = disk.listing(paths)[0]
    assert row["project"] == "example-app" and row["folder"] == str(paths.projects / "example-app")
    assert {entry["folder"] for entry in row["trees"]} == {tree.name, home.slug("feature/a")}
    assert row["size"] > 2000


def test_an_empty_machine_lists_nothing(paths):
    assert disk.listing(paths) == []


def test_unused_keeps_the_newest_and_recent_ones():
    names = [home.slug(b) for b in ("main", "old", "recent")]
    used = {"main": 300.0, "old": 10.0, "recent": 250.0}
    assert disk.unused(names, used, cutoff=100.0) == [home.slug("old")]


def test_a_project_with_only_old_branches_keeps_its_newest():
    names = [home.slug("main"), home.slug("old")]
    assert disk.unused(names, {"main": 20.0, "old": 10.0}, cutoff=100.0) == [home.slug("old")]


def test_a_branch_is_removed_and_comes_back(paths, send):
    main, other = send(), send("feature/a")
    home.remember_setup(paths, "example-app", "feature/a", "key")
    disk.remove_worktree(paths, "example-app", other.name, refuse)
    assert not other.exists() and main.is_dir()
    assert not home.is_current(paths, "example-app", "feature/a", "key")
    assert send("feature/a") == other
    assert (other / "README.md").is_file()


def test_a_project_is_removed_and_comes_back(paths, send):
    tree = send()
    other = send(project="other-app")
    disk.remove_project(paths, "example-app", refuse)
    assert not paths.project_home("example-app").exists() and other.is_dir()
    assert send() == tree


def test_a_denied_removal_is_given_back_first(paths, send, monkeypatch):
    tree = send()
    real, calls = disk.remove_tree, []

    def denied_once(path, roots):
        if path == tree and not calls:
            raise RemovalDenied("owned by root")
        real(path, roots)

    monkeypatch.setattr(disk, "remove_tree", denied_once)
    disk.remove_project(paths, "example-app", calls.append)
    assert calls == [tree] and not tree.exists()


def test_git_forgets_a_removed_branch(paths, send):
    other = send("feature/a")
    disk.remove_worktree(paths, "example-app", other.name, refuse)
    repo = paths.project_home("example-app") / "repo.git"
    listing = subprocess.run(["git", "worktree", "list"], cwd=repo, capture_output=True, text=True)
    assert other.name not in listing.stdout
