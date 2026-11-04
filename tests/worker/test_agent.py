"""The agent loop, one step() at a time: fake clock, fake link, real SubprocessExecutor."""

import time
from dataclasses import replace

import pytest

from mulebox.common.ids import new_id
from mulebox.common.package_cache import CAPABILITIES as PACKAGE_CACHES
from mulebox.common.protocol import MessageType
from mulebox.worker import workspace
from mulebox.worker.agent import HEARTBEAT_S, Agent
from mulebox.worker.executor import RunSpec, SubprocessExecutor, group_alive, unit_name

from mulebox.version import get_version

from .fakes import claim_body


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def executor():
    return SubprocessExecutor(grace_s=0.5)


@pytest.fixture
def agent(node, fake_link, executor, paths, clock):
    return Agent(node, fake_link, executor, paths, clock=clock)


def run_until(agent, done, limit=20.0):
    end = time.monotonic() + limit
    while not done():
        if time.monotonic() > end:
            raise AssertionError("condition not reached")
        agent.step()
        time.sleep(0.05)


def cleaned(agent, link):
    """Cleanup runs beside the loop: step until it is through. Nothing is claimed meanwhile."""
    run_until(agent, lambda: all(job.cleaned for job in agent.finishing))


def result_of(link):
    results = link.of_type(MessageType.RESULT)
    assert len(results) == 1
    return results[0].body


def submit(link, *argv, **kwargs):
    body = claim_body(argv, **kwargs)
    link.claims.append(body)
    return body["job_id"]


def test_passed_job(agent, fake_link, paths):
    job_id = submit(fake_link, "bash", "-c", "cat README.md; git log --format=%an; echo ok",
                    setup="echo setup", toolchain={})
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    result = result_of(fake_link)
    assert (result["outcome"], result["exit_code"]) == ("passed", 0)
    assert result["job_id"] == job_id and result["attempt_id"]
    assert fake_link.log_text() == "setup\nhello\nmulebox\nok\n"
    states = [m.body["state"] for m in fake_link.of_type(MessageType.JOB_UPDATE)]
    assert states == ["running", "cleaning"]
    kinds = [m.type for m in fake_link.sent if m.type is not MessageType.CLAIM]
    assert kinds.index(MessageType.JOB_UPDATE) < kinds.index(MessageType.LOG_CHUNK)
    assert kinds[-1] is MessageType.RESULT
    assert not (paths.jobs / "example-app" / job_id).exists()
    claim = fake_link.of_type(MessageType.CLAIM)[0].body
    assert claim == {"worker": "build-1", "capabilities": ["node", *PACKAGE_CACHES], "free_slots": 1,
                     "toolchains": {}, "version": get_version(),
                     "restarted": True}  # the first claim after a start


def test_failed_job_keeps_exit_code(agent, fake_link):
    submit(fake_link, "bash", "-c", "echo before; exit 3")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert (result_of(fake_link)["outcome"], result_of(fake_link)["exit_code"]) == ("failed", 3)


def test_failed_setup_fails_job(agent, fake_link):
    submit(fake_link, "bash", "-c", "echo never", setup="exit 5")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["exit_code"] == 5
    assert "never" not in fake_link.log_text()


def _running_pgid(agent, fake_link):
    run_until(agent, lambda: agent.active and next(iter(agent.active.values())).handle)
    job = next(iter(agent.active.values()))
    run_until(agent, lambda: "child" in fake_link.log_text())
    return job.handle.pgid


LONG = "(trap '' TERM; sleep 300) & echo child; trap '' TERM; sleep 300"


def test_timeout_leaves_no_processes(agent, fake_link, paths):
    job_id = submit(fake_link, "bash", "-c", LONG, timeout_min=0.02)
    pgid = _running_pgid(agent, fake_link)
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "timed_out"
    assert not group_alive(pgid)
    assert not (paths.jobs / "example-app" / job_id).exists()


def test_cancel_via_heartbeat_leaves_no_processes(agent, fake_link, clock, paths):
    job_id = submit(fake_link, "bash", "-c", LONG)
    pgid = _running_pgid(agent, fake_link)
    clock.now += HEARTBEAT_S - 1
    agent.step()
    assert not fake_link.of_type(MessageType.HEARTBEAT)
    clock.now += 2
    fake_link.cancel = True
    agent.step()
    beat = fake_link.of_type(MessageType.HEARTBEAT)[0].body
    assert beat["lease"] == "worker" and beat["job_id"] == job_id and beat["attempt_id"]
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "cancelled"
    assert not group_alive(pgid)
    assert not (paths.jobs / "example-app" / job_id).exists()


def test_heartbeats_keep_the_job_running(agent, fake_link, clock):
    submit(fake_link, "bash", "-c", "echo child; sleep 300")
    _running_pgid(agent, fake_link)
    for _ in range(10):  # ten heartbeat intervals of fake time, heartbeats answered
        clock.now += HEARTBEAT_S
        agent.step()
    assert len(fake_link.of_type(MessageType.HEARTBEAT)) == 10
    assert agent.active
    agent.shutdown()
    assert result_of(fake_link)["outcome"] == "interrupted"


