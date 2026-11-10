"""Cancelling a GitHub run through `gh` (runners/cancel_run.py)."""

import subprocess

import pytest

from mulebox.runners.cancel_run import cancel_run, run_of
from mulebox.runners.github import GitHubError

URL = "https://github.com/alice/example-app/actions/runs/123"


def gh(code=0, err=""):
    asked = []

    def run(argv):
        asked.append(list(argv))
        return subprocess.CompletedProcess(argv, code, "", err)
    return run, asked


def test_the_run_is_read_from_its_address():
    assert run_of(URL) == ("alice/example-app", "123")
    assert run_of(URL + "/job/9") == ("alice/example-app", "123")


@pytest.mark.parametrize("bad", [None, "", "https://evil.example/alice/app/actions/runs/1",
                                 "https://github.com/alice/app/actions/runs/1; rm",
                                 "https://github.com/../app/actions/runs/1",
                                 "https://github.com/alice/app/actions/runs/-1"])
def test_anything_else_is_refused(bad):
    with pytest.raises(GitHubError):
        run_of(bad)


def test_gh_is_asked_to_cancel():
    run, asked = gh()
    assert cancel_run(URL, run) == "alice/example-app#123"
    assert asked == [["gh", "run", "cancel", "123", "-R", "alice/example-app"]]


def test_a_refusal_says_why_and_how_to_log_in():
    run, _ = gh(1, "HTTP 401: Bad credentials; token is invalid")
    with pytest.raises(GitHubError, match="gh auth login"):
        cancel_run(URL, run)
