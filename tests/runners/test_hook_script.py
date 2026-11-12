"""The started hook script, run by sh for real: it fails closed when mulebox fails."""

import shutil
import subprocess
import time

import pytest

from mulebox.runners import layout


@pytest.fixture
def script(tmp_path):
    def make(code):
        home = tmp_path / "home"
        (home / ".mulebox" / "bin").mkdir(parents=True, exist_ok=True)
        fake = home / ".mulebox" / "bin" / "mulebox"
        fake.write_text(f"#!/bin/sh\nexit {code}\n")
        fake.chmod(0o755)
        path = tmp_path / "started.sh"
        path.write_text(layout.STARTED_SCRIPT)
        return path, {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    return make


def test_an_admitted_job_goes_on(script):
    path, env = script(0)
    assert subprocess.run(["/bin/sh", str(path)], env=env, timeout=10).returncode == 0


def test_a_failure_kills_a_parent_that_is_the_runner_s_worker(script, tmp_path):
    path, env = script(1)
    worker = tmp_path / "bin" / "Runner.Worker"  # a shell under the runner's process name
    worker.parent.mkdir()
    shutil.copy("/bin/sh", worker)
    parent = subprocess.Popen([str(worker), "-c", f"/bin/sh {path}; sleep 30"], env=env)
    assert parent.wait(timeout=10) == -9  # killed before its next step


def test_a_failure_under_an_unknown_parent_waits_it_out(script):
    """Not sure the parent is the job's: the script holds while it lives, then ends."""
    path, env = script(1)
    parent = subprocess.Popen(["/bin/sh", "-c", f"/bin/sh {path} & echo $!; sleep 3"], env=env,
                              stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    time.sleep(1)
    assert _alive(child)  # held while its parent lives
    parent.wait(timeout=10)
    deadline = time.monotonic() + 10
    while _alive(child) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not _alive(child)  # and gone with it


def _alive(pid):
    proc = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return proc.returncode == 0 and not proc.stdout.strip().startswith("Z")
