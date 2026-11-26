"""After a power cut: remembered setups forgotten, and a project home git cannot use made again
(power_cut.py, project_repair.py)."""

import subprocess

from mulebox.common.ids import new_id
from mulebox.worker import power_cut, project_home, project_repair

from .conftest import make_tar

FILES = {".gitignore": "node_modules/\n", "README.md": "hello\n"}


def remember(paths, branch="main", kind=project_home.SETUP):
    project_home.remember_setup(paths, "example-app", branch, "key-1", kind)


def test_a_first_start_and_a_restart_in_one_boot_forget_nothing(paths):
    remember(paths)
    assert power_cut.after_start(paths, "boot-a") is False
    assert power_cut.after_start(paths, "boot-a") is False  # killed, started again: same boot
    assert project_home.is_current(paths, "example-app", "main", "key-1")


def test_a_clean_stop_then_a_reboot_forgets_nothing(paths):
    remember(paths)
    power_cut.after_start(paths, "boot-a")
    power_cut.stopped(paths)
    assert power_cut.after_start(paths, "boot-b") is False
    assert project_home.is_current(paths, "example-app", "main", "key-1")


def test_another_boot_with_no_clean_stop_forgets_every_setup_and_install(paths):
    remember(paths)
    remember(paths, "feature/x", project_home.INSTALL)
    power_cut.after_start(paths, "boot-a")
    assert power_cut.after_start(paths, "boot-b") is True
    assert not project_home.is_current(paths, "example-app", "main", "key-1")
    assert not project_home.is_current(paths, "example-app", "feature/x", "key-1",
                                       project_home.INSTALL)


def test_a_system_with_no_boot_identity_judges_nothing(paths):
    remember(paths)
    power_cut.after_start(paths, "boot-a")
    assert power_cut.after_start(paths, None) is False
    assert project_home.is_current(paths, "example-app", "main", "key-1")


def test_this_systems_boot_is_read():
    assert power_cut.current_boot() is not None


def _send(paths, tmp_path, notes):
    job_id = new_id("job")
    (tmp_path / "up").mkdir(exist_ok=True)
    snapshot = make_tar(tmp_path / "up" / f"{job_id}.tar.gz", FILES)
    return project_repair.prepare(paths, "example-app", "main", job_id, snapshot,
                                  lambda tree: None, notes.append)


def git(tree, *args):
    return subprocess.run(["git", *args], cwd=tree, capture_output=True, text=True, check=True)


def test_a_torn_index_makes_the_branch_folder_again(paths, tmp_path):
    notes = []
    tree = _send(paths, tmp_path, notes).tree
    (tree / "node_modules").mkdir()
    [index] = (paths.projects / "example-app" / "repo.git" / "worktrees").glob("*/index")
    index.write_bytes(b"DIRC\x00torn")
    synced = _send(paths, tmp_path, notes)
    assert "this branch's folder" in notes[0] and len(notes) == 1
    assert (synced.tree / "README.md").read_text() == "hello\n"
    assert not (synced.tree / "node_modules").exists()  # made again: setup runs again
    assert git(synced.tree, "status", "--porcelain").stdout == ""


def test_a_broken_repository_makes_the_project_folder_again(paths, tmp_path):
    notes = []
    _send(paths, tmp_path, notes)
    repo = paths.projects / "example-app" / "repo.git"
    (repo / "HEAD").write_text("")  # a cut mid-write: git no longer sees a repository here
    for obj in (repo / "objects").rglob("*"):
        if obj.is_file():
            obj.chmod(0o644)
            obj.write_bytes(b"")
    synced = _send(paths, tmp_path, notes)
    assert "the project's folder" in notes[-1]
    assert (synced.tree / "README.md").read_text() == "hello\n"
    assert git(synced.tree, "log", "-1", "--format=%s").stdout.startswith("mulebox job-")


def test_a_healthy_folder_says_nothing(paths, tmp_path):
    notes = []
    _send(paths, tmp_path, notes)
    _send(paths, tmp_path, notes)
    assert notes == []
