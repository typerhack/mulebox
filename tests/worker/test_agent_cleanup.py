"""A cleanup that hangs on Docker must not stop the worker's loop. Docker here is a fake."""

import threading
import time
from dataclasses import replace

import pytest

from mulebox.common import compose
from mulebox.common.protocol import MessageType
from mulebox.worker import agent as agent_module
from mulebox.worker import background, compose_job
from mulebox.worker.agent import HEARTBEAT_S, Agent
from mulebox.worker.docker import Docker, DockerError
from mulebox.worker.executor import SubprocessExecutor

from .fake_docker import FakeDocker, ok
from .fakes import claim_body

MODEL = '{"name": "x", "services": {"api": {"image": "redis:7-alpine"}}}'


class HangingDocker(FakeDocker):
    """Answers until `hang` is set, then every listing blocks until `release`, as a stuck
    daemon does until the call's timeout."""

    def __init__(self):
        super().__init__()
        self.responses[("compose", "config")] = ok(MODEL)
        self.hang = threading.Event()
        self.release = threading.Event()
        self.blocked = threading.Event()
        self.calls_while_hung = 0

    def __call__(self, argv, env, cwd, timeout_s):
        if self.hang.is_set():
            self.calls_while_hung += 1
            self.blocked.set()
            assert self.release.wait(30), "the test never released the daemon"
        return super().__call__(argv, env, cwd, timeout_s)


class Clock:
    now = 1_000_000.0

    def __call__(self):
        return self.now


class Supervisor:
    def __init__(self):
        self.ticks = 0

    def tick(self, now, send):
        self.ticks += 1


@pytest.fixture
def daemon():
    fake = HangingDocker()
    yield fake
    fake.release.set()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def supervisor():
    return Supervisor()


@pytest.fixture
def agent(node, fake_link, paths, clock, daemon, supervisor):
    worker = Agent(replace(node, slots=2), fake_link, SubprocessExecutor(grace_s=0.5), paths,
                   clock=clock, docker=Docker(daemon), supervisor=supervisor)
    yield worker
    daemon.release.set()
    for job in worker.active.values():
        if job.handle:
            worker.executor.stop(job.handle)


def submit(link, command, uses_docker=False):
    body = claim_body(["bash", "-c", command])
    if uses_docker:
        body["env"] = {compose.COMPOSE_FILES_KEY: "docker-compose.yml"}
    link.claims.append(body)
    return body["job_id"]


def run_until(agent, done, limit=20.0):
    end = time.monotonic() + limit
    while not done():
        assert time.monotonic() < end, "condition not reached"
        agent.step()
        time.sleep(0.02)


def heartbeats_of(link, job_id):
    return [m for m in link.of_type(MessageType.HEARTBEAT) if m.body["job_id"] == job_id]


def job_stuck_in_cleanup(agent, link, daemon, tmp_path):
    """One compose job that ended and hangs in cleanup, and one plain job still running."""
    ending = submit(link, "true", uses_docker=True)
    agent._claim(agent.clock())
    running = submit(link, "sleep 300")
    agent._claim(agent.clock())
    daemon.hang.set()
    run_until(agent, lambda: daemon.blocked.is_set())
    return ending, running


@pytest.fixture
def docker_stand_in(tmp_path, monkeypatch):
    folder = tmp_path / "stand-in"
    folder.mkdir()
    script = folder / "docker"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{folder}:/usr/bin:/bin")


def test_a_hung_cleanup_leaves_the_other_jobs_lease_alone(
        agent, fake_link, daemon, clock, tmp_path, docker_stand_in):
    _, running = job_stuck_in_cleanup(agent, fake_link, daemon, tmp_path)
    for _ in range(50):  # 150 s of fake time, past the 120 s lease
        clock.now += HEARTBEAT_S
        started = time.monotonic()
        agent.step()
        assert time.monotonic() - started < 2.0
    assert len(heartbeats_of(fake_link, running)) == 50
    assert running in agent.active
    assert not fake_link.of_type(MessageType.RESULT)


