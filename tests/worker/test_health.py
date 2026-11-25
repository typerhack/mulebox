"""The node's own checks (worker/health.py): each check, the streak, the report."""

import subprocess
from dataclasses import replace

from mulebox.common import storage_policy
from mulebox.common.errors import MuleboxError
from mulebox.worker import health
from mulebox.worker.docker import DockerError


def done(code):
    return lambda argv: subprocess.CompletedProcess(argv, code, "", "")


def with_floor(node, floor):
    return replace(node, storage=replace(storage_policy.StoragePolicy(), min_free=floor))


def test_a_healthy_node_has_no_problem(node, paths):
    assert health.run_all(node, paths, ["node"], engine=None, run=done(0)) == []


def test_disk_under_min_free_names_the_folder_and_the_fix(node, paths):
    found = health.disk(with_floor(node, "999TB"), paths)
    assert found[0] == "disk" and "under its min_free of 999.0 TB" in found[1]
    assert "`mulebox storage clean`" in found[2]
    assert health.disk(with_floor(node, "1MB"), paths) is None


def test_a_root_that_cannot_be_written(node, paths):
    paths.staging.chmod(0o500)
    try:
        found = health.roots(node, paths)
    finally:
        paths.staging.chmod(0o700)
    assert found[0] == "roots" and "staging" in found[1] and "writable" in found[2]
    assert not list(paths.staging.glob(".mulebox-health-*"))


def test_git_and_the_executor(node):
    assert health.git(node, done(0)) is None
    assert health.git(node, done(1))[0] == "git"

    def missing(argv):
        raise MuleboxError("no such command")
    assert "no such command" in health.git(node, missing)[1]
    assert health.executor(node, done(0)) is None
    found = health.executor(node, done(1))
    assert found[0] == "executor" and "loginctl enable-linger" in found[2]


def test_ran_names_the_checks_run_all_runs():
    assert health.ran(["node"]) == ["disk", "roots", "git"]
    assert health.ran(["docker", "xcode"], systemd=True) == ["disk", "roots", "git", "executor",
                                                             "docker", "xcode"]


def test_the_executor_is_checked_only_for_systemd(node, paths):
    assert health.run_all(node, paths, [], None, run=done(1), systemd=False)[0][0] == "git"
    checks = [c for c, _, _ in health.run_all(node, paths, [], None, run=done(1), systemd=True)]
    assert checks == ["git", "executor"]


class Engine:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def run(self, *args, timeout_s=None):
        self.calls.append(args)
        if self.error:
            raise self.error
        return "27.0\n"


def test_docker_and_xcode_only_where_offered(node, paths):
    down = Engine(DockerError("Cannot connect to the Docker daemon"))
    assert health.run_all(node, paths, ["node"], down, run=done(0)) == []
    assert not down.calls
    found = health.run_all(node, paths, ["docker"], down, run=done(0))
    assert found[0][0] == "docker" and "Cannot connect" in found[0][1]
    assert "jobs without Docker still run" in found[0][2]
    assert health.docker(node, down, platform="darwin")[2].startswith("start Docker Desktop")
    assert health.run_all(node, paths, ["docker"], Engine(), run=done(0)) == []
    assert health.run_all(node, paths, ["xcode"], None, run=done(1))[-1][0] == "xcode"


class App:
    developer_dir = "/Applications/Xcode.app/Contents/Developer"


def test_xcode_is_checked_as_jobs_run_it(node):
    assert health.xcode(node, done(0), found=lambda: [App()]) is None
    assert "no Xcode is installed" in health.xcode(node, done(0), found=list)[1]
    assert health.xcode(node, done(1), found=lambda: [App()])[1] == "xcodebuild does not run"


def test_docker_down_rests_a_node_whose_floor_is_container():
    docker = [("docker", "Docker does not answer", "start Docker")]
    streak = health.Streak()
    assert not health.report(docker, {}, ["docker"], streak, 1.0)["resting"]
    assert health.report(docker, {}, ["docker"], streak, 1.0, floor="container")["resting"]


def test_a_streak_of_two_projects_rests_the_node_then_one_job_on_trial():
    streak = health.Streak()
    for project in ("a", "a", "a"):
        streak.failed_start(project, 100.0)
    assert streak.problem(100.0) is None  # one project failing is its own
    streak.failed_start("b", 101.0)
    assert streak.until == 101.0 + health.REST_S
    assert streak.problem(102.0)[0] == "streak"
    assert streak.problem(101.0 + health.REST_S) is None and streak.trial
    streak.failed_start("c", 800.0)  # on trial, one more failure rests it again
    assert streak.until == 800.0 + health.REST_S
    streak.started()
    assert streak.problem(801.0) is None and not streak.trial


def test_failures_far_apart_make_no_streak():
    streak = health.Streak()
    streak.failed_start("a", 0.0)
    streak.failed_start("b", 0.0)
    streak.failed_start("c", health.STREAK_S + 1)
    assert streak.until is None


def test_the_report_rests_for_a_whole_node_check_and_withholds_for_docker():
    streak = health.Streak()
    offered = ["compose-v1", "docker", "isolated", "linux"]
    docker = [("docker", "Docker does not answer", "start Docker")]
    report = health.report(docker, {"docker": 50.0}, offered, streak, 60.0, rounds=3)
    assert report == {"resting": False, "until": None, "round": 3, "answers": 0,
                      "withheld": ["compose-v1", "docker", "isolated"],
                      "problems": [{"check": "docker", "message": "Docker does not answer",
                                    "fix": "start Docker", "since": 50.0}]}
    disk = [("disk", "1 GB free", "free space")]
    assert health.report(disk, {}, offered, streak, 60.0)["resting"] is True
    assert health.report([], {}, offered, streak, 60.0)["problems"] == []
