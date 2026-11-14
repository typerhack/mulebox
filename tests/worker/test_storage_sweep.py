"""The worker's own disk sweep (worker/storage_sweep.py) and what it measures
(worker/storage_scan.py), on real project folders made the way jobs make them."""

import os
import time
from dataclasses import replace

import pytest

from mulebox.common.ids import new_id
from mulebox.common.storage_policy import StoragePolicy
from mulebox.worker import project_home as home
from mulebox.worker import storage_scan, storage_sweep
from mulebox.worker.agent import Agent
from mulebox.worker.job import ActiveJob

from .conftest import make_tar

DAY = 86400


class NoDocker:
    def lines(self, *args, **kwargs):
        from mulebox.worker.docker import DockerError
        raise DockerError("no docker here")


@pytest.fixture(autouse=True)
def no_settle(monkeypatch):
    monkeypatch.setattr(storage_sweep, "SETTLE_S", 0.0)


@pytest.fixture
def send(paths, tmp_path):
    def run(branch, days_ago, project="example-app", size=1000):
        snapshot = tmp_path / "snapshot.tar.gz"
        make_tar(snapshot, {"README.md": "hello\n"})
        tree = home.prepare(paths, project, branch, new_id("job"), snapshot).tree
        (tree / "node_modules").mkdir(exist_ok=True)
        (tree / "node_modules" / "dep.js").write_text("x" * size)
        when = time.time() - days_ago * DAY
        log = paths.project_home(project) / "repo.git" / "logs" / "refs" / "heads" / f"tree-{tree.name}"
        os.utime(log, (when, when))
        return tree
    return run


@pytest.fixture
def worker(node, fake_link, paths):
    def make(**policy):
        made = Agent(replace(node, storage=StoragePolicy(**policy)), fake_link, None, paths,
                     docker=NoDocker())
        return made
    return make


def test_last_use_is_the_folders_last_job(paths, send):
    tree = send("main", 3)
    used = storage_scan.last_used(paths, "example-app", tree.name)
    assert time.time() - used == pytest.approx(3 * DAY, abs=60)
    assert storage_scan.last_used(paths, "example-app", "never-made") is None


def test_measure_counts_a_hard_linked_file_once_across_folders(paths, send):
    first = send("main", 1, size=50_000)
    second = send("feature/a", 1, size=10)
    os.link(first / "node_modules" / "dep.js", second / "node_modules" / "linked.js")
    cache = paths.package_cache("example-app", "pnpm")
    cache.mkdir(parents=True)
    os.link(first / "node_modules" / "dep.js", cache / "store.js")
    folders, held = storage_scan.measure(paths)
    total = sum(f.size for f in folders) + held["projects"]["example-app"]["caches"]
    assert 50_000 <= total < 60_000  # the 50 kB file once, not three times
    assert {f.folder for f in folders} == {first.name, second.name}


def test_docker_totals_are_read_from_docker_system_df():
    class Fake:
        def lines(self, *args, **kwargs):
            return ['{"Type":"Images","TotalCount":"99","Size":"9.809GB","Reclaimable":"7.313GB (74%)"}',
                    '{"Type":"Build Cache","TotalCount":"171","Size":"9.746GB","Reclaimable":"6.01GB"}',
                    '{"Type":"Containers","TotalCount":"2","Size":"106.5kB","Reclaimable":"0B (0%)"}']
    found = storage_scan.docker(Fake())
    assert found["images"] == {"size": 9_809_000_000, "reclaimable": 7_313_000_000, "count": 99}
    assert found["build_cache"]["reclaimable"] == 6_010_000_000
    assert found["containers"]["size"] == 106_500
    assert storage_scan.docker(NoDocker()) is None and storage_scan.docker(None) is None


def test_a_sweep_removes_old_folders_and_keeps_the_latest_kept_and_running(worker, paths, send):
    latest, old, kept, busy = (send("main", 1), send("pr/1", 20), send("pr/2", 30),
                               send("pr/3", 40))
    agent = worker()
    agent._take_replies({"storage_keeps": [{"project": "example-app", "branch": "pr/2"}]})
    job = ActiveJob(new_id("job"), "att-1", "example-app", tailer=None, started_at=0.0,
                    last_heartbeat=0.0)
    job.branch = "pr/3"
    agent.active[job.job_id] = job
    agent._sweep()
    assert latest.is_dir() and kept.is_dir() and busy.is_dir() and not old.exists()
    report = agent._storage_fields()["storage"]
    fates = {f["folder"]: f["fate"] for f in report["projects"][0]["folders"]}
    assert fates == {latest.name: "latest", kept.name: "kept", busy.name: "running"}
    assert report["removed"]["count"] == 1 and report["policy"]["unused_days"] == 7
    assert report["disk"]["total"] > 0 and report["disk"]["reserve"] > 0
    assert agent._storage_fields() == {"storage": report}  # offered until a reply comes
    agent._take_replies({})
    assert agent._storage_fields() == {}  # sent once


def test_a_sweep_with_nothing_old_removes_nothing_and_says_when(worker, send):
    send("main", 1)
    newer = send("pr/1", 2)
    agent = worker(unused_days=3)
    agent._sweep()
    assert newer.is_dir()
    folders = agent._storage_fields()["storage"]["projects"][0]["folders"]
    stays = next(f for f in folders if f["folder"] == newer.name)
    assert stays["fate"] == "stays" and stays["removed_in"] == pytest.approx(1.0, abs=0.01)


def test_claims_stop_only_while_folders_are_removed(worker, send, monkeypatch):
    send("main", 1)
    send("pr/1", 20)
    agent = worker()
    seen = []
    real = storage_sweep.project_disk.remove_worktree

    def watch(*args, **kwargs):
        seen.append(agent._housekeeping(time.time()))
        return real(*args, **kwargs)
    monkeypatch.setattr(storage_sweep.project_disk, "remove_worktree", watch)
    agent._store()["next"] = float("inf")  # no sweep of its own from _housekeeping
    agent._sweep()
    assert seen == [True]
    assert agent._housekeeping(time.time()) is False


def test_a_sweep_is_due_an_hour_after_the_last_or_when_space_runs_short(worker, monkeypatch):
    agent = worker()
    state = agent._store()
    assert agent._sweep_due(state) is False  # a minute after start, not before
    state["next"] = 0.0
    assert agent._sweep_due(state) is True
    state["next"], state["last"], state["low_check"] = float("inf"), 0.0, 0.0
    agent.node = replace(agent.node, storage=StoragePolicy(keep_free="90%"))
    assert agent._sweep_due(state) is True  # this disk is surely not 90% free
    state["last"] = time.time()
    state["low_check"] = 0.0
    assert agent._sweep_due(state) is False  # not again within LOW_EVERY_S
