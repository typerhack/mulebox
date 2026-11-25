"""A node that rests, through the real agent loop (worker/agent_health.py): what it claims with,
and a job that could not start judged by the check that follows."""

from dataclasses import replace

import pytest

from mulebox.common import compose
from mulebox.common.errors import MuleboxError
from mulebox.common.protocol import MessageType
from mulebox.worker import health
from mulebox.worker.agent import Agent
from mulebox.worker.executor import SubprocessExecutor

from .fakes import claim_body
from .test_agent import Clock, cleaned, result_of, run_until


class Checks:
    """Stands in for health.run_all: what it finds, and how often it ran."""

    def __init__(self):
        self.found, self.runs = [], 0

    def __call__(self, *args, **kwargs):
        self.runs += 1
        return list(self.found)


@pytest.fixture
def checks(monkeypatch):
    found = Checks()
    monkeypatch.setattr(health, "run_all", found)
    return found


@pytest.fixture
def agent(node, fake_link, paths):
    return Agent(node, fake_link, SubprocessExecutor(grace_s=0.5), paths, clock=Clock())


def checked(agent, checks, runs):
    run_until(agent, lambda: checks.runs >= runs and agent._health_state()["task"] is None)


def last_claim(link):
    return link.of_type(MessageType.CLAIM)[-1].body


def test_a_resting_node_claims_with_no_free_slot(agent, fake_link, checks):
    checks.found = [("disk", "1 GB free", "free space")]
    checked(agent, checks, 1)
    agent.step()
    claim = last_claim(fake_link)
    assert claim["free_slots"] == 0 and claim["slots"] == 1
    assert claim["health"]["resting"] and claim["health"]["problems"][0]["check"] == "disk"
    assert claim["health"]["round"] >= 1
    # what the dashboard shows beside it: the checks run, when, and the floor
    assert "disk" in claim["health"]["ran"] and claim["health"]["checked_at"] is not None
    assert claim["health"]["min_free"] == 5_000_000_000


def test_a_withheld_capability_is_left_out_of_claims(node, fake_link, paths, checks):
    agent = Agent(replace(node, capabilities=("docker",)), fake_link,
                  SubprocessExecutor(grace_s=0.5), paths, clock=Clock())
    checks.found = [("docker", "Docker does not answer", "start Docker")]
    checked(agent, checks, 1)
    agent.step()
    claim = last_claim(fake_link)
    assert claim["free_slots"] == 1
    assert "docker" not in claim["capabilities"] and "compose-v1" not in claim["capabilities"]
    offered = compose.worker_capabilities(("docker",))
    docker_ones = {"compose-v1", "docker", "isolated"} & set(offered)  # isolated: Linux only
    assert claim["health"]["withheld"] == sorted(docker_ones)
    assert not docker_ones & set(claim["capabilities"])


def test_the_coordinator_can_ask_for_a_check(agent, fake_link, checks):
    checked(agent, checks, 1)
    agent._settings({"health_check": True})
    checked(agent, checks, 2)


def failing_start(agent, monkeypatch):
    def boom(*args, **kwargs):
        raise MuleboxError("the project folder could not be made")
    monkeypatch.setattr(agent, "_prepare", boom)


def test_a_start_failed_by_the_node_says_node_fault(agent, fake_link, checks, monkeypatch):
    checked(agent, checks, 1)
    failing_start(agent, monkeypatch)
    fake_link.claims.append(claim_body(["true"]))
    agent.step()
    assert agent.finishing and agent.finishing[0].judging
    checks.found = [("disk", "1 GB free", "free space")]  # the check after the failure
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    result = result_of(fake_link)
    assert result["exit_code"] is None
    assert result["node_fault"] == "build-1 could not set it up: 1 GB free"


def test_a_start_the_check_passes_is_the_job_s_own(agent, fake_link, checks, monkeypatch):
    checked(agent, checks, 1)
    failing_start(agent, monkeypatch)
    fake_link.claims.append(claim_body(["true"]))
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert "node_fault" not in result_of(fake_link)
    assert checks.runs >= 2  # it was judged by a check of its own


def test_a_job_that_starts_ends_a_streak(agent, fake_link, checks):
    checked(agent, checks, 1)
    agent._health_state()["streak"].trial = True
    fake_link.claims.append(claim_body(["true"]))
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    cleaned(agent, fake_link)
    assert not agent._health_state()["streak"].trial


def test_a_retried_job_continues_its_log(agent, fake_link, checks):
    body = claim_body(["echo", "again"])
    body["log_offset"] = 40
    fake_link.claims.append(body)
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    first = min(m.body["offset"] for m in fake_link.of_type(MessageType.LOG_CHUNK))
    assert first == 40


def test_the_first_check_runs_before_any_claim(agent, fake_link, checks):
    checks.found = [("git", "git does not run", "install git")]
    agent.check_now(agent.clock())
    assert not fake_link.sent and checks.runs == 1
    agent.step()
    assert last_claim(fake_link)["free_slots"] == 0 and checks.runs == 1  # not asked again yet


def test_machine_check_is_answered_by_a_check_started_after_the_ask(agent, fake_link, checks):
    checked(agent, checks, 1)
    agent._health_state()["asked"] = True  # a check of its own, already running
    agent.step()
    running = agent._health_state()["task"]
    agent._settings({"health_check": True})
    while not running.done:
        running.wait(1)
    agent.step()  # the running one ends: not the answer
    assert agent._health_report(0.0)["answers"] == 0
    run_until(agent, lambda: agent._health_report(0.0)["answers"] == 1)
