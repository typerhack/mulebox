"""The root-owned file helper: what it mounts, what it may do, and when it refuses."""

import os
import subprocess

import pytest

from mulebox.common import compose, mounts, safepath
from mulebox.common.ids import new_id
from mulebox.common.safepath import PathOutsideRoots, RemovalDenied, UnsafePath
from mulebox.worker import reclaim, workspace
from mulebox.worker.cleaner import Cleaner
from mulebox.worker.docker import Docker, DockerError, DockerMissing

from .fake_docker import FakeDocker


@pytest.fixture
def daemon():
    return FakeDocker()


@pytest.fixture
def docker(daemon):
    return Docker(daemon)


@pytest.fixture
def job(paths):
    job_id = new_id("job")
    folder = paths.job_dir("example-app", job_id)
    (folder / "src").mkdir(parents=True)
    return job_id, folder


def run_call(daemon):
    calls = [c for c in daemon.calls if c[0] == "run"]
    assert len(calls) == 1
    return calls[0]


def test_helper_mounts_exactly_the_job_folder(daemon, docker, paths, job):
    job_id, folder = job
    reclaim.reclaim(docker, paths, "example-app", job_id, "build-1")
    call = run_call(daemon)
    assert call.count("--mount") == 1 and "-v" not in call and "--volume" not in call
    assert call[call.index("--mount") + 1] == f"type=bind,source={folder},target=/reclaim"


def test_helper_has_no_privileges_beyond_that_mount(daemon, docker, paths, job):
    reclaim.reclaim(docker, paths, "example-app", job[0], "build-1")
    call = run_call(daemon)
    for flag in ("--rm", "--network=none", "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges"):
        assert flag in call
    assert {a for a in call if a.startswith("--cap-add=")} == {
        "--cap-add=CHOWN", "--cap-add=DAC_READ_SEARCH", "--cap-add=FOWNER"}
    assert "--privileged" not in call and "--user" not in call
    assert not any(a.startswith(("--pid=", "--ipc", "--device", "--volumes-from")) for a in call)


def test_helper_image_is_pinned_and_chown_does_not_follow_links(daemon, docker, paths, job):
    reclaim.reclaim(docker, paths, "example-app", job[0], "build-1")
    call = run_call(daemon)
    assert "@sha256:" in reclaim.HELPER_IMAGE and reclaim.HELPER_IMAGE in call
    script = call[call.index("-c") + 1]
    assert "chown -hR" in script and "rm" not in script.split()


def test_helper_carries_the_job_labels(daemon, docker, paths, job):
    job_id, _ = job
    reclaim.reclaim(docker, paths, "example-app", job_id, "build-1")
    call = run_call(daemon)
    assert f"{compose.LABEL_JOB}={job_id}" in call
    assert f"{compose.LABEL_WORKER}=build-1" in call


def test_uid_and_gid_are_the_workers(daemon, docker, paths, job):
    reclaim.reclaim(docker, paths, "example-app", job[0], "build-1")
    assert run_call(daemon)[-1] == f"{os.getuid()}:{os.getgid()}"


@pytest.mark.parametrize("project,job_id", [
    ("..", None), ("a/b", None), ("/", None), ("", None), ("ok", "../x"), ("ok", ""),
    ("ok", "job-*")])
def test_bad_names_never_reach_docker(daemon, docker, paths, project, job_id):
    with pytest.raises(UnsafePath):
        reclaim.reclaim(docker, paths, project, job_id or new_id("job"), "build-1")
    assert daemon.calls == []


def test_a_job_folder_that_is_a_symlink_is_refused(daemon, docker, paths, tmp_path):
    job_id = new_id("job")
    (paths.jobs / "example-app").mkdir()
    (paths.jobs / "example-app" / job_id).symlink_to(tmp_path)
    with pytest.raises(UnsafePath, match="symlink"):
        reclaim.reclaim(docker, paths, "example-app", job_id, "build-1")
    assert daemon.calls == []


def test_a_project_folder_that_is_a_symlink_is_refused(daemon, docker, paths, tmp_path):
    job_id = new_id("job")
    (tmp_path / "elsewhere" / job_id).mkdir(parents=True)
    (paths.jobs / "example-app").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(UnsafePath, match="symlink"):
        reclaim.reclaim(docker, paths, "example-app", job_id, "build-1")
    assert daemon.calls == []


def test_a_mount_in_the_job_folder_is_refused(monkeypatch, daemon, docker, paths, job):
    job_id, folder = job
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: [folder / "src"])
    with pytest.raises(UnsafePath, match="mount"):
        reclaim.reclaim(docker, paths, "example-app", job_id, "build-1")
    assert daemon.calls == []


def test_a_mount_above_the_job_folder_is_refused(monkeypatch, daemon, docker, paths, job):
    job_id, folder = job
    monkeypatch.setattr(mounts, "linux_mount_points", lambda: [folder.parent])
    with pytest.raises(UnsafePath, match="mount"):
        reclaim.reclaim(docker, paths, "example-app", job_id, "build-1")
    assert daemon.calls == []


