"""A compose job through the agent, on every outcome.

The job's script really runs, under the subprocess executor, with a stand-in `docker` first
on PATH: it records what it was asked and prints what a test tells it to. The worker's own
Docker calls go to the fake daemon. Teardown is proved by what is left in that daemon.
"""

import json
import stat
import time

import pytest

from mulebox.common import compose
from mulebox.common.protocol import MessageType
from mulebox.worker.agent import Agent
from mulebox.worker.docker import Docker
from mulebox.worker.executor import SubprocessExecutor

from .fake_docker import FakeDocker, ok
from .fakes import claim_body

MODEL = {"name": "x", "services": {"api": {
    "image": "redis:7-alpine",
    "ports": [{"mode": "ingress", "target": 80, "published": "80", "protocol": "tcp"}]}},
    "networks": {"default": {"name": "x_default", "ipam": {}}}}
LONG = "echo running; sleep 300"


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def daemon():
    fake = FakeDocker()
    fake.responses[("compose", "config")] = ok(json.dumps(MODEL))
    return fake


@pytest.fixture
def stand_in(tmp_path, monkeypatch):
    """A `docker` command for the job's script. Writes its calls to a file."""
    folder = tmp_path / "stand-in"
    folder.mkdir()
    log = tmp_path / "docker-calls"
    script = folder / "docker"
    script.write_text(f"""#!/bin/sh
echo "$* | $COMPOSE_PROJECT_NAME | $COMPOSE_FILE | $APP_ENV" >> {log}
case "$*" in
  "compose up --no-start") [ -f {tmp_path}/pull-fails ] && cat {tmp_path}/pull-fails && exit 1 ;;
  "compose up --detach --wait") [ -f {tmp_path}/up-prints ] && cat {tmp_path}/up-prints
      [ -f {tmp_path}/up-fails ] && exit 9 ;;
  "compose logs"*) echo "container said password=hunter2hunter2" ;;
esac
exit 0
""")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{folder}:/usr/bin:/bin")
    return log


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def agent(node, fake_link, paths, clock, daemon, stand_in):
    return Agent(node, fake_link, SubprocessExecutor(grace_s=0.5), paths, clock=clock,
                 docker=Docker(daemon))


def submit(link, command, **kwargs):
    env = {compose.COMPOSE_FILES_KEY: "docker-compose.yml", "APP_ENV": "ci"}
    body = {**claim_body(["bash", "-c", command], **kwargs), "env": env}
    link.claims.append(body)
    return body["job_id"]


def add_resources(daemon, job_id):
    labels = {compose.LABEL_JOB: job_id, compose.LABEL_WORKER: "build-1",
              compose.LABEL_COMPOSE_PROJECT: compose.project_name(job_id)}
    for kind in ("containers", "networks", "volumes"):
        daemon.add_labelled(kind, f"{kind}-{job_id}", labels)
    daemon.add("containers", "their-postgres")
    daemon.add("volumes", "their-data")
    daemon.add("images", "redis-7")


FOREIGN = ["their-postgres", "their-data", "redis-7"]


def run_until(agent, done, limit=20.0):
    end = time.monotonic() + limit
    while not done():
        assert time.monotonic() < end, "condition not reached"
        agent.step()
        time.sleep(0.02)


def result_of(link):
    results = link.of_type(MessageType.RESULT)
    assert len(results) == 1
    return results[0].body


def finished(link):
    return lambda: bool(link.of_type(MessageType.RESULT))


def started(agent):
    return lambda: bool(agent.active) and all(j.handle for j in agent.active.values())


def assert_all_gone(daemon, paths, job_id):
    assert sorted(daemon.left()) == sorted(FOREIGN)
    assert not paths.job_dir("example-app", job_id).exists()


def test_passed(agent, fake_link, daemon, paths, stand_in):
    job_id = submit(fake_link, "echo the job")
    add_resources(daemon, job_id)
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["outcome"] == "passed"
    assert_all_gone(daemon, paths, job_id)
    assert not agent.ports._held


