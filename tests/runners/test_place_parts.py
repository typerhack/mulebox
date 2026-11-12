"""The parts of an isolated runner: image, container, one-job runners, the hook and its bridge."""

import json
import os
import subprocess
import sys

import pytest

from mulebox.runners import jit, layout, place_bridge, place_container, place_hook, place_image
from mulebox.runners.github import GitHubError
from mulebox.runners.names import RunnerUsageError
from mulebox.runners.runner_controls import RunnerControls, RunnerUnit
from mulebox.worker.controls import BOOST_SHARES
from mulebox.worker.docker import DockerError

REPO = "example-org/example-app"
CONFIG = "eyJzZWNyZXQiOiAicnVubmVyIGNvbmZpZyJ9"  # shaped like an encoded jit config


class FakeDocker:
    def __init__(self, images=(), containers=()):
        self.calls, self.images, self.containers = [], set(images), list(containers)

    def run(self, *args, timeout_s=None, **_):
        self.calls.append(args)
        if args[:2] == ("image", "inspect") and args[-1] not in self.images:
            raise DockerError("no such image")
        if args[:2] == ("network", "inspect"):
            raise DockerError("no such network")
        if args[0] == "build":
            self.images.add(args[args.index("--tag") + 1])
        if args[0] == "ps":
            return "\n".join(self.containers)
        return ""


def gh(code=0, out="", err=""):
    calls = []

    def run(argv):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, code, out, err)

    run.calls = calls
    return run


def test_image_tag_follows_version_and_recipe():
    assert place_image.tag("2.338.2").startswith("mulebox-runner:2.338.2-")
    assert place_image.tag("2.338.2") != place_image.tag("2.339.0")
    assert "FROM ghcr.io/actions/actions-runner:2.338.2" in place_image.recipe("2.338.2")


def test_image_built_once(paths):
    docker = FakeDocker()
    image = place_image.ensure(docker, paths, "2.338.2")
    assert [c[0] for c in docker.calls].count("build") == 1
    assert place_image.ensure(docker, paths, "2.338.2") == image
    assert [c[0] for c in docker.calls].count("build") == 1
    assert list((paths.staging / "tmp").iterdir()) == []  # the build folder is gone


def test_container_is_confined(tmp_path):
    argv = place_container.run_argv("c-1", "place-1", "img:1", hooks_dir=tmp_path / "h",
                                    io_dir=tmp_path / "io", diag_dir=tmp_path / "d",
                                    memory_mb=2048)
    joined = " ".join(argv)
    for flag in ("--cap-drop ALL", "--security-opt no-new-privileges", "--pids-limit 4096",
                 "--memory 2048m", "--network mulebox-isolated", "--rm",
                 f"{tmp_path / 'h'}:/mulebox-hooks:ro", "mulebox-tools-place-1:"):
        assert flag in joined
    assert "docker.sock" not in joined and "--privileged" not in joined
    assert CONFIG not in joined  # the config goes on stdin only
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "--volume"]
    assert len(mounts) == 4


def test_memory_limit_and_leftovers():
    assert place_container.memory_limit_mb(16 * 1024 ** 3) == 12 * 1024
    assert place_container.memory_limit_mb(1) == 1024
    docker = FakeDocker(containers=["a", "b"])
    assert place_container.remove_left(docker, "p") == ["a", "b"]
    assert ("rm", "--force", "a") in docker.calls
    place_container.ensure_network(docker)
    assert docker.calls[-1][:2] == ("network", "create")


def test_jit_create_and_errors():
    run = gh(out=json.dumps({"runner": {"id": 7}, "encoded_jit_config": CONFIG}))
    made = jit.create(REPO, "p-abc", ["X64", "mulebox", "X64"], run)
    assert (made.id, made.name, made.config) == (7, "p-abc", CONFIG)
    argv = run.calls[0]
    labels = [a for a in argv if a.startswith("labels[]=")]
    assert labels == ["labels[]=self-hosted", "labels[]=Linux", "labels[]=X64",
                      "labels[]=mulebox"]
    with pytest.raises(GitHubError, match="admin"):
        jit.create(REPO, "p", [], gh(code=1, err="HTTP 403"))
    with pytest.raises(RunnerUsageError):
        jit.create("not a repo", "p", [], run)


