"""A project's home: set up once, kept between jobs, safe from what a job leaves behind."""

import os
import stat
import subprocess

import pytest

from mulebox.common.compose import COMPOSE_FILES_KEY
from mulebox.common.ids import new_id
from mulebox.common.safepath import UnsafePath
from mulebox.worker import project_home as home

from .conftest import make_tar

GITIGNORE = "node_modules/\n.env\n"
FILES = {".gitignore": GITIGNORE, "README.md": "hello\n", "src/app.sh": "echo app\n"}


@pytest.fixture
def send(paths, tmp_path):
    (tmp_path / "up").mkdir(exist_ok=True)

    def run(files=None, branch="main", project="example-app"):
        job_id = new_id("job")
        snapshot = make_tar(tmp_path / "up" / f"{job_id}.tar.gz", files or FILES)
        return home.prepare(paths, project, branch, job_id, snapshot)
    return run


def git(tree, *args):
    return subprocess.run(["git", *args], cwd=tree, capture_output=True, text=True,
                          check=True).stdout


def test_a_first_job_makes_the_folder_with_git_working(send, paths):
    synced = send()
    tree, changed = synced.tree, synced.changed
    assert tree.parent == paths.projects / "example-app" / "trees"
    assert (tree / "README.md").read_text() == "hello\n" and changed == 3
    assert git(tree, "status", "--porcelain") == ""
    assert git(tree, "log", "-1", "--format=%an <%ae>").strip() == "mulebox <mulebox@localhost>"


def test_what_git_ignores_stays(send):
    tree = send().tree
    (tree / "node_modules").mkdir()
    (tree / "node_modules" / "dep.js").write_text("kept")
    send({**FILES, "README.md": "changed\n"})
    assert (tree / "node_modules" / "dep.js").read_text() == "kept"


def test_only_what_changed_is_touched(send):
    tree = send().tree
    os.utime(tree / "src" / "app.sh", (1000, 1000))
    os.utime(tree / "README.md", (1000, 1000))
    assert send({**FILES, "README.md": "changed\n"}).changed == 1
    assert (tree / "src" / "app.sh").stat().st_mtime == 1000
    assert (tree / "README.md").read_text() == "changed\n"
    assert (tree / "README.md").stat().st_mtime != 1000


def test_files_gone_from_the_snapshot_go(send):
    tree = send({**FILES, "old.txt": "x"}).tree
    (tree / "left-by-a-job.txt").write_text("x")
    send()
    assert not (tree / "old.txt").exists() and not (tree / "left-by-a-job.txt").exists()


def test_a_file_changed_by_a_job_comes_back(send):
    tree = send().tree
    (tree / "README.md").write_text("broken by a job")
    send()
    assert (tree / "README.md").read_text() == "hello\n"


def test_a_container_user_can_read_a_mounted_folder(send):
    """A real report: a database's init folder gave `Permission denied` in its container."""
    tree = send({**FILES, "docker/mysql/init/one.sh": "echo"}).tree
    for folder in ("docker", "docker/mysql", "docker/mysql/init"):
        assert stat.S_IMODE((tree / folder).stat().st_mode) == 0o755


def test_a_folder_made_closed_by_an_older_version_opens_on_the_next_job(send):
    files = {**FILES, "docker/init/one.sh": "echo"}
    tree = send(files).tree
    (tree / "docker/init").chmod(0o750)
    (tree / "docker").chmod(0o750)
    send(files)
    assert stat.S_IMODE((tree / "docker/init").stat().st_mode) == 0o755
    assert stat.S_IMODE((tree / "docker").stat().st_mode) == 0o755


def test_a_folder_can_become_a_file(send):
    tree = send({**FILES, "thing/inner.txt": "x"}).tree
    send({**FILES, "thing": "now a file"})
    assert (tree / "thing").read_text() == "now a file"


def test_a_link_left_in_place_of_a_file_is_not_written_through(send, tmp_path):
    tree = send().tree
    outside = tmp_path / "outside.txt"
    outside.write_text("safe")
    (tree / "README.md").unlink()
    (tree / "README.md").symlink_to(outside)
    send()
    assert outside.read_text() == "safe"
    assert not (tree / "README.md").is_symlink()


def test_an_ignored_link_on_the_way_is_refused(send, tmp_path):
    tree = send().tree
    outside = tmp_path / "outside"
    outside.mkdir()
    (tree / ".env").symlink_to(outside)  # ignored as a link, unlike `node_modules/`
    with pytest.raises(UnsafePath):
        send({**FILES, ".env/secret": "x"})
    assert list(outside.iterdir()) == []


