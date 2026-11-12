"""Supervision of runner reservations: process detection and release after a crash."""

import io
import os

import pytest

from mulebox.common.protocol import JobState, MessageType, Outcome
from mulebox.runners import hooks, reservation_file
from mulebox.runners.supervise import (GONE_S, SUPERVISE_S, Supervisor, runner_alive,
                                       runner_alive_ps)
from mulebox.worker.agent import Agent
from mulebox.worker.executor import SubprocessExecutor
from mulebox.worker.link import LinkError, request

from .conftest import RUNNER
from .helpers import Clock

T0 = 10_000.0


def fake_process(proc, pid, argv, cwd):
    entry = proc / str(pid)
    entry.mkdir(parents=True)
    (entry / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in argv) + b"\0")
    os.symlink(cwd, entry / "cwd")


@pytest.fixture
def proc(tmp_path):
    (tmp_path / "proc" / "self").mkdir(parents=True)  # not a pid: skipped
    return tmp_path / "proc"


def test_runner_alive_by_argv_or_cwd(proc, paths, tmp_path):
    folder = paths.runners / RUNNER
    folder.mkdir()
    other = paths.runners / "other-runner"
    assert runner_alive(folder, proc) is False
    fake_process(proc, 10, ["/usr/bin/bash", str(folder / "run.sh")], str(folder))  # not a worker
    fake_process(proc, 11, [str(other / "bin" / "Runner.Worker"), "spawnclient"], str(other))
    assert runner_alive(folder, proc) is False
    fake_process(proc, 12, [str(folder / "bin" / "Runner.Worker"), "spawnclient", "1", "2"],
                 "/")
    assert runner_alive(folder, proc) is True
    assert runner_alive(other, proc) is True


def test_runner_alive_by_cwd_only(proc, paths, tmp_path):
    folder = paths.runners / RUNNER
    (folder / "_work").mkdir(parents=True)
    fake_process(proc, 20, ["Runner.Worker", "spawnclient"], str(folder / "_work"))
    assert runner_alive(folder, proc) is True
    assert runner_alive(paths.runners / f"{RUNNER}-2", proc) is False  # not a prefix match


def test_runner_alive_without_proc(tmp_path):
    assert runner_alive(tmp_path, tmp_path / "no-proc") is False


class Alive:
    def __init__(self):
        self.value = True
        self.asked = []

    def __call__(self, folder):
        self.asked.append(folder)
        return self.value


def grant(gh_env, link, paths):
    clock = Clock()
    assert hooks.started(gh_env, "build-1", link, paths, clock=clock, sleep=clock.sleep,
                         out=io.StringIO()) == 0
    return reservation_file.read(paths, RUNNER)


def test_crashed_runner_is_released_after_60_s(gh_env, link, paths, store):
    job_id = grant(gh_env, link, paths)
    alive = Alive()
    supervisor = Supervisor("build-1", paths.runners, alive=alive)
    sent = []

    def send(msg):
        sent.append(msg.type)
        return link.call(msg)

    supervisor.tick(T0, send)
    assert alive.asked == [paths.runners / RUNNER]
    assert sent == [MessageType.RUNNER_JOBS, MessageType.HEARTBEAT]
    supervisor.tick(T0 + 5, send)  # not due yet
    assert len(sent) == 2
    alive.value = False  # the runner process vanished
    for now in (T0 + SUPERVISE_S, T0 + 2 * SUPERVISE_S, T0 + 6 * SUPERVISE_S):
        supervisor.tick(now, send)
        assert store.get_job(job_id)["state"] == JobState.RUNNING  # gone for < 60 s
    supervisor.tick(T0 + SUPERVISE_S + GONE_S, send)
    job = store.get_job(job_id)
    assert job["state"] == JobState.FINISHED and job["outcome"] == Outcome.INTERRUPTED
    assert sent[-1] is MessageType.RELEASE and supervisor.missing == {}
    supervisor.tick(T0 + 200, send)  # nothing left to watch
    assert sent[-1] is MessageType.RUNNER_JOBS


def test_runner_seen_again_resets_the_wait(gh_env, link, paths, store):
    job_id = grant(gh_env, link, paths)
    alive = Alive()
    supervisor = Supervisor("build-1", paths.runners, alive=alive)
    alive.value = False
    supervisor.tick(T0, link.call)
    alive.value = True  # e.g. between two steps of the job
    supervisor.tick(T0 + 30, link.call)
    alive.value = False
    supervisor.tick(T0 + 70, link.call)  # gone again, but only for 0 s
    assert store.get_job(job_id)["state"] == JobState.RUNNING


