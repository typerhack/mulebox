"""An isolated runner's container outlives a worker restart (place_handover.py)."""

import json
import subprocess
import threading

from mulebox.runners import place, place_container, place_handover

from .test_place_parts import REPO, FakeDocker
from .test_place_run import FakeGh, add


class DeleteGh(FakeGh):
    """GitHub: a DELETE answers `deleted` (False: it gave the runner a job)."""

    def __init__(self, deleted=True, **kw):
        super().__init__(**kw)
        self.deleted = deleted

    def __call__(self, argv):
        done = super().__call__(argv)
        if "DELETE" in argv and not self.deleted:
            return subprocess.CompletedProcess(argv, 1, "", "Runner is still running a job")
        return done


class LiveDocker(FakeDocker):
    """Docker with containers that keep running until `ended`."""

    def __init__(self, running=()):
        super().__init__()
        self.live = set(running)

    def run(self, *args, **kw):
        if args[:2] == ("rm", "--force"):
            self.live.discard(args[-1])
        if args[0] == "inspect":
            self.calls.append(args)
            return "true" if args[-1] in self.live else "false"
        return super().run(*args, **kw)


class StopOnStart:
    """The `docker run` client: the worker is told to stop as soon as the container starts;
    the client then dies of the same signal, the container does not."""

    def __init__(self, stop, docker, container, io_dir, ask):
        self.stdin, self.stop, self.code = self, stop, None
        self.docker, self.container, self.io_dir, self.ask = docker, container, io_dir, ask

    def write(self, data):
        self.docker.live.add(self.container)
        if self.ask:
            (self.io_dir / "request.json").write_text(json.dumps({"GITHUB_ACTOR": "alice"}))
        self.stop.set()

    def close(self):
        pass

    def poll(self):
        return self.code  # the client lives on: it ignores the stop signal

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


def run_round(machine, paths, monkeypatch, gh, ask):
    """One round in which the worker is told to stop; returns its parts and the client."""
    folder = add(machine, FakeGh())
    released = []
    monkeypatch.setattr(place.hooks, "completed", lambda *a, **k: released.append(1))
    monkeypatch.setattr(place, "POLL_S", 0.0)
    docker, stop = LiveDocker(), threading.Event()

    def popen(argv, **_):
        name = argv[argv.index("--name") + 1]
        io_dir = folder / ("io-" + name.rsplit("-", 1)[1])
        return StopOnStart(stop, docker, name, io_dir, ask)

    clients = []

    def popen_kept(argv, **kw):
        clients.append(popen(argv, **kw))
        return clients[-1]

    runner = place.Place(folder, "build-1", None, paths, stop=stop, docker=docker, gh=gh,
                         version=lambda: "2.338.2", popen=popen_kept)
    runner.clients = clients
    released.clear()
    runner.round()
    return folder, runner, docker, released


def test_the_container_has_no_signal_passed_on(tmp_path):
    argv = place_container.run_argv("c", "p", "img", hooks_dir=tmp_path, io_dir=tmp_path,
                                    diag_dir=tmp_path, memory_mb=1024)
    assert "--sig-proxy=false" in argv and "--rm" in argv


def test_a_job_that_asked_outlives_the_worker(machine, paths, monkeypatch):
    folder, runner, docker, released = run_round(machine, paths, monkeypatch, DeleteGh(), True)
    assert runner.handed_over and len(docker.live) == 1
    assert (folder / ".mulebox-place").exists()  # supervision keeps its slot
    assert released == [1]  # only the one before the round: its reservation stays
    assert not (folder / ".mulebox-round").exists()
    assert runner.clients[0].code == -9  # its client is killed, so the worker's stop is quick


def test_a_runner_github_gave_a_job_outlives_the_worker(machine, paths, monkeypatch):
    gh = DeleteGh(deleted=False)
    folder, runner, docker, released = run_round(machine, paths, monkeypatch, gh, False)
    assert runner.handed_over and len(docker.live) == 1
    assert [c for c in gh.calls if "DELETE" in c]


