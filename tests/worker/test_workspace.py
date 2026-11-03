"""Workspaces: extraction into the job folder, one git commit without hooks, cleanup."""

import subprocess

import pytest

from mulebox.common.ids import new_id
from mulebox.common.safepath import UnsafePath
from mulebox.worker import workspace


def _git(src, *args):
    return subprocess.run(["git", *args], cwd=src, capture_output=True, text=True, check=True).stdout


def test_prepare_extracts_and_commits(paths, snapshot):
    job_id = new_id("job")
    src = workspace.prepare(paths, "example-app", job_id, snapshot)
    assert src == paths.jobs / "example-app" / job_id / "src"
    assert (src / "README.md").read_text() == "hello\n"
    assert _git(src, "log", "--format=%an <%ae>").strip() == "mulebox <mulebox@localhost>"
    assert _git(src, "status", "--porcelain") == ""
    assert "src/app.sh" in _git(src, "ls-files")


def test_hooks_never_run(paths, snapshot, tmp_path, monkeypatch):
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
    workspace.prepare(paths, "example-app", new_id("job"), snapshot)
    assert not marker.exists()


def test_prepare_refuses_existing_src(paths, snapshot):
    job_id = new_id("job")
    workspace.prepare(paths, "example-app", job_id, snapshot)
    with pytest.raises(workspace.WorkspaceError, match="already exists"):
        workspace.prepare(paths, "example-app", job_id, snapshot)


@pytest.mark.parametrize("project,job_id", [("../x", None), ("ok", "not-a-job-id"), ("", None)])
def test_unsafe_names_refused(paths, snapshot, project, job_id):
    with pytest.raises(UnsafePath):
        workspace.prepare(paths, project, job_id or new_id("job"), snapshot)


def test_cleanup_and_leftovers(paths, snapshot):
    first, second = new_id("job"), new_id("job")
    workspace.prepare(paths, "example-app", first, snapshot)
    workspace.prepare(paths, "other", second, snapshot)
    (paths.jobs / "example-app" / "notes").mkdir()  # not a job folder: left alone
    workspace.cleanup(paths, "example-app", first)
    assert not (paths.jobs / "example-app" / first).exists()
    removed = workspace.remove_leftovers(paths)
    assert removed == [paths.jobs / "other" / second]
    assert (paths.jobs / "example-app" / "notes").is_dir()
