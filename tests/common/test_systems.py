"""Which system a job runs on (common/systems.py) and `os:` in .mulebox.yml."""

import pytest

from mulebox.common import systems
from mulebox.common.config import ConfigError, load_project_config

MINIMAL = "project: example-app\njobs:\n  check: pnpm check\n"


def project(tmp_path, extra=""):
    path = tmp_path / ".mulebox.yml"
    path.write_text(MINIMAL + extra, encoding="utf-8")
    return load_project_config(path)


def runs_on(tmp_path, extra=""):
    config = project(tmp_path, extra)
    return systems.with_system(config.all_needs, config.system)


def test_the_client_sends_os_as_written_and_adds_no_need(tmp_path):
    assert project(tmp_path).all_needs == () and project(tmp_path).system is None
    assert project(tmp_path, "os: any\n").system == "any"


def test_a_job_runs_on_linux_unless_it_pins_apples_tools(tmp_path):
    assert runs_on(tmp_path) == ["linux"]
    assert runs_on(tmp_path, "toolchain:\n  xcode: '27.2'\n") == ["xcode", "macos"]
    assert runs_on(tmp_path, "needs: [simulator]\n") == ["simulator", "macos"]


def test_os_says_where_or_lets_it_go_anywhere(tmp_path):
    assert runs_on(tmp_path, "os: macos\n") == ["macos"]
    assert runs_on(tmp_path, "os: any\nneeds: [docker]\n") == ["docker"]
    with pytest.raises(ConfigError, match="linux, macos, any"):
        project(tmp_path, "os: windows\n")


def test_a_worker_offers_its_own_system():
    assert systems.offered("darwin") == ("macos",) and systems.offered("linux") == ("linux",)
    assert systems.offered("win32") == ()


def test_an_old_worker_counts_by_what_it_offers():
    assert systems.inferred(["node"]) == ["node", "linux"]
    assert systems.inferred(["xcode"]) == ["xcode", "macos"]
    assert systems.inferred(["macos", "node"]) == ["macos", "node"]


def test_the_coordinator_cannot_be_in_dev_mode(tmp_path):
    from mulebox.common.config import node_config_from
    data = {"name": "build-1", "roles": ["coordinator", "worker"], "dev": True,
            "roots": {name: str(tmp_path / name) for name in ("jobs", "cache", "staging", "runners")}}
    with pytest.raises(ConfigError, match="for other nodes"):
        node_config_from(tmp_path / "node.toml", data)
    worker = {**data, "roles": ["worker"], "coordinator": "build-1"}
    assert node_config_from(tmp_path / "node.toml", worker).dev is True
