"""A check's result as a GitHub commit status (client/github_status.py, M24.6)."""

import io
import subprocess

from mulebox.client import github_status as gs
from mulebox.common.config import ProjectConfig

HEAD = "a" * 40


def fake(dirty="", remote="  origin/main\n", posted=0):
    calls = []

    def run(argv, cwd):
        calls.append(argv)
        out = ""
        if argv[:2] == ["git", "status"]:
            out = dirty
        elif argv[:2] == ["git", "rev-parse"]:
            out = HEAD + "\n"
        elif argv[:2] == ["git", "branch"]:
            out = remote
        code = posted if argv[0] == "gh" else 0
        return subprocess.CompletedProcess(argv, code, out, "HTTP 404" if code else "")

    run.calls = calls
    return run


def project(on=True):
    return ProjectConfig(project="example-app", jobs={"check": "make test"}, github_status=on)


def test_states_from_exit_codes():
    assert gs.state_for(0) == "success"
    assert gs.state_for(1) == gs.state_for(7) == "failure"
    assert gs.state_for(5) == gs.state_for(130) == gs.state_for(75) == "error"


def test_a_clean_pushed_commit_gets_its_status(tmp_path):
    run, out = fake(), io.StringIO()
    code = gs.around(project(), tmp_path, "check", False, out, lambda: 7, run)
    assert code == 7
    [gh] = [c for c in run.calls if c[0] == "gh"]
    assert f"repos/{{owner}}/{{repo}}/statuses/{HEAD}" in gh
    assert "state=failure" in gh and "context=mulebox/check" in gh
    assert "set to failure" in out.getvalue()


def test_no_status_for_changed_or_unpushed_files(tmp_path):
    for run, why in ((fake(dirty=" M app.py\n"), "changes"), (fake(remote=""), "not pushed")):
        out = io.StringIO()
        assert gs.around(project(), tmp_path, "check", False, out, lambda: 0, run) == 0
        assert not [c for c in run.calls if c[0] == "gh"] and why in out.getvalue()


def test_the_commit_is_settled_before_the_job_runs(tmp_path):
    order = []
    run = fake()

    def logged(argv, cwd):
        order.append(argv[0])
        return run(argv, cwd)

    gs.around(project(), tmp_path, "check", False, io.StringIO(),
              lambda: order.append("job") or 0, logged)
    assert order.index("job") > order.index("git") and order[-1] == "gh"


def test_off_detached_or_refused(tmp_path):
    run = fake()
    gs.around(project(on=False), tmp_path, "check", False, io.StringIO(), lambda: 0, run)
    assert run.calls == []
    out = io.StringIO()
    gs.around(project(), tmp_path, "check", True, out, lambda: 0, run)
    assert run.calls == [] and "--detach" in out.getvalue()
    out, run = io.StringIO(), fake(posted=1)
    assert gs.around(project(), tmp_path, "check", False, out, lambda: 0, run) == 0
    assert "could not set the GitHub status (HTTP 404)" in out.getvalue()
