"""An isolated job's container (worker/isolated.py, runspec.py; M23.1)."""

import pytest

from mulebox.common import compose, isolation
from mulebox.common.ids import new_id
from mulebox.worker import isolated, job_image, jobspec, runspec
from mulebox.worker.executor import ExecutorError, RunSpec
from mulebox.worker.ports import PortPool

from .fakes import claim_body


class Docker:
    """Only its presence counts here: the job's unit runs `docker`, not the worker."""


@pytest.fixture
def machine(paths):
    return runspec.Machine("build-1", paths, Docker(), PortPool())


def build(machine, tmp_path, needs=("isolated",), env=None, project="example-app"):
    claim = {**claim_body(["make", "test"]), "needs": list(needs), "env": env or {},
             "project": project}
    job_id = new_id("job")
    spec, notes = runspec.build(machine, job_id, claim, tmp_path, tmp_path / "out.log", [])
    return job_id, spec, notes


def run_part(spec):
    """The `docker run ...` command line the unit ends in."""
    return list(spec.argv[spec.argv.index("docker"):])


def test_a_job_that_asks_runs_in_a_confined_container_of_its_own(machine, tmp_path):
    job_id, spec, notes = build(machine, tmp_path, env={"API_TOKEN": "s3cret-value"})
    run = run_part(spec)
    assert run[:4] == ["docker", "run", "--rm", "--init"]
    for flag in (["--cap-drop", "ALL"], ["--security-opt", "no-new-privileges"],
                 ["--read-only"], ["--network", isolated.network_name(job_id)]):
        assert any(run[i:i + len(flag)] == flag for i in range(len(run)))
    assert f"{compose.LABEL_JOB}={job_id}" in run and f"{compose.LABEL_WORKER}=build-1" in run
    assert f"{tmp_path}:{tmp_path}:rw" in run
    assert run[run.index("--workdir") + 1] == str(tmp_path)
    assert run[-3:] == list(jobspec.build_argv(None, ["make", "test"])[:2]) + [run[-1]]
    assert "isolated: runs in a container" in notes[0]


def test_values_reach_the_container_by_name_only(machine, tmp_path):
    _, spec, _ = build(machine, tmp_path, env={"API_TOKEN": "s3cret-value"})
    assert spec.env["API_TOKEN"] == "s3cret-value"  # the unit's environment holds it
    assert not any("s3cret-value" in arg for arg in spec.argv)
    run = run_part(spec)
    assert run[run.index("API_TOKEN") - 1] == "--env"
    assert f"HOME={isolated.HOME}" in run
    assert not any(arg.startswith("PATH=") and "/opt/homebrew" in arg for arg in run)


def test_nothing_of_the_node_is_mounted_but_what_the_job_needs(machine, paths, tmp_path):
    (paths.cache / "toolchains").mkdir(parents=True, exist_ok=True)
    _, spec, _ = build(machine, tmp_path)
    mounts = [arg for i, arg in enumerate(run_part(spec)) if run_part(spec)[i - 1] == "--volume"]
    assert f"{paths.cache / 'toolchains'}:{paths.cache / 'toolchains'}:ro" in mounts
    assert all(not m.startswith(str(paths.cache.parent.parent / ".ssh")) for m in mounts)
    assert not any("docker.sock" in m for m in mounts)
    assert len(mounts) == 2  # the tree and the toolchains; no repo.git yet, no caches


def test_mulebox_builds_its_image_once_and_a_project_may_name_its_own(machine, tmp_path):
    _, spec, _ = build(machine, tmp_path)
    recipe = job_image.dockerfile(job_image.base_image())
    assert job_image.tag(recipe) in run_part(spec) and recipe in spec.argv
    _, own, notes = build(machine, tmp_path, env={isolation.IMAGE_KEY: "ghcr.io/example/ci:1"})
    assert "ghcr.io/example/ci:1" in run_part(own)
    assert isolation.IMAGE_KEY not in own.env
    assert "ghcr.io/example/ci:1" in notes[0]


def test_a_bad_image_name_from_an_older_client_is_refused(machine, tmp_path):
    with pytest.raises(jobspec.JobSpecError, match="image"):
        build(machine, tmp_path, env={isolation.IMAGE_KEY: "--privileged"})


def test_a_job_that_does_not_ask_runs_as_before(machine, tmp_path):
    _, spec, _ = build(machine, tmp_path, needs=())
    assert "docker" not in spec.argv


def test_isolation_needs_docker(paths, tmp_path):
    with pytest.raises(ExecutorError, match="no Docker"):
        build(runspec.Machine("build-1", paths, None, PortPool()), tmp_path)


def test_a_compose_job_cannot_be_isolated_yet(machine, tmp_path):
    with pytest.raises(ExecutorError, match="compose"):
        build(machine, tmp_path, env={compose.COMPOSE_FILES_KEY: "compose.yml"})


def test_the_image_is_the_nodes_own_system(tmp_path):
    release = tmp_path / "os-release"
    release.write_text('ID=ubuntu\nVERSION_ID="24.04"\n')
    assert job_image.base_image(release) == "ubuntu:24.04"
    release.write_text('ID=fedora\nVERSION_ID="41"\n')
    assert job_image.base_image(release) == job_image.FALLBACK_BASE
    assert job_image.base_image(tmp_path / "missing") == job_image.FALLBACK_BASE
    release.write_text('ID=debian\nVERSION_ID="12; rm -rf /"\n')
    assert job_image.base_image(release) == job_image.FALLBACK_BASE


def test_wrap_keeps_everything_but_the_command(tmp_path):
    spec = RunSpec("mulebox-job-x", ("bash", "-c", "true"), tmp_path, {"A": "1"}, tmp_path / "l")
    wrapped = isolated.wrap(spec, new_id("job"), "build-1", image="alpine:3", bins=[],
                            read_write=[], read_only=[], uid=1000, gid=1000)
    assert (wrapped.name, wrapped.cwd, wrapped.env, wrapped.log_path) == (
        spec.name, spec.cwd, spec.env, spec.log_path)
    assert "1000:1000" in wrapped.argv