def test_a_cancel_gets_through_during_a_hung_cleanup(
        agent, fake_link, daemon, clock, tmp_path, docker_stand_in):
    _, running = job_stuck_in_cleanup(agent, fake_link, daemon, tmp_path)
    fake_link.cancel = True
    clock.now += HEARTBEAT_S
    agent.step()
    assert running not in agent.active
    run_until(agent, lambda: [m for m in fake_link.of_type(MessageType.RESULT)
                              if m.body["job_id"] == running])
    daemon.release.set()
    run_until(agent, lambda: len(fake_link.of_type(MessageType.RESULT)) == 2)


def test_supervision_goes_on_during_a_hung_cleanup(
        agent, fake_link, daemon, clock, supervisor, tmp_path, docker_stand_in):
    job_stuck_in_cleanup(agent, fake_link, daemon, tmp_path)
    before = supervisor.ticks
    for _ in range(5):
        agent.step()
    assert supervisor.ticks == before + 5


def test_the_cleaning_job_keeps_its_own_lease(
        agent, fake_link, daemon, clock, tmp_path, docker_stand_in):
    ending, _ = job_stuck_in_cleanup(agent, fake_link, daemon, tmp_path)
    fake_link.sent.clear()
    clock.now += HEARTBEAT_S
    agent.step()
    assert len(heartbeats_of(fake_link, ending)) == 1


def test_no_new_job_is_claimed_during_a_hung_cleanup(
        agent, fake_link, daemon, tmp_path, docker_stand_in):
    job_stuck_in_cleanup(agent, fake_link, daemon, tmp_path)
    fake_link.sent.clear()
    for _ in range(3):
        agent.step()
    assert not fake_link.of_type(MessageType.CLAIM)


def test_only_one_cleanup_runs_for_a_job(agent, fake_link, daemon, tmp_path, docker_stand_in):
    job_stuck_in_cleanup(agent, fake_link, daemon, tmp_path)
    task = agent.finishing[0].cleanup
    for _ in range(5):
        agent.step()
    assert agent.finishing[0].cleanup is task
    assert daemon.calls_while_hung == 1


def test_a_failed_cleanup_is_tried_again_and_holds_the_result(
        agent, fake_link, daemon, tmp_path, docker_stand_in):
    daemon.fail_remove["containers"] = 100
    job_id = submit(fake_link, "true", uses_docker=True)
    agent._claim(agent.clock())
    daemon.add_labelled("containers", "c1", {compose.LABEL_JOB: job_id})
    run_until(agent, lambda: agent.finishing and daemon.fail_remove["containers"] < 90)
    assert not fake_link.of_type(MessageType.RESULT)
    daemon.fail_remove["containers"] = 0
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert daemon.left() == []


def test_shutdown_waits_for_a_cleanup_and_reports(
        agent, fake_link, daemon, tmp_path, docker_stand_in):
    submit(fake_link, "sleep 300", uses_docker=True)
    agent._claim(agent.clock())
    daemon.hang.set()
    timer = threading.Timer(0.3, daemon.release.set)
    timer.start()
    agent.shutdown()
    timer.join()
    assert fake_link.of_type(MessageType.RESULT)[0].body["outcome"] == "interrupted"


def test_shutdown_gives_up_on_a_cleanup_that_never_ends(
        agent, fake_link, daemon, monkeypatch, tmp_path, docker_stand_in):
    monkeypatch.setattr(agent_module, "SHUTDOWN_WAIT_S", 0.1)
    submit(fake_link, "sleep 300", uses_docker=True)
    agent._claim(agent.clock())
    daemon.hang.set()
    started = time.monotonic()
    agent.shutdown()
    assert time.monotonic() - started < 5
    assert not fake_link.of_type(MessageType.RESULT)  # the next start finds it by label


def test_a_task_reports_any_exception():
    task = background.start_thread(lambda: (_ for _ in ()).throw(ValueError("boom")))
    assert task.wait(5) and isinstance(task.error, ValueError)


def test_compose_config_stays_inside_a_lease_even_when_it_times_out():
    assert 2 * compose_job.CONFIG_TIMEOUT_S < agent_module.LEASE_S


def test_a_docker_failure_in_a_task_is_kept():
    def fails():
        raise DockerError("stuck")

    task = background.start_thread(fails)
    assert task.wait(5) and "stuck" in str(task.error)
