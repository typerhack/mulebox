"""SystemdExecutor with a fake runner: exact argv, parsing, unit-name safety. No systemd."""

import subprocess
from pathlib import Path

import pytest

from mulebox.worker.executor import ExecutorError, RunSpec
from mulebox.worker.systemd import SystemdExecutor, exit_from_props, parse_show, run_argv

UNIT = "mulebox-job-01JC3XAMPLE0000000000000000"


def _spec(**changes):
    base = dict(name=UNIT, argv=("bash", "-c", "set -e\necho 'a b'\n"),
                cwd=Path("/home/alice/.mulebox/jobs/example-app/x/src"),
                env={"MULEBOX": "1", "PATH": "/opt/node/bin:/usr/bin", "ODD": "a b;$(x)"},
                log_path=Path("/home/alice/.mulebox/jobs/example-app/x/out.log"), timeout_s=1200)
    base.update(changes)
    return RunSpec(**base)


def test_run_argv_is_exact():
    assert run_argv(_spec()) == [
        "systemd-run", "--user", f"--unit={UNIT}",
        "--property=RuntimeMaxSec=1200",
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=10s",
        "--property=CPUWeight=50",
        "--property=IOWeight=50",
        "--property=StandardOutput=append:/home/alice/.mulebox/jobs/example-app/x/out.log",
        "--property=StandardError=append:/home/alice/.mulebox/jobs/example-app/x/out.log",
        "--working-directory=/home/alice/.mulebox/jobs/example-app/x/src",
        "--setenv=MULEBOX=1",
        "--setenv=PATH=/opt/node/bin:/usr/bin",
        "--setenv=ODD=a b;$(x)",
        "--", "bash", "-c", "set -e\necho 'a b'\n",
    ]


def test_a_script_reaches_bash_as_written():
    """systemd would expand `${x}` in the command line and turn `$$` into `$`; each `$` doubled
    comes back as one. The environment is not expanded, so it stays as it is."""
    script = 'x=1; echo "${x} ${y:-z} $$ $HOME"\n'
    argv = run_argv(_spec(argv=("bash", "-c", script)))
    assert argv[-1] == 'x=1; echo "$${x} $${y:-z} $$$$ $$HOME"\n'
    assert argv[-1].replace("$$", "$") == script
    assert "--setenv=ODD=a b;$(x)" in argv


def test_runtime_rounds_up():
    assert "--property=RuntimeMaxSec=2" in run_argv(_spec(timeout_s=1.2))


@pytest.mark.parametrize("changes", [
    {"name": "sshd"}, {"name": "mulebox-job-x.service; rm"}, {"env": {"A=B": "1"}},
    {"env": {"A": "x\0y"}}, {"log_path": Path("/tmp/a b/out.log")},
])
def test_run_argv_refuses(changes):
    with pytest.raises(ExecutorError):
        run_argv(_spec(**changes))


def test_parse_show():
    assert parse_show("ActiveState=failed\nResult=timeout\nnoise\nX=a=b\n") == {
        "ActiveState": "failed", "Result": "timeout", "X": "a=b"}


@pytest.mark.parametrize("text,expected", [
    ("LoadState=loaded\nActiveState=active\nSubState=running", (None, False)),
    ("LoadState=loaded\nActiveState=deactivating", (None, False)),
    ("LoadState=not-found\nActiveState=inactive", (0, False)),
    ("LoadState=loaded\nActiveState=inactive\nResult=success", (0, False)),
    ("ActiveState=failed\nResult=exit-code\nExecMainCode=1\nExecMainStatus=2", (2, False)),
    ("ActiveState=failed\nResult=timeout\nExecMainCode=2\nExecMainStatus=15", (143, True)),
    ("ActiveState=failed\nResult=signal\nExecMainCode=2\nExecMainStatus=9", (137, False)),
    ("ActiveState=failed\nResult=resources\nExecMainCode=0\nExecMainStatus=0", (1, False)),
    ("ActiveState=failed\nResult=exit-code\nExecMainStatus=", (1, False)),
])
def test_exit_from_props(text, expected):
    assert exit_from_props(parse_show(text)) == expected


class FakeRunner:
    def __init__(self, replies=None):
        self.calls = []
        self.replies = list(replies or [])

    def __call__(self, argv):
        self.calls.append(list(argv))
        out, code = self.replies.pop(0) if self.replies else ("", 0)
        return subprocess.CompletedProcess(argv, code, out, "boom" if code else "")


def test_start_poll_and_reset_failed():
    runner = FakeRunner([("", 0), ("ActiveState=active\n", 0),
                         ("ActiveState=failed\nResult=timeout\nExecMainCode=2\nExecMainStatus=15\n", 0),
                         ("", 0)])
    ex = SystemdExecutor(runner)
    handle = ex.start(_spec())
    assert runner.calls[0][0] == "systemd-run"
    assert ex.poll(handle) is None
    assert runner.calls[1][:4] == ["systemctl", "--user", "show", UNIT]
    assert ex.poll(handle) == 143 and ex.timed_out(handle)
    assert runner.calls[3] == ["systemctl", "--user", "reset-failed", UNIT]
    assert ex.poll(handle) == 143 and len(runner.calls) == 4  # cached


def test_start_failure():
    with pytest.raises(ExecutorError, match="systemd-run failed"):
        SystemdExecutor(FakeRunner([("", 1)])).start(_spec())


def test_stop_and_kill():
    runner = FakeRunner()
    ex = SystemdExecutor(runner)
    handle = ex.start(_spec())
    ex.stop(handle)
    assert runner.calls[1:] == [["systemctl", "--user", "stop", UNIT],
                                ["systemctl", "--user", "reset-failed", UNIT]]
    assert ex.poll(handle) == 143
    with pytest.raises(ExecutorError):
        ex.kill("ssh.service")


def test_list_orphans_only_returns_mulebox_units():
    listing = (
        f"{UNIT}.service loaded active running mulebox job\n"
        "● mulebox-job-01JC3XAMPLE0000000000000001.service loaded failed failed x\n"
        "mulebox-job-bad;name.service loaded active running x\n"
        "sshd.service loaded active running OpenSSH\n"
        "mulebox-coordinator.service loaded active running x\n\n"
    )
    runner = FakeRunner([(listing, 0)])
    assert SystemdExecutor(runner).list_orphans() == [
        UNIT, "mulebox-job-01JC3XAMPLE0000000000000001"]
    assert runner.calls[0][-1] == "mulebox-job-*"


def test_a_job_without_a_limit_has_no_runtime_limit(tmp_path):
    spec = RunSpec(name="mulebox-job-a", argv=("true",), cwd=tmp_path, env={},
                   log_path=tmp_path / "out.log", timeout_s=None)
    assert not any("RuntimeMaxSec" in arg for arg in run_argv(spec))


def test_freeze_and_weight_of_a_job_unit():
    runner = FakeRunner()
    ex = SystemdExecutor(runner)
    handle = ex.start(_spec())
    ex.freeze(handle, True)
    ex.freeze(handle, False)
    ex.prioritize(handle, True)
    ex.prioritize(handle, False)
    assert runner.calls[1:] == [
        ["systemctl", "--user", "freeze", UNIT], ["systemctl", "--user", "thaw", UNIT],
        ["systemctl", "--user", "set-property", "--runtime", UNIT, "CPUWeight=10000",
         "IOWeight=10000"],
        ["systemctl", "--user", "set-property", "--runtime", UNIT, "CPUWeight=50", "IOWeight=50"]]
