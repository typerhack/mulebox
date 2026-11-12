"""An isolated runner end to end with doubles: add, one round per job, the keeper, remove."""

import io
import json
import subprocess
import threading
from pathlib import Path

import pytest

from mulebox.common.config import ClientConfig
from mulebox.runners import layout, manage, place, place_keeper, place_manage
from mulebox.runners import github as gh_side
from mulebox.runners.manage import RunnerError
from mulebox.runners.names import RunnerUsageError

from .test_place_parts import CONFIG, REPO, FakeDocker


class FakeGh:
    def __init__(self, admin="true", visibility="public", listed=""):
        self.calls, self.admin, self.visibility, self.listed = [], admin, visibility, listed
        self.next_id = 100

    def __call__(self, argv):
        self.calls.append(list(argv))
        out = ""
        if argv[-1].startswith('"\\(.permissions.admin)'):
            out = f"{self.admin} {self.visibility}\n"
        elif any("generate-jitconfig" in a for a in argv):
            self.next_id += 1
            out = json.dumps({"runner": {"id": self.next_id}, "encoded_jit_config": CONFIG})
        elif "--paginate" in argv:
            out = self.listed
        return subprocess.CompletedProcess(argv, 0, out, "")


def add(machine, gh, docker=None, **kw):
    return place_manage.add_isolated(machine, REPO, name=kw.get("name", "place-1"),
                                     labels=("mulebox",), actors=("alice",), gh=gh,
                                     docker=docker or FakeDocker(), version=lambda: "2.338.2")


def test_add_writes_meta_and_builds_the_image(machine, paths):
    docker = FakeDocker()
    folder = add(machine, FakeGh(), docker)
    meta = layout.read_meta(folder)
    assert meta["isolated"] is True and meta["public"] is True
    assert meta["actors"] == ["alice"] and meta["repo"] == REPO
    assert any(c[0] == "build" for c in docker.calls)
    assert place_keeper.place_folders(paths) == [folder]
    assert manage.list_runners(machine)[0].state == "isolated"


def test_add_refuses_without_admin_or_actors(machine):
    with pytest.raises(RunnerError, match="admin"):
        add(machine, FakeGh(admin="false"))
    with pytest.raises(RunnerUsageError):
        place_manage.add_isolated(machine, REPO, name="p", labels=(), actors=(), gh=FakeGh())
    add(machine, FakeGh())
    with pytest.raises(RunnerUsageError, match="already exists"):
        add(machine, FakeGh())


def test_remove_cleans_containers_runners_volume_and_folder(machine, paths):
    folder = add(machine, FakeGh())
    gh = FakeGh(listed="7 place-1-aaaa1111\n8 place-10-bbbb2222\n")
    docker = FakeDocker(containers=["c9"])
    assert place_manage.is_isolated(machine, "place-1")
    place_manage.remove_isolated(machine, "place-1", gh=gh, docker=docker)
    assert not folder.exists()
    deleted = [a for c in gh.calls if "DELETE" in c for a in c if "/runners/" in a]
    assert deleted == [f"repos/{REPO}/actions/runners/7"]
    assert ("rm", "--force", "c9") in docker.calls
    assert ("volume", "rm", "--force", "mulebox-tools-place-1") in docker.calls


class FakeProc:
    """The container: asks the hook question, then ends when answered (or never asks)."""

    def __init__(self, io_dir, ask=True):
        self.io_dir, self.ask, self.stdin, self.code = io_dir, ask, io.BytesIO(), None
        self.stdin.close = lambda: None
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self.ask and self.polls == 1:
            (self.io_dir / "request.json").write_text(json.dumps({
                "GITHUB_REPOSITORY": REPO, "GITHUB_ACTOR": "alice",
                "GITHUB_TRIGGERING_ACTOR": "alice", "GITHUB_EVENT_NAME": "push"}))
            (self.io_dir / "event.json").write_text("{}")
        if not self.ask or (self.io_dir / "answer.json").exists() or self.polls > 200:
            self.code = 0
        return self.code

    def wait(self, timeout=None):
        self.code = 0
        return 0


def make_place(paths, folder, gh, ask=True, decided=None):
    procs = []

    def popen(argv, **_):
        mount = next(v for v in argv if v.endswith(":/mulebox-io"))
        procs.append((argv, FakeProc(Path(mount.rsplit(":", 1)[0]), ask)))
        return procs[-1][1]

    found = place.Place(folder, "build-1", None, paths, stop=threading.Event(),
                        docker=FakeDocker(), gh=gh, version=lambda: "2.338.2", popen=popen)
    found.procs = procs
    return found