def test_containers_start_before_setup_and_the_job(agent, fake_link, stand_in):
    submit(fake_link, "docker compose exec -T api php artisan test",
           setup="docker compose exec -T api composer install")
    run_until(agent, finished(fake_link))
    calls = [line.split(" | ")[0] for line in stand_in.read_text().splitlines()]
    work = [c for c in calls if c.startswith("compose")]
    assert work == ["compose up --no-start", "compose up --detach --wait",
                    "compose exec -T api composer install",
                    "compose exec -T api php artisan test"]


def test_docker_compose_in_a_job_finds_its_project_and_the_env(
        agent, fake_link, stand_in, paths):
    job_id = submit(fake_link, "cd /tmp && docker compose exec -T api true")
    run_until(agent, finished(fake_link))
    line = next(x for x in stand_in.read_text().splitlines() if "exec" in x)
    args, project, file, app_env = line.split(" | ")
    assert project == compose.project_name(job_id)
    assert file == str(paths.job_dir("example-app", job_id) / "compose.mulebox.yml")
    assert app_env == "ci"


def test_ports_are_in_the_jobs_environment_and_log(agent, fake_link):
    submit(fake_link, "echo port=$MULEBOX_PORT_API_80")
    run_until(agent, finished(fake_link))
    text = fake_link.log_text()
    assert "is on 127.0.0.1:" in text and "$MULEBOX_PORT_API_80" in text
    number = text.split("port=")[1].split()[0]
    assert 20000 <= int(number) <= 29999


def test_failed_keeps_the_exit_code_and_shows_container_logs_redacted(
        agent, fake_link, daemon, paths):
    job_id = submit(fake_link, "exit 7")
    add_resources(daemon, job_id)
    run_until(agent, finished(fake_link))
    result = result_of(fake_link)
    assert (result["outcome"], result["exit_code"]) == ("failed", 7)
    text = fake_link.log_text()
    assert "last log lines of its containers" in text and "container said" in text
    assert "hunter2" not in text
    assert_all_gone(daemon, paths, job_id)


def test_passing_job_prints_no_container_logs(agent, fake_link):
    submit(fake_link, "true")
    run_until(agent, finished(fake_link))
    assert "container said" not in fake_link.log_text()


def test_compose_output_is_redacted(agent, fake_link, tmp_path):
    (tmp_path / "up-prints").write_text("Attaching with DB_PASSWORD=hunter2hunter2\n")
    submit(fake_link, "true")
    run_until(agent, finished(fake_link))
    assert "Attaching with" in fake_link.log_text()
    assert "hunter2" not in fake_link.log_text()


def test_up_failing_still_tears_down_and_the_job_never_runs(
        agent, fake_link, daemon, paths, tmp_path, stand_in):
    (tmp_path / "up-fails").write_text("")
    job_id = submit(fake_link, "docker compose exec -T api never")
    add_resources(daemon, job_id)
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["exit_code"] == 9
    assert "never" not in stand_in.read_text()
    assert_all_gone(daemon, paths, job_id)


def test_a_registry_out_of_reach_is_a_job_that_never_ran(
        agent, fake_link, daemon, paths, tmp_path, stand_in):
    (tmp_path / "pull-fails").write_text("Error: dial tcp 192.168.1.50:443: i/o timeout\n")
    job_id = submit(fake_link, "never")
    add_resources(daemon, job_id)
    run_until(agent, finished(fake_link))
    result = result_of(fake_link)
    assert result["outcome"] == "failed" and result["exit_code"] is None
    assert "could not start" in fake_link.log_text()
    assert_all_gone(daemon, paths, job_id)


def test_a_build_failing_in_the_images_stage_keeps_its_code(agent, fake_link, tmp_path):
    (tmp_path / "pull-fails").write_text("failed to solve: did not complete successfully\n")
    submit(fake_link, "never")
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["exit_code"] == 1


def test_setup_failing_still_tears_down(agent, fake_link, daemon, paths):
    job_id = submit(fake_link, "true", setup="exit 5")
    add_resources(daemon, job_id)
    run_until(agent, finished(fake_link))
    assert result_of(fake_link)["exit_code"] == 5
    assert_all_gone(daemon, paths, job_id)
