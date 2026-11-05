"""Compose's own YAML tags, as `mulebox doctor` must read them."""

import json
import shutil
import subprocess

import pytest

from mulebox.client import compose_yaml
from mulebox.client.compose_check import findings

BASE = """\
services:
  app:
    image: x
    privileged: true
    volumes: [/etc:/host]
    environment: {A: "1", B: "2"}
"""


def load(root, *texts):
    names = []
    for index, text in enumerate(texts):
        names.append(f"c{index}.yml")
        (root / names[-1]).write_text(text)
    return compose_yaml.load(root, tuple(names))


def app(root, *texts):
    return load(root, *texts)["services"]["app"]


@pytest.mark.parametrize("value", ["!reset null", "!reset []", "!reset {}", "!reset"])
def test_reset_removes_the_key_whatever_it_carries(tmp_path, value):
    assert "volumes" not in app(tmp_path, BASE, f"services:\n  app:\n    volumes: {value}\n")


def test_reset_inside_a_map_removes_only_that_key(tmp_path):
    over = "services:\n  app:\n    environment:\n      A: !reset null\n      C: '3'\n"
    assert app(tmp_path, BASE, over)["environment"] == {"B": "2", "C": "3"}


def test_reset_in_the_only_file_removes_the_key(tmp_path):
    assert "labels" not in app(tmp_path, "services:\n  app:\n    labels: !reset {}\n")


def test_a_later_file_may_set_a_reset_key_again(tmp_path):
    reset = "services:\n  app:\n    volumes: !reset []\n"
    again = "services:\n  app:\n    volumes: [/var:/v]\n"
    assert app(tmp_path, BASE, reset, again)["volumes"] == ["/var:/v"]


def test_override_replaces_instead_of_merging(tmp_path):
    over = "services:\n  app:\n    volumes: !override [/var:/v]\n"
    assert app(tmp_path, BASE, over)["volumes"] == ["/var:/v"]
    over = "services:\n  app:\n    environment: !override {C: '3'}\n"
    assert app(tmp_path, BASE, over)["environment"] == {"C": "3"}


def test_a_later_file_merges_with_an_override(tmp_path):
    over = "services:\n  app:\n    volumes: !override [/var:/v]\n"
    more = "services:\n  app:\n    volumes: [/opt:/o]\n"
    assert app(tmp_path, BASE, over, more)["volumes"] == ["/var:/v", "/opt:/o"]


@pytest.mark.parametrize(("text", "expected"), [("false", False), ("5", 5), ("word", "word")])
def test_an_overridden_scalar_keeps_its_type(tmp_path, text, expected):
    over = f"services:\n  app:\n    privileged: !override {text}\n"
    assert app(tmp_path, BASE, over)["privileged"] == expected


def test_a_reset_inside_an_override_is_used_up(tmp_path):
    over = "services:\n  app:\n    environment: !override {A: !reset null, C: '3'}\n"
    assert app(tmp_path, BASE, over)["environment"] == {"C": "3"}


def test_an_unknown_tag_is_still_invalid(tmp_path):
    (tmp_path / "c.yml").write_text("services:\n  app: !nonsense x\n")
    found = findings(("c.yml",), tmp_path)
    assert found[0].level == "warn" and "could not check" in found[0].text


def test_doctor_judges_a_project_with_these_tags(tmp_path):
    (tmp_path / "a.yml").write_text(BASE)
    (tmp_path / "b.yml").write_text("services:\n  app:\n    environment: !reset {}\n")
    found = findings(("a.yml", "b.yml"), tmp_path)
    assert found[0].level == "fail" and found[0].topic == "compose"


def test_a_removed_problem_is_no_refusal(tmp_path):
    (tmp_path / "a.yml").write_text(BASE)
    (tmp_path / "b.yml").write_text(
        "services:\n  app:\n    privileged: !reset null\n    volumes: !override [./x:/x]\n")
    assert findings(("a.yml", "b.yml"), tmp_path)[0].level == "ok"


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs a Docker client")
def test_the_result_matches_what_a_real_compose_prints(tmp_path):
    base = ("services:\n  app:\n    image: x\n    ports: ['80:80']\n"
            "    environment: {A: '1', B: '2'}\n    labels: {k: v}\n  gone: {image: y}\n")
    over = ("services:\n  app:\n    ports: !reset []\n    labels: !override {z: w}\n"
            "    environment:\n      A: !reset null\n  gone: !reset null\n")
    ours = load(tmp_path, base, over)
    command = ["docker", "compose", "--project-directory", str(tmp_path), "-f",
               str(tmp_path / "c0.yml"), "-f", str(tmp_path / "c1.yml"), "config", "--format", "json"]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode:
        pytest.skip(f"no usable compose: {done.stderr[:100]}")
    theirs = json.loads(done.stdout)["services"]
    assert set(theirs) == set(ours["services"]) == {"app"}
    assert "ports" not in ours["services"]["app"] and "ports" not in theirs["app"]
    assert theirs["app"]["environment"] == ours["services"]["app"]["environment"]
    assert theirs["app"]["labels"] == ours["services"]["app"]["labels"]
