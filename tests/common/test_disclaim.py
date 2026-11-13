"""A Mac service starts ssh as its own responsible process; nothing changes elsewhere."""

import subprocess
import sys
import time

import pytest

from mulebox.common import disclaim, ssh

on_mac = pytest.mark.skipif(sys.platform != "darwin", reason="responsibility is macOS only")
SERVICE = {"MULEBOX_SERVICE": "launchd"}


def test_only_a_mac_service_disclaims():
    assert disclaim.prefix("darwin", SERVICE)[1:] == ["-m", "mulebox.common.disclaim"]
    assert disclaim.prefix("darwin", {}) == []  # the dev machine's own commands
    assert disclaim.prefix("linux", SERVICE) == []


def test_ssh_argv_starts_with_the_prefix(monkeypatch):
    monkeypatch.setattr(disclaim, "prefix", lambda: ["py", "-m", "mulebox.common.disclaim"])
    argv = ssh.ssh_base_argv("build-1")
    assert argv[:4] == ["py", "-m", "mulebox.common.disclaim", ssh.SSH_BINARY]
    assert argv[-1] == "build-1"


def _helper(*argv):
    return [sys.executable, "-m", "mulebox.common.disclaim", *argv]


@on_mac
def test_exit_code_and_output_come_through():
    done = subprocess.run(_helper("sh", "-c", "read x; echo got $x; echo err >&2; exit 3"),
                          input="in\n", capture_output=True, text=True, timeout=20)
    assert (done.returncode, done.stdout, done.stderr) == (3, "got in\n", "err\n")


@on_mac
def test_a_missing_program_reads_as_ssh_failing():
    done = subprocess.run(_helper("/no/such/program"), capture_output=True, text=True, timeout=20)
    assert done.returncode == 255 and "cannot start /no/such/program" in done.stderr


@on_mac
def test_sigterm_reaches_the_program():
    proc = subprocess.Popen(_helper("sh", "-c", "trap 'exit 7' TERM; while :; do sleep 0.1; done"))
    time.sleep(1.0)  # the shell has set its trap
    proc.terminate()
    assert proc.wait(timeout=20) == 7
