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
    pool = pool or PortPool(free=lambda port, protocol: True, pick=lambda low, high: 24000)

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
    pool = PortPool(free=lambda port, protocol: True, pick=lambda low, high: 24000)
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
    pool = PortPool(free=lambda port, protocol: port != 24000, pick=lambda low, high: 24000)
    assert pool.take("job-a", {"A": "tcp"}) == {"A": 24001}


def test_pool_hands_out_distinct_ports_within_the_range():
    pool = PortPool(pick=lambda low, high: high, free=lambda port, protocol: True)
    got = pool.take("job-a", dict.fromkeys("ABC", "tcp"))
    assert len(set(got.values())) == 3
    assert all(ports.LOW <= port <= ports.HIGH for port in got.values())


def test_pool_holds_a_port_until_released():
    pool = PortPool(free=lambda port, protocol: True, pick=lambda low, high: 24000)
    first = pool.take("job-a", {"A": "tcp"})["A"]
    assert pool.take("job-b", {"A": "tcp"})["A"] != first
    pool.release("job-a")
    assert pool.take("job-c", {"A": "tcp"})["A"] == first


def test_pool_gives_up_with_a_message():
    with pytest.raises(ComposeError, match="no free port"):
        PortPool(free=lambda port, protocol: False).take("job-a", {"A": "tcp"})


def test_is_free_sees_a_real_listener():
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        assert not ports.is_free(server.getsockname()[1])


def test_is_free_sees_a_real_udp_service_a_tcp_probe_would_miss():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as service:
        service.bind(("127.0.0.1", 0))
        port = service.getsockname()[1]
        assert not ports.is_free(port, "udp")
        assert ports.is_free(port, "tcp")


def test_is_free_sees_tcp_only_for_tcp():
    import socket

    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        assert ports.is_free(server.getsockname()[1], "udp")


def test_a_protocol_mulebox_cannot_check_is_refused():
    with pytest.raises(ComposeError, match="sctp"):
        ports.is_free(24000, "sctp")


def test_the_pool_asks_about_each_ports_own_protocol():
    asked = []

    def free(port, protocol):
        asked.append(protocol)
        return True

    PortPool(free=free).take("job-a", {"A": "tcp", "B": "udp"})
    assert asked == ["tcp", "udp"]


def test_a_udp_port_of_a_job_is_probed_as_udp(tmp_path):
    published = [{"mode": "ingress", "target": 53, "published": "53", "protocol": "udp"}]
    daemon = FakeDocker()
    daemon.responses[("compose", "config")] = ok(json.dumps(
        {"name": "x", "services": {"dns": {"image": "x", "ports": published}}}))
    asked = []

    def free(port, protocol):
        asked.append(protocol)
        return True

    job = prepare(daemon, (new_id("job"), tmp_path), pool=PortPool(free=free))
    assert asked == ["udp"] and "MULEBOX_PORT_DNS_53_UDP" in job.extra_env


def test_containers_start_before_anything_of_the_project():
    script = jobspec.build_script("project-setup", ["project-job"], compose_job.script_lines())
    assert script.index("docker compose up") < script.index("project-setup")


# The machine's job_env


def service_env(daemon, tmp_path, environment, project_env=None, machine=None):
    src = tmp_path / "src"
    src.mkdir()
    machine = {"NODE_OPTIONS": "--slow-net"} if machine is None else machine
    model = {"name": "x", "services": {"api": {"image": "x", "environment": environment},
                                       "db": {"image": "y"}}}
    daemon.responses[("compose", "config")] = ok(json.dumps(model))

    def environ(extra):
        return jobspec.build_env(new_id("job"), [], project_env=project_env, extra=extra,
                                 machine_env=machine)

    compose_job.prepare(Docker(daemon), PortPool(), new_id("job"), "build-1", "a.yml", src,
                        project_env or {}, environ, machine_names=tuple(machine))
    written = json.loads((tmp_path / compose_job.GENERATED_FILE).read_text())
    return {name: spec.get("environment") for name, spec in written["services"].items()}


def test_job_env_reaches_every_service(daemon, tmp_path):
    env = service_env(daemon, tmp_path, {"APP": "1"})
    assert env["api"] == {"NODE_OPTIONS": "--slow-net", "APP": "1"}
    assert env["db"] == {"NODE_OPTIONS": "--slow-net"}


def test_what_a_service_sets_wins_over_job_env(daemon, tmp_path):
    env = service_env(daemon, tmp_path, {"NODE_OPTIONS": "--from-compose"})
    assert env["api"] == {"NODE_OPTIONS": "--from-compose"}


def test_a_projects_env_value_is_the_one_that_reaches_services(daemon, tmp_path):
    project = {"NODE_OPTIONS": "${NODE_OPTIONS} --max-old-space-size=2048"}
    env = service_env(daemon, tmp_path, {}, project_env=project)
    assert env["db"] == {"NODE_OPTIONS": "--slow-net --max-old-space-size=2048"}


def test_a_dollar_in_job_env_survives_composes_second_reading(daemon, tmp_path):
    env = service_env(daemon, tmp_path, {}, machine={"PROXY_NOTE": "pa$$word $HOME"})
    assert env["db"] == {"PROXY_NOTE": "pa$$$$word $$HOME"}


def test_no_environment_key_without_job_env(daemon, tmp_path):
    env = service_env(daemon, tmp_path, None, machine={})
    assert env["db"] is None


# Open files


def limits_of(daemon, tmp_path, ulimits):
    src = tmp_path / "src"
    src.mkdir()
    spec = {"image": "mongo:8.2.12"} if ulimits is None else {"image": "x", "ulimits": ulimits}
    daemon.responses[("compose", "config")] = ok(json.dumps(
        {"name": "x", "services": {"db": spec}}))
    compose_job.prepare(Docker(daemon), PortPool(), new_id("job"), "build-1", "a.yml", src, {},
                        lambda extra: dict(extra))
    written = json.loads((tmp_path / compose_job.GENERATED_FILE).read_text())
    return written["services"]["db"]["ulimits"]


def test_a_service_without_a_limit_gets_a_higher_one(daemon, tmp_path):
    assert limits_of(daemon, tmp_path, None) == {"nofile": {"soft": 65536, "hard": 65536}}


@pytest.mark.parametrize("own", [{"soft": 1024, "hard": 2048}, 512])
def test_a_projects_own_limit_always_wins(daemon, tmp_path, own):
    assert limits_of(daemon, tmp_path, {"nofile": own}) == {"nofile": own}


def test_other_limits_of_a_service_stay(daemon, tmp_path):
    limits = limits_of(daemon, tmp_path, {"nproc": 100})
    assert limits == {"nproc": 100, "nofile": {"soft": 65536, "hard": 65536}}
