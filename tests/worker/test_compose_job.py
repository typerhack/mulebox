"""Preparing a compose job against a fake Docker: env, the generated file, ports, the script."""

import json
import os
import subprocess

import pytest

from mulebox.common import compose
from mulebox.common.compose import ComposeError
from mulebox.common.ids import new_id
from mulebox.worker import compose_job, jobspec, ports
from mulebox.worker.docker import Docker
from mulebox.worker.ports import PortPool

from .fake_docker import FakeDocker, ok

MODEL = {
    "name": "ignored",
    "services": {
        "api": {"image": "redis:7-alpine", "container_name": "fixed",
                "ports": [{"mode": "ingress", "target": 8000, "published": "8000",
                           "protocol": "tcp"}]},
        "db": {"image": "redis:7-alpine"},
    },
    "networks": {"default": {"name": "x_default", "ipam": {}}},
}


@pytest.fixture
def daemon():
    fake = FakeDocker()
    fake.responses[("compose", "config")] = ok(json.dumps(MODEL))
    return fake


@pytest.fixture
def job(tmp_path):
    src = tmp_path / "job" / "src"
    src.mkdir(parents=True)
    return new_id("job"), src


def prepare(daemon, job, env=None, files="docker-compose.yml:docker-compose.ci.yml", pool=None):
    job_id, src = job
    env = env or {}
    pool = pool or PortPool(free=lambda port: True, pick=lambda low, high: 24000)

    def build(extra):
        return jobspec.build_env(job_id, [], base_path="/bin", project_env=env, extra=extra)

    return compose_job.prepare(Docker(daemon), pool, job_id, "build-1", files, src, env, build)


def test_compose_gets_all_files_the_project_name_and_the_project_env(daemon, job):
    job_id, src = job
    prepare(daemon, job, env={"APP_ENV": "ci"})
    env = daemon.envs[0]
    assert env["COMPOSE_FILE"] == "docker-compose.yml:docker-compose.ci.yml"
    assert env["COMPOSE_PROJECT_NAME"] == compose.project_name(job_id)
    assert env["APP_ENV"] == "ci" and env["MULEBOX_JOB_ID"] == job_id


def test_the_job_is_pointed_at_the_generated_file_outside_the_checkout(daemon, job):
    job_id, src = job
    ready = prepare(daemon, job)
    generated = src.parent / compose_job.GENERATED_FILE
    assert ready.extra_env["COMPOSE_FILE"] == str(generated)
    assert ready.extra_env["COMPOSE_PROJECT_NAME"] == compose.project_name(job_id)
    data = json.loads(generated.read_text())
    assert data["name"] == compose.project_name(job_id)
    assert data["services"]["api"]["labels"] == {
        compose.LABEL_JOB: job_id, compose.LABEL_WORKER: "build-1"}


def test_ports_reach_the_job_and_compose(daemon, job):
    ready = prepare(daemon, job)
    assert ready.extra_env["MULEBOX_PORT_API_8000"] == "24000"
    assert daemon.envs[1]["MULEBOX_PORT_API_8000"] == "24000"
    generated = job[1].parent / compose_job.GENERATED_FILE
    entry = json.loads(generated.read_text())["services"]["api"]["ports"][0]
    assert entry["published"] == "24000" and entry["host_ip"] == "127.0.0.1"
    assert any("127.0.0.1:24000" in note and "$MULEBOX_PORT_API_8000" in note
               for note in ready.notes)


def test_env_can_use_a_port_it_only_learns_after_the_first_pass(daemon, job):
    env = {"APP_URL": "http://127.0.0.1:${MULEBOX_PORT_API_8000}"}
    prepare(daemon, job, env=env)
    assert daemon.envs[0]["APP_URL"] == "http://127.0.0.1:0"
    assert daemon.envs[1]["APP_URL"] == "http://127.0.0.1:24000"


def test_a_mistyped_port_says_which_ports_exist(daemon, job):
    with pytest.raises(jobspec.JobSpecError, match="MULEBOX_PORT_API_8000"):
        prepare(daemon, job, env={"APP_URL": "${MULEBOX_PORT_WEB_80}"})