def test_jit_ids_of_admin_delete():
    listing = gh(out="11 place-1-aaaa1111\n12 other\n13 place-1-bbbb2222\n"
                     "14 place-1-fast-cccc3333\n15 place-1-short\n")
    assert jit.ids_of(REPO, "place-1", listing) == [11, 13]  # not place-1-fast's
    assert jit.ids_of(REPO, "place-1", gh(code=1)) == []
    assert jit.runner_name("place-1", "abcd1234") == "place-1-abcd1234"
    with pytest.raises(ValueError):
        jit.runner_name("place-1", "x/y")
    assert jit.admin(REPO, gh(out="true public\n")) == (True, "public")
    assert jit.admin(REPO, gh(out="false private\n")) == (False, "private")
    with pytest.raises(GitHubError):
        jit.admin(REPO, gh(code=1, err="Not Found"))
    assert jit.delete(REPO, 11, gh()) is True


def test_read_request_keeps_github_values_only(tmp_path):
    assert place_bridge.read_request(tmp_path) is None
    (tmp_path / "request.json").write_text(json.dumps(
        {"GITHUB_ACTOR": "alice", "RUNNER_NAME": "x", "PATH": "/evil", "GITHUB_X": 3}))
    assert place_bridge.read_request(tmp_path) == {"GITHUB_ACTOR": "alice", "RUNNER_NAME": "x"}
    (tmp_path / "request.json").write_text("[1]")
    assert place_bridge.read_request(tmp_path) == {}


def test_read_request_refuses_a_symlink(tmp_path):
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"GITHUB_ACTOR": "alice"}))
    io_dir = tmp_path / "io"
    io_dir.mkdir()
    os.symlink(secret, io_dir / "request.json")
    assert place_bridge.read_request(io_dir) is None


def place_folder(paths, actors=("alice",)):
    folder = paths.runners / "place-1"
    folder.mkdir()
    layout.write_meta(paths, folder, {"repo": REPO, "actors": list(actors), "isolated": True})
    io_dir = folder / "io"
    io_dir.mkdir()
    (io_dir / "event.json").write_text(json.dumps({"repository": {"id": 1}}))
    return folder, io_dir


def request(actor="alice"):
    return {"GITHUB_REPOSITORY": REPO, "GITHUB_ACTOR": actor, "GITHUB_TRIGGERING_ACTOR": actor,
            "GITHUB_EVENT_NAME": "push", "RUNNER_NAME": "place-1-abcd"}


def test_bridge_refuses_another_account_before_the_slot(paths):
    folder, io_dir = place_folder(paths)
    reserved = []
    ok, message = place_bridge.handle(request("mallory"), folder=folder, io_dir=io_dir,
                                      worker="build-1", link=None, paths=paths,
                                      reserve=lambda *a, **k: reserved.append(a) or 0)
    assert not ok and "refuses" in message and reserved == []
    ok, _ = place_bridge.handle({}, folder=folder, io_dir=io_dir, worker="build-1", link=None,
                                paths=paths, reserve=lambda *a, **k: 0)
    assert not ok


def test_bridge_reserves_under_the_place_name(paths):
    folder, io_dir = place_folder(paths)
    seen = []

    def reserve(env, worker, link, paths_, out):
        seen.append(env)
        out.write("mulebox: slot granted\n")
        return 0

    ok, message = place_bridge.handle(request(), folder=folder, io_dir=io_dir, worker="build-1",
                                      link=None, paths=paths, reserve=reserve)
    assert ok and message == "mulebox: slot granted"
    assert seen[0]["RUNNER_NAME"] == "place-1"
    assert seen[0]["GITHUB_EVENT_PATH"] == str(io_dir / "event.json")


def run_hook(tmp_path, answer):
    """The container's hook script, run here with its io folder moved under tmp_path."""
    io_dir = tmp_path / "io"
    io_dir.mkdir()
    event = tmp_path / "event.json"
    event.write_text("{}")
    if answer is not None:
        (io_dir / "answer.json").write_text(json.dumps(answer))
    script = tmp_path / "started.py"
    script.write_text(place_hook.STARTED_PY.replace(place_hook.IO_MOUNT, str(io_dir)))
    env = {"PATH": os.environ.get("PATH", ""), "GITHUB_ACTOR": "alice", "SECRET": "x",
           "GITHUB_EVENT_PATH": str(event)}
    proc = subprocess.run([sys.executable, str(script)], env=env, capture_output=True,
                          text=True, timeout=30)
    return proc, io_dir


