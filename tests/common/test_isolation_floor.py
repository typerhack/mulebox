"""A node's isolation floor (M23.1 part 3): node.toml, the needs it gives, how the worker and the
coordinator follow it (common/isolation.py, worker/job.py, coordinator/needs.py)."""

import sys

import pytest

from mulebox.common import isolation
from mulebox.common.config import ConfigError, load_node_config, load_project_config
from mulebox.coordinator import needs
from mulebox.worker import live_config
from mulebox.worker.job import floored, uses_docker

ROOTS = ('[roots]\njobs = "/home/alice/.mulebox/jobs"\ncache = "/home/alice/.mulebox/cache"\n'
         'staging = "/home/alice/.mulebox/staging"\nrunners = "/home/alice/.mulebox/runners"\n')
NODE = 'name = "build-1"\nroles = ["coordinator", "worker"]\n'
PROJECT = "project: example-app\njobs:\n  check: make check\n"


def node(tmp_path, extra):
    path = tmp_path / "node.toml"
    path.write_text(NODE + extra + ROOTS, encoding="utf-8")
    return load_node_config(path)


def project(tmp_path, extra=""):
    path = tmp_path / ".mulebox.yml"
    path.write_text(PROJECT + extra, encoding="utf-8")
    return load_project_config(path)


def test_a_node_has_no_floor_unless_it_says_so(tmp_path):
    assert node(tmp_path, "").isolation == "none"


def test_a_linux_node_with_docker_may_isolate_every_job(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    config = node(tmp_path, 'capabilities = ["docker"]\nisolation = "container"\n')
    assert config.isolation == "container"


@pytest.mark.parametrize("platform, extra, words", [
    ("linux", 'isolation = "vm"\n', "must be one of none, container"),
    ("linux", 'isolation = "container"\n', "needs a Linux node with Docker"),
    ("darwin", 'capabilities = ["docker"]\nisolation = "container"\n', "needs a Linux node"),
])
def test_a_floor_the_node_cannot_give_is_a_config_error(tmp_path, monkeypatch, platform, extra,
                                                        words):
    monkeypatch.setattr(sys, "platform", platform)
    with pytest.raises(ConfigError, match=words):
        node(tmp_path, extra)


def test_only_asking_for_none_needs_an_unisolated_node(tmp_path):
    assert project(tmp_path).isolation is None
    assert "unisolated" not in project(tmp_path).all_needs
    assert "unisolated" in project(tmp_path, "isolation: none\n").all_needs
    assert "unisolated" not in project(tmp_path, "isolation: container\n").all_needs


def test_a_node_with_the_floor_isolates_a_job_that_said_nothing():
    claim = {"job_id": "job-1", "needs": ["node"], "env": {}}
    assert floored(claim, "none") is claim
    isolated = floored(claim, "container")
    assert isolated["needs"] == ["node", "isolated"] and uses_docker(isolated)
    assert claim["needs"] == ["node"]  # the claim itself is left as it came
    already = {"job_id": "job-2", "needs": ["isolated"]}
    assert floored(already, "container") is already


def test_asking_for_less_than_every_floor_is_refused_with_the_way_out():
    workers = [{"worker": "build-1", "capabilities": ["docker", "isolated"], "last_seen": 0.0}]
    text = needs.refusal(workers, ["unisolated"])
    assert "unisolated" in text and "isolation: none" in text and "node.toml" in text
    workers.append({"worker": "build-2", "capabilities": ["unisolated"], "last_seen": 0.0})
    assert needs.refusal(workers, ["unisolated"]) is None


def test_the_floor_applies_live(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    before = node(tmp_path, 'capabilities = ["docker"]\n')
    after = node(tmp_path, 'capabilities = ["docker"]\nisolation = "container"\n')
    assert live_config.merged(before, after).isolation == isolation.CONTAINER
