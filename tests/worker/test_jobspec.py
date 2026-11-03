"""The job script: set -e, setup line, then the job argv quoted so it arrives unchanged."""

import json
import subprocess
import sys

import pytest

from mulebox.worker.jobspec import (
    JobSpecError,
    build_argv,
    build_env,
    build_script,
    timeout_seconds,
)

NASTY = ["two words", "it's", '"double"', "$(touch PWNED)", "`touch PWNED`", "a;b", "*",
         "-n", "", "line\nbreak", "back\\slash", "$HOME", "~"]


def test_argv_arrives_unchanged(tmp_path):
    argv = [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", *NASTY]
    proc = subprocess.run(list(build_argv(None, argv)), cwd=tmp_path, capture_output=True,
                          text=True, check=True)
    assert json.loads(proc.stdout) == NASTY
    assert not (tmp_path / "PWNED").exists()


def test_named_job_runs_its_command(tmp_path):
    argv = build_argv("echo setup > s.txt", ["bash", "-c", "cat s.txt; echo 'job ran'"])
    proc = subprocess.run(list(argv), cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0
    assert proc.stdout == "setup\njob ran\n"


def test_failed_setup_stops_the_script(tmp_path):
    argv = build_argv("false", ["bash", "-c", "touch ran"])
    assert subprocess.run(list(argv), cwd=tmp_path).returncode == 1
    assert not (tmp_path / "ran").exists()


def test_job_exit_code_is_kept(tmp_path):
    assert subprocess.run(list(build_argv(None, ["bash", "-c", "exit 7"])), cwd=tmp_path).returncode == 7


def test_script_layout():
    assert build_script("pnpm install", ["pnpm", "check"]) == "set -e\npnpm install\npnpm check\n"
    assert build_script("  ", ["a b"]) == "set -e\n'a b'\n"


@pytest.mark.parametrize("argv", [[], "pnpm check", ["a", 1], ["a\0b"]])
def test_bad_argv(argv):
    with pytest.raises(JobSpecError):
        build_script(None, argv)


def test_env(tmp_path):
    env = build_env("job-1", [tmp_path / "a" / "bin", tmp_path / "b" / "bin"], "/usr/bin")
    assert env == {"MULEBOX": "1", "MULEBOX_JOB_ID": "job-1",
                   "PATH": f"{tmp_path}/a/bin:{tmp_path}/b/bin:/usr/bin"}
    assert "HOME" not in env


def test_timeout_seconds():
    assert timeout_seconds(20) == 1200.0
    for bad in (0, -1, True, "20", 10_000):
        with pytest.raises(JobSpecError):
            timeout_seconds(bad)
