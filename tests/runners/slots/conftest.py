"""Runner fixtures: four roots under tmp_path, a real Store and a local coordinator link."""

import pytest

from mulebox.common.config import NodeConfig
from mulebox.coordinator.node import open_local
from mulebox.worker.link import LocalLink
from mulebox.worker.paths import NodePaths

ROOT_KEYS = ("jobs", "cache", "staging", "runners")
RUNNER = "build-1-example-app"


@pytest.fixture
def node(tmp_path):
    roots = {}
    for key in ROOT_KEYS:
        (tmp_path / "roots" / key).mkdir(parents=True)
        roots[key] = str(tmp_path / "roots" / key)
    return NodeConfig(name="build-1", roles=("coordinator", "worker"), roots=roots)


@pytest.fixture
def paths(node):
    return NodePaths.from_config(node.roots)


@pytest.fixture
def local(node):
    store, staging = open_local(node)
    yield store, staging
    store.close()


@pytest.fixture
def store(local):
    return local[0]


@pytest.fixture
def link(local):
    store, staging = local
    return LocalLink(store, staging, cluster_slots=1)


@pytest.fixture
def gh_env():
    return {
        "GITHUB_REPOSITORY": "example-org/example-app", "GITHUB_RUN_ID": "4242",
        "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": "test", "GITHUB_REF_NAME": "main",
        "GITHUB_WORKFLOW": "CI",
        "GITHUB_SERVER_URL": "https://github.com", "RUNNER_NAME": RUNNER,
    }

