"""The agent loop, one step() at a time: fake clock, fake link, real SubprocessExecutor."""

import threading
import time
from dataclasses import replace

import pytest

from mulebox.common.ids import new_id
from mulebox.common.package_cache import CAPABILITIES as PACKAGE_CACHES
from mulebox.common.protocol import MessageType
from mulebox.worker import workspace
from mulebox.worker.agent import FINISHING_POLL_S, HEARTBEAT_S, POLL_S, Agent
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
    log = fake_link.log_text().splitlines()
    assert "1 files" not in log[0] and log[0].startswith("mulebox: project folder ")
    assert log[1:] == ["setup", "hello", "mulebox", "mulebox", "ok"]  # with the empty first commit
    states = [m.body["state"] for m in fake_link.of_type(MessageType.JOB_UPDATE)]
    assert states == ["running", "cleaning"]
    kinds = [m.type for m in fake_link.sent if m.type is not MessageType.CLAIM]
    assert kinds.index(MessageType.JOB_UPDATE) < kinds.index(MessageType.LOG_CHUNK)
    assert kinds[-1] is MessageType.RESULT
    assert not (paths.jobs / "example-app" / job_id).exists()
    claim = fake_link.of_type(MessageType.CLAIM)[0].body
    assert claim.pop("disk_free") > 0
    assert set(claim.pop("load")) == {"cpu_pct", "cores", "mem_pct", "net_in_kib_s",
                                      "net_out_kib_s"}  # null where no /proc
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


def fake_install(paths, name, version):
    (paths.toolchains_dir() / name / version / "bin").mkdir(parents=True)
    tool = paths.toolchains_dir() / name / version / "bin" / name
    tool.write_text("#!/bin/sh\necho fake $1\n")
    tool.chmod(0o755)


def test_a_toolchain_that_cannot_install_fails_with_a_clear_log(agent, fake_link, paths):
    def no_route(paths, name, version):
        raise OSError("no route to nodejs.org")

    agent.install_toolchain = no_route
    job_id = submit(fake_link, "bash", "-c", "true", toolchain={"node": "22.22.3"})
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert (result_of(fake_link)["outcome"], result_of(fake_link)["exit_code"]) == ("failed", None)
    log = fake_link.log_text()
    assert "no route to nodejs.org" in log and "mulebox toolchain install node 22.22.3" in log
    assert not (paths.jobs / "example-app" / job_id).exists()


def test_a_missing_toolchain_installs_itself_and_the_job_runs(agent, fake_link):
    agent.install_toolchain = fake_install
    submit(fake_link, "node", "ran", toolchain={"node": "22.22.3"})
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    assert result_of(fake_link)["outcome"] == "passed"
    log = fake_link.log_text()
    assert "installing node 22.22.3" in log and "fake ran" in log


def test_a_job_waiting_for_its_toolchain_can_be_cancelled(agent, fake_link):
    release = threading.Event()
    agent.install_toolchain = lambda *args: release.wait(10)
    submit(fake_link, "bash", "-c", "true", toolchain={"node": "22.22.3"})
    agent.step(1000.0)
    assert agent.active
    fake_link.cancel = True
    run_until(agent, lambda: fake_link.of_type(MessageType.RESULT))
    release.set()
    assert result_of(fake_link)["outcome"] == "cancelled"


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
    workspace.job_dir(paths, "example-app", leftover)
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
    assert set(report) == {"output_idle_s", "idle_s", "job_cpu_pct", "cpu_pct", "net_kib_s",
                           "last_line"}
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


def test_a_worker_back_after_the_coordinator_finished_its_job_leaves_nothing(
        agent, fake_link, clock, paths):
    """What the coordinator answers then: the job is over, and it refuses further reports."""
    job_id = submit(fake_link, "bash", "-c", LONG)
    pgid = _running_pgid(agent, fake_link)
    project = agent.active[job_id].project
    fake_link.heartbeat_state, fake_link.cancel = "finished", True
    fake_link.refuse |= {MessageType.LOG_CHUNK, MessageType.STEPS, MessageType.JOB_UPDATE,
                         MessageType.RESULT}
    clock.now += HEARTBEAT_S + 1
    run_until(agent, lambda: not agent.active and not agent.finishing)
    assert not group_alive(pgid)
    assert not paths.job_dir(project, job_id).exists()
    assert not agent.ports._held


