"""Laptop side: token from a fake `gh`, remote command over a fake ssh stream."""

import io
import subprocess

import pytest

from mulebox.common import ssh
from mulebox.common.config import ClientConfig
from mulebox.runners import github
from mulebox.runners.github import GitHubError
from mulebox.runners.names import RunnerUsageError

from .conftest import TOKEN

REPO = "example-org/example-app"
CONFIG = ClientConfig(coordinator="build-1")


class FakeGh:
    def __init__(self, code=0, out=TOKEN + "\n", err=""):
        self.calls, self.result = [], (code, out, err)

    def __call__(self, argv):
        self.calls.append(list(argv))
        return subprocess.CompletedProcess(argv, *self.result)


class FakeStream:
    def __init__(self, lines=(b"Started mulebox-runner@x.service\n",), error=None):
        self.calls, self.lines, self.error = [], lines, error

    def __call__(self, target, argv, *, stdin=None, connect_timeout_s=10):
        self.calls.append((target, list(argv), stdin, connect_timeout_s))
        yield from self.lines
        if self.error is not None:
            raise self.error


def test_register_gets_a_token_and_sends_it_on_stdin():
    gh, stream, out = FakeGh(), FakeStream(), io.StringIO()
    github.register(CONFIG, REPO, labels="mulebox,gpu", run=gh, stream=stream, out=out)
    assert gh.calls == [["gh", "api", "-X", "POST",
                         f"repos/{REPO}/actions/runners/registration-token", "--jq", ".token"]]
    [(target, argv, stdin, _)] = stream.calls
    assert target == "build-1"
    assert argv == [".mulebox/bin/mulebox", "runner", "add", "--repo", REPO,
                    "--labels", "mulebox,gpu"]
    assert stdin == (TOKEN + "\n").encode()
    assert all(TOKEN not in arg for arg in argv)
    assert "Started" in out.getvalue()


def test_unregister_uses_the_remove_token_and_name():
    gh, stream = FakeGh(), FakeStream()
    github.unregister(CONFIG, REPO, name="build-1-example-app", run=gh, stream=stream,
                      out=io.StringIO())
    assert gh.calls[0][4] == f"repos/{REPO}/actions/runners/remove-token"
    assert stream.calls[0][1][2:] == ["remove", "--repo", REPO, "--name", "build-1-example-app"]


@pytest.mark.parametrize("repo", ["-x/y", "a/b/c", "a b/c"])
def test_bad_repo_refused_before_gh_runs(repo):
    gh = FakeGh()
    with pytest.raises(RunnerUsageError):
        github.register(CONFIG, repo, run=gh, stream=FakeStream())
    assert gh.calls == []


def test_gh_failure_is_explained():
    gh = FakeGh(code=1, out="", err="HTTP 403: Must have admin rights to Repository.")
    with pytest.raises(GitHubError, match="admin rights"):
        github.gh_token(REPO, "registration", gh)


def test_remote_output_and_errors_are_redacted():
    out = io.StringIO()
    error = ssh.RemoteError(f"remote failed: {TOKEN}", exit_code=1, stderr=b"")
    stream = FakeStream(lines=[f"echo {TOKEN}\n".encode()], error=error)
    with pytest.raises(GitHubError) as info:
        github.register(CONFIG, REPO, run=FakeGh(), stream=stream, out=out)
    assert TOKEN not in out.getvalue() and "[redacted]" in out.getvalue()
    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_unreachable_stays_unreachable():
    stream = FakeStream(lines=[], error=ssh.SSHUnavailable("cannot connect to build-1"))
    with pytest.raises(ssh.SSHUnavailable):
        github.register(CONFIG, REPO, run=FakeGh(), stream=stream, out=io.StringIO())
