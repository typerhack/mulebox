"""SubprocessExecutor: exit codes, timeout, stop, and no processes left behind."""

import time

import pytest

from mulebox.worker.executor import (
    ExecutorError,
    RunSpec,
    SubprocessExecutor,
    group_alive,
    unit_name,
)


def _spec(tmp_path, script, timeout_s=30.0, env=None):
    return RunSpec(name=unit_name("job-test"), argv=("bash", "-c", script), cwd=tmp_path,
                   env=env or {}, log_path=tmp_path / "out.log", timeout_s=timeout_s)


def _wait(executor, handle, limit=20.0):
    end = time.monotonic() + limit
    while time.monotonic() < end:
        code = executor.poll(handle)
        if code is not None:
            return code
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def _wait_for_file(path, limit=10.0):
    end = time.monotonic() + limit
    while not path.exists() or not path.read_text().strip():
        if time.monotonic() > end:
            raise AssertionError(f"{path} never appeared")
        time.sleep(0.02)
    return path.read_text().strip()


def test_exit_codes_and_output(tmp_path):
    ex = SubprocessExecutor()
    handle = ex.start(_spec(tmp_path, 'echo "out $MULEBOX_X"; echo err >&2; exit 3',
                            env={"MULEBOX_X": "1"}))
    assert _wait(ex, handle) == 3
    assert not ex.timed_out(handle)
    assert ex.running == {}
    assert (tmp_path / "out.log").read_text().splitlines() == ["out 1", "err"]


def test_a_job_does_not_get_the_service_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("MULEBOX_SERVICE", "launchd")  # set on the worker by its launchd plist
    ex = SubprocessExecutor()
    handle = ex.start(_spec(tmp_path, 'echo "[${MULEBOX_SERVICE-unset}]"'))
    assert _wait(ex, handle) == 0
    assert (tmp_path / "out.log").read_text() == "[unset]\n"


def test_signal_exit_code(tmp_path):
    ex = SubprocessExecutor()
    handle = ex.start(_spec(tmp_path, "kill -KILL $$"))
    assert _wait(ex, handle) == 137


def test_timeout_kills_whole_group_including_term_ignorers(tmp_path):
    ex = SubprocessExecutor(grace_s=0.5)
    script = (f"(trap '' TERM; sleep 300) & echo $! > {tmp_path}/child; "
              "trap '' TERM; sleep 300")
    handle = ex.start(_spec(tmp_path, script, timeout_s=0.5))
    _wait_for_file(tmp_path / "child")
    assert _wait(ex, handle) == 137
    assert ex.timed_out(handle)
    assert not group_alive(handle.pgid)


def test_stop_terminates_group(tmp_path):
    ex = SubprocessExecutor(grace_s=5)
    handle = ex.start(_spec(tmp_path, f"sleep 300 & echo $! > {tmp_path}/child; wait"))
    _wait_for_file(tmp_path / "child")
    assert ex.list_orphans() == [unit_name("job-test")]
    started = time.monotonic()
    ex.stop(handle)
    assert time.monotonic() - started < 4  # SIGTERM was enough
    assert not group_alive(handle.pgid)
    assert ex.poll(handle) == 143
    assert ex.list_orphans() == []


def test_leftover_background_processes_are_stopped_when_main_exits(tmp_path):
    ex = SubprocessExecutor(grace_s=1)
    handle = ex.start(_spec(tmp_path, f"sleep 300 & echo $! > {tmp_path}/child; exit 0"))
    assert _wait(ex, handle) == 0
    assert not group_alive(handle.pgid)


def test_kill_by_name_and_duplicate_start(tmp_path):
    ex = SubprocessExecutor(grace_s=1)
    handle = ex.start(_spec(tmp_path, "sleep 300"))
    with pytest.raises(ExecutorError, match="already running"):
        ex.start(_spec(tmp_path, "true"))
    ex.kill(unit_name("job-test"))
    assert not group_alive(handle.pgid)
    ex.kill("mulebox-job-unknown")  # no-op


def test_start_failure(tmp_path):
    spec = RunSpec(unit_name("job-x"), ("/nonexistent/binary",), tmp_path, {},
                   tmp_path / "out.log", 5)
    with pytest.raises(ExecutorError, match="cannot start"):
        SubprocessExecutor().start(spec)
