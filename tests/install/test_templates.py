"""The config templates validate with mulebox's own loaders; the units have the right keys."""

import configparser
import os

import pytest

from mulebox.common.config import load_client_config, load_node_config
from mulebox.common.roots import Roots

from .helpers import INSTALL_DIR, UNIT_DIR, call_install_function


def render_node(tmp_path, name="build-1", home="/home/alice"):
    text = call_install_function(
        "render_node_config", str(INSTALL_DIR / "node.toml.example"), name, home
    )
    path = tmp_path / "node.toml"
    path.write_text(text, encoding="utf-8")
    return path, text


def test_node_template_renders_and_validates(tmp_path):
    path, text = render_node(tmp_path)
    assert "@" not in text
    node = load_node_config(path)
    assert node.name == "build-1"
    assert node.roles == ("coordinator", "worker")
    assert node.coordinator is None
    assert node.slots == 2
    assert node.roots == {
        key: f"/home/alice/.mulebox/{key}"
        for key in ("jobs", "projects", "cache", "staging", "runners")
    }


def test_rendered_roots_pass_the_safety_checks_once_created(tmp_path):
    home = tmp_path / "home"
    path, _ = render_node(tmp_path, home=str(home))
    node = load_node_config(path)
    for root in node.roots.values():
        os.makedirs(root, mode=0o750)
    Roots.from_config(node.roots)


def test_render_keeps_special_characters_literal(tmp_path):
    _, text = render_node(tmp_path, name="a&b", home="/srv/x&y")
    assert 'name = "a&b"' in text
    assert 'jobs = "/srv/x&y/.mulebox/jobs"' in text


@pytest.mark.parametrize(
    "raw, expected",
    [("build-1", "build-1"), ("My Host!", "My-Host-"), ("-_x", "x"), ("!!!", "mulebox-node")],
)
def test_node_name_from_hostname(tmp_path, raw, expected):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "hostname").write_text(f"#!/bin/sh\nprintf '%s\\n' '{raw}'\n")
    (fake / "hostname").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}
    assert call_install_function("node_name", env=env).strip() == expected


def test_venv_minor_reads_pyvenv_cfg(tmp_path):
    (tmp_path / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.12.3\n")
    assert call_install_function("venv_minor", str(tmp_path)).strip() == "3.12"
    (tmp_path / "pyvenv.cfg").write_text("home = /usr/bin\nversion_info = 3.13.1.final.0\n")
    assert call_install_function("venv_minor", str(tmp_path)).strip() == "3.13"
    assert call_install_function("venv_minor", str(tmp_path / "none")).strip() == ""


def test_client_template_validates():
    client = load_client_config(INSTALL_DIR / "client.toml.example")
    assert client.coordinator == "build-1"
    assert client.remote_bin == "~/.mulebox/bin/mulebox"
    assert client.connect_timeout_s == 10


def read_unit(name):
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read(UNIT_DIR / name, encoding="utf-8")
    return parser


@pytest.mark.parametrize(
    "name, command",
    [
        ("mulebox-coordinator.service", "%h/.mulebox/bin/mulebox coordinator serve"),
        ("mulebox-worker.service", "%h/.mulebox/bin/mulebox worker serve"),
        ("mulebox-dashboard.service", "%h/.mulebox/bin/mulebox dashboard serve"),
    ],
)
def test_unit_has_required_keys(name, command):
    unit = read_unit(name)
    service = unit["Service"]
    assert service["Type"] == "simple"
    assert service["ExecStart"] == command
    assert service["Restart"] == "on-failure"
    assert service["RestartSec"] == "5"
    assert service["Environment"] == "PYTHONUNBUFFERED=1"
    assert unit["Install"]["WantedBy"] == "default.target"
    text = (UNIT_DIR / name).read_text(encoding="utf-8")
    assert "/home/" not in text and "User=" not in text


def test_worker_starts_after_coordinator():
    assert read_unit("mulebox-worker.service")["Unit"]["After"] == "mulebox-coordinator.service"


def test_runner_unit_template():
    unit = read_unit("mulebox-runner@.service")
    service = unit["Service"]
    assert service["WorkingDirectory"] == "%h/.mulebox/runners/%i"
    assert service["ExecStart"] == "%h/.mulebox/runners/%i/run.sh"
    assert service["KillMode"] == "process"
    assert service["KillSignal"] == "SIGTERM"
    assert service["TimeoutStopSec"] == "5min"
    assert service["Restart"] == "always"
    assert service["RestartSec"] == "10"
    assert unit["Install"]["WantedBy"] == "default.target"
    text = (UNIT_DIR / "mulebox-runner@.service").read_text(encoding="utf-8")
    assert "/home/" not in text and "User=" not in text


def test_install_copies_but_does_not_enable_the_runner_template():
    copied = call_install_function("printf '%s\\n' \"${UNITS[@]}\"").split()
    assert "mulebox-runner@.service" in copied
    script = 'ROLES=(coordinator worker); wanted_units'
    assert call_install_function(script).split() == [
        "mulebox-coordinator.service", "mulebox-dashboard.service", "mulebox-worker.service"]


def test_only_a_coordinator_machine_runs_the_dashboard():
    script = 'ROLES=(worker); wanted_units'
    assert call_install_function(script).split() == ["mulebox-worker.service"]
