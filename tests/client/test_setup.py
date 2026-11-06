"""`mulebox setup`: each step stops with what to do, and a job is never stopped by accident."""

import pytest

from mulebox.client import setup
from mulebox.common import ssh
from mulebox.common.config import load_client_config


def test_a_failed_login_says_what_to_do(monkeypatch):
    def refuse(*args, **kwargs):
        raise ssh.SSHUnavailable("Permission denied")

    monkeypatch.setattr(setup.ssh, "run_remote", refuse)
    with pytest.raises(setup.SetupError, match="ssh-copy-id build-1"):
        setup.check_login("build-1")


@pytest.mark.parametrize("target", ["-oProxyCommand=x", "-", "bad host", ""])
def test_a_bad_target_is_refused_before_any_ssh(target, monkeypatch):
    monkeypatch.setattr(setup.ssh.subprocess, "Popen", None)
    with pytest.raises(setup.SetupError):
        setup.check_login(target)


def test_running_jobs_stop_an_upgrade(monkeypatch):
    done = []
    monkeypatch.setattr(setup, "check_login", lambda target: None)
    monkeypatch.setattr(setup, "running_jobs", lambda target: ["job-1"])
    monkeypatch.setattr(setup, "install", done.append)
    with pytest.raises(setup.SetupError, match="--now"):
        setup.run("build-1", lambda line: None)
    assert done == []


def test_now_goes_ahead_and_every_step_runs_in_order(monkeypatch):
    done = []
    monkeypatch.setattr(setup, "check_login", lambda target: done.append("login"))
    monkeypatch.setattr(setup, "running_jobs", lambda target: ["job-1"])
    monkeypatch.setattr(setup, "install", lambda target: done.append("install"))
    monkeypatch.setattr(setup, "find_offers", lambda target, say: done.append("offers"))
    monkeypatch.setattr(setup, "write_client_config", lambda t, say: done.append("config"))
    monkeypatch.setattr(setup, "prove", lambda target, say: done.append("prove"))
    setup.run("build-1", lambda line: None, now=True)
    assert done == ["login", "install", "offers", "config", "prove"]


def test_a_machine_without_mulebox_has_no_jobs(monkeypatch):
    def absent(self, msg):
        raise ssh.SSHUnavailable("no route")

    monkeypatch.setattr(setup.Remote, "call", absent)
    assert setup.running_jobs("build-1") == []


def test_the_client_config_is_written_once(tmp_path, monkeypatch):
    path = tmp_path / "config" / "client.toml"
    monkeypatch.setenv("MULEBOX_CONFIG", str(path))
    setup.write_client_config("build-1", lambda line: None)
    assert load_client_config(path).coordinator == "build-1"
    said = []
    setup.write_client_config("build-2", said.append)
    assert load_client_config(path).coordinator == "build-1"
    assert "build-2" in said[0]


def test_docker_advice(monkeypatch):
    said = []
    reply = type("R", (), {"stdout": b'{"docker":"no-access","added":[],"capabilities":[]}'})
    monkeypatch.setattr(setup.ssh, "run_remote", lambda *a, **k: reply)
    setup.find_offers("build-1", said.append)
    assert "plain jobs" in said[0] and "usermod" in said[1]


def test_the_command_gives_advice_not_a_traceback(monkeypatch, capsys):
    from mulebox import cli

    def refuse(*args, **kwargs):
        raise ssh.SSHUnavailable("Permission denied")

    monkeypatch.setattr(setup.ssh, "run_remote", refuse)
    assert cli.main(["setup", "build-1"]) == 1
    err = capsys.readouterr().err
    assert "ssh-copy-id" in err and "Traceback" not in err


def test_a_later_step_failing_is_still_advice(monkeypatch):
    def broken(target):
        raise OSError("connection reset")

    monkeypatch.setattr(setup, "check_login", lambda target: None)
    monkeypatch.setattr(setup, "running_jobs", lambda target: [])
    monkeypatch.setattr(setup, "install", broken)
    with pytest.raises(setup.SetupError, match="run it again"):
        setup.run("build-1", lambda line: None)
