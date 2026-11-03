"""Tests for project config discovery and loading (.mulebox.yml)."""

import textwrap

import pytest

from mulebox.common.config import (
    ConfigError,
    ProjectConfig,
    find_project_config,
    load_project_config,
)
from mulebox.common.errors import MuleboxError

FULL = """\
project: example-app
needs: [node, docker]
toolchain:
  node: 22.22.3
  pnpm: 11.22.0
setup: pnpm install --frozen-lockfile
services: [mongodb]
compose: [docker-compose.yml]
jobs:
  check: pnpm check
  test: pnpm exec vitest run
timeout_min: 20
exclude: [reports/]
"""

MINIMAL = "project: example-app\njobs:\n  check: make check\n"


def write(tmp_path, text, name=".mulebox.yml"):
    path = tmp_path / name
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def error_for(tmp_path, text):
    path = write(tmp_path, text)
    with pytest.raises(ConfigError) as info:
        load_project_config(path)
    assert str(path) in str(info.value)
    return info.value


def test_full_project_config(tmp_path):
    config = load_project_config(write(tmp_path, FULL))
    assert config == ProjectConfig(
        project="example-app",
        needs=("node", "docker"),
        toolchain={"node": "22.22.3", "pnpm": "11.22.0"},
        setup="pnpm install --frozen-lockfile",
        services=("mongodb",),
        compose=("docker-compose.yml",),
        jobs={"check": "pnpm check", "test": "pnpm exec vitest run"},
        timeout_min=20,
        exclude=("reports/",),
    )


def test_minimal_project_config_defaults(tmp_path):
    config = load_project_config(write(tmp_path, MINIMAL))
    assert config.needs == () and config.services == () and config.compose == ()
    assert config.toolchain == {} and config.exclude == ()
    assert config.setup is None
    assert config.timeout_min == 30


def test_config_error_is_mulebox_error(tmp_path):
    err = error_for(tmp_path, "jobs:\n  check: x\n")
    assert isinstance(err, MuleboxError)
    assert err.field == "project"
    assert "project" in str(err) and "required" in str(err)


def test_missing_check_job(tmp_path):
    err = error_for(tmp_path, "project: example-app\njobs:\n  test: x\n")
    assert err.field == "jobs" and "check" in err.problem


def test_missing_jobs(tmp_path):
    assert error_for(tmp_path, "project: example-app\n").field == "jobs"


def test_unknown_top_level_key(tmp_path):
    err = error_for(tmp_path, MINIMAL + "timeout: 5\n")
    assert err.field == "timeout" and "unknown key" in err.problem
    assert "timeout_min" in err.problem


@pytest.mark.parametrize(
    ("extra", "field"),
    [
        ("timeout_min: 0\n", "timeout_min"),
        ("timeout_min: 241\n", "timeout_min"),
        ("timeout_min: '20'\n", "timeout_min"),
        ("timeout_min: true\n", "timeout_min"),
        ("needs: node\n", "needs"),
        ("needs: [node, 3]\n", "needs[1]"),
        ("exclude: ['']\n", "exclude[0]"),
        ("services: {a: b}\n", "services"),
        ("compose: [1]\n", "compose[0]"),
        ("setup: [a, b]\n", "setup"),
        ("setup: '  '\n", "setup"),
        ("toolchain: [node]\n", "toolchain"),
        ("toolchain:\n  python: 3.10\n", "toolchain.python"),
        ("toolchain:\n  node: 22\n", "toolchain.node"),
        ("toolchain:\n  1: x\n", "toolchain"),
    ],
)
def test_invalid_fields(tmp_path, extra, field):
    assert error_for(tmp_path, MINIMAL + extra).field == field


def test_unquoted_version_hint(tmp_path):
    err = error_for(tmp_path, MINIMAL + "toolchain:\n  python: 3.10\n")
    assert "quotes" in err.problem


def test_timeout_bounds_accepted(tmp_path):
    assert load_project_config(write(tmp_path, MINIMAL + "timeout_min: 1\n")).timeout_min == 1
    assert load_project_config(write(tmp_path, MINIMAL + "timeout_min: 240\n")).timeout_min == 240


