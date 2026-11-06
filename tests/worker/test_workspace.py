"""Job folders, and git with fixed settings."""

import pytest

from mulebox.common.ids import new_id
from mulebox.common.safepath import UnsafePath
from mulebox.worker import workspace


@pytest.mark.parametrize("project,job_id", [("../x", None), ("ok", "not-a-job-id"), ("", None)])
def test_unsafe_names_refused(paths, project, job_id):
    with pytest.raises(UnsafePath):
        workspace.job_dir(paths, project, job_id or new_id("job"))


def test_cleanup_and_leftovers(paths):
    first, second = new_id("job"), new_id("job")
    workspace.job_dir(paths, "example-app", first)
    workspace.job_dir(paths, "other", second)
    (paths.jobs / "example-app" / "notes").mkdir()  # not a job folder: left alone
    workspace.cleanup(paths, "example-app", first)
    assert not (paths.jobs / "example-app" / first).exists()
    assert workspace.leftover_job_dirs(paths) == [paths.jobs / "other" / second]
    assert (paths.jobs / "example-app" / "notes").is_dir()


def test_a_failing_git_says_so(tmp_path):
    with pytest.raises(workspace.WorkspaceError, match="git log failed"):
        workspace.git(tmp_path, "log")
