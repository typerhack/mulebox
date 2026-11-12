"""The guard as the hook's first step: it finds its runner itself and fails closed."""

import io
import json

import pytest

from mulebox import cli
from mulebox.runners import guard, layout


@pytest.fixture
def runner(tmp_path):
    folder = tmp_path / "runners" / "build-1-example-app"
    (folder / layout.HOOKS_DIR).mkdir(parents=True)
    (folder / ".runner").write_text("{}")
    (folder / layout.META_FILE).write_text(json.dumps({"repo": "a/b", "actors": ["alice"]}))
    return folder


@pytest.fixture
def env(tmp_path, runner):
    event = tmp_path / "event.json"
    event.write_text('{"ref": "refs/heads/main"}')
    return {"GITHUB_EVENT_PATH": str(event), "GITHUB_ACTOR": "alice",
            "ACTIONS_RUNNER_HOOK_JOB_STARTED": str(runner / layout.HOOKS_DIR / "started.sh")}


def admit(env, cwd=None, killed=(4321,)):
    calls, held, out = [], [], io.StringIO()
    ok = guard.admit(env, out, cwd=cwd, stop=lambda f, m: calls.append(f) or list(killed),
                     wait=lambda: held.append(True))
    return ok, calls, held, out.getvalue()


def test_an_allowed_job_goes_on_untouched(env, runner):
    assert admit(env)[:3] == (True, [], [])


def test_a_refused_job_has_its_runner_process_killed(env, runner):
    ok, calls, held, out = admit({**env, "GITHUB_ACTOR": "mallory"})
    assert not ok and calls == [runner] and not held
    assert "refuses a run started by mallory" in out and "none of its steps runs" in out


def test_a_refused_job_with_no_process_found_is_held(env, runner):
    ok, calls, held, out = admit({**env, "GITHUB_ACTOR": "mallory"}, killed=())
    assert not ok and held == [True] and "holding the job" in out


def test_the_runner_is_found_from_the_working_directory_too(env, runner):
    work = runner / "_work" / "b" / "b"
    work.mkdir(parents=True)
    no_hook_path = {k: v for k, v in env.items() if k != "ACTIONS_RUNNER_HOOK_JOB_STARTED"}
    assert guard.hook_folder(no_hook_path, cwd=str(work)) == runner
    assert admit(no_hook_path, cwd=str(work))[0]


def test_a_hook_that_cannot_tell_its_runner_refuses(env, tmp_path):
    lost = {**env, "ACTIONS_RUNNER_HOOK_JOB_STARTED": str(tmp_path / "x" / "started.sh")}
    ok, calls, _, out = admit(lost, cwd=str(tmp_path))
    assert not ok and calls == [None] and "cannot tell which runner" in out


def test_missing_metadata_refuses(env, runner):
    (runner / layout.META_FILE).unlink()
    ok, _, _, out = admit(env)
    assert not ok and "missing or cannot be read" in out


def test_the_cli_runs_the_guard_before_reading_any_config(env, monkeypatch, tmp_path, capsys):
    killed = []
    monkeypatch.setattr(guard, "kill_workers", lambda folder, m: killed.append(m) or [1])
    for name, value in {**env, "GITHUB_ACTOR": "mallory"}.items():
        monkeypatch.setenv(name, value)
    missing = tmp_path / "no-such-node.toml"
    assert cli.main(["runner-hook", "started", "--config", str(missing)]) == 1
    assert len(killed) == 1 and "refuses a run started by mallory" in capsys.readouterr().out
    assert "refuses a run started by mallory" in killed[0]  # also on the job process's stderr


def test_hold_ends_when_the_job_s_process_is_gone(monkeypatch):
    parents = iter([20, 20, 20, 1])  # reparented to init once Runner.Worker is gone
    monkeypatch.setattr(guard.os, "getppid", lambda: next(parents))
    naps = []
    monkeypatch.setattr(guard.time, "sleep", naps.append)
    guard.hold(poll_s=0.5)
    assert naps == [0.5, 0.5]
