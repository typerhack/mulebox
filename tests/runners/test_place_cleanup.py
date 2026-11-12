"""An isolated runner's cleanup: whatever fails, a round and a removal leave nothing behind."""

import threading

import pytest

from mulebox.runners import layout, manage, place, place_keeper, place_manage
from mulebox.runners.manage import RunnerError

from .test_place_parts import REPO, FakeDocker
from .test_place_run import FakeGh, add, make_place


def test_a_failing_round_still_cleans_up(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    monkeypatch.setattr(place.hooks, "completed", lambda *a, **k: 0)
    gh, docker = FakeGh(), FakeDocker()

    class Broken:
        def __init__(self):
            self.stdin = self

        def write(self, data):
            raise BrokenPipeError("the docker client died")

        def poll(self):
            return 1

    runner = place.Place(folder, "build-1", None, paths, stop=threading.Event(), docker=docker,
                         gh=gh, version=lambda: "2.338.2", popen=lambda argv, **_: Broken())
    with pytest.raises(BrokenPipeError):
        runner.round()
    assert [c for c in docker.calls if c[:2] == ("rm", "--force")]
    assert [c for c in gh.calls if "DELETE" in c]  # the unused runner is gone from GitHub
    assert not (folder / ".mulebox-place").exists()


def test_removing_stops_new_rounds(machine, paths):
    folder = add(machine, FakeGh())
    layout.write_meta(paths, folder, {**layout.read_meta(folder), "removing": True})
    assert place_keeper.place_folders(paths) == []
    with pytest.raises(place.place_container.PlaceError):
        make_place(paths, folder, FakeGh()).round()


def test_remove_waits_for_the_round_to_end(machine, paths):
    folder = add(machine, FakeGh())
    (folder / ".mulebox-round").write_text("1\n")
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        if len(naps) == 3:
            (folder / ".mulebox-round").unlink()  # the worker ended its round

    place_manage.remove_isolated(machine, "place-1", gh=FakeGh(), docker=FakeDocker(),
                                 sleep=sleep)
    assert len(naps) == 3 and not folder.exists()


def test_files_of_the_container_user_are_taken_back_first(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    calls = []
    real = place.remove_tree

    def remove_tree(path, roots):
        calls.append(("remove", path.name))
        if len([c for c in calls if c[0] == "remove"]) == 1:
            raise PermissionError("owned by uid 1001")
        real(path, roots)

    monkeypatch.setattr(place, "remove_tree", remove_tree)
    monkeypatch.setattr(place.reclaim, "reclaim_runner_dir",
                        lambda docker, paths_, path, worker: calls.append(("reclaim", path.name)))
    make_place(paths, folder, FakeGh())._remove(folder / "_diag")
    assert calls == [("remove", "_diag"), ("reclaim", "place-1"), ("remove", "_diag")]


def test_one_failing_cleanup_step_skips_none_of_the_others(machine, paths, monkeypatch):
    folder = add(machine, FakeGh())
    released = []
    monkeypatch.setattr(place.hooks, "completed", lambda env, *a, **k: released.append(env))
    monkeypatch.setattr(place, "POLL_S", 0.0)

    def delete(*a, **k):
        raise TimeoutError("GitHub did not answer")

    monkeypatch.setattr(place.jit, "delete", delete)
    make_place(paths, folder, FakeGh(), ask=False).round()
    assert len(released) == 2  # before, and after despite the failed delete
    assert not (folder / ".mulebox-place").exists() and not (folder / ".mulebox-round").exists()


def test_remove_refuses_to_delete_under_a_running_round(machine, paths):
    folder = add(machine, FakeGh())
    (folder / ".mulebox-round").write_text("1\n")
    with pytest.raises(RunnerError, match="again"):
        place_manage.remove_isolated(machine, "place-1", gh=FakeGh(), docker=FakeDocker(),
                                     wait_s=0.0, sleep=lambda s: None)
    assert folder.exists() and layout.read_meta(folder)["removing"] is True


def test_a_group_grows_and_goes_as_one(machine, paths):
    first = add(machine, FakeGh())
    (first / "_diag").mkdir()  # the first place's state stays when the group grows
    second = add(machine, FakeGh(), count=2)
    assert second.name == "place-1-2" and (first / "_diag").is_dir()
    assert layout.read_meta(second)["group"] == "place-1"
    assert sorted(f.name for f in place_keeper.place_folders(paths)) == ["place-1", "place-1-2"]
    assert manage.find_by_repo(machine, REPO) == "place-1"  # the group, by its first
    place_manage.remove_isolated(machine, "place-1", gh=FakeGh(), docker=FakeDocker())
    assert not first.exists() and not second.exists()
