"""Repository, runner name, label and unit name rules."""

import pytest

from mulebox.runners import names
from mulebox.runners.names import RunnerUsageError


@pytest.mark.parametrize("repo", ["example-org/example-app", "alice/app.js", "a/b_c-d"])
def test_good_repos(repo):
    assert names.check_repo(repo) == repo


@pytest.mark.parametrize("repo", ["-x/y", "a/b/c", "a b/c", "a/b c", "example-org",
                                  "/app", "org/", "org/..", "org/.", " a/b", "a/b\n", ""])
def test_bad_repos(repo):
    with pytest.raises(RunnerUsageError):
        names.check_repo(repo)


def test_default_name_and_unit():
    name = names.default_name("build-1", "example-org/example-app")
    assert name == "build-1-example-app"
    assert names.unit_name(name) == "mulebox-runner@build-1-example-app.service"
    assert len(names.default_name("build-1", "o/" + "a" * 100)) == names.MAX_NAME


@pytest.mark.parametrize("name", ["-x", "a/b", "a b", "", "x" * 65, "../x"])
def test_bad_runner_names(name):
    with pytest.raises(RunnerUsageError):
        names.check_name(name)


def test_labels():
    assert names.parse_labels(None) == ("mulebox",)
    assert names.parse_labels("mulebox, gpu") == ("mulebox", "gpu")
    for bad in ("a,,b", "a b", "-x", "a;b"):
        with pytest.raises(RunnerUsageError):
            names.parse_labels(bad)


def test_repo_url():
    assert names.repo_url("example-org/example-app") == "https://github.com/example-org/example-app"