def test_a_link_where_a_folder_goes_is_removed_not_followed(send, tmp_path):
    tree = send().tree
    outside = tmp_path / "outside"
    outside.mkdir()
    (tree / "node_modules").symlink_to(outside)
    send({**FILES, "node_modules/dep.js": "x"})
    assert list(outside.iterdir()) == []
    assert (tree / "node_modules" / "dep.js").read_text() == "x"


def test_a_lost_file_of_a_job_is_counted(send):
    tree = send().tree
    (tree / "made-by-setup.txt").write_text("x")
    assert send().lost == 1
    assert send().lost == 0


def test_branches_have_their_own_folders_in_one_repository(send, paths):
    main = send().tree
    other = send({**FILES, "README.md": "other\n"}, branch="feature/a").tree
    third = send(branch="feature-a").tree
    assert len({main, other, third}) == 3
    assert (main / "README.md").read_text() == "hello\n"
    assert (other / "README.md").read_text() == "other\n"
    listing = git(paths.projects / "example-app" / "repo.git", "worktree", "list")
    assert str(main) in listing and str(other) in listing


def test_no_branch_has_a_folder_too(send):
    tree = send(branch=None).tree
    assert tree.name == home.NO_BRANCH


def test_projects_are_apart(send):
    assert send().tree != send(project="other-app").tree


def test_hooks_never_run(send, tmp_path, monkeypatch):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    marker = tmp_path / "hook-ran"
    for name in ("pre-commit", "commit-msg", "post-commit"):
        hook = hooks / name
        hook.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
        hook.chmod(0o755)
    config = tmp_path / "gitconfig"
    config.write_text(f"[core]\n\thooksPath = {hooks}\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    send()
    assert not marker.exists()


@pytest.mark.parametrize("project", ["../x", "", "a/b"])
def test_unsafe_project_names_are_refused(send, project):
    with pytest.raises(UnsafePath):
        send(project=project)


CLAIM = {"setup": "pnpm install", "toolchain": {"node": "22.0.0"}, "env": {"CI": "1"}}


def test_the_key_is_stable_and_follows_what_setup_depends_on(send):
    tree = send({**FILES, "pnpm-lock.yaml": "one", "web/package.json": "{}"}).tree
    key = home.setup_key(tree, CLAIM)
    assert home.setup_key(tree, CLAIM) == key
    assert home.setup_key(tree, {**CLAIM, "setup": "other"}) != key
    assert home.setup_key(tree, {**CLAIM, "toolchain": {"node": "24.0.0"}}) != key
    assert home.setup_key(tree, {**CLAIM, "env": {"CI": "2"}}) != key
    send({**FILES, "pnpm-lock.yaml": "two", "web/package.json": "{}"})
    assert home.setup_key(tree, CLAIM) != key


def test_source_changes_do_not_touch_the_key(send):
    tree = send({**FILES, "pnpm-lock.yaml": "one"}).tree
    key = home.setup_key(tree, CLAIM)
    send({**FILES, "pnpm-lock.yaml": "one", "README.md": "changed\n"})
    assert home.setup_key(tree, CLAIM) == key


def test_setup_state_is_per_branch(send, paths):
    send()
    home.remember_setup(paths, "example-app", "main", "k")
    assert home.is_current(paths, "example-app", "main", "k")
    assert not home.is_current(paths, "example-app", "main", "other")
    assert not home.is_current(paths, "example-app", "feature", "k")
    home.forget_setup(paths, "example-app", "main")
    assert not home.is_current(paths, "example-app", "main", "k")


def test_a_version_file_counts_for_setup(send):
    tree = send({**FILES, "VERSION": "1.0.0\n"}).tree
    claim = {"setup": "pip install -e .", "toolchain": {}, "env": {}}
    before = home.setup_key(tree, claim)
    (tree / "VERSION").write_text("1.0.1\n")
    assert home.setup_key(tree, claim) != before


def test_an_install_depends_on_the_compose_files_too(tmp_path):
    (tmp_path / "compose.yml").write_text("services: {}\n")
    claim = {"install": "npm ci", "toolchain": {}, "env": {COMPOSE_FILES_KEY: "compose.yml"}}
    key = home.install_key(tmp_path, claim)
    assert home.setup_key(tmp_path, claim) != key
    (tmp_path / "compose.yml").write_text("services: {api: {image: node:24}}\n")
    assert home.install_key(tmp_path, claim) != key


def test_setup_and_install_are_remembered_apart(send, paths):
    send()
    home.remember_setup(paths, "example-app", "main", "k", home.INSTALL)
    assert home.is_current(paths, "example-app", "main", "k", home.INSTALL)
    assert not home.is_current(paths, "example-app", "main", "k")