def run_job(agent, link, *argv, **kwargs):
    count = len(link.of_type(MessageType.RESULT))
    submit(link, *argv, **{"toolchain": {}, **kwargs})
    run_until(agent, lambda: len(link.of_type(MessageType.RESULT)) > count)
    return link.of_type(MessageType.RESULT)[-1].body


SETUP = "echo x > ignored.txt"


def test_a_setup_runs_once_and_what_git_ignores_stays(agent, fake_link, ignored_snapshot):
    first = run_job(agent, fake_link, "bash", "-c", "cat ignored.txt", setup=SETUP)
    second = run_job(agent, fake_link, "bash", "-c", "cat ignored.txt", setup=SETUP)
    assert (first["outcome"], second["outcome"]) == ("passed", "passed")
    assert fake_link.log_text().count("setup skipped") == 1


def test_a_setup_runs_again_if_what_it_made_was_not_ignored(agent, fake_link):
    first = run_job(agent, fake_link, "bash", "-c", "cat made.txt", setup="echo x > made.txt")
    second = run_job(agent, fake_link, "bash", "-c", "cat made.txt", setup="echo x > made.txt")
    assert (first["outcome"], second["outcome"]) == ("passed", "passed")
    assert "setup skipped" not in fake_link.log_text()


def test_a_failed_setup_runs_again(agent, fake_link):
    run_job(agent, fake_link, "true", setup="exit 3")
    run_job(agent, fake_link, "true", setup="exit 3")
    assert "setup skipped" not in fake_link.log_text()


def test_a_failed_check_after_a_good_setup_keeps_the_setup(agent, fake_link):
    run_job(agent, fake_link, "false", setup="true")
    run_job(agent, fake_link, "true", setup="true")
    assert fake_link.log_text().count("setup skipped") == 1


def test_the_job_folder_goes_and_the_project_stays(agent, fake_link, paths):
    run_job(agent, fake_link, "true", branch="main")
    run_until(agent, lambda: not agent.finishing)
    assert not list((paths.jobs / "example-app").iterdir())
    assert list((paths.projects / "example-app" / "trees").iterdir())


def test_a_finishing_job_is_not_kept_waiting(agent, fake_link):
    assert agent.wait_s() == POLL_S
    agent.finishing.append(object())
    assert agent.wait_s() == FINISHING_POLL_S
    agent.finishing.clear()


def test_a_finishing_job_holds_its_slot_and_no_more(agent, fake_link):
    agent.node = replace(agent.node, slots=2)
    assert agent._free_slots() == 2
    agent.finishing.append(object())
    assert agent._free_slots() == 1
    agent.finishing.clear()


INSTALL = "echo x > ignored.txt"


def test_an_install_runs_once_and_is_counted_apart(agent, fake_link, ignored_snapshot):
    first = run_job(agent, fake_link, "bash", "-c", "cat ignored.txt", install=INSTALL)
    second = run_job(agent, fake_link, "bash", "-c", "cat ignored.txt", install=INSTALL)
    assert (first["outcome"], second["outcome"]) == ("passed", "passed")
    assert fake_link.log_text().count("install skipped") == 1


def test_a_failed_install_is_not_a_failed_check_and_runs_again(agent, fake_link):
    first = run_job(agent, fake_link, "true", install="exit 3")
    assert first["outcome"] == "failed" and first["exit_code"] is None
    assert "the project's `install` failed" in fake_link.log_text()
    run_job(agent, fake_link, "true", install="exit 3")
    assert "install skipped" not in fake_link.log_text()


def test_a_failed_check_after_a_good_install_keeps_the_install(agent, fake_link, ignored_snapshot):
    run_job(agent, fake_link, "false", install="true")
    third = run_job(agent, fake_link, "true", install="true")
    assert third["outcome"] == "passed" and fake_link.log_text().count("install skipped") == 1