def test_heartbeats_keep_the_worker_lease(gh_env, link, paths, store):
    job_id = grant(gh_env, link, paths)
    before = store.get_job(job_id)["worker_lease_until"]
    supervisor = Supervisor("build-1", paths.runners, alive=lambda folder: True)
    supervisor.tick(T0, link.call)
    assert store.get_job(job_id)["worker_lease_until"] >= before


def test_queued_reservation_of_a_dead_runner_is_released(link, paths, store):
    reply = link.call(request(MessageType.RESERVE, worker="build-1",
                              repository="example-org/example-app", job="test",
                              run_id="77", run_attempt="1", runner=RUNNER))
    supervisor = Supervisor("build-1", paths.runners, alive=lambda folder: False)
    supervisor.tick(T0, link.call)
    supervisor.tick(T0 + GONE_S, link.call)
    job = store.get_job(reply.body["job_id"])
    assert job["state"] == JobState.FINISHED and job["outcome"] == Outcome.INTERRUPTED


def test_agent_step_runs_supervision(node, paths):
    class Link:
        def __init__(self):
            self.sent = []

        def call(self, msg):
            self.sent.append(msg.type)
            raise LinkError("unreachable (test)")

    link = Link()
    supervisor = Supervisor("build-1", paths.runners, alive=lambda folder: True)
    agent = Agent(node, link, SubprocessExecutor(), paths, clock=lambda: T0,
                  supervisor=supervisor)
    agent.step()  # the link error is absorbed; the agent backs off
    assert link.sent == [MessageType.RUNNER_JOBS]
    assert supervisor.next_at == T0 + SUPERVISE_S


def test_a_released_slot_gets_its_runner_log_read_to_the_end(gh_env, link, paths, store):
    job_id = grant(gh_env, link, paths)
    diag = paths.runners / RUNNER / "_diag"
    diag.mkdir(parents=True)
    diary = diag / "Worker_20261107-100431-utc.log"
    diary.write_text("[x INFO StepsRunner] Processing step: DisplayName='Tests'\n")
    supervisor = Supervisor("build-1", paths.runners, alive=lambda folder: True)
    supervisor.tick(T0, link.call)  # starts following the slot
    with open(diary, "a") as fh:
        fh.write("[x INFO StepsRunner] Processing step: DisplayName='Last step'\n")
    link.call(request(MessageType.RELEASE, job_id=job_id, outcome="passed"))
    supervisor.next_follow = T0 + 10 * SUPERVISE_S  # no regular read before the round
    supervisor.tick(T0 + SUPERVISE_S, link.call)
    assert supervisor.logs == {}
    assert link.staging.log_path(job_id).read_text() == (
        "mulebox: step: Tests\nmulebox: step: Last step\n")


def test_a_heartbeat_carries_the_runner_jobs_cpu_and_step(gh_env, link, paths, store):
    from mulebox.runners.runner_meter import RunnerMeter
    job_id = grant(gh_env, link, paths)
    diag = paths.runners / RUNNER / "_diag"
    diag.mkdir(parents=True)
    (diag / "Worker_20261107-100431-utc.log").write_text(
        "[x INFO StepsRunner] Processing step: DisplayName='Run pnpm check'\n")
    used = iter([{"runner": 5.0}, {"runner": 25.0}])
    supervisor = Supervisor("build-1", paths.runners, alive=lambda folder: True,
                            meter=RunnerMeter(read=lambda runner: next(used)))
    supervisor.tick(T0, link.call)
    supervisor.tick(T0 + SUPERVISE_S, link.call)
    activity = store.get_job(job_id)["activity"]
    assert activity == {"job_cpu_pct": 200.0, "step": "Run pnpm check"}


def test_runner_alive_on_a_mac_reads_the_arguments_from_ps(paths):
    folder = paths.runners / RUNNER
    worker = f"{folder}/bin/Runner.Worker spawnclient 115 118"
    assert runner_alive_ps(folder, lambda: ["/sbin/launchd", worker]) is True
    assert runner_alive_ps(paths.runners / f"{RUNNER}-2", lambda: [worker]) is False
    assert runner_alive_ps(folder, lambda: [f"{folder}/bin/Runner.Listener run"]) is False
    assert runner_alive_ps(folder, lambda: None) is False  # seen as nothing, as without /proc
    assert runner_alive_ps(folder, lambda: [f"tail -f {folder}/bin/Runner.Worker"]) is False
    assert runner_alive_ps(folder, lambda: [f"{folder}/bin/Runner.WorkerX"]) is False


def test_runner_alive_on_a_mac_with_a_space_in_the_folder(tmp_path):
    folder = tmp_path / "Mac HD" / "runners" / "app-1"
    assert runner_alive_ps(folder, lambda: [f"  {folder}/bin/Runner.Worker spawnclient 1 2"])