def test_an_idle_runner_github_deleted_goes_with_the_worker(machine, paths, monkeypatch):
    gh = DeleteGh(deleted=True)
    folder, runner, docker, released = run_round(machine, paths, monkeypatch, gh, False)
    assert not runner.handed_over and not docker.live
    assert not (folder / ".mulebox-place").exists() and released == [1, 1]


def held_place(machine, paths, monkeypatch, gh, request=None, answer=None):
    folder = add(machine, FakeGh())
    container = place_handover.container_name("place-1", "abcd1234")
    io_dir = folder / "io-abcd1234"
    io_dir.mkdir()
    if request is not None:
        (io_dir / "request.json").write_text(json.dumps(request))
    if answer is not None:
        (io_dir / "answer.json").write_text(json.dumps(answer))
    (folder / ".mulebox-place").write_text(container + "\n")
    docker = LiveDocker([container])
    released = []
    monkeypatch.setattr(place.hooks, "completed", lambda *a, **k: released.append(1))
    monkeypatch.setattr(place, "POLL_S", 0.0)
    runner = place.Place(folder, "build-1", None, paths, stop=threading.Event(), docker=docker,
                         gh=gh, version=lambda: "2.338.2", popen=None)
    return folder, runner, docker, container, io_dir, released


def test_the_next_worker_answers_a_job_and_ends_its_round(machine, paths, monkeypatch):
    folder, runner, docker, container, io_dir, released = held_place(
        machine, paths, monkeypatch, FakeGh(), request={"GITHUB_ACTOR": "alice"})
    decided = []

    def handle(request, **kw):
        decided.append(request)
        docker.live.discard(container)  # granted, the job runs and ends
        return True, "mulebox: slot granted"

    monkeypatch.setattr(place.place_bridge, "handle", handle)
    runner.round()
    assert decided and json.loads((io_dir / "answer.json").read_text())["ok"] is True
    assert released and not (folder / ".mulebox-place").exists()
    assert ("rm", "--force", container) in docker.calls  # the round ended as usual
    assert not [c for c in docker.calls if c and c[0] == "build"]  # no new container yet


def test_an_answered_job_is_not_decided_again(machine, paths, monkeypatch):
    folder, runner, docker, container, io_dir, released = held_place(
        machine, paths, monkeypatch, FakeGh(), request={"GITHUB_ACTOR": "alice"},
        answer={"ok": True, "message": ""})
    monkeypatch.setattr(place.place_bridge, "handle", lambda *a, **k: 1 / 0)
    polls = []

    def inspect_then_end(*args, **kw):
        polls.append(1)
        if len(polls) > 3:
            docker.live.discard(container)
        return LiveDocker.run(docker, *args, **kw)

    monkeypatch.setattr(docker, "run", inspect_then_end)
    runner.round()
    assert released and not (folder / ".mulebox-place").exists()


def test_a_held_container_is_kept_again_when_github_lists_no_runner(machine, paths,
                                                                    monkeypatch):
    folder, runner, docker, container, io_dir, released = held_place(
        machine, paths, monkeypatch, FakeGh(listed=""))
    runner.stop.set()
    runner._watch(place_handover.Held(docker, container), container, io_dir, REPO, None)
    assert runner.handed_over and container in docker.live


def test_held_needs_a_running_container_of_its_own_place(machine, paths):
    folder = add(machine, FakeGh())
    (folder / "io-abcd1234").mkdir()
    for marker in ("mulebox-place-other-abcd1234", "mulebox-place-place-1-../../x"):
        (folder / ".mulebox-place").write_text(marker + "\n")
        assert place_handover.held(LiveDocker([marker]), "place-1", folder, "io-") is None
    name = "mulebox-place-place-1-abcd1234"
    (folder / ".mulebox-place").write_text(name + "\n")
    assert place_handover.held(LiveDocker(), "place-1", folder, "io-") is None  # not running
    assert place_handover.held(LiveDocker([name]), "place-1", folder, "io-") == (
        name, folder / "io-abcd1234")
