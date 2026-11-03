"""The runner hooks end to end against a real Store, with an injected clock and sleep."""

import io

import pytest

from mulebox import cli
from mulebox.common.protocol import JobState, MessageType, Outcome
from mulebox.coordinator import store as st
from mulebox.runners import hooks, reservation_file
from mulebox.worker.link import LinkError, request

from .conftest import RUNNER
from .helpers import Clock, agent_job, finish_agent_job


def started(gh_env, link, paths, clock=None, **env):
    clock = clock or Clock()
    out = io.StringIO()
    code = hooks.started({**gh_env, **env}, "build-1", link, paths, clock=clock,
                         sleep=clock.sleep, out=out)
    return code, out.getvalue()


def test_started_then_completed(gh_env, link, paths, store):
    code, out = started(gh_env, link, paths)
    assert code == 0 and "build slot granted" in out
    job_id = reservation_file.read(paths, RUNNER)
    job = store.get_job(job_id)
    assert job["state"] == JobState.RUNNING and job["kind"] == "runner"
    assert job["project"] == "example-org__example-app" and job["branch"] == "main"
    assert job["run_url"] == "https://github.com/example-org/example-app/actions/runs/4242"
    assert (paths.runners / RUNNER / ".mulebox-reservation").read_text() == job_id + "\n"
    again, _ = started(gh_env, link, paths)  # a retried hook finds the same reservation
    assert again == 0 and reservation_file.read(paths, RUNNER) == job_id
    out = io.StringIO()
    assert hooks.completed({**gh_env, "GITHUB_JOB_STATUS": "success"}, link, paths,
                           out=out) == 0
    assert store.get_job(job_id)["outcome"] == Outcome.PASSED
    assert not (paths.runners / RUNNER / ".mulebox-reservation").exists()
    assert "released" in out.getvalue()


def test_started_waits_behind_agent_job(gh_env, link, paths, store, local):
    busy = agent_job(link, *local)

    def free_after_a_while(clock):
        if clock.sleeps == 40:  # 80 s of waiting
            finish_agent_job(link, busy)

    clock = Clock(on_sleep=free_after_a_while)
    code, out = started(gh_env, link, paths, clock)
    assert code == 0 and clock.sleeps == 40
    notices = [line for line in out.splitlines() if "waiting for a build slot" in line]
    assert notices == ["mulebox: waiting for a build slot (position 1)"] * 3  # 0, 30, 60 s
    assert store.get_job(reservation_file.read(paths, RUNNER))["state"] == JobState.RUNNING


def test_started_gives_up_after_timeout(gh_env, link, paths, store, local):
    agent_job(link, *local)
    clock = Clock()
    code, out = started(gh_env, link, paths, clock, MULEBOX_HOOK_TIMEOUT_MIN="1")
    assert code == 1 and "gave up waiting for a build slot after 1 minutes" in out
    assert clock.now - 500.0 == pytest.approx(60.0, abs=2.0)
    assert reservation_file.read(paths, RUNNER) is None
    (job,) = _reservations(store)
    assert job["state"] == JobState.FINISHED and job["outcome"] == Outcome.CANCELLED


def test_started_retries_when_the_link_fails(gh_env, link, paths):
    class Flaky:
        failures = 3

        def call(self, msg):
            if self.failures:
                self.failures -= 1
                raise LinkError("unreachable (test)")
            return link.call(msg)

    clock = Clock()
    code, _ = started(gh_env, Flaky(), paths, clock)
    assert code == 0 and clock.sleeps == 3


@pytest.mark.parametrize("env,message", [
    ({"RUNNER_NAME": ""}, "RUNNER_NAME"),
    ({"RUNNER_NAME": "../escape"}, "not a safe folder name"),
    ({"MULEBOX_HOOK_TIMEOUT_MIN": "soon"}, "must be a number"),
])
def test_started_refuses_bad_environment(gh_env, link, paths, env, message):
    code, out = started(gh_env, link, paths, **env)
    assert code == 1 and message in out


def test_started_fails_when_the_reservation_was_cancelled(gh_env, link, paths, store, local):
    agent_job(link, *local)

    def cancel_it(clock):
        job_id = reservation_file.read(paths, RUNNER)
        reply = link.call(request(MessageType.CANCEL, job_id=job_id))  # `mulebox cancel`
        assert reply.body["state"] == "finished"

    code, out = started(gh_env, link, paths, Clock(on_sleep=cancel_it))
    assert code == 1 and "ended (cancelled)" in out


@pytest.mark.parametrize("status,outcome", [
    ("failure", Outcome.FAILED), ("cancelled", Outcome.CANCELLED), (None, Outcome.PASSED),
])
def test_completed_maps_job_status(gh_env, link, paths, store, status, outcome):
    started(gh_env, link, paths)
    job_id = reservation_file.read(paths, RUNNER)
    env = dict(gh_env) if status is None else {**gh_env, "GITHUB_JOB_STATUS": status}
    assert hooks.completed(env, link, paths, out=io.StringIO()) == 0
    assert store.get_job(job_id)["outcome"] == outcome


def test_completed_without_reservation_or_coordinator(gh_env, link, paths, store):
    out = io.StringIO()
    assert hooks.completed(gh_env, link, paths, out=out) == 0
    assert "no build slot reservation" in out.getvalue()
    started(gh_env, link, paths)

    class Down:
        def call(self, msg):
            raise LinkError("unreachable (test)")

    assert hooks.completed(gh_env, Down(), paths, out=io.StringIO()) == 0
    assert reservation_file.read(paths, RUNNER) is None  # removed anyway


def test_cli_runner_hook(gh_env, node, store, monkeypatch, tmp_path, capsys):
    config = tmp_path / "node.toml"
    roots = "\n".join(f'{key} = "{value}"' for key, value in node.roots.items())
    config.write_text(f'name = "build-1"\nroles = ["coordinator", "worker"]\n'
                      f"[roots]\n{roots}\n", encoding="utf-8")
    for key, value in gh_env.items():
        monkeypatch.setenv(key, value)
    assert cli.main(["runner-hook", "started", "--config", str(config)]) == 0
    assert "build slot granted" in capsys.readouterr().out
    assert cli.main(["runner-hook", "completed", "--config", str(config)]) == 0
    assert [j["state"] for j in _reservations(store)] == ["finished"]
    missing = str(tmp_path / "missing.toml")
    assert cli.main(["runner-hook", "started", "--config", missing]) == 1
    assert cli.main(["runner-hook", "completed", "--config", missing]) == 0


def _reservations(store):
    with store.read() as conn:
        return st.select_jobs(conn, "kind = 'runner'")
