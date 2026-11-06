"""`mulebox project-home` from argument to folders, in temporary roots only."""

import argparse
import io
import tarfile

import pytest

from mulebox.common.ids import new_id
from mulebox.coordinator import holds, uploads
from mulebox.coordinator.errors import Conflict
from mulebox.worker import project_commands as commands
from mulebox.worker import project_home as home
from mulebox.worker.paths import NodePaths

from .helpers import claimed, queued, snapshot, submit

NOW = 1_000_000_000.0


@pytest.fixture
def machine(node, store, staging, tmp_path, monkeypatch):
    paths = NodePaths.from_config(node.roots)
    monkeypatch.setattr(commands, "_load", lambda args: (node, paths))
    monkeypatch.setattr(commands, "_local", lambda n: (store, staging))
    monkeypatch.setattr(commands.time, "time", lambda: NOW)

    def tree(branch):
        tar = tmp_path / "snapshot.tar.gz"
        with tarfile.open(tar, "w:gz") as out:
            info = tarfile.TarInfo("README.md")
            info.size = 6
            out.addfile(info, io.BytesIO(b"hello\n"))
        return home.prepare(paths, "example-app", branch, new_id("job"), tar).tree

    return tree


def clean(yes):
    return commands._clean(argparse.Namespace(days=14, yes=yes))


def reset(branch=None, yes=True, project="example-app"):
    return commands._reset(argparse.Namespace(project=project, branch=branch, caches=False,
                                              yes=yes))


def jobs(store, staging):
    queued(store, staging, now=NOW - 86400 * 30, branch="old")
    queued(store, staging, now=NOW - 86400, branch="main")


def test_clean_lists_until_yes(machine, store, staging, capsys):
    old, main = machine("old"), machine("main")
    jobs(store, staging)
    assert clean(yes=False) == 0
    assert old.is_dir() and "would remove 1" in capsys.readouterr().out
    assert clean(yes=True) == 0
    assert not old.exists() and main.is_dir()
    with store.read() as conn:
        assert not holds.held(conn, 0.0)


def test_reset_lists_until_yes(machine):
    tree = machine("main")
    assert reset(yes=False) == 0
    assert tree.is_dir()


def test_reset_of_a_branch_leaves_the_rest(machine):
    main, other = machine("main"), machine("feature/a")
    assert reset("feature/a") == 0
    assert main.is_dir() and not other.exists()


def test_reset_removes_the_project_and_its_base(machine, store, staging):
    tree = machine("main")
    data, digest = snapshot()
    job_id = submit(store, staging)
    uploads.accept_upload(store, staging, job_id, digest, io.BytesIO(data), NOW)
    staging.remove_upload(job_id)
    assert reset() == 0
    assert not tree.exists() and staging.open_base("example-app") is None


def test_reset_is_refused_while_a_job_runs(machine, store, staging):
    tree = machine("main")
    claimed(store, staging, now=NOW)
    with pytest.raises(Conflict, match="running"):
        reset()
    assert tree.is_dir()