def test_a_round_answers_the_job_and_releases(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    released = []
    monkeypatch.setattr(place.hooks, "completed", lambda env, *a, **k: released.append(env))
    monkeypatch.setattr(place, "POLL_S", 0.0)
    granted = []

    def handle(request, **kw):
        granted.append(request)
        return True, "mulebox: slot granted"

    monkeypatch.setattr(place.place_bridge, "handle", handle)
    gh = FakeGh()
    runner = make_place(paths, folder, gh)
    runner.round()
    [(argv, proc)] = runner.procs
    assert proc.stdin.getvalue() == (CONFIG + "\n").encode()  # the config on stdin only
    assert CONFIG not in " ".join(argv)
    assert granted and granted[0]["GITHUB_ACTOR"] == "alice"
    assert json.loads((proc.io_dir / "answer.json").read_text())["ok"] is True
    assert released == [{"RUNNER_NAME": "place-1"}] * 2  # before the round (a left slot), after
    assert not (folder / ".mulebox-place").exists()
    assert not [c for c in gh.calls if "DELETE" in c]  # it got its job: GitHub removes it


def test_a_round_with_no_job_deletes_its_runner(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    monkeypatch.setattr(place.hooks, "completed", lambda *a, **k: 0)
    monkeypatch.setattr(place, "POLL_S", 0.0)
    gh = FakeGh()
    make_place(paths, folder, gh, ask=False).round()
    assert [c for c in gh.calls if "DELETE" in c]


def test_a_round_refuses_a_folder_that_is_not_isolated(paths):
    folder = paths.runners / "plain"
    folder.mkdir()
    layout.write_meta(paths, folder, {"repo": REPO})
    with pytest.raises(place.place_container.PlaceError):
        make_place(paths, folder, FakeGh()).round()


def test_keeper_starts_and_stops_threads(machine, paths):
    made = []

    class Stub:
        def __init__(self, folder, *a, stop):
            self.stop = stop
            made.append(folder.name)

        def run(self):
            self.stop.wait(5)

    clock = iter(range(0, 1000, 20)).__next__
    keeper = place_keeper.PlaceKeeper("build-1", None, paths, make=Stub, clock=clock)
    folder = add(machine, FakeGh())
    keeper.sync()
    assert made == ["place-1"] and keeper.running["place-1"][0].is_alive()
    place_manage.remove_isolated(machine, "place-1", gh=FakeGh(), docker=FakeDocker())
    keeper.sync()
    assert keeper.running == {} and not folder.exists()
    keeper.shutdown()


def test_register_isolated_sends_no_token_and_allows_public():
    seen = []

    def stream(target, argv, *, stdin=None, connect_timeout_s=10):
        seen.append((argv, stdin))
        yield b"ok\n"

    gh_calls = []

    def run(argv):
        gh_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "alice\n", "")

    gh_side.register(ClientConfig(coordinator="build-1"), REPO, isolated=True, run=run,
                     stream=stream, out=io.StringIO())
    [(argv, stdin)] = seen
    assert "--isolated" in argv and argv[argv.index("--actors") + 1] == "alice"
    assert stdin == b"\n"
    assert not [c for c in gh_calls if any("registration-token" in a for a in c)]
    assert not [c for c in gh_calls if c[-1] == ".visibility"]


def test_a_slot_still_waited_for_is_given_up_with_its_container(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    monkeypatch.setattr(place.hooks, "completed", lambda *a, **k: 0)
    monkeypatch.setattr(place, "POLL_S", 0.0)
    waits = []

    def started(env, worker, link, paths_, *, sleep, out):
        while True:  # the coordinator never grants it
            waits.append(1)
            sleep(0.01)

    monkeypatch.setattr(place.hooks, "started", started)
    monkeypatch.setattr(place.guard, "refusal", lambda env, meta: None)
    runner = make_place(paths, folder, FakeGh())
    runner.round()  # the container ends after 200 polls
    answer = json.loads((runner.procs[0][1].io_dir / "answer.json").read_text())
    assert answer["ok"] is False and "ended before it got a slot" in answer["message"]
    assert waits


def test_each_round_has_its_own_io_folder(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    monkeypatch.setattr(place.hooks, "completed", lambda *a, **k: 0)
    monkeypatch.setattr(place, "POLL_S", 0.0)
    runner = make_place(paths, folder, FakeGh(), ask=False)
    runner.round()
    first = runner.procs[0][1].io_dir
    (first / "answer.json").write_text(json.dumps({"ok": True}))  # a late answer for round 1
    runner.round()
    second = runner.procs[1][1].io_dir
    assert first != second and not first.exists()
    assert not (second / "answer.json").exists()  # the next job never sees it