def test_coordinator_unreachable_stops_cleans_and_reports_later(agent, fake_link, clock, paths):
    job_id = submit(fake_link, "bash", "-c", "echo child; sleep 300")
    pgid = _running_pgid(agent, fake_link)
    fake_link.down = True
    for _ in range(5):
        clock.now += 20
        agent.step()
    assert agent.active  # 100 s without a reply: keep running
    clock.now += 21
    agent.step()
    cleaned(agent, fake_link)
    assert not agent.active and not group_alive(pgid)
    assert not (paths.jobs / "example-app" / job_id).exists()
    assert not fake_link.of_type(MessageType.RESULT)
    clock.now += 1
    agent.step()  # still down: nothing claimed, nothing lost
    fake_link.down = False
    clock.now += 10
    agent.step()
    assert result_of(fake_link)["outcome"] == "interrupted"
    kinds = [m.type for m in fake_link.sent]
    assert kinds.index(MessageType.RESULT) > max(
        i for i, m in enumerate(fake_link.sent) if m.type is MessageType.JOB_UPDATE)
    assert [m.body["state"] for m in fake_link.of_type(MessageType.JOB_UPDATE)][-1] == "cleaning"
    assert kinds[-2:] == [MessageType.RESULT, MessageType.CLAIM]  # report first, then claim


def test_error_reply_to_result_counts_as_delivered(agent, fake_link):
    fake_link.refuse.add(MessageType.RESULT)
    submit(fake_link, "bash", "-c", "true")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert not agent.finishing


def test_coordinator_says_job_is_over(agent, fake_link, clock):
    submit(fake_link, "bash", "-c", "echo child; sleep 300")
    pgid = _running_pgid(agent, fake_link)
    fake_link.heartbeat_state = "finished"
    clock.now += 20
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "interrupted"
    assert not group_alive(pgid)


def test_missing_toolchain_fails_with_a_clear_log(agent, fake_link, paths):
    job_id = submit(fake_link, "bash", "-c", "true", toolchain={"node": "22.22.3"})
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert (result_of(fake_link)["outcome"], result_of(fake_link)["exit_code"]) == ("failed", None)
    assert "mulebox toolchain install node 22.22.3" in fake_link.log_text()
    assert not (paths.jobs / "example-app" / job_id).exists()


def test_refused_running_update_cancels_without_starting(agent, fake_link, executor):
    fake_link.refuse.add(MessageType.JOB_UPDATE)
    submit(fake_link, "bash", "-c", "touch /should/not/run")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "cancelled"
    assert executor.running == {}


def test_unsafe_project_name_fails(agent, fake_link):
    submit(fake_link, "true", project="../escape")
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "failed"


def test_unreachable_during_snapshot_fetch(agent, fake_link, paths):
    job_id = submit(fake_link, "true")
    original = fake_link.fetch_snapshot

    def fetch(jid, dest):
        fake_link.down = True
        original(jid, dest)

    fake_link.fetch_snapshot = fetch
    agent.step()
    cleaned(agent, fake_link)
    assert not (paths.jobs / "example-app" / job_id).exists()
    fake_link.down = False
    agent.step(agent.clock() + 10)
    assert result_of(fake_link)["outcome"] == "interrupted"


def test_recovery_removes_orphans_and_leftovers(agent, executor, paths, snapshot, tmp_path):
    leftover = new_id("job")
    workspace.prepare(paths, "example-app", leftover, snapshot)
    spec = RunSpec(unit_name(new_id("job")), ("sleep", "300"), tmp_path, {},
                   tmp_path / "orphan.log", 300)
    orphan = executor.start(spec)
    assert executor.list_orphans() == [spec.name]
    agent.recover()
    assert executor.list_orphans() == []
    assert not group_alive(orphan.pgid)
    assert not (paths.jobs / "example-app" / leftover).exists()


def test_the_claim_reports_the_compose_capability_itself(node, fake_link, executor, paths, clock):
    worker = Agent(replace(node, capabilities=("docker",)), fake_link, executor, paths, clock=clock)
    worker.step()
    assert fake_link.of_type(MessageType.CLAIM)[0].body["capabilities"][:2] == ["docker", "compose-v1"]


def test_job_env_of_the_node_reaches_the_job(node, fake_link, executor, paths, clock):
    worker = Agent(replace(node, job_env={"FROM_MACHINE": "yes"}), fake_link, executor, paths,
                   clock=clock)
    submit(fake_link, "bash", "-c", "echo got=$FROM_MACHINE")
    run_until(worker, lambda: fake_link.of_type(MessageType.RESULT))
    assert "got=yes" in fake_link.log_text()


def test_heartbeats_say_what_the_job_is_doing(agent, fake_link, clock):
    submit(fake_link, "bash", "-c", LONG)
    _running_pgid(agent, fake_link)
    clock.now += HEARTBEAT_S + 1
    agent.step()
    report = fake_link.of_type(MessageType.HEARTBEAT)[-1].body["activity"]
    assert set(report) == {"output_idle_s", "idle_s", "cpu_pct", "net_kib_s"}
    assert report["output_idle_s"] >= 0
    fake_link.cancel = True
    clock.now += HEARTBEAT_S + 1
    agent.step()


def test_output_moves_the_time_of_the_last_output(agent, fake_link, clock):
    job_id = submit(fake_link, "bash", "-c", f"echo hello; {LONG}")
    _running_pgid(agent, fake_link)
    job = agent.active[job_id]
    run_until(agent, lambda: job.last_output > 0 or "hello" in fake_link.log_text())
    assert job.last_output >= job.started_at
    fake_link.cancel = True
    clock.now += HEARTBEAT_S + 1
    agent.step()
