"""A compose job that does not end by itself, or cannot start. Setup: test_agent_compose.py."""

import json

from mulebox.common.protocol import MessageType
from mulebox.worker.agent import HEARTBEAT_S, Agent
from mulebox.worker.docker import Docker
from mulebox.worker.executor import SubprocessExecutor

from .fake_docker import ok
from .fakes import claim_body
from .test_agent_compose import (  # noqa: F401
    LONG,
    MODEL,
    add_resources,
    agent,
    assert_all_gone,
    clock,
    daemon,
    finished,
    result_of,
    run_until,
    started,
    stand_in,
    submit,
)


def test_cancelled(agent, fake_link, daemon, paths, clock):
    job_id = submit(fake_link, LONG)
    add_resources(daemon, job_id)
    run_until(agent, started(agent))
    fake_link.cancel = True
    clock.now += HEARTBEAT_S
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["outcome"] == "cancelled"
    assert_all_gone(daemon, paths, job_id)


def test_timed_out(agent, fake_link, daemon, paths):
    job_id = submit(fake_link, LONG, timeout_min=0.02)
    add_resources(daemon, job_id)
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["outcome"] == "timed_out"
    assert_all_gone(daemon, paths, job_id)


def test_interrupted_by_a_worker_stopping(agent, fake_link, daemon, paths):
    job_id = submit(fake_link, LONG)
    add_resources(daemon, job_id)
    run_until(agent, started(agent))
    agent.shutdown()
    assert result_of(fake_link)["outcome"] == "interrupted"
    assert_all_gone(daemon, paths, job_id)


def test_interrupted_when_the_coordinator_forgot_the_job(agent, fake_link, daemon, paths, clock):
    job_id = submit(fake_link, LONG)
    add_resources(daemon, job_id)
    run_until(agent, started(agent))
    fake_link.heartbeat_state = "finished"
    clock.now += HEARTBEAT_S
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["outcome"] == "interrupted"
    assert_all_gone(daemon, paths, job_id)


def test_a_failing_teardown_holds_the_result_and_the_slot(agent, fake_link, daemon, paths):
    job_id = submit(fake_link, "true")
    add_resources(daemon, job_id)
    daemon.fail_remove["containers"] = 12
    run_until(agent, lambda: agent.finishing)
    agent.step()
    assert not fake_link.of_type(MessageType.RESULT)
    assert paths.job_dir("example-app", job_id).exists()
    assert len(fake_link.of_type(MessageType.CLAIM)) <= 1
    daemon.fail_remove["containers"] = 0
    run_until(agent, finished(fake_link))
    assert_all_gone(daemon, paths, job_id)


def test_a_compose_file_docker_refuses_fails_the_job_with_the_reason(
        agent, fake_link, daemon, paths):
    import subprocess

    daemon.responses[("compose", "config")] = subprocess.CompletedProcess(
        [], 1, "", "yaml: line 3: could not find expected ':'")
    job_id = submit(fake_link, "touch never")
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["outcome"] == "failed"
    assert "could not find expected" in fake_link.log_text()
    assert not paths.job_dir("example-app", job_id).exists()


def test_a_refused_compose_file_says_why(agent, fake_link, daemon):
    model = json.loads(json.dumps(MODEL))
    model["services"]["api"]["network_mode"] = "host"
    daemon.responses[("compose", "config")] = ok(json.dumps(model))
    submit(fake_link, "true")
    run_until(agent, finished(fake_link))
    assert "network_mode: host" in fake_link.log_text()


def test_a_worker_without_docker_fails_clearly(node, fake_link, paths, clock, stand_in):
    agent = Agent(node, fake_link, SubprocessExecutor(grace_s=0.5), paths, clock=clock)
    submit(fake_link, "true")
    run_until(agent, finished(fake_link))
    assert "no Docker" in fake_link.log_text()


def test_a_job_without_compose_never_calls_docker(agent, fake_link, daemon):
    fake_link.claims.append(claim_body(["bash", "-c", "true"]))
    run_until(agent, finished(fake_link))
    assert daemon.calls == []
