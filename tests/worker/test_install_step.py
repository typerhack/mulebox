"""An `install`: tried again when the network failed, once when the project did, in real bash."""

import subprocess

from mulebox.worker.install_step import TRIES, script_lines
from mulebox.worker.jobspec import build_script


def run(tmp_path, line):
    script = build_script(None, ["echo", "command ran"], install=line)
    script = script.replace("sleep $((try * 5))", "true")
    return subprocess.run(["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True)


def test_a_good_install_runs_once_and_the_job_goes_on(tmp_path):
    done = run(tmp_path, "echo x >> tries")
    assert done.returncode == 0 and "command ran" in done.stdout
    assert (tmp_path / "tries").read_text().count("x") == 1


def test_a_lost_network_is_tried_again_and_can_recover(tmp_path):
    line = 'echo x >> tries; [ "$(wc -l < tries)" -ge 2 ] || { echo "ECONNRESET reading"; exit 1; }'
    done = run(tmp_path, line)
    assert done.returncode == 0 and "command ran" in done.stdout
    assert "trying again" in done.stdout


def test_a_network_that_stays_gone_ends_the_job_with_the_install_s_code(tmp_path):
    done = run(tmp_path, 'echo x >> tries; echo "getaddrinfo ENOTFOUND registry"; exit 4')
    assert done.returncode == 4 and "command ran" not in done.stdout
    assert (tmp_path / "tries").read_text().count("x") == TRIES


def test_a_project_s_own_failure_is_not_tried_again(tmp_path):
    done = run(tmp_path, 'echo x >> tries; echo "lockfile out of date"; exit 2')
    assert done.returncode == 2 and "command ran" not in done.stdout
    assert (tmp_path / "tries").read_text().count("x") == 1


def test_a_failing_line_in_the_install_stops_it_as_in_a_job(tmp_path):
    assert run(tmp_path, "false\necho still here").returncode == 1


def test_quotes_in_the_line_arrive(tmp_path):
    assert script_lines("x")[-1] == "mulebox_install x"
    assert "it's" in run(tmp_path, """echo "it's" """).stdout
