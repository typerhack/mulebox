"""What the rewrite adds to every service: the machine's job_env, and an open files limit."""

import json

import pytest

from mulebox.common.ids import new_id
from mulebox.worker import compose_job, jobspec
from mulebox.worker.docker import Docker
from mulebox.worker.ports import PortPool

from .fake_docker import FakeDocker, ok


@pytest.fixture
def daemon():
    return FakeDocker()


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