def test_a_missing_job_folder_is_refused(daemon, docker, paths):
    with pytest.raises(UnsafePath, match="does not exist"):
        reclaim.reclaim(docker, paths, "example-app", new_id("job"), "build-1")
    assert daemon.calls == []


@pytest.mark.parametrize("source", ["/a,target=/etc", "/a,b"])
def test_a_comma_cannot_add_mount_options(source):
    with pytest.raises(UnsafePath, match="comma"):
        reclaim.helper_args(source, new_id("job"), "build-1", 1000, 1000)


def test_only_the_jobs_root_may_be_mounted(paths):
    """The cache root is a configured root too, but never holds job folders."""
    roots = safepath.Roots((paths.jobs,))
    (paths.cache / "x").mkdir()
    with pytest.raises(PathOutsideRoots):
        safepath.confirm_dir(paths.cache / "x", roots)


# The cleaner: reclaim only after safepath was denied, then delete through safepath again.


def deny_once(monkeypatch, paths):
    real, denied = workspace.cleanup, []

    def cleanup(*args):
        if not denied:
            denied.append(True)
            raise RemovalDenied("permission denied removing a root-owned file")
        real(*args)

    monkeypatch.setattr(workspace, "cleanup", cleanup)


def test_cleaner_reclaims_when_denied_then_deletes_through_safepath(
        monkeypatch, daemon, docker, paths, job):
    job_id, folder = job
    deny_once(monkeypatch, paths)
    Cleaner(paths, "build-1", docker).clean("example-app", job_id, uses_docker=False)
    run_call(daemon)
    assert not folder.exists()


def test_cleaner_does_not_use_docker_when_nothing_is_denied(daemon, docker, paths, job):
    job_id, folder = job
    Cleaner(paths, "build-1", docker).clean("example-app", job_id, uses_docker=False)
    assert daemon.calls == [] and not folder.exists()


def test_teardown_comes_before_the_folder(daemon, docker, paths, job, monkeypatch):
    job_id, folder = job
    order = []
    real = workspace.cleanup
    monkeypatch.setattr(workspace, "cleanup", lambda *a: (order.append(list(daemon.calls)), real(*a)))
    Cleaner(paths, "build-1", docker).clean("example-app", job_id, uses_docker=True)
    assert order[0], "docker was asked before the folder went"


def test_without_docker_denied_stays_denied(monkeypatch, paths, job):
    deny_once(monkeypatch, paths)
    with pytest.raises(RemovalDenied):
        Cleaner(paths, "build-1", None).clean("example-app", job[0], uses_docker=False)


def test_a_failing_helper_keeps_the_job_for_a_retry(monkeypatch, daemon, docker, paths, job):
    deny_once(monkeypatch, paths)
    daemon.responses[("run",)] = subprocess.CompletedProcess([], 1, "", "no image")
    with pytest.raises(DockerError):
        Cleaner(paths, "build-1", docker).clean("example-app", job[0], uses_docker=False)
    assert job[1].exists()


# Recovery after a crash.


def test_recover_cleans_folders_and_labelled_resources(daemon, docker, paths, job):
    job_id, folder = job
    gone = new_id("job")  # its folder is gone already; only containers are left
    for one in (job_id, gone):
        daemon.add_labelled("containers", f"c-{one}", {
            compose.LABEL_JOB: one, compose.LABEL_WORKER: "build-1"})
    daemon.add("containers", "their-postgres")
    cleaned = Cleaner(paths, "build-1", docker).recover()
    assert daemon.left() == ["their-postgres"] and not folder.exists()
    assert gone in cleaned and str(folder) in cleaned


def test_recover_finds_compose_resources_through_the_job_folder(daemon, docker, paths, job):
    job_id, _ = job
    daemon.add_labelled("containers", "side", {
        compose.LABEL_COMPOSE_PROJECT: compose.project_name(job_id)})
    Cleaner(paths, "build-1", docker).recover()
    assert daemon.left() == []


def test_recover_goes_on_past_a_job_it_cannot_clean(monkeypatch, daemon, docker, paths):
    first, second = sorted(new_id("job") for _ in range(2))
    for job_id in (first, second):
        paths.job_dir("example-app", job_id).mkdir(parents=True)
    real = workspace.cleanup

    def cleanup(_paths, project, job_id):
        if job_id == first:
            raise UnsafePath("cannot be removed")
        real(_paths, project, job_id)

    monkeypatch.setattr(workspace, "cleanup", cleanup)
    cleaned = Cleaner(paths, "build-1", docker).recover()
    assert cleaned == [str(paths.job_dir("example-app", second))]
    assert paths.job_dir("example-app", first).exists()


def test_recover_on_a_machine_without_docker(daemon, docker, paths, job):
    daemon.missing = True
    cleaned = Cleaner(paths, "build-1", docker).recover()
    assert cleaned == [str(job[1])] and not job[1].exists()


def test_recover_survives_a_dead_daemon(daemon, docker, paths):
    daemon.responses[("ps",)] = subprocess.CompletedProcess([], 1, "", "no daemon")
    assert Cleaner(paths, "build-1", docker).recover() == []


def test_docker_missing_is_a_docker_error():
    assert issubclass(DockerMissing, DockerError)
