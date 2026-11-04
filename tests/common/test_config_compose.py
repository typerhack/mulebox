"""`compose:` and the refused `services:` in .mulebox.yml."""

import textwrap

import pytest

from mulebox.common import compose
from mulebox.common.config import ConfigError, load_project_config

MINIMAL = "project: example-app\njobs:\n  check: make check\n"


def write(tmp_path, text):
    path = tmp_path / ".mulebox.yml"
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def touch(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_text("services: {}\n", encoding="utf-8")


def error_for(tmp_path, text):
    with pytest.raises(ConfigError) as info:
        load_project_config(write(tmp_path, text))
    return info.value


@pytest.mark.parametrize("value", ["[mongodb]", "[]", "{a: b}", ""])
def test_services_is_refused_with_what_to_use_instead(tmp_path, value):
    err = error_for(tmp_path, f"{MINIMAL}services: {value}\n")
    assert err.field == "services"
    assert "not supported" in err.problem
    assert "compose:" in err.problem and "env:" in err.problem


@pytest.mark.parametrize(
    "name", ["/etc/compose.yml", "../compose.yml", "a/../b.yml", "-f.yml", "a b.yml", "a:b.yml"])
def test_compose_files_must_be_plain_paths_in_the_project(tmp_path, name):
    assert error_for(tmp_path, f"{MINIMAL}compose: ['{name}']\n").field == "compose[0]"


def test_compose_entries_must_be_strings(tmp_path):
    assert error_for(tmp_path, f"{MINIMAL}compose: [1]\n").field == "compose[0]"


def test_compose_file_must_exist(tmp_path):
    err = error_for(tmp_path, MINIMAL + "compose: [missing.yml]\n")
    assert err.field == "compose[0]" and "missing.yml" in err.problem


def test_compose_file_listed_twice(tmp_path):
    touch(tmp_path, "a.yml")
    assert error_for(tmp_path, MINIMAL + "compose: [a.yml, a.yml]\n").field == "compose[1]"


def test_compose_files_keep_their_order_and_imply_docker(tmp_path):
    touch(tmp_path, "docker-compose.yml", "docker-compose.ci.yml")
    text = MINIMAL + "needs: [node]\ncompose: [docker-compose.yml, docker-compose.ci.yml]\n"
    config = load_project_config(write(tmp_path, text))
    assert config.compose == ("docker-compose.yml", "docker-compose.ci.yml")
    assert config.needs == ("node",) and config.all_needs == ("node", "docker")


def test_docker_is_not_needed_twice_or_without_compose(tmp_path):
    touch(tmp_path, "a.yml")
    both = load_project_config(write(tmp_path, MINIMAL + "needs: [docker]\ncompose: [a.yml]\n"))
    assert both.all_needs == ("docker",)
    assert load_project_config(write(tmp_path, MINIMAL)).all_needs == ()


@pytest.mark.parametrize("key", compose.RESERVED_ENV)
def test_compose_env_names_are_reserved_only_for_a_compose_project(tmp_path, key):
    touch(tmp_path, "a.yml")
    err = error_for(tmp_path, f"{MINIMAL}compose: [a.yml]\nenv:\n  {key}: x\n")
    assert err.field == f"env.{key}"
    assert load_project_config(write(tmp_path, f"{MINIMAL}env:\n  {key}: x\n")).env == {key: "x"}
