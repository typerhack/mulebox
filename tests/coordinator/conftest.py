"""Coordinator fixtures: four sibling roots under tmp_path, a Staging and an open Store."""

import pytest

from mulebox.common.config import NodeConfig
from mulebox.common.safepath import Roots
from mulebox.coordinator.staging import Staging
from mulebox.coordinator.store import Store

ROOT_NAMES = ("jobs", "cache", "staging", "runners")


@pytest.fixture
def root_map(tmp_path):
    roots = {}
    for name in ROOT_NAMES:
        path = tmp_path / "roots" / name
        path.mkdir(parents=True)
        roots[name] = str(path)
    return roots


@pytest.fixture
def node(root_map):
    return NodeConfig(name="build-1", roles=("coordinator", "worker"), roots=root_map)


@pytest.fixture
def staging(root_map):
    return Staging(Roots.from_config(root_map), root_map["staging"])


@pytest.fixture
def store(staging):
    with Store(staging.db_path).open() as opened:
        yield opened
