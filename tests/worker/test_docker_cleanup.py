"""Docker cleanup, proved against a fake daemon: only exact job labels, never anything else."""

import subprocess

import pytest

from mulebox.common import compose
from mulebox.common.ids import new_id
from mulebox.worker import docker_cleanup
from mulebox.worker.docker import Docker, DockerError, DockerMissing, default_runner

from .fake_docker import FakeDocker


def job_labels(job_id, worker="build-1"):
    return {compose.LABEL_JOB: job_id, compose.LABEL_WORKER: worker,
            compose.LABEL_COMPOSE_PROJECT: compose.project_name(job_id)}


@pytest.fixture
def daemon():
    return FakeDocker()


@pytest.fixture
def docker(daemon):
    return Docker(daemon)


def add_job(daemon, job_id):
    labels = job_labels(job_id)
    for kind in ("containers", "networks", "volumes", "images"):
        daemon.add_labelled(kind, f"{kind}-{job_id}", labels)


def add_foreign(daemon):
    """What must survive: other people's and other jobs' resources, stopped or not."""
    daemon.add("containers", "their-postgres")
    daemon.add("containers", "their-compose", com__docker__compose__project="my-app")
    daemon.add("containers", "similar-name",
               com__docker__compose__project="mulebox-other")
    daemon.add("volumes", "their-data")
    daemon.add("networks", "their-net", com__docker__compose__project="my-app")
    daemon.add("images", "redis-7")
    daemon.add("images", "their-build", mulebox__job="job-not-a-real-id")


def test_teardown_removes_all_four_kinds_and_nothing_else(daemon, docker):
    job_id, other = new_id("job"), new_id("job")
    add_job(daemon, job_id)
    add_job(daemon, other)
    add_foreign(daemon)
    before = set(daemon.left())
    docker_cleanup.teardown(docker, job_id)
    assert before - set(daemon.left()) == {f"{k}-{job_id}" for k in
                                           ("containers", "networks", "volumes", "images")}
    assert not any(other in r for c in daemon.removals() for r in c if job_id not in r)


def test_every_listing_is_filtered_on_one_exact_job(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    docker_cleanup.teardown(docker, job_id)
    listings = [c for c in daemon.calls if c not in daemon.removals()]
    assert listings
    for call in listings:
        assert call.count("--filter") == 1
        value = call[call.index("--filter") + 1]
        assert value in (compose.job_filter(job_id), compose.project_filter(job_id))


def test_nothing_is_called_prune_or_system(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    docker_cleanup.teardown(docker, job_id)
    assert not any({"prune", "system"} & set(call) for call in daemon.calls)


def test_a_job_with_nothing_removes_nothing(daemon, docker):
    add_foreign(daemon)
    docker_cleanup.teardown(docker, new_id("job"))
    assert daemon.removals() == []


def test_containers_go_before_what_they_use_and_images_last(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    docker_cleanup.teardown(docker, job_id)
    assert [c[0] for c in daemon.removals()] == ["rm", "network", "volume", "image"]


def test_container_volumes_go_with_the_container(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    docker_cleanup.teardown(docker, job_id)
    assert daemon.removals()[0][:3] == ("rm", "--force", "--volumes")


def test_something_only_compose_labelled_is_found(daemon, docker):
    """A job that ran `docker compose -f x up` itself: no mulebox label, same project."""
    job_id = new_id("job")
    daemon.add_labelled("containers", "side", {
        compose.LABEL_COMPOSE_PROJECT: compose.project_name(job_id)})
    docker_cleanup.teardown(docker, job_id)
    assert daemon.left() == []


def test_a_failed_removal_is_retried(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    daemon.fail_remove["networks"] = 1
    docker_cleanup.teardown(docker, job_id)
    assert daemon.left() == []


def test_what_stays_is_reported_so_the_agent_retries(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    daemon.fail_remove["volumes"] = 99
    with pytest.raises(DockerError, match="1 volumes"):
        docker_cleanup.teardown(docker, job_id)


def test_an_image_alone_does_not_hold_the_job(daemon, docker):
    job_id = new_id("job")
    add_job(daemon, job_id)
    daemon.fail_remove["images"] = 99
    docker_cleanup.teardown(docker, job_id)
    assert daemon.left() == [f"images-{job_id}"]


def test_teardown_refuses_a_bad_id_before_any_call(daemon, docker):
    with pytest.raises(compose.ComposeError):
        docker_cleanup.teardown(docker, "job-*")
    assert daemon.calls == []


def test_labelled_jobs_lists_this_workers_jobs_only(daemon, docker):
    mine, theirs = new_id("job"), new_id("job")
    add_job(daemon, mine)
    daemon.add_labelled("containers", "other", job_labels(theirs, "build-2"))
    add_foreign(daemon)
    assert docker_cleanup.labelled_jobs(docker, "build-1") == [mine]


def test_labelled_jobs_ignores_a_label_that_is_no_job_id(daemon, docker):
    daemon.add_labelled("containers", "x", {compose.LABEL_JOB: "../../etc",
                                            compose.LABEL_WORKER: "build-1"})
    assert docker_cleanup.labelled_jobs(docker, "build-1") == []


def test_listing_for_recovery_is_filtered_on_label_and_worker(daemon, docker):
    docker_cleanup.labelled_jobs(docker, "build-1")
    assert daemon.calls
    for call in daemon.calls:
        filters = [call[i + 1] for i, word in enumerate(call) if word == "--filter"]
        assert filters == ["label=mulebox.job", "label=mulebox.worker=build-1"]


@pytest.mark.parametrize("args", [("system", "prune", "-af"), ("volume", "prune", "-f"),
                                  ("container", "prune"), ("image", "prune", "-a"),
                                  ("network", "prune")])
def test_prune_cannot_be_run_at_all(daemon, docker, args):
    with pytest.raises(DockerError, match="never"):
        docker.run(*args)
    assert daemon.calls == []


def test_errors_are_redacted(docker, daemon):
    daemon.responses[("compose",)] = subprocess.CompletedProcess(
        [], 1, "", "failed with password=hunter2hunter2")
    with pytest.raises(DockerError) as info:
        docker.run("compose", "config")
    assert "hunter2" not in str(info.value)


def test_no_docker_on_the_machine(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(DockerMissing):
        Docker(default_runner).run("version")
