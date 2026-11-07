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
    in_file_order,
    port_references,
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


def test_port_references_finds_only_ports():
    env = {"A": "${MULEBOX_PORT_API_80}/${MULEBOX_JOB_ID}", "B": "plain"}
    assert port_references(env) == ["MULEBOX_PORT_API_80"]


def test_lines_from_the_worker_run_before_setup():
    assert build_script("setup", ["job"], ("first",)) == (
        'set -e\nfirst\nmulebox_dir="$PWD"\nsetup\ncd -- "$mulebox_dir"\njob\n')


def test_extra_cannot_be_changed_by_project_env():
    env = build_env("job-1", [], base_path="/bin", extra={"COMPOSE_FILE": "/mine"},
                    project_env={"COMPOSE_FILE": "/theirs", "URL": "x:${COMPOSE_FILE}"})
    assert env["COMPOSE_FILE"] == "/mine" and env["URL"] == "x:/theirs"


def test_script_layout():
    assert build_script("pnpm install", ["pnpm", "check"]) == (
        'set -e\nmulebox_dir="$PWD"\npnpm install\ncd -- "$mulebox_dir"\npnpm check\n')
    assert build_script("  ", ["a b"]) == "set -e\n'a b'\n"


@pytest.mark.parametrize("argv", [[], "pnpm check", ["a", 1], ["a\0b"]])
def test_bad_argv(argv):
    with pytest.raises(JobSpecError):
        build_script(None, argv)


def test_env(tmp_path):
    env = build_env("job-1", [tmp_path / "a" / "bin", tmp_path / "b" / "bin"], "/usr/bin")
    assert env == {"MULEBOX": "1", "MULEBOX_JOB_ID": "job-1", "MULEBOX_JOB_SLUG": "job_1",
                   "PATH": f"{tmp_path}/a/bin:{tmp_path}/b/bin:/usr/bin"}
    assert "HOME" not in env


def test_timeout_seconds():
    assert timeout_seconds(20) == 1200.0
    for bad in (0, -1, True, "20", 10_000):
        with pytest.raises(JobSpecError):
            timeout_seconds(bad)


def test_project_env_expands_mulebox_and_earlier_values():
    env = build_env("job-01ABC", [], "/usr/bin",
                    {"DB": "app_ci_${MULEBOX_JOB_SLUG}", "URL": "mongodb://localhost/${DB}"})
    assert env["DB"] == "app_ci_job_01abc"
    assert env["URL"] == "mongodb://localhost/app_ci_job_01abc"
    assert env["MULEBOX_JOB_ID"] == "job-01ABC"


def test_project_env_is_not_a_shell():
    env = build_env("job-1", [], "/usr/bin", {"X": "$(touch pwned) `id` $HOME"})
    assert env["X"] == "$(touch pwned) `id` $HOME"  # only ${NAME} is replaced


def test_project_env_unknown_reference_fails():
    with pytest.raises(JobSpecError, match="NOPE"):
        build_env("job-1", [], "/usr/bin", {"X": "${NOPE}"})


def test_job_env_cannot_move_a_path_the_worker_set():
    env = build_env("job-1", [], base_path="/bin", extra={"COMPOSER_CACHE_DIR": "/cache/mine"},
                    machine_env={"COMPOSER_CACHE_DIR": "/elsewhere"})
    assert env["COMPOSER_CACHE_DIR"] == "/cache/mine"


def test_file_order_comes_back_from_sorted_json():
    arrived = {"A_URL": "${Z_HOST}:1", "Z_HOST": "db"}  # sorted, as JSON brings it
    assert list(in_file_order(arrived, ["Z_HOST", "A_URL"])) == ["Z_HOST", "A_URL"]
    env = build_env("job-1", [], base_path="/bin",
                    project_env=in_file_order(arrived, ["Z_HOST", "A_URL"]))
    assert env["A_URL"] == "db:1"


def test_a_later_name_stays_unknown_without_the_order():
    with pytest.raises(JobSpecError, match="earlier env entry"):
        build_env("job-1", [], base_path="/bin",
                  project_env=in_file_order({"A_URL": "${Z_HOST}", "Z_HOST": "db"}))


def test_names_the_order_lacks_go_last():
    assert list(in_file_order({"A": "1", "B": "2", "C": "3"}, ["C", "GONE"])) == ["C", "A", "B"]


def test_a_cd_in_setup_stays_there_and_what_it_exports_reaches_the_command(tmp_path):
    import subprocess
    (tmp_path / "web").mkdir()
    script = build_script("cd web && export FROM_SETUP=yes", ["bash", "-c", 'echo "$PWD $FROM_SETUP"'])
    out = subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True,
                         check=True).stdout
    assert out == f"{tmp_path} yes\n"
