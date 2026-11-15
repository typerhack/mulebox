"""Slimming idle branch folders (worker/slim.py): the plan (storage_rules.py), the sweep
(storage_sweep.py, storage_clearing.py) on real folders made the way jobs make them, and the
next job running `setup` again."""

import os
import time

from mulebox.common.ids import new_id
from mulebox.common.storage_policy import StoragePolicy
from mulebox.common.tree_size import freed
from mulebox.worker import project_home as home
from mulebox.worker import slim, storage_rules
from mulebox.worker.storage_rules import Folder

from .conftest import make_tar
from .test_storage_sweep import DAY, no_settle, worker  # noqa: F401

HOUR = 3600
NOW = 1_000_000.0


def _job(paths, tmp_path, branch, hours_ago, project="example-app"):
    snapshot = tmp_path / "snapshot.tar.gz"
    make_tar(snapshot, {"README.md": "hello\n", ".gitignore": "node_modules/\n.next/\n.env\n"})
    tree = home.prepare(paths, project, branch, new_id("job"), snapshot).tree
    for name, size in (("node_modules/dep/index.js", 4000), (".next/cache/a.bin", 6000),
                       (".env", 10), ("notes.txt", 7)):
        (tree / name).parent.mkdir(parents=True, exist_ok=True)
        (tree / name).write_text("x" * size)
    home.remember_setup(paths, project, branch, "key")
    when = time.time() - hours_ago * HOUR
    log = paths.project_home(project) / "repo.git" / "logs" / "refs" / "heads" / f"tree-{tree.name}"
    os.utime(log, (when, when))
    return tree


def test_a_folder_idle_past_slim_hours_is_due_never_the_latest_kept_or_running():
    folders = [Folder("app", "new", 10, NOW - 1 * HOUR), Folder("app", "idle", 10, NOW - 13 * HOUR),
               Folder("app", "kept", 10, NOW - 20 * HOUR), Folder("app", "busy", 10, NOW - 30 * HOUR),
               Folder("app", "fresh", 10, NOW - 2 * HOUR),
               Folder("app", "done", 10, NOW - 40 * HOUR, slim="done")]
    plan = storage_rules.plan(folders, StoragePolicy(), NOW, {("app", "kept")}, {("app", "busy")})
    assert [f.folder for f in plan.to_slim] == ["idle"]
    slims = {f.folder: f.slim for f in plan.folders}
    assert slims == {"new": None, "idle": "due", "kept": None, "busy": None, "fresh": None,
                     "done": "done"}
    off = storage_rules.plan(folders, StoragePolicy(slim_hours=0), NOW, set(), set())
    assert off.to_slim == []


def test_freed_counts_a_hard_linked_file_only_when_every_link_goes(tmp_path):
    store, a, b = tmp_path / "store", tmp_path / "a", tmp_path / "b"
    for folder in (store, a, b):
        folder.mkdir()
    (store / "f").write_text("x" * 100)
    os.link(store / "f", a / "f")
    (a / "own").write_text("y" * 10)
    (b / "g").write_text("z" * 50)
    os.link(b / "g", b / "g2")
    assert freed([a]) == 10  # the store keeps its file
    assert freed([b]) == 50  # both links go
    assert freed([a, store]) == 110


def test_a_sweep_slims_an_idle_folder_and_its_next_job_runs_setup_again(worker, paths, tmp_path):
    _job(paths, tmp_path, "main", 1)
    idle = _job(paths, tmp_path, "pr/1", 20)
    agent = worker()
    agent._sweep()
    assert (idle / "README.md").is_file() and (idle / "notes.txt").is_file()
    assert not (idle / "node_modules").exists() and not (idle / ".next").exists()
    assert not (idle / ".env").exists()
    assert slim.is_slim(paths, "example-app", idle.name)
    assert not home.is_current(paths, "example-app", "pr/1", "key")
    report = agent._store()["report"]
    assert report["sweep"]["slimmed"] == 1 and report["sweep"]["slimmed_bytes"] == 10010
    row = next(f for f in report["projects"][0]["folders"] if f["folder"] == idle.name)
    assert row["slim"] == "done" and row["fate"] == "stays"
    agent._sweep()  # slimmed once only
    assert agent._store()["report"]["sweep"]["slimmed"] == 0
    snapshot = tmp_path / "again.tar.gz"
    make_tar(snapshot, {"README.md": "hello\n", ".gitignore": "node_modules/\n.next/\n.env\n"})
    home.prepare(paths, "example-app", "pr/1", new_id("job"), snapshot)
    assert not slim.is_slim(paths, "example-app", idle.name)


def test_a_due_folder_says_what_slimming_frees_before_it_runs(worker, paths, tmp_path):
    _job(paths, tmp_path, "main", 1)
    idle = _job(paths, tmp_path, "pr/1", 20)
    agent = worker(auto_clean=False)
    agent._sweep()
    row = next(f for f in agent._store()["report"]["projects"][0]["folders"]
               if f["folder"] == idle.name)
    assert (row["slim"], row["frees"]) == ("due", 10010)
    assert (idle / "node_modules").is_dir()  # with the cleanup off, only said
