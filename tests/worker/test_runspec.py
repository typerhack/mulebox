"""What a job's capabilities add to its environment."""

import pytest

from mulebox.common.ids import new_id
from mulebox.worker import runspec
from mulebox.worker.executor import ExecutorError
from mulebox.worker.ports import PortPool

from .fakes import claim_body


@pytest.fixture
def machine(paths):
    return runspec.Machine("build-1", paths, None, PortPool())


def build(machine, tmp_path, needs=(), env=None):
    claim = {**claim_body(["true"]), "needs": list(needs), "env": env or {}}
    return runspec.build(machine, new_id("job"), claim, tmp_path, tmp_path / "out.log", [])


def test_playwright_jobs_share_a_folder_in_the_cache_root(machine, paths, tmp_path):
    spec, _ = build(machine, tmp_path, needs=["playwright"])
    assert spec.env["PLAYWRIGHT_BROWSERS_PATH"] == str(paths.cache / "playwright")
    assert (paths.cache / "playwright").is_dir()


def test_other_jobs_keep_playwrights_default(machine, paths, tmp_path):
    spec, _ = build(machine, tmp_path, needs=["node"])
    assert "PLAYWRIGHT_BROWSERS_PATH" not in spec.env
    assert not (paths.cache / "playwright").exists()


def test_env_cannot_move_the_browser_folder(machine, paths, tmp_path):
    spec, _ = build(machine, tmp_path, needs=["playwright"],
                    env={"PLAYWRIGHT_BROWSERS_PATH": "/somewhere/else"})
    assert spec.env["PLAYWRIGHT_BROWSERS_PATH"] == str(paths.cache / "playwright")


def test_compose_without_docker_is_refused(machine, tmp_path):
    with pytest.raises(ExecutorError, match="no Docker"):
        build(machine, tmp_path, env={"MULEBOX_COMPOSE_FILES": "a.yml"})


def with_job_env(paths):
    return runspec.Machine("build-1", paths, None, PortPool(), {"NODE_OPTIONS": "--slow-net"})


def test_the_machines_job_env_reaches_every_job(paths, tmp_path):
    spec, _ = build(with_job_env(paths), tmp_path)
    assert spec.env["NODE_OPTIONS"] == "--slow-net"


def test_a_project_overrides_the_machine(paths, tmp_path):
    spec, _ = build(with_job_env(paths), tmp_path, env={"NODE_OPTIONS": "--max-old-space-size=2048"})
    assert spec.env["NODE_OPTIONS"] == "--max-old-space-size=2048"


def test_a_project_can_add_to_the_machine(paths, tmp_path):
    env = {"NODE_OPTIONS": "${NODE_OPTIONS} --max-old-space-size=2048"}
    spec, _ = build(with_job_env(paths), tmp_path, env=env)
    assert spec.env["NODE_OPTIONS"] == "--slow-net --max-old-space-size=2048"


def test_the_machine_cannot_change_what_mulebox_sets(paths, tmp_path):
    machine = runspec.Machine("build-1", paths, None, PortPool(), {"MULEBOX": "0"})
    spec, _ = build(machine, tmp_path)
    assert spec.env["MULEBOX"] == "1"