@pytest.mark.parametrize("name", ["example app", "../evil", "-x", "a/b", ""])
def test_invalid_project_name(tmp_path, name):
    assert error_for(tmp_path, f"project: '{name}'\njobs:\n  check: x\n").field == "project"


@pytest.mark.parametrize(
    ("jobs", "field"),
    [
        ("jobs: [check]\n", "jobs"),
        ("jobs:\n  check: 5\n", "jobs.check"),
        ("jobs:\n  check: ''\n", "jobs.check"),
        ("jobs:\n  check: x\n  test: [a]\n", "jobs.test"),
    ],
)
def test_invalid_jobs(tmp_path, jobs, field):
    assert error_for(tmp_path, f"project: example-app\n{jobs}").field == field


def test_null_optional_field_is_default(tmp_path):
    assert load_project_config(write(tmp_path, MINIMAL + "setup:\n")).setup is None


@pytest.mark.parametrize("text", ["", "# only a comment\n"])
def test_empty_file(tmp_path, text):
    assert "empty" in error_for(tmp_path, text).problem


@pytest.mark.parametrize("text", ["- a\n- b\n", "just text\n", "42\n"])
def test_top_level_must_be_mapping(tmp_path, text):
    assert "mapping" in error_for(tmp_path, text).problem


def test_invalid_yaml(tmp_path):
    err = error_for(tmp_path, "project: [unclosed\n")
    assert "invalid YAML" in err.problem and "line" in err.problem


def test_yaml_tags_are_refused(tmp_path):
    err = error_for(tmp_path, "project: !!python/object/apply:os.system ['true']\n")
    assert "invalid YAML" in err.problem


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_project_config(tmp_path / ".mulebox.yml")
    assert "not found" in str(info.value)


def test_unreadable_path_is_config_error(tmp_path):
    with pytest.raises(ConfigError):
        load_project_config(tmp_path)


def test_find_in_start_dir(tmp_path):
    path = write(tmp_path, MINIMAL)
    assert find_project_config(tmp_path) == path.resolve()


def test_find_walks_up(tmp_path):
    path = write(tmp_path, MINIMAL)
    nested = tmp_path / "src" / "deep"
    nested.mkdir(parents=True)
    assert find_project_config(nested) == path.resolve()


def test_find_from_a_file(tmp_path):
    path = write(tmp_path, MINIMAL)
    source = tmp_path / "main.py"
    source.write_text("", encoding="utf-8")
    assert find_project_config(source) == path.resolve()


def test_find_prefers_nearest(tmp_path):
    write(tmp_path, MINIMAL)
    inner_dir = tmp_path / "packages" / "web"
    inner_dir.mkdir(parents=True)
    inner = write(inner_dir, MINIMAL)
    assert find_project_config(inner_dir) == inner.resolve()


def test_find_ignores_directory_named_like_config(tmp_path):
    (tmp_path / "a" / ".mulebox.yml").mkdir(parents=True)
    path = write(tmp_path, MINIMAL)
    assert find_project_config(tmp_path / "a") == path.resolve()


def test_find_none_raises(tmp_path, monkeypatch):
    import mulebox.common.config as config_module

    monkeypatch.setattr(config_module, "PROJECT_FILE", ".mulebox-test-absent.yml")
    with pytest.raises(ConfigError) as info:
        find_project_config(tmp_path)
    assert str(tmp_path.resolve()) in str(info.value)


ENV_BASE = "project: example-app\njobs:\n  check: make check\n"


def test_env_values(tmp_path):
    cfg = load_project_config(write(tmp_path, ENV_BASE + 'env:\n  CI: "1"\n  DB: app_${MULEBOX_JOB_SLUG}\n'))
    assert cfg.env == {"CI": "1", "DB": "app_${MULEBOX_JOB_SLUG}"}


@pytest.mark.parametrize("key", ["PATH", "HOME", "MULEBOX_JOB_ID", "1BAD", "A-B"])
def test_env_rejects_reserved_or_bad_names(tmp_path, key):
    assert f"env.{key}" in str(error_for(tmp_path, ENV_BASE + f'env:\n  {key}: "x"\n'))