def test_hook_asks_and_follows_an_allowed_answer(tmp_path):
    proc, io_dir = run_hook(tmp_path, {"ok": True, "message": "mulebox: slot granted"})
    assert proc.returncode == 0 and "slot granted" in proc.stdout
    sent = json.loads((io_dir / "request.json").read_text())
    assert sent["GITHUB_ACTOR"] == "alice" and "SECRET" not in sent
    assert (io_dir / "event.json").read_text() == "{}"


def test_hook_fails_on_a_refusal(tmp_path):
    proc, _ = run_hook(tmp_path, {"ok": False, "message": "mulebox: refused"})
    assert proc.returncode == 1 and "refused" in proc.stdout


def test_hook_files_are_read_only_for_the_container(paths):
    folder = paths.runners / "place-1"
    folder.mkdir()
    hooks = place_hook.write_hooks(paths, folder)
    assert oct(os.stat(hooks).st_mode & 0o777) == "0o755"
    assert os.stat(hooks / "started.sh").st_mode & 0o111


def test_controls_pause_a_place_container():
    log = []

    class Docker:
        def run(self, *args):
            log.append(args)
            return ""

    controls = RunnerControls(RunnerUnit(lambda *a: log.append(("systemctl", *a))), Docker(),
                              lambda runner: [], place=lambda runner: "mulebox-place-p-1")
    controls.follow([{"job_id": "j", "state": "running", "runner": "p", "paused": True,
                      "boost": True}])
    for held, _, _ in controls.held.values():
        assert held.task.wait(5.0) and held.task.error is None
    assert ("update", "--cpu-shares", str(BOOST_SHARES), "mulebox-place-p-1") in log
    assert ("pause", "mulebox-place-p-1") in log
    assert not [c for c in log if c[0] == "systemctl"]


def test_diag_files_are_never_opened_through_a_link(tmp_path):
    from mulebox.runners import diary
    from mulebox.runners.diag_files import open_diag

    runner = tmp_path / "runner"
    (runner / "_diag" / "pages").mkdir(parents=True)
    secret = tmp_path / "hosts.yml"
    secret.write_text("oauth_token: gho_secret\n")
    os.symlink(secret, runner / "_diag" / "Worker_20261112-000000-utc.log")
    os.symlink(secret, runner / "_diag" / "pages" / "a_b_1.log")
    os.mkfifo(runner / "_diag" / "pages" / "a_c_1.log")
    assert open_diag(runner, "Worker_20261112-000000-utc.log") is None
    assert open_diag(runner, "pages", "a_b_1.log") is None
    assert open_diag(runner, "pages", "a_c_1.log") is None  # a FIFO would block a reader
    assert open_diag(runner, "..", "hosts.yml") is None
    assert diary.read_result(runner) is None
    (runner / "_diag" / "pages" / "real.log").write_text("ok")
    with open_diag(runner, "pages", "real.log") as fh:
        assert fh.read() == b"ok"
    os.rename(runner / "_diag" / "pages", tmp_path / "elsewhere")
    os.symlink(tmp_path / "elsewhere", runner / "_diag" / "pages")
    assert open_diag(runner, "pages", "real.log") is None  # a linked folder on the way too


def test_a_long_diary_is_read_from_its_end(tmp_path, monkeypatch):
    from mulebox.runners import diary

    diag = tmp_path / "runner" / "_diag"
    diag.mkdir(parents=True)
    log = diag / "Worker_20261112-000000-utc.log"
    log.write_text("x" * 5000 + "\n")
    monkeypatch.setattr(diary, "MAX_DIARY_BYTES", 100)
    seen = []
    monkeypatch.setattr(diary, "job_result", lambda text: seen.append(text))
    diary.read_result(tmp_path / "runner")
    assert seen == ["x" * 99 + "\n"]
