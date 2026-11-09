"""`mulebox runner caches`: a runner uses a project's package caches, with fakes for systemctl."""

import pytest

from mulebox.runners import layout, manage, runner_caches
from mulebox.runners.names import RunnerUsageError

from .conftest import TOKEN

NAME = "build-1-example-app"


@pytest.fixture
def runner(machine):
    return manage.add(machine, "example-org/example-app", TOKEN, name=NAME, labels=("mulebox",))


def env_lines(folder):
    return (folder / ".env").read_text().splitlines()


def test_a_runner_gets_the_projects_cache_folders_and_is_restarted(machine, fakes, paths, runner):
    env = runner_caches.share(machine, NAME, "example-app", ["cache-npm"])
    folder = paths.package_cache("example-app", "npm")
    assert env == {"MULEBOX_CACHE_NPM": str(folder), "npm_config_cache": str(folder)}
    assert folder.is_dir()
    lines = env_lines(runner)
    assert f"npm_config_cache={folder}" in lines and lines[0] == "LANG=C.UTF-8"
    assert any(line.startswith("ACTIONS_RUNNER_HOOK_JOB_STARTED=") for line in lines)
    assert fakes.systemctl_calls[-1] == ["systemctl", "--user", "restart",
                                         f"mulebox-runner@{NAME}.service"]
    assert layout.read_meta(runner)["caches_of"] == "example-app"


def test_off_removes_only_the_cache_lines(machine, paths, runner):
    before = env_lines(runner)
    runner_caches.share(machine, NAME, "example-app")
    assert len(env_lines(runner)) > len(before)
    assert runner_caches.share(machine, NAME, None) == {}
    assert env_lines(runner) == before


def test_a_busy_or_unknown_runner_or_a_bad_name_is_refused(machine, paths, runner):
    with pytest.raises(RunnerUsageError, match="no runner"):
        runner_caches.share(machine, "build-1-other", "example-app")
    with pytest.raises(RunnerUsageError, match="project name"):
        runner_caches.share(machine, NAME, "../etc")
    with pytest.raises(RunnerUsageError, match="unknown cache"):
        runner_caches.share(machine, NAME, "example-app", ["cache-maven"])
    (runner / layout.RESERVATION_FILE).write_text("job-1\n")
    with pytest.raises(RunnerUsageError, match="job running"):
        runner_caches.share(machine, NAME, "example-app")
