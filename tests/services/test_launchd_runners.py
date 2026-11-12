"""GitHub runners as launchd agents (services/launchd_runners.py), against a stand-in launchctl
and, for pause, real process groups of this machine."""

import plistlib
import subprocess
import time

import pytest

from mulebox.services.base import RUNNING, STOPPED, ServiceError
from mulebox.services.launchd_runners import runner_definition, runner_label

from .test_launchd import FakeLaunchd, services

NAME = "build-1-example-app"


class WithPid(FakeLaunchd):
    """`launchctl print` of a loaded agent also gives the pid of its first process."""

    def __init__(self, pid=None):
        super().__init__()
        self.pid = pid

    def __call__(self, argv):
        done = super().__call__(argv)
        if argv[1] == "print" and done.returncode == 0 and argv[2].count("/") == 2 \
                and self.pid is not None:
            done.stdout += f"\tpid = {self.pid}\n"
        return done


def process(own_group):
    proc = subprocess.Popen(["sleep", "30"], start_new_session=own_group)
    return proc


def state_of(pid):
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                          text=True).stdout.strip()


def test_the_definition_runs_run_sh_like_the_systemd_template(tmp_path):
    folder = tmp_path / ".mulebox" / "runners" / NAME
    plist = runner_definition(NAME, folder, "/usr/bin", tmp_path / "logs")
    assert plist["Label"] == "mulebox-runner-build-1-example-app"
    assert plist["ProgramArguments"] == [str(folder / "run.sh")]
    assert plist["WorkingDirectory"] == str(folder)
    assert plist["EnvironmentVariables"]["RUNNER_MANUALLY_TRAP_SIG"] == "1"
    assert plist["KeepAlive"] is True and plist["ThrottleInterval"] == 10
    assert plist["ExitTimeOut"] == 300 and plist["Nice"] == 5
    assert plist["StandardOutPath"] == str(tmp_path / "logs" / f"runner-{NAME}.log")


def test_start_state_restart_and_stop(tmp_path):
    fake = WithPid()
    manager = services(tmp_path, fake)
    manager.runner_check(tmp_path / "anywhere")  # any runners root will do on a Mac
    manager.runner_start(NAME, tmp_path / "runners" / NAME)
    written = tmp_path / "Library" / "LaunchAgents" / f"{runner_label(NAME)}.plist"
    assert plistlib.loads(written.read_bytes())["Label"] == runner_label(NAME)
    assert fake.labels() == {runner_label(NAME)}
    assert manager.runner_state(NAME) == RUNNING
    manager.runner_restart(NAME)
    assert ["launchctl", "kickstart", "-k", f"gui/501/{runner_label(NAME)}"] in fake.calls
    manager.runner_stop(NAME)
    assert manager.runner_state(NAME) == STOPPED and fake.loaded == set()
    assert f"gui/501/{runner_label(NAME)}" in fake.disabled
    assert written.is_file()  # disabled, not deleted: outside mulebox's roots
    manager.runner_start(NAME, tmp_path / "runners" / NAME)  # added again: enabled again
    assert manager.runner_state(NAME) == RUNNING


def test_a_bad_name_is_refused():
    with pytest.raises(ServiceError):
        runner_label("../evil")


def test_pause_stops_the_agents_own_group_and_resume_continues_it(tmp_path):
    proc = process(own_group=True)
    try:
        fake = WithPid(proc.pid)
        manager = services(tmp_path, fake)
        manager.runner_start(NAME, tmp_path / NAME)
        assert manager.runner_group(NAME) == proc.pid
        manager.runner_freeze(NAME, True)
        end = time.monotonic() + 5
        while not state_of(proc.pid).startswith("T"):
            assert time.monotonic() < end, "the group was not stopped"
            time.sleep(0.02)
        manager.runner_freeze(NAME, False)
        while state_of(proc.pid).startswith("T"):
            assert time.monotonic() < end, "the group was not continued"
            time.sleep(0.02)
        manager.runner_boost(NAME, True)  # nothing to raise without root; no error
    finally:
        proc.kill()
        proc.wait()


def test_a_first_process_that_leads_no_group_is_never_signalled_as_one(tmp_path):
    proc = process(own_group=False)  # in this test's own group
    try:
        manager = services(tmp_path, WithPid(proc.pid))
        manager.runner_start(NAME, tmp_path / NAME)
        assert manager.runner_group(NAME) is None
        with pytest.raises(ServiceError, match="not paused"):
            manager.runner_freeze(NAME, True)
        assert not state_of(proc.pid).startswith("T")
    finally:
        proc.kill()
        proc.wait()


def test_no_group_when_the_agent_is_not_running(tmp_path):
    manager = services(tmp_path, WithPid())
    assert manager.runner_group(NAME) is None
    assert manager.runner_group("../evil") is None
    manager.runner_freeze(NAME, False)  # nothing to continue: no error
