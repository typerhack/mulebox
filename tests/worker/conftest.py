"""Shared worker fixtures: four roots under tmp_path, a snapshot, a fake coordinator link."""

import pytest

from mulebox.common.config import NodeConfig
from mulebox.worker.paths import NodePaths

from .fakes import FakeLink, make_tar

ROOT_KEYS = ("jobs", "cache", "staging", "runners")


@pytest.fixture
def roots_config(tmp_path):
    config = {}
    for key in ROOT_KEYS:
        (tmp_path / key).mkdir()
        config[key] = str(tmp_path / key)
    return config


@pytest.fixture
def paths(roots_config):
    return NodePaths.from_config(roots_config)


@pytest.fixture
def node(roots_config):
    return NodeConfig(name="build-1", roles=("coordinator", "worker"), roots=roots_config,
                      capabilities=("node",))


@pytest.fixture
def snapshot(tmp_path):
    (tmp_path / "upload").mkdir()
    return make_tar(tmp_path / "upload" / "snap.tar.gz",
                    {"README.md": "hello\n", "src/app.sh": "echo app\n"})


@pytest.fixture
def ignored_snapshot(snapshot):
    make_tar(snapshot, {".gitignore": "ignored.txt\n", "README.md": "hello\n"})
    return snapshot


@pytest.fixture
def fake_link(snapshot):
    return FakeLink(snapshot)
