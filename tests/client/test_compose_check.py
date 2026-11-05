"""What `mulebox doctor` can tell from compose files, with the worker's own policy."""

import json
import os
import shutil
import subprocess

import pytest

from mulebox.client import compose_check, compose_yaml
from mulebox.client.compose_check import findings, model_of

FILE = "docker-compose.yml"


def one(root, text, *more):
    (root / FILE).write_text(text)
    names = [FILE]
    for index, extra in enumerate(more):
        names.append(f"extra-{index}.yml")
        (root / names[-1]).write_text(extra)
    found = findings(tuple(names), root)
    assert len(found) == 1
    return found[0]


def refused(root, text, *more):
    found = one(root, text, *more)
    assert found.level == "fail" and found.topic == "compose", found
    return found.text


def service(*lines):
    body = "".join(f"    {line}\n" for line in lines)
    return f"services:\n  app:\n    image: x\n{body}"


def test_no_compose_files_says_nothing(tmp_path):
    assert findings((), tmp_path) == []


def test_a_plain_file_is_fine(tmp_path):
    found = one(tmp_path, service("volumes: [./src:/app, data:/data]") + "volumes:\n  data:\n")
    assert found.level == "ok" and FILE in found.text


@pytest.mark.parametrize("section", ["volumes", "networks"])
def test_an_external_resource_in_use_is_refused(tmp_path, section):
    use = "volumes: [shared:/d]" if section == "volumes" else "networks: [shared]"
    text = service(use) + f"{section}:\n  shared:\n    external: true\n"
    assert "shared is external" in refused(tmp_path, text)


def test_an_external_default_network_is_refused(tmp_path):
    assert "default is external" in refused(
        tmp_path, service() + "networks:\n  default:\n    external: true\n")


def test_what_no_service_uses_is_not_in_the_model(tmp_path):
    """`docker compose config` drops it, so the worker would not refuse it."""
    text = service() + ("volumes:\n  old:\n    external: true\n"
                        "secrets:\n  old:\n    external: true\n")
    assert one(tmp_path, text).level == "ok"


def test_a_service_of_an_inactive_profile_is_not_judged(tmp_path):
    text = service("volumes_from: [tools]") + (
        "  tools:\n    image: x\n    privileged: true\n    profiles: [debug]\n")
    assert one(tmp_path, text).level == "ok"


def test_refusals_come_from_the_policy(tmp_path):
    assert "network_mode" in refused(tmp_path, service("network_mode: host"))
    assert "privileged" in refused(tmp_path, service("privileged: true"))


@pytest.mark.parametrize("volume, reason", [
    ("/var/run/docker.sock:/var/run/docker.sock:ro", "socket"),
    ("/data:/data", "writable"),
    ("../sibling:/data", "writable"),
    ("/opt:/opt:ro,z", "relabels"),
])
def test_short_volumes_are_read(tmp_path, volume, reason):
    assert reason in refused(tmp_path, service(f"volumes: ['{volume}']"))


def test_a_long_form_volume_is_read(tmp_path):
    text = service("volumes:", "  - type: bind", "    source: /data", "    target: /d")
    assert "/data" in refused(tmp_path, text)


def test_relative_paths_start_at_the_first_files_folder(tmp_path):
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "c.yml").write_text(service("volumes: [../src:/app]"))
    assert findings(("docker/c.yml",), tmp_path)[0].level == "ok"
    (tmp_path / "docker" / "c.yml").write_text(service("volumes: [../../up:/app]"))
    assert "../up" in findings(("docker/c.yml",), tmp_path)[0].text


def test_a_later_file_wins(tmp_path):
    assert one(tmp_path, service("privileged: true"), service("privileged: false")).level == "ok"
    assert "privileged" in refused(tmp_path, service(), service("privileged: true"))


def test_a_later_file_replaces_a_mount_with_the_same_target(tmp_path):
    assert one(tmp_path, service("volumes: ['/data:/d']"),
               service("volumes: ['./data:/d']")).level == "ok"


def test_a_value_with_a_variable_is_left_to_the_machine(tmp_path):
    text = service("volumes: ['${DATA:-/data}:/d']", "network_mode: $MODE")
    assert one(tmp_path, text).level == "ok"


def test_a_doubled_dollar_is_no_variable(tmp_path):
    assert model_of({"services": {"a": {"command": "echo $$HOME"}}}, FILE)[
        "services"]["a"]["command"] == "echo $$HOME"


@pytest.mark.parametrize("text", ["services: [", "- a\n- b\n", "services:\n  a: !nonsense x\n"])
def test_a_file_that_cannot_be_read_is_a_warning(tmp_path, text):
    found = one(tmp_path, text)
    assert found.level == "warn" and "could not check" in found.text


def test_a_wrong_shape_is_a_warning(tmp_path):
    assert one(tmp_path, "services:\n  app: 12\n").level == "warn"


@pytest.mark.parametrize("text", [
    service() + "include: [other.yml]\n",
    service("extends:", "  file: other.yml", "  service: base"),
])
def test_files_not_followed_are_named(tmp_path, text):
    found = one(tmp_path, text)
    assert found.level == "ok" and "not read" in found.text


def test_the_model_matches_what_a_real_compose_prints(tmp_path):
    """Skipped without a Docker client; `config` needs no daemon, and reads only these files."""
    if not shutil.which("docker") or subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=False).returncode:
        pytest.skip("no docker compose here")
    (tmp_path / "docker").mkdir()
    (tmp_path / "docker" / "c.yml").write_text(
        "services:\n  a:\n    image: x\n    volumes: ['../src:/app:ro', used:/u]\n"
        "  b:\n    image: x\n    profiles: [off]\n"
        "volumes:\n  used:\n  unused:\n    external: true\n")
    printed = json.loads(subprocess.run(
        ["docker", "compose", "-f", "docker/c.yml", "config", "--format", "json"], cwd=tmp_path,
        capture_output=True, text=True, check=True).stdout)
    ours = model_of(compose_yaml.load(tmp_path, ("docker/c.yml",)), "docker/c.yml")
    assert set(ours["volumes"]) == set(printed["volumes"])
    theirs = printed["services"]["a"]["volumes"]
    root = os.path.realpath(tmp_path)
    assert os.path.join(root, ours["services"]["a"]["volumes"][0]["source"]) == theirs[0]["source"]
    assert ours["services"]["a"]["volumes"][0]["read_only"] == theirs[0]["read_only"]
    assert ours["services"]["b"] == {} and "b" not in printed["services"]


def test_registries_of_the_files_images(tmp_path):
    (tmp_path / FILE).write_text(
        "services:\n  a: {image: redis:7}\n  b: {image: ghcr.io/x/y:1}\n"
        "  c: {image: 'registry.example.com:5000/z'}\n  d: {image: library/mongo}\n"
        "  e: {image: 'x/${TAG}'}\n  f: {image: mine, build: .}\n  g: {build: .}\n")
    assert compose_check.registries((FILE,), tmp_path) == [
        "ghcr.io", "registry-1.docker.io", "registry.example.com:5000"]


def test_no_registries_from_a_file_that_cannot_be_read(tmp_path):
    (tmp_path / FILE).write_text("services: [")
    assert compose_check.registries((FILE,), tmp_path) == []