def test_uid_and_gid_are_there_for_user_lines_in_compose_files(daemon, job):
    env = prepare(daemon, job).extra_env
    assert env["UID"] == str(os.getuid()) and env["GID"] == str(os.getgid())


def test_notes_say_what_was_dropped(daemon, job):
    assert any("container_name fixed" in note for note in prepare(daemon, job).notes)


def test_the_checkout_can_be_read_by_a_container_user(daemon, job):
    job[1].chmod(0o750)
    prepare(daemon, job)
    assert job[1].stat().st_mode & 0o777 == 0o755


def test_a_broken_compose_file_is_a_clear_error(daemon, job):
    daemon.responses[("compose", "config")] = subprocess.CompletedProcess(
        [], 1, "", "services.api.ports must be a list")
    with pytest.raises(ComposeError, match="must be a list"):
        prepare(daemon, job)


def test_a_refused_project_writes_nothing(daemon, job):
    bad = json.loads(json.dumps(MODEL))
    bad["services"]["api"]["privileged"] = True
    daemon.responses[("compose", "config")] = ok(json.dumps(bad))
    with pytest.raises(ComposeError, match="privileged"):
        prepare(daemon, job)
    assert not (job[1].parent / compose_job.GENERATED_FILE).exists()


def test_garbage_from_compose_is_an_error(daemon, job):
    daemon.responses[("compose", "config")] = ok("not json")
    with pytest.raises(ComposeError, match="JSON"):
        prepare(daemon, job)


@pytest.mark.parametrize("files", ["../a.yml", "/etc/a.yml", "a.yml:/b.yml"])
def test_a_tampered_file_list_is_refused_on_the_worker(daemon, job, files):
    with pytest.raises(ComposeError):
        prepare(daemon, job, files=files)
    assert daemon.calls == []


def test_a_bad_job_id_is_refused(daemon, tmp_path):
    with pytest.raises(ComposeError):
        compose_job.prepare(Docker(daemon), PortPool(), "job-*", "build-1", "a.yml", tmp_path,
                            {}, lambda extra: {})


def test_two_jobs_get_different_ports(daemon, tmp_path):
    pool = PortPool(free=lambda port: True, pick=lambda low, high: 24000)
    envs = []
    for name in ("one", "two"):
        src = tmp_path / name / "src"
        src.mkdir(parents=True)
        envs.append(prepare(daemon, (new_id("job"), src), pool=pool).extra_env)
    assert envs[0]["MULEBOX_PORT_API_8000"] != envs[1]["MULEBOX_PORT_API_8000"]


def test_script_starts_containers_and_waits_for_them():
    lines = compose_job.script_lines()
    assert lines[-1] == "docker compose up --detach --wait"
    assert not any("--no-deps" in line or " down" in line for line in lines)


# The port pool


def test_pool_skips_ports_in_use():
    pool = PortPool(free=lambda port: port != 24000, pick=lambda low, high: 24000)
    assert pool.take("job-a", ["A"]) == {"A": 24001}


def test_pool_hands_out_distinct_ports_within_the_range():
    pool = PortPool(pick=lambda low, high: high, free=lambda port: True)
    got = pool.take("job-a", ["A", "B", "C"])
    assert len(set(got.values())) == 3
    assert all(ports.LOW <= port <= ports.HIGH for port in got.values())


def test_pool_holds_a_port_until_released():
    pool = PortPool(free=lambda port: True, pick=lambda low, high: 24000)
    first = pool.take("job-a", ["A"])["A"]
    assert pool.take("job-b", ["A"])["A"] != first
    pool.release("job-a")
    assert pool.take("job-c", ["A"])["A"] == first


def test_pool_gives_up_with_a_message():
    with pytest.raises(ComposeError, match="no free port"):
        PortPool(free=lambda port: False).take("job-a", ["A"])


def test_is_free_sees_a_real_listener():
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        assert not ports.is_free(server.getsockname()[1])
